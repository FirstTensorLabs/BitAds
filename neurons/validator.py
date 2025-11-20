import argparse
import os
import time
import traceback
from typing import List

from bittensor.core.config import Config
from bittensor.core.settings import BLOCKTIME, NETWORKS
from bittensor.utils.btlogging import logging

from bitads_v3_core.app.scoring import ScoreCalculator
from bitads_v3_core.domain.models import ScoreResult

from core.constants import NETUIDS
from core.adapters.config_source import ValidatorConfigSource
from core.adapters.miner_stats_source import ValidatorMinerStatsSource
from core.adapters.p95_provider import ValidatorP95Provider
from core.adapters.score_sink import ValidatorScoreSink
from core.adapters.burn_data_source import ValidatorBurnDataSource
from core.adapters.dynamic_config_source import ValidatorDynamicConfigSource
from core.adapters.campaign_source import ValidatorCampaignSource, ICampaignSource
from core.bittensor_factory import BittensorFactory
from core.resolvers import MechIdResolver, BurnPercentageResolver, WindowDaysGetter
from core.validator_config import ValidatorConfig
from core.domain.campaign import Campaign


class Validator:
    """
    Main validator class.
    
    Following Single Responsibility Principle - orchestrates validation workflow.
    Following Dependency Inversion Principle - depends on abstractions (interfaces).
    """
    
    def __init__(self, validator_config: ValidatorConfig = None):
        """
        Initialize validator.
        
        Args:
            validator_config: Optional validator configuration. Uses defaults if not provided.
        """
        self.config = self._get_config()
        self._setup_logging()
        
        # Create Bittensor objects using factory
        bt_objects = BittensorFactory.create(self.config)
        self.wallet = bt_objects.wallet
        self.subtensor = bt_objects.subtensor
        self.metagraph = bt_objects.metagraph
        self.dendrite = bt_objects.dendrite
        self.my_uid = bt_objects.my_uid
        
        # Initialize timing
        self.last_update = self.subtensor.blocks_since_last_update(
            self.config.netuid, self.my_uid
        )
        self.tempo = self.subtensor.tempo(self.config.netuid)
        
        # Use provided config or defaults
        if validator_config is None:
            validator_config = ValidatorConfig()
        
        # Initialize core interfaces
        self._initialize_core_components(validator_config)
    
    def _initialize_core_components(self, validator_config: ValidatorConfig):
        """Initialize all core components following dependency injection."""
        # Dynamic config source (for window_days, sales_emission_ratio, p95_config)
        self.dynamic_config_source = ValidatorDynamicConfigSource()
        
        # Campaign source (for fetching campaigns with mech_ids)
        self.campaign_source = ValidatorCampaignSource()
        
        # Config source (delegates to dynamic_config_source for P95)
        self.config_source = ValidatorConfigSource(
            dynamic_config_source=self.dynamic_config_source
        )
        self.miner_stats_source = ValidatorMinerStatsSource()
        self.p95_provider = ValidatorP95Provider(
            config_source=self.config_source,
            miner_stats_source=self.miner_stats_source,
        )
        
        # Window days getter (fetches from dynamic_config_source per scope)
        window_days_getter = WindowDaysGetter(self.dynamic_config_source)
        
        # Sales emission ratio getter (fetches from dynamic_config_source per scope)
        def sales_emission_ratio_getter(scope: str):
            return self.dynamic_config_source.get_sales_emission_ratio(scope)
        
        # Burn data source
        self.burn_data_source = ValidatorBurnDataSource(
            subtensor=self.subtensor,
            netuid=self.config.netuid,
            window_days_getter=window_days_getter,
            sales_emission_ratio_getter=sales_emission_ratio_getter,
        )
        
        # Build mechid mapping from campaigns
        campaigns = self.campaign_source.get_campaigns()
        scope_to_mechid = {campaign.scope: campaign.mech_id for campaign in campaigns}
        
        # Resolvers
        mechid_resolver = MechIdResolver(
            scope_to_mechid=scope_to_mechid,
            default_mechid=validator_config.campaign_mechid,
        )
        burn_percentage_resolver = BurnPercentageResolver(self.burn_data_source)
        
        # Score sink
        self.score_sink = ValidatorScoreSink(
            subtensor=self.subtensor,
            wallet=self.wallet,
            metagraph=self.metagraph,
            netuid=self.config.netuid,
            tempo=self.tempo,
            mechid_resolver=mechid_resolver,
            burn_percentage_resolver=burn_percentage_resolver,
        )
        
        # Score calculator
        self.score_calculator = ScoreCalculator(
            p95_provider=self.p95_provider,
            use_soft_cap=validator_config.use_soft_cap,
            use_flooring=validator_config.use_flooring,
        )

    def _get_config(self) -> Config:
        """Get Bittensor configuration."""
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--netuid", type=int, default=NETUIDS[NETWORKS[0]], help="The chain subnet uid."
        )
        from bittensor.core.subtensor import Subtensor
        from bittensor_wallet import Wallet
        Subtensor.add_args(parser)
        logging.add_args(parser)
        Wallet.add_args(parser)
        
        config = Config(parser)
        config.full_path = os.path.expanduser(
            "{}/{}/{}/netuid{}/validator".format(
                config.logging.logging_dir,
                config.wallet.name,
                config.wallet.hotkey,
                config.netuid,
            )
        )
        os.makedirs(config.full_path, exist_ok=True)
        return config

    def _setup_logging(self):
        """Set up logging."""
        logging(config=self.config, logging_dir=self.config.full_path)
        logging.info(
            f"Running validator for subnet: {self.config.netuid} "
            f"on network: {self.config.subtensor.network}"
        )
    
    def get_campaigns(self) -> List[Campaign]:
        """
        Get list of active campaigns with their mechanism IDs.
        
        Fetches campaigns from campaign_source, which loads them from external source.
        """
        return self.campaign_source.get_campaigns()
    
    def compute_scores_for_scope(self, scope: str) -> List[ScoreResult]:
        """
        Compute scores for all miners for a given scope.
        
        Args:
            scope: Scope identifier (e.g., "network", "campaign:123")
        
        Returns:
            List of ScoreResult entries
        """
        # Fetch miner statistics for this scope
        window_days = self.burn_data_source.window_days_getter()
        miner_stats_list = self.miner_stats_source.fetch_window(scope, window_days)
        
        if not miner_stats_list:
            logging.warning(f"No miner stats found for scope {scope}, using zero scores")
            # Produce zero scores for all hotkeys (miners with no work get 0)
            return [ScoreResult(miner_id=hotkey, base=0.0, refund_multiplier=1.0, score=0.0) for hotkey in self.metagraph.hotkeys]
        
        # Compute scores using ScoreCalculator
        score_results = self.score_calculator.score_many(miner_stats_list, scope)
        return score_results
    
    def set_weights_for_scope(self, scope: str) -> None:
        """
        Compute scores and set weights for a specific scope/campaign.
        
        Args:
            scope: Scope identifier
        """
        logging.info(f"Computing scores for scope: {scope}")
        
        # Compute scores
        score_results = self.compute_scores_for_scope(scope)
        # Delegate publishing (which sets weights) to the score sink
        self.score_sink.publish(score_results, scope)

    def run(self):
        """Main validation loop."""
        logging.info("Starting validator loop.")
        while True:
            try:
                self._sync_and_process()
            except RuntimeError as e:
                logging.error(f"Runtime error in validator loop: {e}")
                traceback.print_exc()
            except KeyboardInterrupt:
                logging.success("Keyboard interrupt detected. Exiting validator.")
                break
    
    def _sync_and_process(self):
        """Sync metagraph and process weights if needed."""
        self.metagraph.sync()
        
        if self.last_update >= self.tempo:
            self._process_weights()
            self.p95_provider.update_percentiles()
            self.last_update = 0
        else:
            self._sleep_until_next_update()
    
    def _process_weights(self):
        """Process weights for all active campaigns."""
        campaigns = self.get_campaigns()
        logging.info(f"Processing {len(campaigns)} campaigns: {campaigns}")
        
        for campaign in campaigns:
            try:
                self.set_weights_for_scope(campaign.scope)
            except Exception as e:
                logging.error(f"Error setting weights for {campaign.scope}: {e}")
                traceback.print_exc()
    
    def _sleep_until_next_update(self):
        """Sleep until next weight update is due."""
        sleep_seconds = max(1, (self.tempo - self.last_update) * BLOCKTIME)
        logging.info(f"Not time to set weights yet. Sleeping for {sleep_seconds} seconds.")
        time.sleep(sleep_seconds)
        self.last_update = self.subtensor.blocks_since_last_update(
            self.config.netuid, self.my_uid
        )


# Run the validator.
if __name__ == "__main__":
    validator = Validator()
    validator.run()
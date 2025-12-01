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

from core.constants import (
    NETUIDS,
    DEFAULT_USE_SOFT_CAP,
    DEFAULT_USE_FLOORING,
    DEFAULT_W_SALES,
    DEFAULT_W_REV,
    DEFAULT_SOFT_CAP_THRESHOLD,
    DEFAULT_SOFT_CAP_FACTOR,
)
from core.adapters.config_source import ValidatorConfigSource
from core.adapters.miner_stats_source import ValidatorMinerStatsSource
from core.adapters.p95_provider import ValidatorP95Provider
from core.adapters.score_sink import ValidatorScoreSink
from core.adapters.burn_data_source import ValidatorBurnDataSource
from core.adapters.dynamic_config_source import ValidatorDynamicConfigSource, get_default_config
from core.adapters.campaign_source import ValidatorCampaignSource, ICampaignSource
from core.bittensor_factory import BittensorFactory
from core.resolvers import MechIdResolver, BurnPercentageResolver, FixedBurnPercentageResolver, WindowDaysGetter
from core.domain.campaign import Campaign
from core.constants import DEFAULT_MECHID


class Validator:
    """
    Main validator class.
    
    Following Single Responsibility Principle - orchestrates validation workflow.
    Following Dependency Inversion Principle - depends on abstractions (interfaces).
    """
    
    def __init__(self):
        """
        Initialize validator.
        
        Configuration is now fetched from the API (use_soft_cap, use_flooring from P95 config).
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
        
        # Initialize core interfaces
        self._initialize_core_components()   
    
    def _initialize_core_components(self):
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
            dynamic_config_source=self.dynamic_config_source,
        )
        
        # Window days getter (fetches from dynamic_config_source per scope)
        window_days_getter = WindowDaysGetter(self.dynamic_config_source)
        
        # Sales emission ratio getter (fetches from dynamic_config_source per scope)
        def sales_emission_ratio_getter(scope: str):
            config = self.dynamic_config_source.get_config(scope)
            return config.sales_emission_ratio if config is not None else None
        
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
            default_mechid=DEFAULT_MECHID,
        )

        # Prepare burn percentage resolvers:
        # - Global fixed override from CLI (if provided)
        # - Dynamic resolver based on sales/emissions
        # - Optional per-scope fixed burn percentage from DynamicConfig
        if self.config.burn_percentage_override is not None:
            logging.info(f"Using fixed burn percentage override: {self.config.burn_percentage_override}% (global)")
            self._global_fixed_burn_resolver = FixedBurnPercentageResolver(self.config.burn_percentage_override)
        else:
            self._global_fixed_burn_resolver = None

        self._dynamic_burn_resolver = BurnPercentageResolver(self.burn_data_source)

        def burn_percentage_resolver(scope: str):
            """
            Resolve burn percentage for a scope with the following precedence:
            1. Global CLI override (burn_percentage_override)
            2. Per-scope fixed burn_percentage from DynamicConfig (if set)
            3. Dynamic burn calculation from sales/emission data
            """
            # 1. Global fixed override (highest precedence)
            if self._global_fixed_burn_resolver is not None:
                return self._global_fixed_burn_resolver(scope)

            # 2. Per-scope fixed burn percentage from dynamic config
            scope_config = self.dynamic_config_source.get_config(scope)
            if scope_config is not None and scope_config.burn_percentage is not None:
                # Use FixedBurnPercentageResolver for this scope when burn_percentage is set
                return FixedBurnPercentageResolver(scope_config.burn_percentage)(scope)

            # 3. Fallback to dynamic calculation
            return self._dynamic_burn_resolver(scope)
        
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
        
        # Score calculator is now created dynamically per-scope in set_weights_for_scope
        # to use scope-specific configuration (use_soft_cap, use_flooring, weights, etc.)

    def _get_config(self) -> Config:
        """Get Bittensor configuration."""
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--netuid", type=int, default=NETUIDS[NETWORKS[0]], help="The chain subnet uid."
        )
        parser.add_argument(
            "--burn-percentage-override",
            type=float,
            default=None,
            help="Override burn percentage with a fixed value (0.0-100.0). Useful for testing on testnet where emissions might be 0. If not provided, burn percentage is calculated dynamically."
        )
        from bittensor.core.subtensor import Subtensor
        from bittensor_wallet import Wallet
        Subtensor.add_args(parser)
        logging.add_args(parser)
        Wallet.add_args(parser)
        
        config = Config(parser)
        
        # Validate burn percentage override if provided
        if config.burn_percentage_override is not None:
            if config.burn_percentage_override < 0.0 or config.burn_percentage_override > 100.0:
                raise ValueError(
                    f"burn_percentage_override must be between 0.0 and 100.0, got {config.burn_percentage_override}"
                )
        
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
    
    def compute_scores_for_scope(self, scope: str, score_calculator: ScoreCalculator) -> List[ScoreResult]:
        """
        Compute scores for all miners for a given scope.
        
        Args:
            scope: Scope identifier (e.g., "network", "campaign:123")
            score_calculator: ScoreCalculator instance configured for this scope
        
        Returns:
            List of ScoreResult entries
        """
        # Fetch miner statistics for this scope
        window_days = self.burn_data_source.window_days_getter(scope)
        miner_stats_list = self.miner_stats_source.fetch_window(scope, window_days)
        
        if not miner_stats_list:
            logging.warning(f"No miner stats found for scope {scope}, using zero scores")
            # Produce zero scores for all hotkeys (miners with no work get 0)
            return [ScoreResult(miner_id=hotkey, base=0.0, refund_multiplier=1.0, score=0.0) for hotkey in self.metagraph.hotkeys]
        
        # Compute scores using ScoreCalculator
        score_results = score_calculator.score_many(miner_stats_list, scope)
        return score_results
    
    def set_weights_for_scope(self, scope: str) -> None:
        """
        Compute scores and set weights for a specific scope/campaign.
        
        Creates ScoreCalculator dynamically with scope-specific configuration
        to allow runtime changes to scoring parameters.
        
        Args:
            scope: Scope identifier
        """
        logging.info(f"Computing scores for scope: {scope}")
        
        # Get scope-specific configuration, using defaults if unavailable
        scope_config = self.dynamic_config_source.get_config(scope)
        if scope_config is None:
            logging.warning(f"No configuration found for scope {scope}, using defaults")
            scope_config = get_default_config(scope)
        
        # Create ScoreCalculator with scope-specific configuration
        score_calculator = ScoreCalculator(
            p95_provider=self.p95_provider,
            use_soft_cap=scope_config.use_soft_cap,
            use_flooring=scope_config.use_flooring,
            w_sales=scope_config.w_sales,
            w_rev=scope_config.w_rev,
            soft_cap_threshold=scope_config.soft_cap_threshold,
            soft_cap_factor=scope_config.soft_cap_factor,
        )
        
        # Compute scores
        score_results = self.compute_scores_for_scope(scope, score_calculator)
        # Delegate publishing (which sets weights) to the score sink
        self.score_sink.publish(score_results, scope)
    
    def set_weights(self) -> None:
        """
        One-time weight setting for all active campaigns.
        
        Syncs metagraph, updates percentiles, and sets weights for all campaigns.
        Does not check timing constraints - useful for manual updates or testing.
        """
        logging.info("Starting one-time weight setting...")
        
        # Sync metagraph to get latest state
        logging.info("Syncing metagraph...")
        self.metagraph.sync()
        
        # Update percentiles before computing scores
        logging.info("Updating percentiles...")
        self.p95_provider.update_percentiles()
        
        # Get all active campaigns
        campaigns = self.get_campaigns()
        logging.info(f"Found {len(campaigns)} active campaigns: {campaigns}")
        
        if not campaigns:
            logging.warning("No active campaigns found.")
            return
        
        # Set weights for each campaign
        for campaign in campaigns:
            try:
                logging.info(f"Setting weights for campaign: {campaign.scope} (mech_id: {campaign.mech_id})")
                self.set_weights_for_scope(campaign.scope)
                logging.success(f"Successfully set weights for {campaign.scope}")
            except Exception as e:
                logging.error(f"Error setting weights for {campaign.scope}: {e}")
                traceback.print_exc()
        
        logging.success("Weight setting completed.")

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
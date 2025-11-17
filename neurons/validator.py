import argparse
import os
import time
import traceback
from typing import Dict, List, Optional, Tuple, Callable

from bittensor.core.config import Config
from bittensor.core.dendrite import Dendrite
from bittensor.core.settings import BLOCKTIME, NETWORKS
from bittensor.core.subtensor import Subtensor
from bittensor.utils.btlogging import logging
from bittensor_wallet import Wallet

from bitads_v3_core.app.ports import (
    IConfigSource,
    IMinerStatsSource,
    IP95Provider,
    IScoreSink,
)
from bitads_v3_core.app.scoring import ScoreCalculator
from bitads_v3_core.domain.models import (
    MinerWindowStats,
    P95Config,
    P95Mode,
    Percentiles,
    ScoreResult,
)
from core.constants import NETUIDS
from adapters.config_source import ValidatorConfigSource
from adapters.miner_stats_source import ValidatorMinerStatsSource
from adapters.p95_provider import ValidatorP95Provider
from adapters.score_sink import ValidatorScoreSink


class Validator:
    def __init__(self):
        self.config = self.get_config()
        self.setup_logging()
        self.setup_bittensor_objects()
        self.my_uid = self.metagraph.hotkeys.index(self.wallet.hotkey.ss58_address)
        self.last_update = self.subtensor.blocks_since_last_update(
            self.config.netuid, self.my_uid
        )
        self.tempo = self.subtensor.tempo(self.config.netuid)
        
        # Initialize bitads_v3_core interfaces
        self.config_source = ValidatorConfigSource()
        self.miner_stats_source = ValidatorMinerStatsSource()
        self.p95_provider = ValidatorP95Provider(
            config_source=self.config_source,
            miner_stats_source=self.miner_stats_source,
        )
        # mechid resolver: network -> 1, campaign order -> 2+
        def mechid_resolver(scope: str) -> int:
            if scope == "network":
                return 0
            # Fallback; validator.get_campaigns() maintains order, but resolver is simple here
            return 1

        # burn_percentage resolver: returns burn percentage for a given scope
        # TODO: Replace with actual external source when available
        def burn_percentage_resolver(scope: str) -> Optional[float]:
            """
            Get burn percentage for a given scope.
            
            Args:
                scope: Scope identifier (e.g., "network", "campaign:123")
            
            Returns:
                Burn percentage (0.0-100.0) or None to disable burn
            """
            # For now, return None (no burn) - can be replaced with external source
            return None

        self.score_sink = ValidatorScoreSink(
            subtensor=self.subtensor,
            wallet=self.wallet,
            metagraph=self.metagraph,
            netuid=self.config.netuid,
            tempo=self.tempo,
            mechid_resolver=mechid_resolver,
            burn_percentage_resolver=burn_percentage_resolver,
        )
        self.score_calculator = ScoreCalculator(
            p95_provider=self.p95_provider,
            use_soft_cap=False,  # Can be made configurable
            use_flooring=False,  # Can be made configurable
        )

    def get_config(self):
        # Set up the configuration parser.
        parser = argparse.ArgumentParser()
        # Adds override arguments for network and netuid.
        parser.add_argument(
            "--netuid", type=int, default=NETUIDS[NETWORKS[0]], help="The chain subnet uid."
        )
        # Adds subtensor specific arguments.
        Subtensor.add_args(parser)
        # Adds logging specific arguments.
        logging.add_args(parser)
        # Adds wallet specific arguments.
        Wallet.add_args(parser)
        # Parse the config.
        config = Config(parser)
        # Set up logging directory.
        config.full_path = os.path.expanduser(
            "{}/{}/{}/netuid{}/validator".format(
                config.logging.logging_dir,
                config.wallet.name,
                config.wallet.hotkey,
                config.netuid,
            )
        )
        # Ensure the logging directory exists.
        os.makedirs(config.full_path, exist_ok=True)
        return config

    def setup_logging(self):
        # Set up logging.
        logging(config=self.config, logging_dir=self.config.full_path)
        logging.info(
            f"Running validator for subnet: {self.config.netuid} on network: {self.config.subtensor.network} with config:"
        )
        logging.info(self.config)

    def setup_bittensor_objects(self):
        # Build Bittensor validator objects.
        logging.info("Setting up Bittensor objects.")

        # Initialize wallet.
        self.wallet = Wallet(config=self.config)
        logging.info(f"Wallet: {self.wallet}")

        # Initialize subtensor.
        self.subtensor = Subtensor(config=self.config)
        logging.info(f"Subtensor: {self.subtensor}")

        # Initialize dendrite.
        self.dendrite = Dendrite(wallet=self.wallet)
        logging.info(f"Dendrite: {self.dendrite}")

        # Initialize metagraph.
        self.metagraph = self.subtensor.metagraph(self.config.netuid)
        logging.info(f"Metagraph: {self.metagraph}")

        # Connect the validator to the network.
        if self.wallet.hotkey.ss58_address not in self.metagraph.hotkeys:
            logging.error(
                f"Your validator: {self.wallet} is not registered to chain connection: {self.subtensor} \nRun 'btcli register' and try again."
            )
            exit()
        else:
            # Each validator gets a unique identity (UID) in the network.
            self.my_subnet_uid = self.metagraph.hotkeys.index(
                self.wallet.hotkey.ss58_address
            )
            logging.info(f"Running validator on uid: {self.my_subnet_uid}")

        # Set up initial scoring weights for validation.
        logging.info("Building validation weights.")
    
    def get_campaigns(self) -> List[str]:
        """
        Get list of active campaigns.
        
        TODO: Implement actual campaign fetching logic.
        For now, returns network scope and placeholder campaigns.
        """
        # Return network scope and example campaigns
        # In production, fetch from your data source
        campaigns = ["network", "local"]  # Network-level scoring
        # TODO: Add actual campaign IDs from your system
        # campaigns.extend([f"campaign:{cid}" for cid in active_campaign_ids])
        return campaigns
    
    def compute_scores_for_scope(self, scope: str) -> List[ScoreResult]:
        """
        Compute scores for all miners for a given scope.
        
        Args:
            scope: Scope identifier (e.g., "network", "campaign:123")
        
        Returns:
            List of ScoreResult entries
        """
        # Fetch miner statistics for this scope
        miner_stats_list = self.miner_stats_source.fetch_window(scope)
        
        if not miner_stats_list:
            logging.warning(f"No miner stats found for scope {scope}, using zero scores")
            # Produce zero scores for all UIDs (miners with no work get 0)
            return [ScoreResult(miner_id=str(uid), base=0.0, refund_multiplier=1.0, score=0.0) for uid in self.metagraph.uids]
        
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
        # The Main Validation Loop.
        logging.info("Starting validator loop.")
        while True:
            try:
                # Sync metagraph and check whether it's time to set weights
                self.metagraph.sync()

                if self.last_update >= self.tempo:
                    # Get list of active campaigns only when it's time to set weights
                    campaigns = self.get_campaigns()
                    logging.info(f"Processing {len(campaigns)} campaigns: {campaigns}")
                    
                    # Process each campaign (multiple set_weights calls, one per campaign)
                    for scope in campaigns:
                        try:
                            self.set_weights_for_scope(scope)
                        except Exception as e:
                            logging.error(f"Error setting weights for {scope}: {e}")
                            traceback.print_exc()
                            continue
                    
                    # Update percentiles cache for next iteration
                    self.p95_provider.update_percentiles()
                    # Record the duration of blocks since the last update
                    self.last_update = 0
                else:
                    # Not time yet: sleep for requested duration
                    sleep_seconds = max(1, (self.tempo - self.last_update) * BLOCKTIME)
                    logging.info(f"Not time to set weights yet. Sleeping for {sleep_seconds} seconds.")
                    time.sleep(sleep_seconds)
                    self.last_update = self.subtensor.blocks_since_last_update(
                        self.config.netuid, self.my_uid
                    )

            except RuntimeError as e:   
                logging.error(e)
                traceback.print_exc()

            except KeyboardInterrupt:
                logging.success("Keyboard interrupt detected. Exiting validator.")
                exit()


# Run the validator.
if __name__ == "__main__":
    validator = Validator()
    validator.run()
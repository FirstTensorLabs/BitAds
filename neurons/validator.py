import argparse
import os
import time
import traceback
from typing import List

from bittensor.core.subtensor import Subtensor
from bittensor.core import settings
from bittensor import Axon, Wallet
from bittensor.core.config import Config
from bittensor.core.settings import BLOCKTIME, NETWORKS
from bittensor.utils.btlogging import logging

from bitads_v3_core.app.scoring import ScoreCalculator
from bitads_v3_core.domain.creator_burn import apply_creator_burn
from bitads_v3_core.domain.models import ScoreResult

from core import __version__, version_as_int
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
from core.adapters.miner_stats_source import ValidatorMinerStatsSource, StorageMinerStatsSource
from core.adapters.pending_miners_source import StoragePendingMinersSource
from core.adapters.p95_provider import ValidatorP95Provider
from core.adapters.score_sink import ValidatorScoreSink
from core.adapters.burn_data_source import ValidatorBurnDataSource
from core.adapters.dynamic_config_source import ValidatorDynamicConfigSource, StorageDynamicConfigSource, get_default_config
from core.adapters.campaign_source import ValidatorCampaignSource, StorageCampaignSource, ICampaignSource
from core.bittensor_factory import BittensorFactory
from core.resolvers import MechIdResolver, BurnPercentageResolver, FixedBurnPercentageResolver, WindowDaysGetter
from core.domain.campaign import Campaign
from core.constants import DEFAULT_MECHID, PENDING_MINER_MIN_SCORE

try:
    # Optional Prometheus support for metrics exporting.
    # If prometheus_client is not installed, metrics are simply disabled.
    from prometheus_client import Counter, Gauge, Histogram, start_http_server

    _PROMETHEUS_AVAILABLE = True
except ImportError:
    Counter = Gauge = Histogram = start_http_server = None  # type: ignore
    _PROMETHEUS_AVAILABLE = False


class Validator:
    """
    Main validator class.
    
    Following Single Responsibility Principle - orchestrates validation workflow.
    Following Dependency Inversion Principle - depends on abstractions (interfaces).
    """
    
    def __init__(self, enable_metrics: bool = True):
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
        # Stable identifier for this validator instance (used in metrics labels).
        try:
            self.hotkey_address = self.wallet.hotkey.ss58_address  # type: ignore[attr-defined]
        except Exception:
            self.hotkey_address = "unknown"

        # Metrics depend on wallet / hotkey being initialized.
        # Allow callers (e.g., one-off scripts like set_weights.py) to disable
        # Prometheus entirely, so we don't start a metrics HTTP server for
        # local/utility runs.
        self._metrics_enabled = enable_metrics
        if self._metrics_enabled:
            self._setup_metrics()
        
        
        # Initialize timing
        self.last_update = self.subtensor.blocks_since_last_update(
            self.config.netuid, self.my_uid
        )
        self.tempo = self.subtensor.tempo(self.config.netuid)
        
        # Initialize core interfaces
        self._initialize_core_components()   

    def _setup_metrics(self) -> None:
        """
        Optionally start Prometheus metrics exporter and register core metrics.
        
        Metrics are enabled by default, but can be disabled via the
        --disable-telemetry flag. The metrics server uses config.axon.port
        (e.g. --axon.port or AXON_PORT).
        
        If prometheus_client is not available, metrics are disabled gracefully.
        """
        self.metric_loop_iterations = None
        self.metric_sync_and_process_duration = None
        self.metric_last_process_success = None
        self.metric_active_campaigns = None
        self.metric_weights_sets_total = None
        self.metric_weights_errors_total = None
        self.metric_version = None

        # Allow operators to disable telemetry completely via config flag.
        # When disabled, we skip metrics and do not serve the axon.
        if getattr(self.config, "disable_telemetry", False):
            logging.info("Telemetry disabled via --disable-telemetry flag (metrics and axon not served).")
            return

        # Use axon port from config for metrics server.
        raw_port = getattr(self.config.axon, "port", 9100)
        if raw_port is None:
            raw_port = 9100
        try:
            port = int(raw_port)
        except (ValueError, TypeError):
            logging.warning(f"Invalid axon.port value '{raw_port}', metrics disabled.")
            return

        if not _PROMETHEUS_AVAILABLE:
            logging.warning(
                "Prometheus metrics requested but prometheus_client is not installed. "
                "Install prometheus_client to enable metrics or use --disable-telemetry."
            )
            return

        try:
            start_http_server(port)
            axon = Axon(wallet=self.wallet, config=self.config)
            self.subtensor.serve_axon(self.config.netuid, axon)
            logging.info(f"Started Prometheus metrics server on port {port}")
        except Exception as e:
            logging.warning(f"Failed to start Prometheus metrics server on port {port}: {e}")
            return

        # Core process metrics
        self.metric_loop_iterations = Counter(
            "validator_loop_iterations_total",
            "Total number of iterations of the main validator loop.",
            ["hotkey"],
        ).labels(hotkey=self.hotkey_address)
        self.metric_sync_and_process_duration = Histogram(
            "validator_sync_and_process_duration_seconds",
            "Duration of sync and process cycle in seconds.",
            buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
            labelnames=["hotkey"],
        ).labels(hotkey=self.hotkey_address)
        self.metric_last_process_success = Gauge(
            "validator_last_process_success",
            "1 if the last sync/process cycle succeeded, 0 otherwise.",
            ["hotkey"],
        ).labels(hotkey=self.hotkey_address)

        # Campaign/weights metrics
        self.metric_active_campaigns = Gauge(
            "validator_active_campaigns",
            "Number of active campaigns processed in the last cycle.",
            ["hotkey"],
        ).labels(hotkey=self.hotkey_address)
        self.metric_weights_sets_total = Counter(
            "validator_weights_sets_total",
            "Total number of successful weight-setting operations.",
            ["hotkey", "scope"],
        )
        self.metric_weights_errors_total = Counter(
            "validator_weights_errors_total",
            "Total number of errors during weight-setting operations.",
            ["hotkey", "scope"],
        )
        
        # Version metric
        self.metric_version = Gauge(
            "validator_version",
            "Validator version as integer (converted from semantic version string).",
            ["hotkey", "version_string"],
        ).labels(hotkey=self.hotkey_address, version_string=__version__)
        # Set the version value
        self.metric_version.set(version_as_int)
    
    def _initialize_core_components(self):
        """Initialize all core components following dependency injection."""
        # Get network from config
        network = self.config.subtensor.network
        
        # Dynamic config source (for window_days, sales_emission_ratio, p95_config)
        self.dynamic_config_source = StorageDynamicConfigSource(network=network)
        
        # Campaign source (for fetching campaigns with mech_ids)
        self.campaign_source = StorageCampaignSource(network=network)
        
        # Config source (delegates to dynamic_config_source for P95)
        self.config_source = ValidatorConfigSource(
            dynamic_config_source=self.dynamic_config_source
        )
        self.miner_stats_source = StorageMinerStatsSource(network=network)
        self.pending_miners_source = StoragePendingMinersSource(network=network)

        # Build mapping from mech_scope to campaign_scope for P95 provider.
        # This allows P95 provider to fetch miner stats using campaign_id when
        # scope is mech_scope. If multiple campaigns share the same mech_id we
        # keep the first campaign as the "primary" source for P95.
        campaigns = self.campaign_source.get_campaigns()
        mech_scope_to_campaign_scope: dict[str, str] = {}
        for campaign in campaigns:
            mech_scope = f"mech{campaign.mech_id}"
            if mech_scope not in mech_scope_to_campaign_scope:
                mech_scope_to_campaign_scope[mech_scope] = campaign.scope
        logging.info(
            f"Built mech_scope -> primary campaign_scope mapping for P95: "
            f"{mech_scope_to_campaign_scope}"
        )
        
        self.p95_provider = ValidatorP95Provider(
            config_source=self.config_source,
            miner_stats_source=self.miner_stats_source,
            dynamic_config_source=self.dynamic_config_source,
            mech_scope_to_campaign_scope=mech_scope_to_campaign_scope,
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
            miner_stats_source=self.miner_stats_source,
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

        def burn_percentage_resolver(scope: str, miner_stats_scope: str = None):
            """
            Resolve burn percentage for a scope with the following precedence:
            1. Global CLI override (burn_percentage_override)
            2. Per-scope fixed burn_percentage from DynamicConfig (if set)
            3. Dynamic burn calculation from sales/emission data
            
            Args:
                scope: Scope identifier for config (e.g., "mech0", "mech1")
                miner_stats_scope: Scope identifier for fetching miner stats (e.g., campaign_id).
                                  If not provided, uses scope.
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
            return self._dynamic_burn_resolver(scope, miner_stats_scope=miner_stats_scope)

        self.burn_percentage_resolver = burn_percentage_resolver
        
        # Score sink (now uses a single mechanism; mech is no longer varied per scope)
        self.score_sink = ValidatorScoreSink(
            subtensor=self.subtensor,
            wallet=self.wallet,
            metagraph=self.metagraph,
            netuid=self.config.netuid,
            tempo=self.tempo,
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
        parser.add_argument(
            "--disable-telemetry",
            action="store_true",
            help="Disable Prometheus metrics / telemetry (enabled by default).",
        )
      
        Subtensor.add_args(parser)
        Wallet.add_args(parser)
        Axon.add_args(parser)
        logging.add_args(parser)
        
        
        config = Config(parser)

        if config.subtensor.chain_endpoint != settings.DEFAULTS.subtensor.chain_endpoint:
            config.subtensor.network = None
        
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
    
    def compute_scores_for_campaign(self, campaign: Campaign, score_calculator: ScoreCalculator) -> List[ScoreResult]:
        """
        Compute scores for all miners for a given campaign.
        
        Args:
            campaign: Campaign object with scope and mech_id
            score_calculator: ScoreCalculator instance configured for this campaign
        
        Returns:
            List of ScoreResult entries
        """
        mech_scope = f"mech{campaign.mech_id}"
        
        logging.info(f"Computing scores: campaign_id={campaign.scope}, mech_id={campaign.mech_id}, mech_scope={mech_scope}")
        
        # Fetch miner statistics using campaign scope (campaign_id)
        # Window days should be fetched for mech_scope (config is stored per mechanism, not per campaign)
        window_days = self.burn_data_source.window_days_getter(mech_scope)
        logging.info(f"Fetching miner stats: campaign_scope={campaign.scope}, window_days={window_days} (from mech_scope={mech_scope})")
        miner_stats_list = self.miner_stats_source.fetch_window(campaign.scope, window_days)
        
        if not miner_stats_list:
            logging.warning(f"No miner stats found for campaign {campaign.scope}, using zero scores")
            # Start with zero for all; pending-only miners get minimum score
            score_results = [
                ScoreResult(miner_id=hotkey, base=0.0, refund_multiplier=1.0, score=0.0)
                for hotkey in self.metagraph.hotkeys
            ]
            pending_miners = self.pending_miners_source.get_pending_miners(campaign.scope)
            for hotkey in pending_miners:
                if hotkey in self.metagraph.hotkeys:
                    idx = self.metagraph.hotkeys.index(hotkey)
                    score_results[idx] = ScoreResult(
                        miner_id=hotkey,
                        base=PENDING_MINER_MIN_SCORE,
                        refund_multiplier=1.0,
                        score=PENDING_MINER_MIN_SCORE,
                    )
            if pending_miners:
                logging.info(
                    f"Assigned minimum score ({PENDING_MINER_MIN_SCORE}) to "
                    f"{len(pending_miners)} pending-only miners for campaign {campaign.scope} (no miner-stats)"
                )
            return score_results

        logging.info(f"Fetched {len(miner_stats_list)} miner stats for campaign_scope={campaign.scope}, computing scores with mech_scope={mech_scope}")
        
        # Cache miner stats in P95 provider to avoid duplicate fetch in AUTO mode
        self.p95_provider.set_miner_stats_cache(campaign.scope, miner_stats_list)
        
        # Compute scores using ScoreCalculator
        # P95 provider will use cached miner stats if needed (AUTO mode)
        score_results = score_calculator.score_many(miner_stats_list, mech_scope)
        logging.info(f"Computed {len(score_results)} scores for mech_scope={mech_scope}")

        # Miners with only pending orders (not in miner-stats) get minimum reward
        # so they are not removed from the subnet. A miner is either on the pending
        # list or in miner-stats for this campaign, not both.
        miners_with_score = {r.miner_id for r in score_results}
        pending_miners = self.pending_miners_source.get_pending_miners(campaign.scope)
        for hotkey in pending_miners:
            if hotkey not in miners_with_score and hotkey in self.metagraph.hotkeys:
                score_results.append(
                    ScoreResult(
                        miner_id=hotkey,
                        base=PENDING_MINER_MIN_SCORE,
                        refund_multiplier=1.0,
                        score=PENDING_MINER_MIN_SCORE,
                    )
                )
                miners_with_score.add(hotkey)
        if pending_miners and len(score_results) > len(miner_stats_list):
            logging.info(
                f"Added minimum score ({PENDING_MINER_MIN_SCORE}) for "
                f"{len(score_results) - len(miner_stats_list)} pending-only miners in campaign {campaign.scope}"
            )
        
        # Clear miner stats cache for this campaign after processing is complete
        # This ensures we fetch fresh stats on the next iteration
        self.p95_provider.clear_miner_stats_cache(campaign.scope)
        
        return score_results
    
    def set_weights_for_campaign(self, campaign: Campaign) -> None:
        """
        Compute scores and set weights for a specific campaign.
        
        Creates ScoreCalculator dynamically with campaign-specific configuration
        to allow runtime changes to scoring parameters.
        
        Args:
            campaign: Campaign object with scope and mech_id
        """
        mech_scope = f"mech{campaign.mech_id}"
        
        logging.info(f"Computing scores for campaign: {campaign.scope} (mech_id: {campaign.mech_id}, mech_scope: {mech_scope})")
        
        # Get scope-specific configuration using mech_scope (for new API format)
        scope_config = self.dynamic_config_source.get_config(mech_scope)
        if scope_config is None:
            logging.warning(f"No configuration found for mech_scope {mech_scope}, using defaults")
            scope_config = get_default_config(mech_scope)
        else:
            logging.info(f"Using config for mech_scope={mech_scope}: use_soft_cap={scope_config.use_soft_cap}, use_flooring={scope_config.use_flooring}, w_sales={scope_config.w_sales}, w_rev={scope_config.w_rev}")
        
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
        
        # Compute scores for this campaign
        score_results = self.compute_scores_for_campaign(campaign, score_calculator)
        # Delegate publishing (which sets weights) to the score sink.
        # Empty score_results -> sink uses burn (owner only). If we have results but set_weights fails, leave as is.
        success, message = self.score_sink.publish(score_results, mech_scope, miner_stats_scope=campaign.scope)
        if not success:
            logging.warning(f"Set weights failed for campaign {campaign.scope}; leaving weights as is: {message}")
    
    def run(self):
        """Main validation loop."""
        logging.info("Starting validator loop.")
        while True:
            try:
                if getattr(self, "metric_loop_iterations", None) is not None:
                    self.metric_loop_iterations.inc()

                start_time = time.time()
                self._sync_and_process()
                duration = time.time() - start_time

                if getattr(self, "metric_sync_and_process_duration", None) is not None:
                    self.metric_sync_and_process_duration.observe(duration)
                if getattr(self, "metric_last_process_success", None) is not None:
                    self.metric_last_process_success.set(1.0)
            except RuntimeError as e:
                logging.error(f"Runtime error in validator loop: {e}")
                traceback.print_exc()
                if getattr(self, "metric_last_process_success", None) is not None:
                    self.metric_last_process_success.set(0.0)
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
        """Process weights for all active campaigns.

        With all companies sharing the same mech ID, we:
        1. Compute per-campaign score arrays.
        2. Aggregate them into a single rating array for all miners using each
           campaign's ``emission_split`` percentage from ``subnet_campaigns.json``.
        3. Apply burn rules once via the score sink and submit a single
           ``set_weights`` extrinsic.
        """
        campaigns = self.get_campaigns()
        logging.info(f"Processing {len(campaigns)} campaigns: {campaigns}")

        if getattr(self, "metric_active_campaigns", None) is not None:
            self.metric_active_campaigns.set(len(campaigns))

        if not campaigns:
            logging.info("Zero active campaigns; setting weights to subnet owner (burn) then sleeping 60s.")
            success, message = self.score_sink.set_weights_to_owner_only()
            if success:
                logging.info(f"Set weights to owner (burn): {message}")
            else:
                logging.warning(f"Set weights to owner failed: {message}")
            return

        # Prepare emission-based weights per campaign.
        raw_splits = [
            c.emission_split for c in campaigns if c.emission_split is not None and c.emission_split > 0
        ]
        if raw_splits:
            total_split = sum(raw_splits)
            campaign_weights: dict[str, float] = {}
            for c in campaigns:
                if c.emission_split is not None and c.emission_split > 0:
                    campaign_weights[c.scope] = float(c.emission_split) / total_split
            # Any campaign without explicit split gets zero weight.
        else:
            # If no emission_split is provided, distribute weights uniformly.
            uniform_weight = 1.0 / len(campaigns)
            campaign_weights = {c.scope: uniform_weight for c in campaigns}

        # Aggregated scores aligned to metagraph.uids.
        aggregated_scores = [0.0] * len(self.metagraph.uids)

        # Use the first campaign's mech_id/config as the mech_scope/burn scope.
        primary_campaign = campaigns[0]
        primary_mech_scope = f"mech{primary_campaign.mech_id}"

        for campaign in campaigns:
            mech_scope = f"mech{campaign.mech_id}"
            try:
                logging.info(
                    f"Computing scores for aggregation: campaign_scope={campaign.scope}, "
                    f"mech_id={campaign.mech_id}, mech_scope={mech_scope}"
                )

                # Get scope-specific configuration using mech_scope.
                scope_config = self.dynamic_config_source.get_config(mech_scope)
                if scope_config is None:
                    logging.warning(f"No configuration found for mech_scope {mech_scope}, using defaults")
                    scope_config = get_default_config(mech_scope)
                else:
                    logging.info(
                        f"Using config for mech_scope={mech_scope}: "
                        f"use_soft_cap={scope_config.use_soft_cap}, "
                        f"use_flooring={scope_config.use_flooring}, "
                        f"w_sales={scope_config.w_sales}, w_rev={scope_config.w_rev}"
                    )

                # Create ScoreCalculator with scope-specific configuration.
                score_calculator = ScoreCalculator(
                    p95_provider=self.p95_provider,
                    use_soft_cap=scope_config.use_soft_cap,
                    use_flooring=scope_config.use_flooring,
                    w_sales=scope_config.w_sales,
                    w_rev=scope_config.w_rev,
                    soft_cap_threshold=scope_config.soft_cap_threshold,
                    soft_cap_factor=scope_config.soft_cap_factor,
                )

                # Compute scores for this campaign.
                score_results = self.compute_scores_for_campaign(campaign, score_calculator)

                # Build UID->score map (miner_id is hotkey).
                uids = list(self.metagraph.uids)
                scores_by_uid: dict[int, float] = {}
                for result in score_results:
                    if result.miner_id not in self.metagraph.hotkeys:
                        continue
                    hotkey_index = self.metagraph.hotkeys.index(result.miner_id)
                    if hotkey_index < len(self.metagraph.uids):
                        uid = self.metagraph.uids[hotkey_index]
                        scores_by_uid[uid] = result.score
                miner_scores = [scores_by_uid.get(uid, 0.0) for uid in uids]

                # Apply this campaign's burn_percentage (per mechanism/company config).
                burn_percentage = None
                if self.burn_percentage_resolver is not None:
                    burn_percentage = self.burn_percentage_resolver(
                        mech_scope, miner_stats_scope=campaign.scope
                    )
                creator_uid = self.score_sink._get_owner_uid()

                if burn_percentage is not None and burn_percentage > 0.0:
                    try:
                        final_uids, final_weights = apply_creator_burn(
                            uids=uids,
                            miner_scores=miner_scores,
                            creator_uid=creator_uid,
                            burn_percentage=burn_percentage,
                        )
                        weights_dict = dict(zip(final_uids, final_weights))
                        campaign_weights_vec = [
                            weights_dict.get(uid, 0.0) for uid in self.metagraph.uids
                        ]
                        if sum(campaign_weights_vec) == 0.0:
                            owner_index = self.score_sink._get_owner_index()
                            if owner_index is not None:
                                campaign_weights_vec = [0.0] * len(uids)
                                campaign_weights_vec[owner_index] = 1.0
                        logging.info(
                            f"Applied burn {burn_percentage}% for campaign {campaign.scope} (mech_scope={mech_scope})"
                        )
                    except Exception as e:
                        logging.warning(
                            f"Failed to apply creator burn for campaign {campaign.scope}: {e}, using normalized scores"
                        )
                        total = sum(miner_scores)
                        campaign_weights_vec = (
                            [s / total for s in miner_scores]
                            if total > 0
                            else [0.0] * len(uids)
                        )
                        if total <= 0:
                            owner_index = self.score_sink._get_owner_index()
                            if owner_index is not None:
                                campaign_weights_vec[owner_index] = 1.0
                else:
                    total = sum(miner_scores)
                    if total > 0:
                        campaign_weights_vec = [s / total for s in miner_scores]
                    else:
                        campaign_weights_vec = [0.0] * len(uids)
                        owner_index = self.score_sink._get_owner_index()
                        if owner_index is not None:
                            campaign_weights_vec[owner_index] = 1.0

                emission_weight = campaign_weights.get(campaign.scope, 0.0)
                if emission_weight <= 0.0:
                    continue

                # Aggregate into global scores using emission-based weight.
                for idx, w in enumerate(campaign_weights_vec):
                    aggregated_scores[idx] += emission_weight * w

                if getattr(self, "metric_weights_sets_total", None) is not None:
                    self.metric_weights_sets_total.labels(
                        hotkey=self.hotkey_address,
                        scope=mech_scope,
                    ).inc()
            except Exception as e:
                logging.error(f"Error computing aggregated scores for campaign {campaign.scope}: {e}")
                traceback.print_exc()
                if getattr(self, "metric_weights_errors_total", None) is not None:
                    self.metric_weights_errors_total.labels(
                        hotkey=self.hotkey_address,
                        scope=mech_scope,
                    ).inc()

        # If all aggregated scores are zero, fallback to owner-only burn behaviour.
        if sum(aggregated_scores) == 0.0:
            logging.info(
                "Aggregated scores are all zero; setting weights to subnet owner (burn) "
                "and skipping on-chain aggregation publish."
            )
            success, message = self.score_sink.set_weights_to_owner_only()
            if success:
                logging.info(f"Set weights to owner (burn): {message}")
            else:
                logging.warning(f"Set weights to owner failed: {message}")
            return

        # Final normalisation of aggregated scores into [0,1] with sum 1.
        total_agg = sum(aggregated_scores)
        final_scores = [s / total_agg for s in aggregated_scores]

        # Build a single ScoreResult list for all miners using aggregated scores.
        aggregated_results: list[ScoreResult] = []
        for hotkey, score in zip(self.metagraph.hotkeys, final_scores):
            aggregated_results.append(
                ScoreResult(
                    miner_id=hotkey,
                    base=score,
                    refund_multiplier=1.0,
                    score=score,
                )
            )

        # Publish once via score sink. We use the primary mech_scope for configuration
        # and burn calculation, and the primary campaign as miner_stats_scope input
        # for burn percentage resolver.
        logging.info(
            f"Publishing aggregated scores for {len(self.metagraph.hotkeys)} miners "
            f"using primary_mech_scope={primary_mech_scope}, "
            f"primary_campaign_scope={primary_campaign.scope}"
        )
        success, message = self.score_sink.publish(
            aggregated_results,
            primary_mech_scope,
            miner_stats_scope=primary_campaign.scope,
            apply_burn=False,
        )
        if not success:
            logging.warning(
                f"Set weights failed for aggregated campaigns; leaving weights as is: {message}"
            )
    
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
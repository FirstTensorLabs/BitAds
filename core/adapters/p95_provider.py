from typing import Dict, Optional, List, Tuple

from bittensor.utils.btlogging import logging
from bitads_v3_core.app.ports import IConfigSource, IMinerStatsSource, IP95Provider
from bitads_v3_core.domain.models import Percentiles, P95Mode, MinerWindowStats
from bitads_v3_core.domain.percentiles import compute_auto_p95
from core.adapters.dynamic_config_source import IDynamicConfigSource


class ValidatorP95Provider(IP95Provider):
    """P95 provider that computes percentiles from miner stats or uses manual values."""

    def __init__(
        self,
        config_source: IConfigSource,
        miner_stats_source: IMinerStatsSource,
        dynamic_config_source: Optional[IDynamicConfigSource] = None,
        prev_percentiles: Optional[Dict[str, Percentiles]] = None,
        mech_scope_to_campaign_scope: Optional[Dict[str, str]] = None,
    ):
        self.config_source = config_source
        self.miner_stats_source = miner_stats_source
        self.dynamic_config_source = dynamic_config_source
        self.prev_percentiles = prev_percentiles or {}
        self.current_percentiles: Dict[str, Percentiles] = {}
        # Mapping from mech_scope (e.g., "mech1") to campaign_scope (campaign_id)
        # Used when fetching miner stats for P95 calculation in AUTO mode
        self.mech_scope_to_campaign_scope = mech_scope_to_campaign_scope or {}
        # Cache for miner stats to avoid duplicate fetches
        # Key: campaign_scope (campaign_id), Value: List[Tuple[str, MinerWindowStats]]
        self._miner_stats_cache: Dict[str, List[Tuple[str, MinerWindowStats]]] = {}

    def get_effective_p95(self, scope: str) -> Percentiles:
        """Get effective P95 percentiles for the given scope."""
        if scope in self.current_percentiles:
            logging.debug(f"P95Provider: using cached percentiles for scope='{scope}'")
            return self.current_percentiles[scope]

        p95_config = self.config_source.get_p95_config(scope)
        logging.info(f"P95Provider: getting P95 for scope='{scope}', mode={p95_config.mode}")

        if p95_config.mode == P95Mode.MANUAL:
            percentiles = Percentiles(
                p95_sales=p95_config.manual_p95_sales or 0.0,
                p95_revenue_usd=p95_config.manual_p95_revenue_usd or 0.0,
            )
            logging.info(f"P95Provider: using MANUAL mode for scope='{scope}': p95_sales={percentiles.p95_sales}, p95_revenue_usd={percentiles.p95_revenue_usd}")
        else:
            # For AUTO mode, if scope is a mech_scope (e.g., "mech1"), 
            # use the corresponding campaign_scope (campaign_id) for fetching miner stats
            # Miner stats are stored per campaign, not per mechanism
            miner_stats_scope = self.mech_scope_to_campaign_scope.get(scope, scope)
            if miner_stats_scope != scope:
                logging.info(f"P95Provider: mapping mech_scope='{scope}' -> campaign_scope='{miner_stats_scope}' for miner stats")
            else:
                logging.debug(f"P95Provider: using scope='{scope}' directly for miner stats")
            
            # Check cache first to avoid duplicate fetches
            # Cache persists for the entire campaign processing iteration
            if miner_stats_scope in self._miner_stats_cache:
                miner_stats_list = self._miner_stats_cache[miner_stats_scope]
                logging.debug(f"P95Provider: using cached miner stats for campaign_scope='{miner_stats_scope}' (requested scope='{scope}')")
            else:
                miner_stats_list = self.miner_stats_source.fetch_window(miner_stats_scope)
                logging.info(f"P95Provider: fetched {len(miner_stats_list)} miner stats for scope='{miner_stats_scope}' (requested scope='{scope}')")
                # Cache the fetched stats for potential reuse during this iteration
                self._miner_stats_cache[miner_stats_scope] = miner_stats_list
            
            stats = [stats for _, stats in miner_stats_list]
            prev = self.prev_percentiles.get(scope)
            # Get use_flooring from dynamic_config_source if available
            use_flooring = False
            if self.dynamic_config_source is not None:
                config = self.dynamic_config_source.get_config(scope)
                if config is not None:
                    use_flooring = config.use_flooring
            percentiles = compute_auto_p95(
                stats,
                prev=prev,
                alpha=p95_config.ema_alpha,
                use_flooring=use_flooring,
            )

        self.current_percentiles[scope] = percentiles
        return percentiles

    def set_miner_stats_cache(self, campaign_scope: str, miner_stats: List[Tuple[str, MinerWindowStats]]) -> None:
        """
        Set miner stats cache for a campaign scope to avoid duplicate fetches.
        
        This should be called before get_effective_p95 if miner stats are already available.
        The cache persists for the entire campaign processing iteration and is cleared
        in update_percentiles() at the end of each iteration.
        
        Args:
            campaign_scope: Campaign scope identifier (campaign_id)
            miner_stats: List of (miner_id, MinerWindowStats) tuples
        """
        self._miner_stats_cache[campaign_scope] = miner_stats
        logging.info(f"P95Provider: cached {len(miner_stats)} miner stats for campaign_scope='{campaign_scope}' (will be reused for this iteration)")
    
    def clear_miner_stats_cache(self, campaign_scope: str = None) -> None:
        """
        Clear miner stats cache for a specific campaign or all campaigns.
        
        Args:
            campaign_scope: If provided, clears cache only for this campaign. 
                          If None, clears all cached stats.
        """
        if campaign_scope is not None:
            if campaign_scope in self._miner_stats_cache:
                del self._miner_stats_cache[campaign_scope]
                logging.debug(f"P95Provider: cleared miner stats cache for campaign_scope='{campaign_scope}'")
        else:
            self._miner_stats_cache.clear()
            logging.debug("P95Provider: cleared all miner stats cache")
    
    def update_percentiles(self):
        """Move current percentiles to prev and clear cache for next iteration."""
        self.prev_percentiles = self.current_percentiles.copy()
        self.current_percentiles.clear()
        # Clear miner stats cache as well
        self._miner_stats_cache.clear()



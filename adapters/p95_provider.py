from typing import Dict, Optional, List, Tuple

from bitads_v3_core.app.ports import IConfigSource, IMinerStatsSource, IP95Provider
from bitads_v3_core.domain.models import Percentiles, P95Mode
from bitads_v3_core.domain.percentiles import compute_auto_p95


class ValidatorP95Provider(IP95Provider):
    """P95 provider that computes percentiles from miner stats or uses manual values."""

    def __init__(
        self,
        config_source: IConfigSource,
        miner_stats_source: IMinerStatsSource,
        prev_percentiles: Optional[Dict[str, Percentiles]] = None,
    ):
        self.config_source = config_source
        self.miner_stats_source = miner_stats_source
        self.prev_percentiles = prev_percentiles or {}
        self.current_percentiles: Dict[str, Percentiles] = {}

    def get_effective_p95(self, scope: str) -> Percentiles:
        """Get effective P95 percentiles for the given scope."""
        if scope in self.current_percentiles:
            return self.current_percentiles[scope]

        p95_config = self.config_source.get_p95_config(scope)

        if p95_config.mode == P95Mode.MANUAL:
            percentiles = Percentiles(
                p95_sales=p95_config.manual_p95_sales or 0.0,
                p95_revenue_usd=p95_config.manual_p95_revenue_usd or 0.0,
            )
        else:
            miner_stats_list = self.miner_stats_source.fetch_window(scope)
            stats = [stats for _, stats in miner_stats_list]
            prev = self.prev_percentiles.get(scope)
            percentiles = compute_auto_p95(
                stats,
                prev=prev,
                alpha=p95_config.ema_alpha,
                use_flooring=False,
            )

        self.current_percentiles[scope] = percentiles
        return percentiles

    def update_percentiles(self):
        """Move current percentiles to prev and clear cache for next iteration."""
        self.prev_percentiles = self.current_percentiles.copy()
        self.current_percentiles.clear()



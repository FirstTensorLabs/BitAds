from typing import Optional

from bittensor.utils.btlogging import logging

from bitads_v3_core.app.ports import IConfigSource
from bitads_v3_core.domain.models import P95Config, P95Mode


class ValidatorConfigSource(IConfigSource):
    """Config source that provides P95 configuration per scope."""

    def __init__(self, default_p95_sales: float = 60.0, default_p95_revenue: float = 4000.0):
        self.default_p95_sales = default_p95_sales
        self.default_p95_revenue = default_p95_revenue
        # TODO: Load from config file, database, or API

    def get_p95_config(self, scope: str) -> P95Config:
        """
        Get P95 configuration for the given scope.

        TODO: Implement actual config loading logic.
        For now, returns MANUAL mode for 'network' and AUTO for others.
        """
        if scope == "network":
            return P95Config(
                mode=P95Mode.MANUAL,
                manual_p95_sales=self.default_p95_sales,
                manual_p95_revenue_usd=self.default_p95_revenue,
                scope=scope,
            )
        # For campaign scopes, use AUTO mode by default
        return P95Config(mode=P95Mode.AUTO, ema_alpha=0.1, scope=scope)



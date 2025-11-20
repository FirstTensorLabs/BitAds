from typing import Optional

from bittensor.utils.btlogging import logging

from bitads_v3_core.app.ports import IConfigSource
from bitads_v3_core.domain.models import P95Config, P95Mode
from core.adapters.dynamic_config_source import IDynamicConfigSource


class ValidatorConfigSource(IConfigSource):
    """
    Config source that provides P95 configuration per scope.
    
    Delegates to dynamic_config_source if available, otherwise uses defaults.
    """

    def __init__(
        self,
        dynamic_config_source: Optional[IDynamicConfigSource] = None,
        default_p95_sales: float = 60.0,
        default_p95_revenue: float = 4000.0,
    ):
        """
        Initialize config source.
        
        Args:
            dynamic_config_source: Optional source for fetching dynamic P95 config
            default_p95_sales: Default P95 sales value
            default_p95_revenue: Default P95 revenue value
        """
        self.dynamic_config_source = dynamic_config_source
        self.default_p95_sales = default_p95_sales
        self.default_p95_revenue = default_p95_revenue

    def get_p95_config(self, scope: str) -> P95Config:
        """
        Get P95 configuration for the given scope.
        
        First tries to fetch from dynamic_config_source if available.
        Otherwise falls back to default logic.
        
        Args:
            scope: Scope identifier
        
        Returns:
            P95Config for the scope
        """
        # Try to fetch from dynamic config source first
        if self.dynamic_config_source is not None:
            p95_config = self.dynamic_config_source.get_p95_config(scope)
            if p95_config is not None:
                return p95_config
        
        # Fallback to default logic
        if scope == "network":
            return P95Config(
                mode=P95Mode.MANUAL,
                manual_p95_sales=self.default_p95_sales,
                manual_p95_revenue_usd=self.default_p95_revenue,
                scope=scope,
            )
        # For campaign scopes, use AUTO mode by default
        return P95Config(mode=P95Mode.AUTO, ema_alpha=0.1, scope=scope)



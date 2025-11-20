"""
Validator configuration and constants.

Following KISS principle - keep configuration simple and centralized.
"""
from typing import Callable

# Default configuration values
DEFAULT_WINDOW_DAYS = 30
DEFAULT_NETWORK_MECHID = 0
DEFAULT_CAMPAIGN_MECHID = 1
DEFAULT_USE_SOFT_CAP = False
DEFAULT_USE_FLOORING = False


class ValidatorConfig:
    """Simple configuration container for validator settings."""
    
    def __init__(
        self,
        window_days: int = DEFAULT_WINDOW_DAYS,
        network_mechid: int = DEFAULT_NETWORK_MECHID,
        campaign_mechid: int = DEFAULT_CAMPAIGN_MECHID,
        use_soft_cap: bool = DEFAULT_USE_SOFT_CAP,
        use_flooring: bool = DEFAULT_USE_FLOORING,
    ):
        """
        Initialize validator configuration.
        
        Args:
            window_days: Number of days for burn calculation window
            network_mechid: Mechanism ID for network scope
            campaign_mechid: Default mechanism ID for campaign scopes
            use_soft_cap: Whether to use soft cap in scoring
            use_flooring: Whether to use flooring in scoring
        """
        self.window_days = window_days
        self.network_mechid = network_mechid
        self.campaign_mechid = campaign_mechid
        self.use_soft_cap = use_soft_cap
        self.use_flooring = use_flooring


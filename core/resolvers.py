"""
Resolvers for validator configuration.

This module contains resolver functions that map scopes to configuration values.
Following Single Responsibility Principle - each resolver has one clear purpose.
"""
from typing import Callable, Dict, Optional

from core.adapters.burn_data_source import IBurnDataSource
from core.adapters.dynamic_config_source import IDynamicConfigSource
from core.burn_calculator import get_burn_percentage_from_sales
from core.constants import DEFAULT_MECHID, DEFAULT_WINDOW_DAYS


class MechIdResolver:
    """
    Resolves mechanism ID for a given scope.
    
    Uses a mapping of scope -> mech_id loaded from campaigns.
    """
    
    def __init__(self, scope_to_mechid: Dict[str, int], default_mechid: int = DEFAULT_MECHID):
        """
        Initialize mechid resolver.
        
        Args:
            scope_to_mechid: Dictionary mapping scope strings to mechanism IDs
            default_mechid: Default mechanism ID if scope not found in mapping
        """
        self.scope_to_mechid = scope_to_mechid
        self.default_mechid = default_mechid
    
    def __call__(self, scope: str) -> int:
        """
        Resolve mechanism ID for a scope.
        
        Args:
            scope: Scope identifier (e.g., "network", "campaign:123")
        
        Returns:
            Mechanism ID
        """
        return self.scope_to_mechid.get(scope, self.default_mechid)


class BurnPercentageResolver:
    """
    Resolves burn percentage for a given scope based on sales-to-emissions ratio.
    
    This resolver calculates the burn percentage to ensure miners don't become
    over-profitable when emissions exceed the value they generate.
    """
    
    def __init__(self, burn_data_source: IBurnDataSource):
        """
        Initialize burn percentage resolver.
        
        Args:
            burn_data_source: Data source for fetching burn calculation data
        """
        self.burn_data_source = burn_data_source
    
    def __call__(self, scope: str) -> Optional[float]:
        """
        Get burn percentage for a given scope.
        
        Calculation logic:
        1. Get emission amount in TAO for the period
        2. Get TAO/USD price and calculate emission_in_usd
        3. Get total sales in USD from miners
        4. Get target sales-to-emission ratio (e.g., 1.0 for 1:1, 1.5 for 1.5:1)
        5. Calculate burn percentage:
           - If emissions <= sales * ratio: burn = 0%
           - Otherwise: burn = (emissions - sales * ratio) / emissions * 100%
        
        Args:
            scope: Scope identifier (e.g., "network", "campaign:123")
        
        Returns:
            Burn percentage (0.0-100.0) or None to disable burn
        """
        burn_data = self.burn_data_source.get_burn_data(scope)
        
        if burn_data is None:
            return None
        
        return get_burn_percentage_from_sales(
            emission_in_tao=burn_data.emission_in_tao,
            tao_price_usd=burn_data.tao_price_usd,
            total_sales_usd=burn_data.total_sales_usd,
            sales_emission_ratio=burn_data.sales_emission_ratio,
        )


class WindowDaysGetter:
    """
    Getter for window days configuration per scope.
    
    Fetches window_days from external source dynamically.
    """
    
    def __init__(self, dynamic_config_source: IDynamicConfigSource):
        """
        Initialize window days getter.
        
        Args:
            dynamic_config_source: Source for fetching dynamic configuration
        """
        self.dynamic_config_source = dynamic_config_source
    
    def __call__(self, scope: str) -> int:
        """
        Get window days for a given scope.
        
        Args:
            scope: Scope identifier
        
        Returns:
            Window days (defaults to DEFAULT_WINDOW_DAYS if unavailable)
        """
        window_days = self.dynamic_config_source.get_window_days(scope)
        return window_days if window_days is not None else DEFAULT_WINDOW_DAYS


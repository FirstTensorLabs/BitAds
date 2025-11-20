"""
Interface for fetching dynamic configuration from external sources.

This module provides interfaces for fetching configuration that may change
at runtime, such as window_days, sales_emission_ratio, and P95 config.
"""
from abc import ABC, abstractmethod
from typing import Optional

from bitads_v3_core.domain.models import P95Config


class IDynamicConfigSource(ABC):
    """Interface for fetching dynamic configuration per scope."""
    
    @abstractmethod
    def get_window_days(self, scope: str) -> Optional[int]:
        """
        Get window days for a given scope.
        
        Args:
            scope: Scope identifier (e.g., "network", "campaign:123")
        
        Returns:
            Window days, or None if unavailable
        """
        pass
    
    @abstractmethod
    def get_sales_emission_ratio(self, scope: str) -> Optional[float]:
        """
        Get sales-to-emission ratio for a given scope.
        
        Args:
            scope: Scope identifier
        
        Returns:
            Sales-to-emission ratio (e.g., 1.0 for 1:1, 1.5 for 1.5:1), or None if unavailable
        """
        pass
    
    @abstractmethod
    def get_p95_config(self, scope: str) -> Optional[P95Config]:
        """
        Get full P95 configuration for a given scope.
        
        Args:
            scope: Scope identifier
        
        Returns:
            P95Config, or None if unavailable
        """
        pass


class ValidatorDynamicConfigSource(IDynamicConfigSource):
    """
    Implementation of dynamic config source.
    
    TODO: Implement actual API calls to fetch:
    - window_days from external source
    - sales_emission_ratio from external source
    - full P95 config from external source
    """
    
    def get_window_days(self, scope: str) -> Optional[int]:
        """
        Get window days for a given scope.
        
        TODO: Implement fetching from external API.
        
        Args:
            scope: Scope identifier
        
        Returns:
            Window days, or None if unavailable
        """
        # TODO: Implement fetching from external source
        # For now, return default
        return 30
    
    def get_sales_emission_ratio(self, scope: str) -> Optional[float]:
        """
        Get sales-to-emission ratio for a given scope.
        
        TODO: Implement fetching from external API.
        
        Args:
            scope: Scope identifier
        
        Returns:
            Sales-to-emission ratio, or None if unavailable
        """
        # TODO: Implement fetching from external source
        # For now, return default
        return 1.0
    
    def get_p95_config(self, scope: str) -> Optional[P95Config]:
        """
        Get full P95 configuration for a given scope.
        
        TODO: Implement fetching from external API.
        This should return the complete P95Config with all parameters.
        
        Args:
            scope: Scope identifier
        
        Returns:
            P95Config, or None if unavailable
        """
        # TODO: Implement fetching from external source
        # For now, delegate to the existing config source logic
        # This should be replaced with external API call
        return None


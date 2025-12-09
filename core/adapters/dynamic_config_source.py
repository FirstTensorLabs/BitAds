"""
Interface for fetching dynamic configuration from external sources.

This module provides interfaces for fetching configuration that may change
at runtime, such as window_days, sales_emission_ratio, and P95 config.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Tuple
import os
import time
import requests
from bittensor.utils.btlogging import logging

from bitads_v3_core.domain.models import P95Config, P95Mode
from core.constants import (
    DEFAULT_WINDOW_DAYS, 
    DEFAULT_SALES_EMISSION_RATIO, 
    DEFAULT_USE_SOFT_CAP,
    DEFAULT_USE_FLOORING,
    DEFAULT_W_SALES,
    DEFAULT_W_REV,
    DEFAULT_SOFT_CAP_THRESHOLD,
    DEFAULT_SOFT_CAP_FACTOR,
    NETWORK_BASE_URLS,
)


@dataclass
class DynamicConfig:
    """Complete dynamic configuration for a scope."""
    window_days: int
    sales_emission_ratio: float
    p95_config: P95Config
    use_soft_cap: bool
    use_flooring: bool
    w_sales: float
    w_rev: float
    soft_cap_threshold: int
    soft_cap_factor: float
    # Optional fixed burn percentage for this scope (0.0-100.0).
    # If set, this value should be used instead of the dynamic burn calculator.
    burn_percentage: Optional[float] = None


def get_default_config(scope: str) -> DynamicConfig:
    """
    Get default DynamicConfig for a scope.
    
    Args:
        scope: Scope identifier
        
    Returns:
        DynamicConfig with default values
    """
    from bitads_v3_core.domain.models import P95Config, P95Mode
    
    return DynamicConfig(
        window_days=DEFAULT_WINDOW_DAYS,
        sales_emission_ratio=DEFAULT_SALES_EMISSION_RATIO,
        p95_config=P95Config(mode=P95Mode.AUTO, ema_alpha=0.1, scope=scope),
        use_soft_cap=DEFAULT_USE_SOFT_CAP,
        use_flooring=DEFAULT_USE_FLOORING,
        w_sales=DEFAULT_W_SALES,
        w_rev=DEFAULT_W_REV,
        soft_cap_threshold=DEFAULT_SOFT_CAP_THRESHOLD,
        soft_cap_factor=DEFAULT_SOFT_CAP_FACTOR,
        burn_percentage=None,
    )


class IDynamicConfigSource(ABC):
    """Interface for fetching dynamic configuration per scope."""
    
    @abstractmethod
    def get_config(self, scope: str) -> Optional[DynamicConfig]:
        """
        Get complete dynamic configuration for a given scope.
        
        Args:
            scope: Scope identifier (e.g., "network", "campaign:123")
        
        Returns:
            DynamicConfig with all configuration values, or None if unavailable
        """
        pass


class ValidatorDynamicConfigSource(IDynamicConfigSource):
    """
    Implementation of dynamic config source.
    
    Fetches configuration from the mock API /config endpoint.
    Uses caching to prevent API spam (5 minute default TTL).
    """
    
    def __init__(self, api_base_url: str = None, cache_ttl: int = 300):
        """
        Initialize dynamic config source.
        
        Args:
            api_base_url: Base URL for the API. If not provided, must be set via API_BASE_URL env var.
            cache_ttl: Cache time-to-live in seconds. Defaults to 300 (5 minutes).
        
        Raises:
            ValueError: If API_BASE_URL is not provided and not set in environment.
        """
        self.api_base_url = api_base_url or os.getenv("API_BASE_URL")
        if not self.api_base_url:
            raise ValueError("API_BASE_URL must be set as environment variable or passed as parameter")
        self.cache_ttl = cache_ttl
        # Cache structure: {scope: (config_data, timestamp)}
        self._cache: Dict[str, Tuple[dict, float]] = {}
    
    def _fetch_config_raw(self, scope: str) -> Optional[dict]:
        """
        Fetch config from API for a given scope.
        
        Uses caching to prevent API spam. Returns cached data if available and still valid.
        
        Args:
            scope: Scope identifier
        
        Returns:
            Config dictionary, or None if unavailable
        """
        current_time = time.time()
        
        # Check cache first
        if scope in self._cache:
            cached_data, cache_timestamp = self._cache[scope]
            if current_time - cache_timestamp < self.cache_ttl:
                logging.debug(f"Using cached config for scope {scope}")
                return cached_data
            else:
                # Cache expired, remove it
                del self._cache[scope]
        
        # Fetch from API
        try:
            url = f"{self.api_base_url}/config"
            response = requests.get(url, params={"scope": scope}, timeout=10)
            response.raise_for_status()
            config_data = response.json()
            
            # Store in cache
            self._cache[scope] = (config_data, current_time)
            logging.debug(f"Fetched and cached config for scope {scope}")
            return config_data
            
        except requests.exceptions.RequestException as e:
            logging.warning(f"Failed to fetch config from API for scope {scope}: {e}")
            return None
        except (ValueError, KeyError, TypeError) as e:
            logging.warning(f"Failed to parse config API response for scope {scope}: {e}")
            return None
    
    def get_config(self, scope: str) -> Optional[DynamicConfig]:
        """
        Get complete dynamic configuration for a given scope.
        
        Args:
            scope: Scope identifier
        
        Returns:
            DynamicConfig with all configuration values, or None if unavailable
        """
        config_data = self._fetch_config_raw(scope)
        if config_data is None:
            return None
        
        try:
            # Parse P95 config
            p95_config_data = config_data.get("p95_config", {})
            mode_str = p95_config_data.get("mode", "auto")
            mode = P95Mode.MANUAL if mode_str == "manual" else P95Mode.AUTO
            
            p95_config = P95Config(
                mode=mode,
                manual_p95_sales=p95_config_data.get("manual_p95_sales"),
                manual_p95_revenue_usd=p95_config_data.get("manual_p95_revenue_usd"),
                ema_alpha=p95_config_data.get("ema_alpha"),
                scope=scope
            )
            
            return DynamicConfig(
                window_days=config_data.get("window_days", DEFAULT_WINDOW_DAYS),
                sales_emission_ratio=config_data.get("sales_emission_ratio", DEFAULT_SALES_EMISSION_RATIO),
                p95_config=p95_config,
                use_soft_cap=p95_config_data.get("use_soft_cap", DEFAULT_USE_SOFT_CAP),
                use_flooring=p95_config_data.get("use_flooring", DEFAULT_USE_FLOORING),
                w_sales=p95_config_data.get("w_sales", DEFAULT_W_SALES),
                w_rev=p95_config_data.get("w_rev", DEFAULT_W_REV),
                soft_cap_threshold=p95_config_data.get("soft_cap_threshold", DEFAULT_SOFT_CAP_THRESHOLD),
                soft_cap_factor=p95_config_data.get("soft_cap_factor", DEFAULT_SOFT_CAP_FACTOR),
                # Optional fixed burn percentage for this scope. Falls back to None when not present.
                burn_percentage=config_data.get("burn_percentage"),
            )
        except (ValueError, KeyError, TypeError) as e:
            logging.warning(f"Failed to parse config for scope {scope}: {e}")
        return None


class StorageDynamicConfigSource(IDynamicConfigSource):
    """
    Implementation of dynamic config source that fetches from dev-storage.bitads.ai.
    
    Fetches configuration from https://dev-storage.bitads.ai/data/subnet_config.json
    for test network. Returns None for finney network.
    
    This provides subnet-level configuration (not per-scope).
    """
    
    def __init__(self, network: str = None, cache_ttl: int = 300):
        """
        Initialize storage dynamic config source.
        
        Args:
            network: Subtensor network name ("test" or "finney"). 
                    If not provided, will try to get from SUBTENSOR_NETWORK env var.
            cache_ttl: Cache time-to-live in seconds. Defaults to 300 (5 minutes).
        """
        self.network = network or os.getenv("SUBTENSOR_NETWORK", "").lower()
        self.base_url = NETWORK_BASE_URLS.get(self.network)
        self.cache_ttl = cache_ttl
        # Cache structure: (config_data, timestamp)
        self._cache: Optional[Tuple[dict, float]] = None
    
    def _fetch_config_raw(self) -> Optional[dict]:
        """
        Fetch config from storage.
        
        Uses caching to prevent API spam. Returns cached data if available and still valid.
        
        Returns:
            Config dictionary, or None if unavailable
        """
        current_time = time.time()
        
        # Check cache first
        if self._cache is not None:
            cached_data, cache_timestamp = self._cache
            if current_time - cache_timestamp < self.cache_ttl:
                logging.debug("Using cached config from storage")
                return cached_data
            else:
                # Cache expired, clear it
                self._cache = None
        
        # Check if network is supported and has a base URL
        if self.base_url is None:
            if self.network in NETWORK_BASE_URLS:
                logging.debug(f"StorageDynamicConfigSource: {self.network} network not supported yet")
            else:
                logging.warning(f"StorageDynamicConfigSource: unknown network '{self.network}'")
            return None
        
        # Fetch from storage
        try:
            url = f"{self.base_url}/data/subnet_config.json"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            config_data = response.json()
            
            # Store in cache
            self._cache = (config_data, current_time)
            logging.debug("Fetched and cached config from storage")
            return config_data
            
        except requests.exceptions.RequestException as e:
            logging.warning(f"Failed to fetch config from storage: {e}")
            return None
        except (ValueError, KeyError, TypeError) as e:
            logging.warning(f"Failed to parse config storage response: {e}")
            return None
    
    def get_config(self, scope: str) -> Optional[DynamicConfig]:
        """
        Get complete dynamic configuration for a given scope.
        
        This provides subnet-level configuration, so it returns the same config
        for all scopes when available.
        
        Args:
            scope: Scope identifier (e.g., "network", "campaign:123")
        
        Returns:
            DynamicConfig with all configuration values, or None if unavailable
        """
        config_data = self._fetch_config_raw()
        if config_data is None:
            return None
        
        try:
            # Parse P95 config
            p95_config_data = config_data.get("p95_config", {})
            mode_str = p95_config_data.get("mode", "auto")
            mode = P95Mode.MANUAL if mode_str == "manual" else P95Mode.AUTO
            
            p95_config = P95Config(
                mode=mode,
                manual_p95_sales=p95_config_data.get("manual_p95_sales"),
                manual_p95_revenue_usd=p95_config_data.get("manual_p95_revenue_usd"),
                ema_alpha=p95_config_data.get("ema_alpha"),
                scope=scope
            )
            
            return DynamicConfig(
                window_days=config_data.get("window_days", DEFAULT_WINDOW_DAYS),
                sales_emission_ratio=config_data.get("sales_emission_ratio", DEFAULT_SALES_EMISSION_RATIO),
                p95_config=p95_config,
                use_soft_cap=p95_config_data.get("use_soft_cap", DEFAULT_USE_SOFT_CAP),
                use_flooring=p95_config_data.get("use_flooring", DEFAULT_USE_FLOORING),
                w_sales=p95_config_data.get("w_sales", DEFAULT_W_SALES),
                w_rev=p95_config_data.get("w_rev", DEFAULT_W_REV),
                soft_cap_threshold=p95_config_data.get("soft_cap_threshold", DEFAULT_SOFT_CAP_THRESHOLD),
                soft_cap_factor=p95_config_data.get("soft_cap_factor", DEFAULT_SOFT_CAP_FACTOR),
                # Optional fixed burn percentage. Falls back to None when not present.
                burn_percentage=config_data.get("burn_percentage"),
            )
        except (ValueError, KeyError, TypeError) as e:
            logging.warning(f"Failed to parse config from storage for scope {scope}: {e}")
            return None


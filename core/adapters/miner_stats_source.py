from typing import List, Tuple
import os
import requests
from bittensor.utils.btlogging import logging

from bitads_v3_core.app.ports import IMinerStatsSource
from bitads_v3_core.domain.models import MinerWindowStats
from core.constants import DEFAULT_WINDOW_DAYS, NETWORK_BASE_URLS


class ValidatorMinerStatsSource(IMinerStatsSource):
    """Miner stats source - fetches from mock API."""

    def __init__(self, api_base_url: str = None):
        """
        Initialize miner stats source.
        
        Args:
            api_base_url: Optional base URL for the API. If not provided, will try API_BASE_URL env var.
        """
        self.api_base_url = api_base_url or os.getenv("API_BASE_URL")

    def fetch_window(self, scope: str, window_days: int = DEFAULT_WINDOW_DAYS) -> List[Tuple[str, MinerWindowStats]]:
        """
        Fetch miner statistics for a rolling window.

        Args:
            scope: Scope identifier
            window_days: Window size in days
        
        Returns:
            List of tuples (miner_id, MinerWindowStats)
        """
        # If no API base URL is configured, gracefully return an empty list
        if not self.api_base_url:
            logging.info("ValidatorMinerStatsSource: no API_BASE_URL configured; returning empty miner stats list")
            return []

        try:
            url = f"{self.api_base_url}/miner-stats"
            response = requests.get(
                url,
                params={"scope": scope, "window_days": window_days},
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            miners_data = data.get("miners", [])
            results = []
            
            for miner_data in miners_data:
                miner_id = miner_data.get("miner_id")
                sales = miner_data.get("sales", 0)
                revenue_usd = miner_data.get("revenue_usd", 0.0)
                refund_orders = miner_data.get("refund_orders", 0)
                
                if miner_id is not None:
                    stats = MinerWindowStats(
                        sales=sales,
                        revenue_usd=revenue_usd,
                        refund_orders=refund_orders
                    )
                    results.append((miner_id, stats))
            
            logging.info(f"Fetched {len(results)} miner stats for scope {scope}, window {window_days} days")
            return results
            
        except requests.exceptions.RequestException as e:
            logging.warning(f"Failed to fetch miner stats from API for scope {scope}: {e}")
            return []
        except (ValueError, KeyError, TypeError) as e:
            logging.warning(f"Failed to parse miner stats API response for scope {scope}: {e}")
        return []


class StorageMinerStatsSource(IMinerStatsSource):
    """
    Miner stats source that fetches from dev-storage.bitads.ai.
    
    Fetches miner statistics from:
    https://dev-storage.bitads.ai/data/subnet_miner-stats-{scope}.json
    for test network. Returns empty list for finney network.
    """
    
    def __init__(self, network: str = None):
        """
        Initialize storage miner stats source.
        
        Args:
            network: Subtensor network name ("test" or "finney"). 
                    If not provided, will try to get from SUBTENSOR_NETWORK env var.
        """
        self.network = network or os.getenv("SUBTENSOR_NETWORK", "").lower()
        self.base_url = NETWORK_BASE_URLS.get(self.network)
    
    def fetch_window(self, scope: str, window_days: int = DEFAULT_WINDOW_DAYS) -> List[Tuple[str, MinerWindowStats]]:
        """
        Fetch miner statistics for a rolling window.
        
        Args:
            scope: Scope identifier (campaign_id for campaigns)
            window_days: Window size in days (ignored for storage source)
        
        Returns:
            List of tuples (miner_id, MinerWindowStats)
        """
        # Check if network is supported and has a base URL
        if self.base_url is None:
            if self.network in NETWORK_BASE_URLS:
                logging.debug(f"StorageMinerStatsSource: {self.network} network not supported yet, returning empty list")
            else:
                logging.warning(f"StorageMinerStatsSource: unknown network '{self.network}', returning empty list")
            return []
        
        try:
            # URL pattern: subnet_miner-stats-{scope}.json
            url = f"{self.base_url}/data/subnet_miner-stats-{scope}.json"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            # Storage returns array directly, not wrapped in "miners"
            miners_data = response.json()
            
            # Ensure it's a list
            if not isinstance(miners_data, list):
                logging.warning(f"StorageMinerStatsSource: expected array for scope {scope}, got {type(miners_data)}")
                return []
            
            results = []
            for miner_data in miners_data:
                miner_id = miner_data.get("miner_id")
                sales = miner_data.get("sales", 0)
                revenue_usd = miner_data.get("revenue_usd", 0.0)
                refund_orders = miner_data.get("refund_orders", 0)
                
                if miner_id is not None:
                    stats = MinerWindowStats(
                        sales=sales,
                        revenue_usd=revenue_usd,
                        refund_orders=refund_orders
                    )
                    results.append((miner_id, stats))
            
            logging.info(f"Fetched {len(results)} miner stats from storage for scope {scope}")
            return results
            
        except requests.exceptions.RequestException as e:
            logging.warning(f"Failed to fetch miner stats from storage for scope {scope}: {e}")
            return []
        except (ValueError, KeyError, TypeError) as e:
            logging.warning(f"Failed to parse miner stats storage response for scope {scope}: {e}")
            return []


from typing import List, Tuple
import os
import requests
from bittensor.utils.btlogging import logging

from bitads_v3_core.app.ports import IMinerStatsSource
from bitads_v3_core.domain.models import MinerWindowStats
from core.constants import DEFAULT_WINDOW_DAYS


class ValidatorMinerStatsSource(IMinerStatsSource):
    """Miner stats source - fetches from mock API."""

    def __init__(self, api_base_url: str = None):
        """
        Initialize miner stats source.
        
        Args:
            api_base_url: Base URL for the API. If not provided, must be set via API_BASE_URL env var.
        
        Raises:
            ValueError: If API_BASE_URL is not provided and not set in environment.
        """
        self.api_base_url = api_base_url or os.getenv("API_BASE_URL")
        if not self.api_base_url:
            raise ValueError("API_BASE_URL must be set as environment variable or passed as parameter")

    def fetch_window(self, scope: str, window_days: int = DEFAULT_WINDOW_DAYS) -> List[Tuple[str, MinerWindowStats]]:
        """
        Fetch miner statistics for a rolling window.

        Args:
            scope: Scope identifier
            window_days: Window size in days
        
        Returns:
            List of tuples (miner_id, MinerWindowStats)
        """
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



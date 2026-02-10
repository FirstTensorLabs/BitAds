"""
Adapter for fetching the list of pending miners per campaign from storage.

Pending miners are miners who have only pending orders (not yet in miner-stats)
and should receive a minimum reward so they are not removed from the subnet.

API: {base_url}/data/subnet_pending_miners-{campaign_id}.json
Example: https://dev-storage.bitads.ai/data/subnet_pending_miners-0497f5b9-ab35-4848-854b-623be3198fb9.json
"""
import os
from typing import List

import requests
from bittensor.utils.btlogging import logging

from core.constants import NETWORK_BASE_URLS


class IPendingMinersSource:
    """Interface for fetching pending miners list per campaign."""

    def get_pending_miners(self, campaign_id: str) -> List[str]:
        """
        Get list of hotkeys (miner IDs) that have only pending orders for this campaign.

        A miner is either on this list or in miner-stats for the campaign, not both.
        These miners should receive a minimum score so they are not removed from the subnet.

        Args:
            campaign_id: Campaign scope identifier (UUID).

        Returns:
            List of hotkey strings (ss58 addresses). Empty list if unavailable or on error.
        """
        raise NotImplementedError


class StoragePendingMinersSource(IPendingMinersSource):
    """
    Fetches pending miners from storage.

    URL: {base_url}/data/subnet_pending_miners-{campaign_id}.json
    Response includes "miners": ["5ExzDrb...", ...]
    """

    def __init__(self, network: str = None):
        self.network = network or os.getenv("SUBTENSOR_NETWORK", "finney").lower()
        self.base_url = NETWORK_BASE_URLS.get(self.network)

    def get_pending_miners(self, campaign_id: str) -> List[str]:
        if self.base_url is None:
            return []

        try:
            url = f"{self.base_url}/data/subnet_pending_miners-{campaign_id}.json"
            response = requests.get(url, timeout=10)
            if response.status_code == 404:
                logging.debug(f"No pending miners file for campaign {campaign_id}")
                return []
            response.raise_for_status()
            data = response.json()
            miners = data.get("miners", [])
            if not isinstance(miners, list):
                return []
            # Ensure all entries are strings (hotkeys)
            out = [m for m in miners if isinstance(m, str)]
            if out:
                logging.info(
                    f"Fetched {len(out)} pending miners for campaign {campaign_id} "
                    f"(pending_miners_total={data.get('pending_miners_total', '?')})"
                )
            return out
        except requests.exceptions.RequestException as e:
            logging.debug(f"Could not fetch pending miners for campaign {campaign_id}: {e}")
            return []
        except (ValueError, KeyError, TypeError) as e:
            logging.warning(f"Failed to parse pending miners response for campaign {campaign_id}: {e}")
            return []

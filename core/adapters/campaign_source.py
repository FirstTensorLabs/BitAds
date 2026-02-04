"""
Interface for fetching campaigns from external sources.
"""
from abc import ABC, abstractmethod
from typing import List
import os
import requests
from bittensor.utils.btlogging import logging

from core.domain.campaign import Campaign
from core.constants import NETWORK_BASE_URLS


class ICampaignSource(ABC):
    """Interface for fetching campaigns."""
    
    @abstractmethod
    def get_campaigns(self) -> List[Campaign]:
        """
        Get list of active campaigns with their mechanism IDs.
        
        Returns:
            List of Campaign objects, each with scope and mech_id
        """
        pass


class ValidatorCampaignSource(ICampaignSource):
    """
    Implementation of campaign source.
    
    Fetches campaigns from the mock API /campaigns endpoint.
    """
    
    def __init__(self, api_base_url: str = None):
        """
        Initialize campaign source.
        
        Args:
            api_base_url: Optional base URL for the API. If not provided, will try API_BASE_URL env var.
        """
        self.api_base_url = api_base_url or os.getenv("API_BASE_URL")
    
    def get_campaigns(self) -> List[Campaign]:
        """
        Get list of active campaigns.
        
        Returns:
            List of Campaign objects
        """
        # If no API base URL is configured, gracefully return an empty list
        if not self.api_base_url:
            logging.info("ValidatorCampaignSource: no API_BASE_URL configured; returning empty campaign list")
            return []
        try:
            url = f"{self.api_base_url}/campaigns"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            campaigns_data = response.json()
            
            campaigns = []
            for campaign_data in campaigns_data:
                # Map campaign_id from API to scope for Campaign model
                campaign_id = campaign_data.get("campaign_id")
                mech_id = campaign_data.get("mech_id")
                status = campaign_data.get("status", 1)  # Default to 1 (active) if not specified
                
                logging.debug(f"Campaign from API: campaign_id={campaign_id}, mech_id={mech_id}, status={status}")
                
                # Only include campaigns with status = 1 (active)
                if campaign_id is not None and mech_id is not None and status == 1:
                    campaigns.append(Campaign(scope=campaign_id, mech_id=mech_id))
                    logging.info(f"✓ Added active campaign: campaign_id={campaign_id}, mech_id={mech_id}, mech_scope=mech{mech_id}")
                elif campaign_id is not None:
                    logging.info(f"✗ Skipped inactive campaign: campaign_id={campaign_id}, mech_id={mech_id}, status={status}")
            
            logging.info(f"Fetched {len(campaigns)} active campaigns from API (status=1)")
            if campaigns:
                logging.info(f"Active campaigns mapping: {[(c.scope, c.mech_id, f'mech{c.mech_id}') for c in campaigns]}")
            return campaigns
            
        except requests.exceptions.RequestException as e:
            logging.warning(f"Failed to fetch campaigns from API: {e}")
            # Return empty list on error
            return []
        except (ValueError, KeyError, TypeError) as e:
            logging.warning(f"Failed to parse campaigns API response: {e}")
            return []


class StorageCampaignSource(ICampaignSource):
    """
    Implementation of campaign source that fetches from dev-storage.bitads.ai.
    
    Fetches campaigns from https://dev-storage.bitads.ai/data/subnet_campaigns.json
    for test network. Returns empty list for finney network.
    """
    
    def __init__(self, network: str = None):
        """
        Initialize storage campaign source.
        
        Args:
            network: Subtensor network name ("test" or "finney"). 
                    If not provided, will try to get from SUBTENSOR_NETWORK env var.
        """
        self.network = network or os.getenv("SUBTENSOR_NETWORK", "finney").lower()
        self.base_url = NETWORK_BASE_URLS.get(self.network)
    
    def get_campaigns(self) -> List[Campaign]:
        """
        Get list of active campaigns from storage.
        
        Returns:
            List of Campaign objects. Returns empty list for finney network or unknown networks.
        """
        # Check if network is supported and has a base URL
        if self.base_url is None:
            if self.network in NETWORK_BASE_URLS:
                logging.info(f"StorageCampaignSource: {self.network} network not supported yet, returning empty list")
            else:
                logging.warning(f"StorageCampaignSource: unknown network '{self.network}', returning empty list")
            return []
        
        try:
            url = f"{self.base_url}/data/subnet_campaigns.json"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # Extract campaigns array from response
            campaigns_data = data.get("campaigns", [])
            
            campaigns = []
            for index, campaign_data in enumerate(campaigns_data):
                campaign_id = campaign_data.get("campaign_id")
                mech_id = campaign_data.get("mech_id")
                status = campaign_data.get("status", 1)  # Default to 1 (active) if not specified
                
                logging.debug(f"Campaign from storage: campaign_id={campaign_id}, mech_id={mech_id}, status={status}")
                
                # Only include campaigns with status = 1 (active)
                if campaign_id is not None and status == 1:
                    campaigns.append(Campaign(scope=campaign_id, mech_id=mech_id))
                    logging.info(f"✓ Added active campaign: campaign_id={campaign_id}, mech_id={mech_id}, mech_scope=mech{mech_id}")
                elif campaign_id is not None:
                    logging.info(f"✗ Skipped inactive campaign: campaign_id={campaign_id}, mech_id={mech_id}, status={status}")
            
            logging.info(f"Fetched {len(campaigns)} active campaigns from storage (status=1)")
            if campaigns:
                logging.info(f"Active campaigns mapping: {[(c.scope, c.mech_id, f'mech{c.mech_id}') for c in campaigns]}")
            return campaigns
            
        except requests.exceptions.RequestException as e:
            logging.warning(f"Failed to fetch campaigns from storage: {e}")
            return []
        except (ValueError, KeyError, TypeError) as e:
            logging.warning(f"Failed to parse campaigns storage response: {e}")
            return []


"""
Interface for fetching campaigns from external sources.
"""
from abc import ABC, abstractmethod
from typing import List
import os
import requests
from bittensor.utils.btlogging import logging

from core.domain.campaign import Campaign


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
            api_base_url: Base URL for the API. If not provided, must be set via API_BASE_URL env var.
        
        Raises:
            ValueError: If API_BASE_URL is not provided and not set in environment.
        """
        self.api_base_url = api_base_url or os.getenv("API_BASE_URL")
        if not self.api_base_url:
            raise ValueError("API_BASE_URL must be set as environment variable or passed as parameter")
    
    def get_campaigns(self) -> List[Campaign]:
        """
        Get list of active campaigns.
        
        Returns:
            List of Campaign objects
        """
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
                if campaign_id is not None and mech_id is not None:
                    campaigns.append(Campaign(scope=campaign_id, mech_id=mech_id))
            
            logging.info(f"Fetched {len(campaigns)} campaigns from API")
            return campaigns
            
        except requests.exceptions.RequestException as e:
            logging.warning(f"Failed to fetch campaigns from API: {e}")
            # Return empty list on error
            return []
        except (ValueError, KeyError, TypeError) as e:
            logging.warning(f"Failed to parse campaigns API response: {e}")
            return []


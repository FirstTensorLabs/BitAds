"""
Interface for fetching campaigns from external sources.
"""
from abc import ABC, abstractmethod
from typing import List

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
    
    TODO: Implement actual API calls to fetch campaigns with mech_ids.
    """
    
    def get_campaigns(self) -> List[Campaign]:
        """
        Get list of active campaigns.
        
        TODO: Implement fetching from external API.
        Should return campaigns with their associated mech_ids.
        For example:
        - campaign1 -> mech_id 0
        - campaign2 -> mech_id 1
        - network -> mech_id 0 (or separate mech_id)
        
        Returns:
            List of Campaign objects
        """
        # TODO: Implement fetching from external source
        # For now, return default campaigns
        return [
            Campaign(scope="network", mech_id=0),
            Campaign(scope="local", mech_id=1),
        ]


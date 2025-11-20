"""
Campaign domain model.

Represents a campaign with its associated mechanism ID.
"""
from dataclasses import dataclass


@dataclass
class Campaign:
    """Represents a campaign with its scope and mechanism ID."""
    
    scope: str  # Scope identifier (e.g., "network", "campaign:123")
    mech_id: int  # Mechanism ID for this campaign
    
    def __str__(self) -> str:
        return f"Campaign(scope={self.scope}, mech_id={self.mech_id})"


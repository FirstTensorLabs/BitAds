"""
Campaign domain model.

Represents a campaign with its associated mechanism ID.
"""
from dataclasses import dataclass


@dataclass
class Campaign:
    """Represents a campaign with its scope, mechanism ID and optional emission split."""
    
    scope: str  # Scope identifier (e.g., "network", "campaign:123")
    mech_id: int  # Mechanism ID for this campaign
    # Percentage of the total subnet emission allocated to this campaign (0-100).
    # When None, the campaign will be treated as having no explicit split configured.
    emission_split: float | None = None
    
    def __str__(self) -> str:
        return (
            f"Campaign(scope={self.scope}, mech_id={self.mech_id}, "
            f"emission_split={self.emission_split})"
        )


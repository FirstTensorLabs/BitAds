"""
Constants used throughout the validator.

All project constants are centralized here for easy maintenance and configuration.
"""
from bittensor.core.settings import NETWORKS

# Network configuration
NETUIDS = {
    NETWORKS[0]: 16,
    NETWORKS[1]: 368,
}

# Burn calculation constants
MINER_EMISSION_PERCENT = 0.41  # Percentage of emissions that go to miners

# Default configuration values
DEFAULT_WINDOW_DAYS = 30
DEFAULT_NETWORK_MECHID = 0
DEFAULT_CAMPAIGN_MECHID = 1
DEFAULT_USE_SOFT_CAP = False
DEFAULT_USE_FLOORING = False

# Scoring defaults (matching bitads_v3_core constants)
DEFAULT_W_SALES = 0.40
DEFAULT_W_REV = 0.60
DEFAULT_SOFT_CAP_THRESHOLD = 3
DEFAULT_SOFT_CAP_FACTOR = 0.30

# P95 configuration defaults
DEFAULT_P95_SALES = 60.0
DEFAULT_P95_REVENUE_USD = 4000.0

# Sales emission ratio defaults
DEFAULT_SALES_EMISSION_RATIO = 1.0  # 1:1 ratio (miners earn what they generate)

# Resolver defaults
DEFAULT_MECHID = 0  # Default mechanism ID if scope not found
"""
Pytest configuration for tests with logging enabled.
"""
import logging
import sys

# Configure logging to show INFO and above by default
# Can be overridden with pytest --log-cli-level flag
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

# Enable bittensor logging
try:
    from bittensor.utils.btlogging import logging as bt_logging
    # Configure bittensor logging to show INFO level
    bt_logging.enable_info()
except ImportError:
    pass


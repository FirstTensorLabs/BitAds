"""
One-time weight setting script.

This script sets weights for all active campaigns without checking timing constraints.
Useful for manual weight updates or testing.
"""
from neurons.validator import Validator


def main():
    """Set weights for all active campaigns once."""
    # Disable Prometheus / telemetry for this one-off utility script.
    # We don't want to start the metrics HTTP server (port 9100) when
    # running set_weights.py locally.
    validator = Validator(enable_metrics=False)
    validator.set_weights()


if __name__ == "__main__":
    main()


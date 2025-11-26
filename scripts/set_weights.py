"""
One-time weight setting script.

This script sets weights for all active campaigns without checking timing constraints.
Useful for manual weight updates or testing.
"""
from neurons.validator import Validator


def main():
    """Set weights for all active campaigns once."""
    validator = Validator()
    validator.set_weights()


if __name__ == "__main__":
    main()


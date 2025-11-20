"""
Factory for creating and validating Bittensor objects.

Following Dependency Inversion Principle - depends on abstractions.
Following Single Responsibility Principle - only responsible for object creation.
"""
from typing import Optional

from bittensor.core.config import Config
from bittensor.core.dendrite import Dendrite
from bittensor.core.metagraph import Metagraph
from bittensor.core.subtensor import Subtensor
from bittensor.utils.btlogging import logging
from bittensor_wallet import Wallet


class BittensorObjects:
    """Container for Bittensor-related objects."""
    
    def __init__(
        self,
        wallet: Wallet,
        subtensor: Subtensor,
        metagraph: Metagraph,
        dendrite: Dendrite,
        my_uid: int,
    ):
        """
        Initialize Bittensor objects container.
        
        Args:
            wallet: Bittensor wallet
            subtensor: Bittensor subtensor connection
            metagraph: Bittensor metagraph
            dendrite: Bittensor dendrite
            my_uid: Validator's UID
        """
        self.wallet = wallet
        self.subtensor = subtensor
        self.metagraph = metagraph
        self.dendrite = dendrite
        self.my_uid = my_uid


class BittensorFactory:
    """Factory for creating Bittensor objects."""
    
    @staticmethod
    def create(config: Config) -> BittensorObjects:
        """
        Create and validate all Bittensor objects.
        
        Args:
            config: Bittensor configuration
        
        Returns:
            BittensorObjects container
        
        Raises:
            SystemExit: If validator is not registered on the subnet
        """
        logging.info("Setting up Bittensor objects.")
        
        # Initialize wallet
        wallet = Wallet(config=config)
        logging.info(f"Wallet: {wallet}")
        
        # Initialize subtensor
        subtensor = Subtensor(config=config)
        logging.info(f"Subtensor: {subtensor}")
        
        # Initialize dendrite
        dendrite = Dendrite(wallet=wallet)
        logging.info(f"Dendrite: {dendrite}")
        
        # Initialize metagraph
        metagraph = subtensor.metagraph(config.netuid)
        logging.info(f"Metagraph: {metagraph}")
        
        # Validate registration
        if wallet.hotkey.ss58_address not in metagraph.hotkeys:
            logging.error(
                f"Validator {wallet} is not registered on subnet {config.netuid}. "
                f"Run 'btcli register' and try again."
            )
            raise SystemExit(1)
        
        # Get validator UID
        my_uid = metagraph.hotkeys.index(wallet.hotkey.ss58_address)
        logging.info(f"Running validator on UID: {my_uid}")
        
        logging.info("Bittensor objects initialized successfully.")
        
        return BittensorObjects(
            wallet=wallet,
            subtensor=subtensor,
            metagraph=metagraph,
            dendrite=dendrite,
            my_uid=my_uid,
        )


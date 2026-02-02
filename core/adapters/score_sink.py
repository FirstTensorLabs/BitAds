from typing import Callable, Dict, List, Optional, Tuple

from bittensor.core.settings import DEFAULT_PERIOD
from bittensor.core.subtensor import commit_timelocked_weights_extrinsic, set_weights_extrinsic
from bittensor.core.types import UIDs, Weights
from bittensor.utils.btlogging import logging
import bittensor as bt
from bitads_v3_core.app.ports import IScoreSink
from bitads_v3_core.domain.models import ScoreResult
from bitads_v3_core.domain.creator_burn import apply_creator_burn
from core import version_as_int


class ValidatorScoreSink(IScoreSink):
    """
    Score sink that sets weights on-chain for a given scope.
    It converts ScoreResult list into normalized weights and calls set_weights.
    """

    def __init__(
        self,
        subtensor: bt.Subtensor,
        wallet: bt.Wallet,
        metagraph: bt.Metagraph,
        netuid: int,
        tempo: int,
        mechid_resolver: Callable[[str], int],
        burn_percentage_resolver: Optional[Callable[[str], Optional[float]]] = None,
    ):
        self.subtensor = subtensor
        self.wallet = wallet
        self.metagraph = metagraph
        self.netuid = netuid
        self.tempo = tempo
        self.mechid_resolver = mechid_resolver
        self.burn_percentage_resolver = burn_percentage_resolver  # Callable that takes scope and returns burn percentage (None means no burn, 0.0-100.0 for burn percentage)

    def _get_owner_uid(self) -> Optional[int]:
        """
        Get the subnet owner's UID from the metagraph.
        
        Returns:
            Owner UID if found, None otherwise
        """
        try:
            owner_hotkey = self.subtensor.get_subnet_owner_hotkey(self.netuid)
            index = self.metagraph.hotkeys.index(owner_hotkey)
            if index < len(self.metagraph.uids):
                return self.metagraph.uids[index]
        except (ValueError, AttributeError, IndexError, Exception) as e:
            logging.warning(f"Failed to get owner UID: {e}")
        return None

    def _get_owner_index(self) -> Optional[int]:
        """
        Get the subnet owner's index in metagraph.uids.
        
        Returns:
            Owner index if found, None otherwise
        """
        try:
            owner_hotkey = self.subtensor.get_subnet_owner_hotkey(self.netuid)
            index = self.metagraph.hotkeys.index(owner_hotkey)
            if index < len(self.metagraph.uids):
                return index
        except (ValueError, AttributeError, IndexError, Exception) as e:
            logging.warning(f"Failed to get owner index: {e}")
        return None

    def _set_owner_weight_fallback(self, weights: List[float]) -> None:
        """
        Set the subnet owner's weight to 1.0 as fallback when all scores are zero.
        
        Args:
            weights: List of weights aligned to metagraph.uids (modified in place)
        """
        owner_index = self._get_owner_index()
        if owner_index is not None:
            weights[owner_index] = 1.0

    def set_weights_to_owner_only(self, mechid: int = 0) -> Tuple[bool, str]:
        """
        Set weights to subnet owner only (burn behaviour). Used when there are no
        campaigns or when normal weight setting fails.
        
        Args:
            mechid: Mechanism ID for the weight set (use DEFAULT_MECHID when no campaigns).
        
        Returns:
            (success, message) from the set_weights extrinsic.
        """
        owner_index = self._get_owner_index()
        if owner_index is None:
            logging.warning("Cannot set weights to owner: owner UID not found")
            return False, "Owner UID not found"
        weights = [0.0] * len(self.metagraph.uids)
        weights[owner_index] = 1.0
        logging.info(f"Setting weights to subnet owner only (burn behaviour), mechid={mechid}")
        return self._set_weights(
            wallet=self.wallet,
            netuid=self.netuid,
            uids=self.metagraph.uids,
            weights=weights,
            mechid=mechid,
            wait_for_inclusion=True,
        )

    def publish(self, scores: List[ScoreResult], scope: str, miner_stats_scope: str = None) -> Tuple[bool, str]:
        """
        Publish score results by setting weights on-chain for the given scope.
        Assumes miner_id is a hotkey string; maps hotkeys to UIDs via metagraph.
        Miners not in scores get 0.0 (no work = no score).
        Applies creator burn if burn_percentage is set.
        
        Args:
            scores: List of score results
            scope: Scope identifier for config (e.g., "mech0", "mech1")
            miner_stats_scope: Scope identifier for fetching miner stats (e.g., campaign_id).
                              If not provided, uses scope.
        
        Returns:
            (success, message) from the set_weights extrinsic.
        """
        mechid = self.mechid_resolver(scope)
        logging.info(f"Publishing {len(scores)} scores for scope: {scope} (mechid={mechid})")

        # Empty score list: use burn (set weights to subnet owner only)
        if not scores or all(score.score == 0.0 for score in scores):
            logging.info(f"Empty score results for scope {scope}; using burn (set weights to subnet owner).")
            return self.set_weights_to_owner_only(mechid)

        # Build UID->score map
        # miner_id is a hotkey string, need to find corresponding UID
        scores_by_uid: Dict[int, float] = {}
        for result in scores:
            try:
                # miner_id is a hotkey string, find its UID in metagraph
                if result.miner_id not in self.metagraph.hotkeys:
                    logging.warning(f"Hotkey {result.miner_id} not found in metagraph for scope {scope}")
                    continue
                
                hotkey_index = self.metagraph.hotkeys.index(result.miner_id)
                if hotkey_index < len(self.metagraph.uids):
                    uid = self.metagraph.uids[hotkey_index]
                    scores_by_uid[uid] = result.score
                else:
                    logging.warning(f"Hotkey index {hotkey_index} out of range for UIDs in scope {scope}")
            except (ValueError, AttributeError, IndexError) as e:
                logging.warning(f"Could not map miner_id (hotkey) {result.miner_id} to UID for scope {scope}: {e}")

        # Build initial weights aligned to metagraph.uids
        # Miners not in scores get 0.0 (no work = no score)
        uids = list(self.metagraph.uids)
        miner_scores = [scores_by_uid.get(uid, 0.0) for uid in uids]
        
        # Get burn percentage for this scope (if resolver is provided)
        burn_percentage = None
        if self.burn_percentage_resolver is not None:
            burn_percentage = self.burn_percentage_resolver(scope)
        
        # Calculate weights before burn (normalized)
        total = sum(miner_scores)
        if total > 0:
            weights_before_burn = [s / total for s in miner_scores]
        else:
            weights_before_burn = [0.0] * len(uids)
            self._set_owner_weight_fallback(weights_before_burn)
        
        # Apply creator burn if enabled
        if burn_percentage is not None and burn_percentage > 0.0:
            try:
                # Log weights before burn
                logging.info(f"[yellow]Weights BEFORE burn ({burn_percentage}%) for scope {scope}:[/yellow] {weights_before_burn}")
                
                # Find owner UID externally
                creator_uid = self._get_owner_uid()
                final_uids, final_weights = apply_creator_burn(
                    uids=uids,
                    miner_scores=miner_scores,
                    creator_uid=creator_uid,
                    burn_percentage=burn_percentage,
                )
                
                # Map final_weights back to metagraph.uids alignment
                # (apply_creator_burn may return different UIDs, but we need to align to metagraph.uids)
                weights_dict = dict(zip(final_uids, final_weights))
                weights = [weights_dict.get(uid, 0.0) for uid in self.metagraph.uids]
                
                # If all weights are zero (all scores were zero), apply owner fallback
                if sum(weights) == 0.0:
                    self._set_owner_weight_fallback(weights)
                
                # Log weights after burn
                logging.info(f"[green]Weights AFTER burn ({burn_percentage}%) for scope {scope}:[/green] {weights}")
                logging.info(f"Applied creator burn: {burn_percentage}% for scope {scope}")
            except Exception as e:
                logging.warning(f"Failed to apply creator burn for scope {scope}: {e}, falling back to normal weights")
                # Fall back to normal normalization (use weights_before_burn)
                weights = weights_before_burn
        else:
            # No burn: use weights_before_burn
            weights = weights_before_burn
        
        logging.info(f"[blue]Setting weights for {scope} (mechid={mechid}):[/blue] {weights}")
        success, message = self._set_weights(
            wallet=self.wallet,
            netuid=self.netuid,
            uids=self.metagraph.uids,
            weights=weights,
            mechid=mechid,
            wait_for_inclusion=True,
        )
        logging.info(f"Set weights result for {scope}: success={success}, message={message}")
        return success, message


    def _set_weights(self, 
            wallet: bt.Wallet,
            netuid: int,
            uids: UIDs,
            weights: Weights,
            version_key: int = None,
            wait_for_inclusion: bool = False,
            wait_for_finalization: bool = False,
            max_retries: int = 5,
            block_time: float = 12.0,
            period: Optional[int] = DEFAULT_PERIOD,
            mechid: int = 0,
            commit_reveal_version: int = 4,
    ) -> tuple[bool, str]:
        """
        Set weights on-chain for the given scope.
        """
        # Use project version if version_key not provided
        if version_key is None:
            version_key = version_as_int
        
        retries = 0
        success = False
        message = "No attempt made. Perhaps it is too soon to commit weights!"
        if (
            uid := self.subtensor.get_uid_for_hotkey_on_subnet(wallet.hotkey.ss58_address, netuid)
        ) is None:
            return (
                False,
                f"Hotkey {wallet.hotkey.ss58_address} not registered in subnet {netuid}",
            )

        if self.subtensor.commit_reveal_enabled(netuid=netuid):
            # go with `commit_timelocked_mechanism_weights_extrinsic` extrinsic

            while retries < max_retries and success is False:
                logging.info(
                    f"Committing weights for subnet [blue]{netuid}[/blue]. "
                    f"Attempt [blue]{retries + 1}[blue] of [green]{max_retries}[/green]."
                )
                success, message = commit_timelocked_weights_extrinsic(
                    subtensor=self.subtensor,
                    wallet=wallet,
                    netuid=netuid,
                    mechid=mechid,
                    uids=uids,
                    weights=weights,
                    version_key=version_key,
                    wait_for_inclusion=wait_for_inclusion,
                    wait_for_finalization=wait_for_finalization,
                    block_time=block_time,
                    period=period,
                    commit_reveal_version=commit_reveal_version,
                )
                retries += 1
            return success, message
        else:
            # go with `set_mechanism_weights_extrinsic`

            while retries < max_retries and success is False:
                logging.info(
                    f"Setting weights for subnet [blue]{netuid}[/blue]. "
                    f"Attempt [blue]{retries + 1}[/blue] of [green]{max_retries}[/green]."
                )
                success, message = set_weights_extrinsic(
                    subtensor=self.subtensor,
                    wallet=wallet,
                    netuid=netuid,
                    mechid=mechid,
                    uids=uids,
                    weights=weights,
                    version_key=version_key,
                    wait_for_inclusion=wait_for_inclusion,
                    wait_for_finalization=wait_for_finalization,
                    period=period,
                )
                retries += 1

            return success, message

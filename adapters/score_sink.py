from typing import Callable, Dict, List, Optional

from bittensor.utils.btlogging import logging
import bittensor as bt
from bitads_v3_core.app.ports import IScoreSink
from bitads_v3_core.domain.models import ScoreResult
from bitads_v3_core.domain.creator_burn import apply_creator_burn


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

    def publish(self, scores: List[ScoreResult], scope: str) -> None:
        """
        Publish score results by setting weights on-chain for the given scope.
        Assumes miner_id == UID string; fill missing with zero scores (no work = 0).
        Applies creator burn if burn_percentage is set.
        """
        mechid = self.mechid_resolver(scope)
        logging.info(f"Publishing {len(scores)} scores for scope: {scope} (mechid={mechid})")

        # Build UID->score map
        scores_by_uid: Dict[int, float] = {}
        for result in scores:
            try:
                uid = int(result.miner_id)
                scores_by_uid[uid] = result.score
            except ValueError:
                logging.warning(f"Could not convert miner_id {result.miner_id} to UID for scope {scope}")

        # Build initial weights aligned to metagraph.uids
        # Miners not in scores get 0.0 (no work = no score)
        uids = list(self.metagraph.uids)
        miner_scores = [scores_by_uid.get(uid, 0.0) for uid in uids]
        
        # Get burn percentage for this scope (if resolver is provided)
        burn_percentage = None
        if self.burn_percentage_resolver is not None:
            burn_percentage = self.burn_percentage_resolver(scope)
        
        # Apply creator burn if enabled
        if burn_percentage is not None and burn_percentage > 0.0:
            try:
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
                
                logging.info(f"Applied creator burn: {burn_percentage}% for scope {scope}")
            except Exception as e:
                logging.warning(f"Failed to apply creator burn for scope {scope}: {e}, falling back to normal weights")
                # Fall back to normal normalization
                total = sum(miner_scores)
                if total > 0:
                    weights = [s / total for s in miner_scores]
                else:
                    weights = [0.0] * len(uids)
                    self._set_owner_weight_fallback(weights)
        else:
            # No burn: normalize weights normally
            total = sum(miner_scores)
            if total > 0:
                weights = [s / total for s in miner_scores]
            else:
                # All scores are 0: set all weights to 0 (no normalization possible)
                weights = [0.0] * len(uids)
                self._set_owner_weight_fallback(weights)
        
        logging.info(f"[blue]Setting weights for {scope} (mechid={mechid}): {weights[:5]}...[/blue]")
        result = self.subtensor.set_weights(
            netuid=self.netuid,
            wallet=self.wallet,
            uids=self.metagraph.uids,
            weights=weights,
            wait_for_inclusion=True,
            period=self.tempo,
            mechid=mechid,
        )
        logging.info(f"Set weights result for {scope}: {result}")



from typing import Callable, Dict, List

from bittensor.utils.btlogging import logging
import bittensor as bt
from bitads_v3_core.app.ports import IScoreSink
from bitads_v3_core.domain.models import ScoreResult


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
    ):
        self.subtensor = subtensor
        self.wallet = wallet
        self.metagraph = metagraph
        self.netuid = netuid
        self.tempo = tempo
        self.mechid_resolver = mechid_resolver

    def publish(self, scores: List[ScoreResult], scope: str) -> None:
        """
        Publish score results by setting weights on-chain for the given scope.
        Assumes miner_id == UID string; fill missing with zero scores (no work = 0).
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

        # Build weights aligned to metagraph.uids
        # Miners not in scores get 0.0 (no work = no score)
        
        weights = [scores_by_uid.get(uid, 0.0) for uid in self.metagraph.uids]
        total = sum(weights)
        if total > 0:
            weights = [w / total for w in weights]
        else:
            # All scores are 0: set all weights to 0 (no normalization possible)
            weights = [0.0] * len(weights)
            # set the owner weight to 1.0 as fallback
            owner_hotkey = self.subtensor.get_subnet_owner_hotkey(self.netuid)
            index = self.metagraph.hotkeys.index(owner_hotkey)
            weights[index] = 1.0
        
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



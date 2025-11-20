"""
Test cases for ValidatorScoreSink with creator burn functionality.
"""
import unittest
from unittest.mock import Mock, MagicMock, patch
from typing import List, Optional

from bitads_v3_core.domain.models import ScoreResult
from core.adapters.score_sink import ValidatorScoreSink


TOLERANCE = 1e-9


class TestValidatorScoreSink(unittest.TestCase):
    """Test cases for ValidatorScoreSink with burn functionality."""
    
    def setUp(self):
        """Set up test fixtures with mocked Bittensor objects."""
        # Create mock subtensor
        self.mock_subtensor = Mock()
        self.mock_subtensor.get_subnet_owner_hotkey.return_value = "5CreatorHotkey123456789012345678901234567890123"
        self.mock_subtensor.get_uid_for_hotkey_on_subnet.return_value = 0  # Validator is registered
        self.mock_subtensor.commit_reveal_enabled.return_value = False  # Use simple set_weights
        
        # Create mock wallet
        self.mock_wallet = Mock()
        self.mock_wallet.hotkey.ss58_address = "5ValidatorHotkey123456789012345678901234567890123"
        
        # Create mock metagraph
        self.mock_metagraph = Mock()
        self.mock_metagraph.uids = [0, 1, 2, 3, 99]  # UIDs including creator at index 4 (UID 99)
        self.mock_metagraph.hotkeys = [
            "5ValidatorHotkey123456789012345678901234567890123",  # Index 0
            "5Miner1Hotkey123456789012345678901234567890123",     # Index 1
            "5Miner2Hotkey123456789012345678901234567890123",     # Index 2
            "5Miner3Hotkey123456789012345678901234567890123",     # Index 3
            "5CreatorHotkey123456789012345678901234567890123",    # Index 4 (creator)
        ]
        
        # Creator UID is 99 (at index 4)
        self.creator_uid = 99
        self.creator_index = 4
        
        # Mock mechid resolver
        def mechid_resolver(scope: str) -> int:
            return 0 if scope == "network" else 1
        
        self.mechid_resolver = mechid_resolver
        
        # Create score sink instance
        self.score_sink = ValidatorScoreSink(
            subtensor=self.mock_subtensor,
            wallet=self.mock_wallet,
            metagraph=self.mock_metagraph,
            netuid=1,
            tempo=100,
            mechid_resolver=self.mechid_resolver,
            burn_percentage_resolver=None,  # No burn by default
        )
    
    def test_no_burn_weights_normalized(self):
        """Test that weights are normalized correctly when no burn is applied."""
        scores = [
            ScoreResult(miner_id="5Miner1Hotkey123456789012345678901234567890123", base=0.5, refund_multiplier=1.0, score=0.5),
            ScoreResult(miner_id="5Miner2Hotkey123456789012345678901234567890123", base=0.3, refund_multiplier=1.0, score=0.3),
            ScoreResult(miner_id="5Miner3Hotkey123456789012345678901234567890123", base=0.2, refund_multiplier=1.0, score=0.2),
        ]
        
        # Mock _set_weights to capture the weights
        captured_weights = []
        def mock_set_weights(**kwargs):
            captured_weights.append(kwargs['weights'])
            return (True, "Success")
        
        self.score_sink._set_weights = mock_set_weights
        
        self.score_sink.publish(scores, "network")
        
        # Check that weights were normalized
        self.assertEqual(len(captured_weights), 1)
        weights = captured_weights[0]
        
        # Weights should sum to 1.0
        self.assertAlmostEqual(sum(weights), 1.0, delta=TOLERANCE)
        
        # Check normalized values
        # Miner1 is at index 1, Miner2 at index 2, Miner3 at index 3
        total_score = 0.5 + 0.3 + 0.2
        self.assertAlmostEqual(weights[1], 0.5 / total_score, delta=TOLERANCE)
        self.assertAlmostEqual(weights[2], 0.3 / total_score, delta=TOLERANCE)
        self.assertAlmostEqual(weights[3], 0.2 / total_score, delta=TOLERANCE)
        # UID 0 (validator) and 99 (creator) should have 0.0 (no scores)
        self.assertAlmostEqual(weights[0], 0.0, delta=TOLERANCE)
        self.assertAlmostEqual(weights[4], 0.0, delta=TOLERANCE)
    
    def test_burn_50_percent(self):
        """Test that 50% burn is applied correctly."""
        def burn_resolver(scope: str) -> Optional[float]:
            return 50.0
        
        self.score_sink.burn_percentage_resolver = burn_resolver
        
        scores = [
            ScoreResult(miner_id="5Miner1Hotkey123456789012345678901234567890123", base=0.5, refund_multiplier=1.0, score=0.5),
            ScoreResult(miner_id="5Miner2Hotkey123456789012345678901234567890123", base=0.3, refund_multiplier=1.0, score=0.3),
            ScoreResult(miner_id="5Miner3Hotkey123456789012345678901234567890123", base=0.2, refund_multiplier=1.0, score=0.2),
        ]
        
        captured_weights = []
        def mock_set_weights(**kwargs):
            captured_weights.append(kwargs['weights'])
            return (True, "Success")
        
        self.score_sink._set_weights = mock_set_weights
        
        self.score_sink.publish(scores, "network")
        
        # Check that weights were calculated
        self.assertEqual(len(captured_weights), 1)
        weights = captured_weights[0]
        
        # Weights should sum to 1.0
        self.assertAlmostEqual(sum(weights), 1.0, delta=TOLERANCE)
        
        # Creator (UID 99, index 4) should have 0.5 weight
        self.assertAlmostEqual(weights[self.creator_index], 0.5, delta=TOLERANCE)
        
        # Miners should share the remaining 0.5 proportionally
        # Miner1 is at index 1, Miner2 at index 2, Miner3 at index 3
        total_score = 0.5 + 0.3 + 0.2
        miner_weights_sum = weights[1] + weights[2] + weights[3]
        self.assertAlmostEqual(miner_weights_sum, 0.5, delta=TOLERANCE)
        
        # Check proportional distribution (scaled by 0.5)
        # Miner1 is at index 1, Miner2 at index 2, Miner3 at index 3
        self.assertAlmostEqual(weights[1], (0.5 / total_score) * 0.5, delta=TOLERANCE)
        self.assertAlmostEqual(weights[2], (0.3 / total_score) * 0.5, delta=TOLERANCE)
        self.assertAlmostEqual(weights[3], (0.2 / total_score) * 0.5, delta=TOLERANCE)
        
        # Validator at index 0 should have 0.0
        self.assertAlmostEqual(weights[0], 0.0, delta=TOLERANCE)
    
    def test_burn_30_percent(self):
        """Test that 30% burn is applied correctly."""
        def burn_resolver(scope: str) -> Optional[float]:
            return 30.0
        
        self.score_sink.burn_percentage_resolver = burn_resolver
        
        scores = [
            ScoreResult(miner_id="5Miner1Hotkey123456789012345678901234567890123", base=0.5, refund_multiplier=1.0, score=0.5),
            ScoreResult(miner_id="5Miner2Hotkey123456789012345678901234567890123", base=0.3, refund_multiplier=1.0, score=0.3),
            ScoreResult(miner_id="5Miner3Hotkey123456789012345678901234567890123", base=0.2, refund_multiplier=1.0, score=0.2),
        ]
        
        captured_weights = []
        def mock_set_weights(**kwargs):
            captured_weights.append(kwargs['weights'])
            return (True, "Success")
        
        self.score_sink._set_weights = mock_set_weights
        
        self.score_sink.publish(scores, "network")
        
        weights = captured_weights[0]
        
        # Creator should have 0.3 weight
        self.assertAlmostEqual(weights[self.creator_index], 0.3, delta=TOLERANCE)
        
        # Miners should share 0.7
        # Miner1 is at index 1, Miner2 at index 2, Miner3 at index 3
        miner_weights_sum = weights[1] + weights[2] + weights[3]
        self.assertAlmostEqual(miner_weights_sum, 0.7, delta=TOLERANCE)
        
        # Validator at index 0 should have 0.0
        self.assertAlmostEqual(weights[0], 0.0, delta=TOLERANCE)
    
    def test_burn_100_percent(self):
        """Test that 100% burn sends all weight to creator."""
        def burn_resolver(scope: str) -> Optional[float]:
            return 100.0
        
        self.score_sink.burn_percentage_resolver = burn_resolver
        
        scores = [
            ScoreResult(miner_id="5Miner1Hotkey123456789012345678901234567890123", base=0.5, refund_multiplier=1.0, score=0.5),
            ScoreResult(miner_id="5Miner2Hotkey123456789012345678901234567890123", base=0.3, refund_multiplier=1.0, score=0.3),
            ScoreResult(miner_id="5Miner3Hotkey123456789012345678901234567890123", base=0.2, refund_multiplier=1.0, score=0.2),
        ]
        
        captured_weights = []
        def mock_set_weights(**kwargs):
            captured_weights.append(kwargs['weights'])
            return (True, "Success")
        
        self.score_sink._set_weights = mock_set_weights
        
        self.score_sink.publish(scores, "network")
        
        weights = captured_weights[0]
        
        # Creator should have all weight (1.0)
        self.assertAlmostEqual(weights[self.creator_index], 1.0, delta=TOLERANCE)
        
        # All miners should have 0.0
        # Miner1 is at index 1, Miner2 at index 2, Miner3 at index 3
        self.assertAlmostEqual(weights[1], 0.0, delta=TOLERANCE)
        self.assertAlmostEqual(weights[2], 0.0, delta=TOLERANCE)
        self.assertAlmostEqual(weights[3], 0.0, delta=TOLERANCE)
    
    def test_burn_with_creator_in_scores(self):
        """Test burn when creator UID is already in the scores list."""
        def burn_resolver(scope: str) -> Optional[float]:
            return 30.0
        
        self.score_sink.burn_percentage_resolver = burn_resolver
        
        # Include creator hotkey in scores
        scores = [
            ScoreResult(miner_id="5Miner1Hotkey123456789012345678901234567890123", base=0.5, refund_multiplier=1.0, score=0.5),
            ScoreResult(miner_id="5Miner2Hotkey123456789012345678901234567890123", base=0.3, refund_multiplier=1.0, score=0.3),
            ScoreResult(miner_id="5CreatorHotkey123456789012345678901234567890123", base=0.2, refund_multiplier=1.0, score=0.2),  # Creator
        ]
        
        captured_weights = []
        def mock_set_weights(**kwargs):
            captured_weights.append(kwargs['weights'])
            return (True, "Success")
        
        self.score_sink._set_weights = mock_set_weights
        
        self.score_sink.publish(scores, "network")
        
        weights = captured_weights[0]
        
        # Creator should have burn weight (0.3), not its score-based weight
        self.assertAlmostEqual(weights[self.creator_index], 0.3, delta=TOLERANCE)
        
        # Miners should share 0.7 (creator's score should be excluded from normalization)
        # Miner1 is at index 1, Miner2 at index 2
        total_miner_score = 0.5 + 0.3  # Creator's 0.2 is excluded
        miner_weights_sum = weights[1] + weights[2]
        self.assertAlmostEqual(miner_weights_sum, 0.7, delta=TOLERANCE)
        
        # Verify proportional distribution
        self.assertAlmostEqual(weights[1], (0.5 / total_miner_score) * 0.7, delta=TOLERANCE)
        self.assertAlmostEqual(weights[2], (0.3 / total_miner_score) * 0.7, delta=TOLERANCE)
        
        # Validator at index 0 should have 0.0
        self.assertAlmostEqual(weights[0], 0.0, delta=TOLERANCE)
    
    def test_burn_creator_not_found(self):
        """Test that burn is skipped gracefully when creator is not found."""
        def burn_resolver(scope: str) -> Optional[float]:
            return 50.0
        
        self.score_sink.burn_percentage_resolver = burn_resolver
        
        # Make creator lookup fail
        self.mock_subtensor.get_subnet_owner_hotkey.return_value = "5UnknownHotkey123456789012345678901234567890123"
        
        scores = [
            ScoreResult(miner_id="5Miner1Hotkey123456789012345678901234567890123", base=0.5, refund_multiplier=1.0, score=0.5),
            ScoreResult(miner_id="5Miner2Hotkey123456789012345678901234567890123", base=0.3, refund_multiplier=1.0, score=0.3),
            ScoreResult(miner_id="5Miner3Hotkey123456789012345678901234567890123", base=0.2, refund_multiplier=1.0, score=0.2),
        ]
        
        captured_weights = []
        def mock_set_weights(**kwargs):
            captured_weights.append(kwargs['weights'])
            return (True, "Success")
        
        self.score_sink._set_weights = mock_set_weights
        
        self.score_sink.publish(scores, "network")
        
        weights = captured_weights[0]
        
        # Should fall back to normal normalization (no burn)
        # Miner1 is at index 1, Miner2 at index 2, Miner3 at index 3
        total_score = 0.5 + 0.3 + 0.2
        self.assertAlmostEqual(weights[1], 0.5 / total_score, delta=TOLERANCE)
        self.assertAlmostEqual(weights[2], 0.3 / total_score, delta=TOLERANCE)
        self.assertAlmostEqual(weights[3], 0.2 / total_score, delta=TOLERANCE)
        # Validator at index 0 and creator should have 0.0
        self.assertAlmostEqual(weights[0], 0.0, delta=TOLERANCE)
        self.assertAlmostEqual(weights[self.creator_index], 0.0, delta=TOLERANCE)
    
    def test_burn_zero_scores_fallback(self):
        """Test that owner weight is set to 1.0 when all scores are zero."""
        def burn_resolver(scope: str) -> Optional[float]:
            return 50.0
        
        self.score_sink.burn_percentage_resolver = burn_resolver
        
        # Empty scores (all zeros)
        scores = []
        
        captured_weights = []
        def mock_set_weights(**kwargs):
            captured_weights.append(kwargs['weights'])
            return (True, "Success")
        
        self.score_sink._set_weights = mock_set_weights
        
        self.score_sink.publish(scores, "network")
        
        weights = captured_weights[0]
        
        # Owner should have 1.0 weight as fallback
        self.assertAlmostEqual(weights[self.creator_index], 1.0, delta=TOLERANCE)
        # All other weights should be 0.0
        for i in range(len(weights)):
            if i != self.creator_index:
                self.assertAlmostEqual(weights[i], 0.0, delta=TOLERANCE)
    
    def test_scope_specific_burn(self):
        """Test that different scopes can have different burn percentages."""
        def burn_resolver(scope: str) -> Optional[float]:
            if scope == "network":
                return 10.0
            elif scope == "campaign:123":
                return 20.0
            else:
                return None
        
        self.score_sink.burn_percentage_resolver = burn_resolver
        
        scores = [
            ScoreResult(miner_id="5Miner1Hotkey123456789012345678901234567890123", base=0.5, refund_multiplier=1.0, score=0.5),
            ScoreResult(miner_id="5Miner2Hotkey123456789012345678901234567890123", base=0.3, refund_multiplier=1.0, score=0.3),
            ScoreResult(miner_id="5Miner3Hotkey123456789012345678901234567890123", base=0.2, refund_multiplier=1.0, score=0.2),
        ]
        
        # Test network scope
        weights_network = []
        def mock_set_weights_network(**kwargs):
            weights_network.append(kwargs['weights'])
            return (True, "Success")
        
        self.score_sink._set_weights = mock_set_weights_network
        self.score_sink.publish(scores, "network")
        
        # Test campaign scope
        weights_campaign = []
        def mock_set_weights_campaign(**kwargs):
            weights_campaign.append(kwargs['weights'])
            return (True, "Success")
        
        self.score_sink._set_weights = mock_set_weights_campaign
        self.score_sink.publish(scores, "campaign:123")
        
        # Network should have 10% burn
        self.assertAlmostEqual(weights_network[0][self.creator_index], 0.1, delta=TOLERANCE)
        
        # Campaign should have 20% burn
        self.assertAlmostEqual(weights_campaign[0][self.creator_index], 0.2, delta=TOLERANCE)
    
    def test_burn_percentage_none_disables_burn(self):
        """Test that returning None from resolver disables burn."""
        def burn_resolver(scope: str) -> Optional[float]:
            return None  # Explicitly disable burn
        
        self.score_sink.burn_percentage_resolver = burn_resolver
        
        scores = [
            ScoreResult(miner_id="5Miner1Hotkey123456789012345678901234567890123", base=0.5, refund_multiplier=1.0, score=0.5),
            ScoreResult(miner_id="5Miner2Hotkey123456789012345678901234567890123", base=0.3, refund_multiplier=1.0, score=0.3),
            ScoreResult(miner_id="5Miner3Hotkey123456789012345678901234567890123", base=0.2, refund_multiplier=1.0, score=0.2),
        ]
        
        captured_weights = []
        def mock_set_weights(**kwargs):
            captured_weights.append(kwargs['weights'])
            return (True, "Success")
        
        self.score_sink._set_weights = mock_set_weights
        
        self.score_sink.publish(scores, "network")
        
        weights = captured_weights[0]
        
        # Should be normalized without burn
        # Miner1 is at index 1, Miner2 at index 2, Miner3 at index 3
        total_score = 0.5 + 0.3 + 0.2
        self.assertAlmostEqual(weights[1], 0.5 / total_score, delta=TOLERANCE)
        self.assertAlmostEqual(weights[self.creator_index], 0.0, delta=TOLERANCE)
    
    def test_burn_percentage_zero_disables_burn(self):
        """Test that returning 0.0 from resolver disables burn."""
        def burn_resolver(scope: str) -> Optional[float]:
            return 0.0  # Zero burn
        
        self.score_sink.burn_percentage_resolver = burn_resolver
        
        scores = [
            ScoreResult(miner_id="5Miner1Hotkey123456789012345678901234567890123", base=0.5, refund_multiplier=1.0, score=0.5),
            ScoreResult(miner_id="5Miner2Hotkey123456789012345678901234567890123", base=0.3, refund_multiplier=1.0, score=0.3),
            ScoreResult(miner_id="5Miner3Hotkey123456789012345678901234567890123", base=0.2, refund_multiplier=1.0, score=0.2),
        ]
        
        captured_weights = []
        def mock_set_weights(**kwargs):
            captured_weights.append(kwargs['weights'])
            return (True, "Success")
        
        self.score_sink._set_weights = mock_set_weights
        
        self.score_sink.publish(scores, "network")
        
        weights = captured_weights[0]
        
        # Should be normalized without burn (0.0 is treated as no burn)
        # Miner1 is at index 1, Miner2 at index 2, Miner3 at index 3
        total_score = 0.5 + 0.3 + 0.2
        self.assertAlmostEqual(weights[1], 0.5 / total_score, delta=TOLERANCE)
        self.assertAlmostEqual(weights[self.creator_index], 0.0, delta=TOLERANCE)


if __name__ == "__main__":
    unittest.main()


"""Cross-document claim candidate matching."""
from .candidate_finder import CandidateFinder, ClaimPair
from .matcher import ClaimMatcher

__all__ = ["CandidateFinder", "ClaimPair", "ClaimMatcher"]

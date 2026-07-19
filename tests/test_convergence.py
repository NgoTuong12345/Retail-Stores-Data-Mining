"""Tests for convergence detection."""
import pytest
from dkkd.convergence import converged


class TestConverged:
    def test_three_trailing_zero_added_converges(self):
        history = [
            {'strategy': 'a', 'added': 5},
            {'strategy': 'b', 'added': 0},
            {'strategy': 'c', 'added': 0},
            {'strategy': 'd', 'added': 0},
        ]
        ok, reason = converged(history)
        assert ok is True
        assert '3' in reason

    def test_two_trailing_zero_not_converged(self):
        history = [
            {'strategy': 'a', 'added': 5},
            {'strategy': 'b', 'added': 0},
            {'strategy': 'c', 'added': 0},
        ]
        ok, reason = converged(history)
        assert ok is False

    def test_mixed_trailing_not_converged(self):
        history = [
            {'strategy': 'a', 'added': 0},
            {'strategy': 'b', 'added': 3},
            {'strategy': 'c', 'added': 0},
        ]
        ok, reason = converged(history)
        assert ok is False

    def test_empty_history_not_converged(self):
        ok, reason = converged([])
        assert ok is False

    def test_all_zero_from_start(self):
        history = [
            {'strategy': 'a', 'added': 0},
            {'strategy': 'b', 'added': 0},
            {'strategy': 'c', 'added': 0},
        ]
        ok, reason = converged(history)
        assert ok is True

"""AGENTS.md doc-lint — verify strategy catalog and dead-ends stay in sync."""
import pytest
from pathlib import Path

from dkkd.strategies import REGISTRY

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AGENTS_MD = PROJECT_ROOT / 'AGENTS.md'
FAILED_CASES_MD = PROJECT_ROOT / 'docs' / 'archive' / 'succeeded_failed_cases.md'


class TestAgentsDocLint:
    """Verify AGENTS.md stays in sync with code and documentation."""

    @pytest.fixture
    def agents_text(self):
        assert AGENTS_MD.exists(), 'AGENTS.md not found at project root'
        return AGENTS_MD.read_text(encoding='utf-8')

    def test_every_registered_strategy_in_catalog(self, agents_text):
        """Every name in the strategy REGISTRY must appear in AGENTS.md."""
        missing = []
        for name in REGISTRY:
            if name not in agents_text:
                missing.append(name)
        assert missing == [], (
            f'Strategies registered but missing from AGENTS.md: {missing}'
        )

    def test_every_failed_case_represented(self, agents_text):
        """Every failed-case heading in succeeded_failed_cases.md
        must be represented in AGENTS.md Dead Ends section."""
        if not FAILED_CASES_MD.exists():
            pytest.skip('succeeded_failed_cases.md not found')

        failed_text = FAILED_CASES_MD.read_text(encoding='utf-8')

        # Extract failed case headings (### A. ..., ### B. ..., etc.)
        import re
        headings = re.findall(
            r'^### ([A-F])\. (.+)$',
            failed_text.split('## 🔴 2.')[1] if '## 🔴 2.' in failed_text else '',
            re.MULTILINE,
        )

        # Each failed case should have a corresponding entry in AGENTS.md
        # We check for key phrases from each heading
        key_phrases = {
            'A': 'numeric ID search',
            'B': 'reCAPTCHA',
            'C': 'Pagination',
            'D': 'Field-qualified',
            'E': 'Wildcards',
            'F': 'Special-char',
        }

        missing = []
        for letter, heading in headings:
            phrase = key_phrases.get(letter, heading)
            # Case-insensitive check
            if phrase.lower() not in agents_text.lower():
                missing.append(f'{letter}. {heading} (key phrase: {phrase!r})')

        assert missing == [], (
            f'Failed cases from succeeded_failed_cases.md missing from AGENTS.md: {missing}'
        )

    def test_convergence_rule_documented(self, agents_text):
        """The convergence rule must be explicitly stated."""
        assert '3 consecutive' in agents_text.lower() or '3 consecutive' in agents_text

    def test_api_constraints_documented(self, agents_text):
        """Hard API constraints must be documented."""
        assert '10-row' in agents_text or '10 row' in agents_text
        assert 'reCAPTCHA' in agents_text
        assert 'throttle' in agents_text.lower() or 'rate-limit' in agents_text.lower()

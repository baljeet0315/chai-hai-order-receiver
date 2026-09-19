"""Runs the synthetic messages through the REAL Claude API.

Skipped automatically when ANTHROPIC_API_KEY is not set.
Run only these:   pytest tests/test_parser_live.py -v
Cost: about 75 short API calls per run.
"""

import pytest

from app.config import settings
from tests.parser_cases import CASES

pytestmark = pytest.mark.skipif(
    not settings.anthropic_api_key or settings.anthropic_api_key == "your-key-here",
    reason="ANTHROPIC_API_KEY not set",
)


@pytest.fixture(scope="module")
def parser():
    from app.parser import ClaudeParser
    return ClaudeParser()


@pytest.mark.parametrize("text,pending,intent,expected", CASES, ids=[c[0][:40] for c in CASES])
def test_parser_case(parser, text, pending, intent, expected):
    result = parser.parse(text, pending)
    assert result.intent == intent, f"intent {result.intent!r}, notes: {result.notes}"
    if intent in ("order",):
        got = {i.product_id: i.packs for i in result.items}
        assert got == expected
    elif intent == "follow_up":
        got = {i.product_id: (i.action, i.packs if i.action != "remove" else None) for i in result.items}
        assert got == expected
    else:
        assert result.items == [] or intent == "non_order"

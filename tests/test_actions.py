import re
from pathlib import Path

from app import prompts
from app.actions import Kind


def test_every_action_has_an_instruction_and_none_are_orphaned():
    assert set(Kind) == set(prompts.KIND_INSTRUCTIONS)


def test_the_orchestrator_never_uses_a_raw_string_for_an_action():
    src = (Path(__file__).parent.parent / "app" / "sop.py").read_text()
    assert not re.findall(r'"kind": "', src)
    assert "Kind." in src


def test_lookups_with_plain_strings_still_work():
    assert prompts.KIND_INSTRUCTIONS["review_result"] == prompts.KIND_INSTRUCTIONS[Kind.REVIEW_RESULT]

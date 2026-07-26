"""Description-contract test (DESIGN §6.3): a keyword check that catches
deleted text, not ignored text — honestly scoped."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from grip_mcp import descriptions as D

EXPECTED_TOOLS = {
    "list_projects", "set_project", "update_project_defaults",
    "describe_workspace", "identify", "add_grip", "get_grip", "list_grips",
    "update_grip", "rename_grip", "remove_grip", "set_reading", "transpose",
    "set_sequence", "list_sequences", "remove_sequence", "render",
    "define_tuning", "remove_tuning",
}


def test_all_v1_tools_described():
    assert set(D.TOOL_DESCRIPTIONS) == EXPECTED_TOOLS


def test_descriptions_versioned():
    assert D.DESCRIPTIONS_VERSION


def test_server_instructions_keywords():
    s = D.SERVER_INSTRUCTIONS
    # The §6.3 contract, clause by clause:
    assert "most literal" in s                  # top != "the answer"
    assert "chosen" in s and "LEAD" in s        # lead with the user's name
    assert "decided_at" in s                    # calibration
    assert "tiebreak" in s and "unique" in s
    assert "name->shape" in s.lower() or "name->shape" in s  # the bridge
    assert "VERIFY" in s                        # verified, never asserted
    assert "render=false" in s                  # bulk-capture idiom
    assert "strip" in s
    assert "created or opened" in s             # created-vs-opened confirm
    assert "PARTIAL success" in s               # capture atomicity
    assert "never a re-send" in s


def test_tool_description_keywords():
    d = D.TOOL_DESCRIPTIONS
    assert "REFUSES" in d["set_project"] and "create=true" in d["set_project"]
    assert "close-match" in d["set_project"]
    assert "LOW to HIGH" in d["add_grip"]
    assert "chosen_miss" in d["add_grip"] and "set_reading" in d["add_grip"]
    assert "render=false" in d["add_grip"]
    assert "most literal" in d["identify"] and "decided_at" in d["identify"]
    assert "three tiers" in d["set_reading"]
    assert "FULL" in d["set_reading"]
    assert "opens_fretted" in d["transpose"] and "count" in d["transpose"]
    assert "covariantly" in d["transpose"] and "derived_from" in d["transpose"]
    assert "capo-relative" in d["transpose"] and "capo-relative" in d["define_tuning"]
    assert "XOR" in d["transpose"] and "XOR" in d["render"]  # exactly-one-of
    assert "default_tuning" in d["remove_tuning"]
    assert "stale" in d["describe_workspace"] or "stale" in d["get_grip"]
    assert "ecosystem-wide" in d["list_projects"]

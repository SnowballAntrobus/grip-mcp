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
    "set_instrument_tuning", "retune_plan",  # Phase 2b
    "find_voicings", "render_neck",          # Phase 2a
    "journal", "list_journal", "history",    # feedback round 1
    "analyze",                               # Phase 3
    "set_rhythm", "list_rhythms", "remove_rhythm",     # rhythm (rev 3)
    "export_timeline", "export_midi", "render_audio",  # rhythm (rev 3)
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
    assert "render" in s and "strip" in s       # renders on request
    assert "created or opened" in s             # created-vs-opened confirm
    assert "PARTIAL success" in s               # capture atomicity
    assert "never a re-send" in s


def test_tool_description_keywords():
    d = D.TOOL_DESCRIPTIONS
    assert "REFUSES" in d["set_project"] and "create=true" in d["set_project"]
    assert "close-match" in d["set_project"]
    assert "LOW to HIGH" in d["add_grip"]
    assert "chosen_miss" in d["add_grip"] and "set_reading" in d["add_grip"]
    assert "working title" in d["add_grip"]
    # Gesture idiom: both shapes as grips, adjacency in the sequence.
    assert "BOTH shapes" in d["add_grip"]
    assert "voice-leading" in d["add_grip"]
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
    # Phase 2b: the honestly-scoped heuristic warning (§9) must stay said.
    assert "declarations, not guitars" in d["set_instrument_tuning"]
    assert "heuristics ONLY" in d["retune_plan"]
    assert "aggressive" in d["retune_plan"]
    assert "not a peg turn" in d["retune_plan"]
    # Phase 2a: exact-by-construction search; deterministic ranking.
    assert "exact by construction" in d["find_voicings"]
    assert "never tuned weights" in d["find_voicings"]
    assert "capo-relative" in d["find_voicings"]
    assert "suggestions" in d["find_voicings"]
    # Rhythm (RHYTHM_DESIGN rev 3): the load-bearing clauses stay said.
    assert "PHYSICAL" in d["set_rhythm"]          # indices are physical
    assert "'bass'" in d["set_rhythm"]            # the bass is symbolic
    assert "AT DEFINITION" in d["set_rhythm"]     # stored-expanded
    assert "mandatory" in d["set_rhythm"]         # swing subdivision
    assert "meter_mismatch" in d["set_rhythm"]
    assert "meter_mismatch" in d["set_sequence"]
    assert "its own tempo" in d["set_sequence"]   # child-meter rule
    assert "'whole'" in d["set_sequence"]         # unassigned default
    assert "realized form" in d["export_timeline"]  # hash target
    assert "events_stored" in d["export_timeline"]
    assert "3840" in d["export_midi"]             # fixed PPQ
    assert "truncate at retrigger" in d["export_midi"]
    assert "quarter-note BPM" in d["export_midi"]  # the DAW caveat
    assert "overwritten" in d["render_audio"]     # single-file, no GC
    assert "ONLY" in d["render_audio"]            # stagger scope
    assert "velocity never weights" in d["analyze"]
    # Notation (NOTATION_DESIGN rev 2): relay, never redraw.
    assert "notation" in d["set_rhythm"]
    assert "notation_conflict" in d["set_rhythm"]
    assert "echo-verify" in d["set_rhythm"]
    assert "never draw your own grid" in d["set_rhythm"]
    assert "governing meter" in d["set_sequence"]  # attachment echo
    assert "verbatim" in d["set_sequence"]
    assert "verbatim" in d["list_rhythms"]


def test_server_instructions_notation_keywords():
    s = D.SERVER_INSTRUCTIONS
    assert "VERBATIM" in s
    assert "never draw your own grid" in s
    assert "echo-verify" in s
    assert "don't guess" in s  # the dotless-idiom posture

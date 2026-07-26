"""Input-contract smoke tests for the reference engine (DESIGN §7.1)."""

import pytest

import refengine as R


def test_zero_sounding_strings_error():
    with pytest.raises(R.InputError):
        R.identify([None] * 6)


def test_negative_fret_error():
    with pytest.raises(R.InputError):
        R.identify([-1, None, None, None, None, None])


def test_length_mismatch_error_names_both_lengths():
    with pytest.raises(R.InputError, match="5.*6|6.*5"):
        R.identify([0, 0, 0, 0, 0])


def test_single_pc_multi_string_pitch_report():
    r = R.identify([0, None, None, None, None, 0])  # {E2, E4}
    assert r["candidates"] == []
    assert r["decided_at"] is None
    assert r["pitch_report"]["pitches"] == ["E2", "E4"]
    assert r["pitch_report"]["doubling"] == 2


def test_two_pc_input_generates():
    r = R.identify([3, 1, None, None, None, None])  # Gm-O
    assert r["candidates"][0]["name"] == "Gdym3"
    assert r["mode"] == "context-free"


def test_unknown_tuning_is_instructive():
    with pytest.raises(R.InputError, match="standard"):
        R.identify([0, 0], "nonesuch")


def test_bad_context_key_is_instructive():
    with pytest.raises(R.InputError, match="grammar"):
        R.identify([2, 2, 2, None, None, None], context_key="E minor")


def test_engine_reports_versions():
    r = R.identify([3, 1, None, None, None, None])
    assert r["engine_version"] == R.REF_ENGINE_VERSION
    assert r["table_version"]

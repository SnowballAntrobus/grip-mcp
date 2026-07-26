"""Project storage and lifecycle (DESIGN §3, §5.1, §10).

* `library.json` is the source of truth; `derived.json` is a regenerable
  cache. Reads are always fresh (content hash authoritative); the
  pre-write hash check catches external modification inside a call's
  read-to-write window; absent files are expected-absent, never conflict.
* Writes are atomic (temp + os.replace) with a `.bak`, for derived.json
  too; the first write bootstraps grip/, .gitignore, library.json and
  derived.json in one consistent step.
* Fresh-project reads are empty libraries (decision 53) — no files, no
  error.
* Writes are confined to the project's grip/ namespace,
  resolve-then-verify.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from pathlib import Path

from . import theory

SCHEMA_VERSION = 1
STANDARD_TUNING = ["E2", "A2", "D3", "G3", "B3", "E4"]
RESERVED_SLUGS = {"strip", "adhoc"}
_SLUG_RE = re.compile(r"^[a-z0-9_-]{1,40}$")


class StoreError(ValueError):
    """Structured, instructive storage rejection."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def validate_slug(slug: str, kind: str) -> str:
    if not isinstance(slug, str) or not _SLUG_RE.match(slug):
        raise StoreError(
            "bad_slug",
            f"{kind} {slug!r} must match [a-z0-9_-], 1-40 chars",
        )
    if "__" in slug:
        raise StoreError(
            "bad_slug",
            f"{kind} {slug!r} must not contain consecutive underscores "
            "(reserved as the exports filename separator)",
        )
    if slug in RESERVED_SLUGS:
        raise StoreError(
            "reserved_slug",
            f"{kind} {slug!r} is reserved (render filename prefix)",
        )
    return slug


def project_root() -> Path:
    """Default root: ~/grip_sessions (user feedback, 2026-07-26).
    MUSIC_PROJECT_ROOT still overrides — point it at a shared root
    (e.g. ~/music_projects) to keep the §3 cross-tool bus with cdp-mcp."""
    return Path(
        os.environ.get("MUSIC_PROJECT_ROOT", "~/grip_sessions")
    ).expanduser()


def empty_library() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "default_tuning": "standard",
        "tunings": {"standard": list(STANDARD_TUNING)},
        "grips": {},
        "sequences": {},
        "rhythms": {},
    }


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Library validation (structural; instructive errors)
# ---------------------------------------------------------------------------

def _validate_library(lib: dict) -> None:
    if not isinstance(lib, dict):
        raise StoreError("bad_library", "library.json is not an object")
    if lib.get("schema_version") != SCHEMA_VERSION:
        raise StoreError(
            "bad_schema_version",
            f"library schema_version {lib.get('schema_version')!r}; "
            f"this engine reads {SCHEMA_VERSION}",
        )
    for field, typ in (("tunings", dict), ("grips", dict),
                       ("sequences", dict), ("default_tuning", str)):
        if not isinstance(lib.get(field), typ):
            raise StoreError(
                "bad_library", f"library field {field!r} missing or mistyped"
            )
    for gid, grip in lib["grips"].items():
        if not isinstance(grip, dict) or "strings" not in grip \
                or "tuning" not in grip:
            raise StoreError(
                "bad_grip", f"grip {gid!r} missing strings/tuning"
            )
    for name, seq in lib["sequences"].items():
        if isinstance(seq, list):
            ok = all(isinstance(x, str) for x in seq)
        elif isinstance(seq, dict):
            steps = seq.get("steps")
            ok = isinstance(steps, list) and all(
                isinstance(x, str)
                or (isinstance(x, dict) and isinstance(x.get("item"), str))
                for x in steps
            )
        else:
            ok = False
        if not ok:
            raise StoreError(
                "bad_sequence",
                f"sequence {name!r} is neither a list of grip ids nor an "
                "object with steps (RHYTHM_DESIGN §5)",
            )
    rhythms = lib.get("rhythms")
    if rhythms is not None and not isinstance(rhythms, dict):
        raise StoreError("bad_library", "rhythms must be an object")
    inst = lib.get("instrument")
    if inst is not None:
        if not isinstance(inst, dict) or not isinstance(
            inst.get("declarations"), list
        ) or not all(
            isinstance(d, dict) and "tuning" in d and "since" in d
            for d in inst["declarations"]
        ):
            raise StoreError(
                "bad_instrument",
                "instrument must be {declarations: [{tuning, since}, ...]} "
                "(Phase 2b declaration history)",
            )


# ---------------------------------------------------------------------------
# Tuning resolution (recursive from+capo chains; cycle detection)
# ---------------------------------------------------------------------------

def resolve_tuning(lib: dict, name: str) -> dict:
    """-> {"pitches": [str], "capo": int, "chain": [names]}.

    Capo-derived tunings sound (open + capo); grip frets stay
    capo-relative (absolute pitch = open + capo + fret).
    """
    tunings = lib["tunings"]
    chain, capo = [], 0
    current = name
    while True:
        if current in chain:
            raise StoreError(
                "tuning_cycle",
                f"tuning {name!r} resolves through a cycle: "
                f"{' -> '.join(chain + [current])}",
            )
        chain.append(current)
        if current not in tunings:
            raise StoreError(
                "unknown_tuning",
                f"tuning {current!r} is not defined"
                + (f" (referenced via {name!r})" if current != name else "")
                + f"; known: {sorted(tunings)}",
            )
        entry = tunings[current]
        if isinstance(entry, list):
            base = entry
            break
        if not isinstance(entry, dict) or "from" not in entry:
            raise StoreError(
                "bad_tuning", f"tuning {current!r} is neither pitches nor from+capo"
            )
        capo += int(entry.get("capo", 0))
        current = entry["from"]
    midis = [theory.parse_pitch(p) + capo for p in base]
    pitches = [
        theory.pitch_str(theory.load_table()["_canonical_lof"][m % 12], m)
        for m in midis
    ]
    return {"pitches": pitches, "capo": capo, "chain": chain}


def tuning_flags(lib: dict) -> list[dict]:
    """Dangling/cycle flags for describe_workspace (load never fails)."""
    flags = []
    for name in lib["tunings"]:
        try:
            resolve_tuning(lib, name)
        except StoreError as e:
            flags.append({"code": e.code, "detail": e.detail})
    dt = lib["default_tuning"]
    if dt not in lib["tunings"]:
        flags.append({
            "code": "dangling_default_tuning",
            "detail": f"default_tuning {dt!r} is not a defined tuning; "
                      "fix via update_project_defaults or a hand edit",
        })
    for gid, grip in lib["grips"].items():
        if grip["tuning"] not in lib["tunings"]:
            flags.append({
                "code": "dangling_grip_tuning",
                "detail": f"grip {gid!r} references undefined tuning "
                          f"{grip['tuning']!r}",
            })
    decl = current_declaration(lib)
    if decl and decl["tuning"] not in lib["tunings"]:
        flags.append({
            "code": "dangling_instrument_tuning",
            "detail": f"the declared instrument tuning {decl['tuning']!r} "
                      "is not a defined tuning; re-declare via "
                      "set_instrument_tuning or hand-edit",
        })
    return flags


def current_declaration(lib: dict) -> dict | None:
    """The project's current instrument-tuning declaration (Phase 2b):
    the last entry of the declaration history, or None. The server tracks
    declarations, not guitars (open question 5's deliberate wrinkle)."""
    decls = (lib.get("instrument") or {}).get("declarations") or []
    return decls[-1] if decls else None


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class Store:
    """One project's grip/ namespace. Load-fresh, hash-guarded writes."""

    def __init__(self, root: Path, project: str):
        validate_slug(project, "project name")
        self.project = project
        self.dir = (root / project).resolve()
        if root.resolve() not in self.dir.parents:
            raise StoreError("bad_path", "project path escapes the root")
        self.grip_dir = self.dir / "grip"
        self.library_path = self.grip_dir / "library.json"
        self.derived_path = self.grip_dir / "derived.json"
        self.renders_dir = self.grip_dir / "renders"
        self.exports_dir = self.dir / "exports"  # the cross-tool bus (§3)
        self.journal_path = self.grip_dir / "journal.jsonl"
        self.history_path = self.grip_dir / "history.jsonl"
        self._lib_hash: str | None = None  # hash at last load; None = absent

    # -- reads --------------------------------------------------------------

    def load(self) -> dict:
        """Fresh read. Absent files = empty library (decision 53)."""
        if not self.library_path.exists():
            self._lib_hash = None
            lib = empty_library()
        else:
            data = self.library_path.read_bytes()
            self._lib_hash = _sha(data)
            try:
                lib = json.loads(data)
            except json.JSONDecodeError as e:
                raise StoreError(
                    "bad_json", f"library.json is not valid JSON: {e}"
                ) from None
            _validate_library(lib)
            # The built-in standard is immutable: always the built-in.
            lib["tunings"]["standard"] = list(STANDARD_TUNING)
        return lib

    def load_derived(self) -> dict:
        if not self.derived_path.exists():
            return {
                "schema_version": SCHEMA_VERSION,
                "engine_version": theory.ENGINE_VERSION,
                "grips": {},
            }
        try:
            d = json.loads(self.derived_path.read_bytes())
        except json.JSONDecodeError:
            d = None  # regenerable cache: corrupt = absent
        if not isinstance(d, dict) or d.get("engine_version") != theory.ENGINE_VERSION:
            return {
                "schema_version": SCHEMA_VERSION,
                "engine_version": theory.ENGINE_VERSION,
                "grips": {},
            }
        return d

    # -- writes -------------------------------------------------------------

    def _atomic_write(self, path: Path, payload: dict) -> None:
        data = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(data, encoding="utf-8")
        if path.exists():
            shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
        os.replace(tmp, path)

    def save(self, lib: dict, derived: dict | None = None,
             op: dict | None = None) -> None:
        """Hash-guarded, atomic; first write bootstraps the namespace.
        `op` ({"tool": ..., "detail": ...}) appends to the mutation
        history log — the project's own progress record."""
        _validate_library(lib)
        # Pre-write integrity: absent-file is expected-absent, not conflict.
        if self.library_path.exists():
            current = _sha(self.library_path.read_bytes())
            if self._lib_hash is None or current != self._lib_hash:
                raise StoreError(
                    "external_modification",
                    "library.json changed on disk since this call read it; "
                    "re-read and retry (nothing was written)",
                )
        elif self._lib_hash is not None:
            raise StoreError(
                "external_modification",
                "library.json disappeared since this call read it; "
                "re-read and retry (nothing was written)",
            )
        first_write = not self.library_path.exists()
        self.grip_dir.mkdir(parents=True, exist_ok=True)
        if first_write:
            gi = self.grip_dir / ".gitignore"
            if not gi.exists():
                gi.write_text("derived.json\n", encoding="utf-8")
        self._atomic_write(self.library_path, lib)
        self._atomic_write(
            self.derived_path,
            derived if derived is not None else self.load_derived(),
        )
        self._lib_hash = _sha(self.library_path.read_bytes())
        if op is not None:
            self.append_jsonl(self.history_path, dict(op))

    # -- append-only logs (journal + mutation history) ----------------------

    def append_jsonl(self, path: Path, entry: dict) -> dict:
        """Append one record (atomic rewrite; these logs are small and
        append-only — last-writer-wins is acceptable here, unlike the
        library)."""
        import datetime as _dt
        entry = {
            "ts": _dt.datetime.now(_dt.timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ"),
            **entry,
        }
        self.grip_dir.mkdir(parents=True, exist_ok=True)
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(existing + line, encoding="utf-8")
        os.replace(tmp, path)
        return entry

    def read_jsonl(self, path: Path, limit: int | None = None,
                   newest_first: bool = True) -> list[dict]:
        if not path.exists():
            return []
        out = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # a corrupt line never blocks the rest
        if newest_first:
            out.reverse()
        return out[:limit] if limit else out

    # -- derived cache ------------------------------------------------------

    @staticmethod
    def input_hash(strings, pitches) -> str:
        blob = json.dumps([strings, pitches, theory.ENGINE_VERSION])
        return _sha(blob.encode())[:16]

    def derive_grip(self, lib: dict, derived: dict, gid: str) -> dict:
        """Ensure derived.json entry for gid is current; returns the entry
        {input_hash, midi, candidates, decided_at} (full context-free set,
        §7.5). Mutates `derived` in place; caller persists via save()."""
        grip = lib["grips"][gid]
        res = resolve_tuning(lib, grip["tuning"])
        h = self.input_hash(grip["strings"], res["pitches"])
        entry = derived["grips"].get(gid)
        if entry and entry.get("input_hash") == h:
            return entry
        r = theory.identify(grip["strings"], res["pitches"])
        entry = {
            "input_hash": h,
            "midi": r["midi"],
            "candidates": r["candidates"],
            "decided_at": r["decided_at"],
            "pitch_report": r.get("pitch_report"),
        }
        derived["grips"][gid] = entry
        return entry


# ---------------------------------------------------------------------------
# Ecosystem-level project scan (DESIGN §6.2)
# ---------------------------------------------------------------------------

def list_projects(root: Path) -> dict:
    """Scan MUSIC_PROJECT_ROOT ecosystem-wide; malformed entries are
    skipped with a warning, never a crash."""
    projects, warnings = [], []
    if not root.exists():
        return {"projects": [], "warnings": []}
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        entry = {"name": child.name, "grips": 0,
                 "namespaces": sorted(
                     p.name for p in child.iterdir() if p.is_dir()
                 )}
        libp = child / "grip" / "library.json"
        if libp.exists():
            try:
                lib = json.loads(libp.read_bytes())
                _validate_library(lib)
                entry["grips"] = len(lib["grips"])
                entry["sequences"] = len(lib["sequences"])
            except (StoreError, json.JSONDecodeError, OSError) as e:
                warnings.append({
                    "code": "malformed_project",
                    "detail": f"{child.name}: {e}",
                })
                continue
        projects.append(entry)
    return {"projects": projects, "warnings": warnings}


def close_matches(name: str, existing: list[str], n: int = 3) -> list[str]:
    import difflib
    return difflib.get_close_matches(name, existing, n=n, cutoff=0.5)


# ---------------------------------------------------------------------------
# Sequence structure (song sections; nesting via "@name" items)
# ---------------------------------------------------------------------------

def flatten_sequence(lib: dict, name: str, _stack: tuple = ()) -> list[str]:
    """Resolve a sequence to its grip ids, expanding "@other" references
    recursively with cycle detection. Song structures compose without
    duplication: edit the section once, every containing structure sees
    it."""
    if name in _stack:
        raise StoreError(
            "sequence_cycle",
            f"sequence {name!r} contains itself: "
            f"{' -> '.join(_stack + (name,))}",
        )
    if name not in lib["sequences"]:
        raise StoreError(
            "unknown_sequence",
            f"sequence {name!r} not found; known: "
            f"{sorted(lib['sequences'])}",
        )
    from . import rhythm as RH
    out: list[str] = []
    for step in RH.seq_steps(lib["sequences"][name]):
        item = RH.step_item(step)
        if item.startswith("@"):
            out.extend(flatten_sequence(lib, item[1:], _stack + (name,)))
        else:
            out.append(item)
    return out


def sequence_references(lib: dict, name: str) -> list[str]:
    """Sequences whose items reference @name directly."""
    from . import rhythm as RH
    ref = "@" + name
    return [
        s for s, seq in lib["sequences"].items()
        if any(RH.step_item(x) == ref for x in RH.seq_steps(seq))
    ]


def rhythm_flags(lib: dict) -> list[dict]:
    """Dangling-rhythm / meter-mismatch flags for describe_workspace —
    hand edits get the dangling treatment: load flagged, touching tools
    error instructively (RHYTHM_DESIGN §5)."""
    from . import rhythm as RH
    flags = []
    rhythms = lib.get("rhythms") or {}
    for name, pat in rhythms.items():
        try:
            RH.validate_pattern(pat)
        except RH.RhythmError as e:
            flags.append({"code": "bad_rhythm",
                          "detail": f"rhythm {name!r}: {e.detail}"})
    for sname, seq in lib["sequences"].items():
        if not isinstance(seq, dict):
            continue
        meter = seq.get("meter")
        for rname in RH.assigned_rhythms(seq):
            if rname in RH.BUILTINS:
                continue
            pat = rhythms.get(rname)
            if pat is None:
                flags.append({
                    "code": "dangling_rhythm",
                    "detail": f"sequence {sname!r} assigns rhythm "
                              f"{rname!r} which is not defined; define it "
                              "via set_rhythm or fix the hand edit",
                })
            elif (meter is not None
                    and isinstance(pat, dict)
                    and pat.get("meter") != list(meter)):
                flags.append({
                    "code": "meter_mismatch",
                    "detail": f"sequence {sname!r} ({meter}) assigns "
                              f"rhythm {rname!r} ({pat.get('meter')}); "
                              "no silent reinterpretation",
                })
    return flags

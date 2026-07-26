"""The V1 tool surface, transport-independent (DESIGN §6).

Every method returns an envelope dict — never raises for user-level
problems: `{"project": ...}` always; mutating responses add
`stored: true|false` and `warnings: [{code, detail}]` (codes:
chosen_miss, render_failed, chosen_staled, opens_fretted); failures are
`{"error": {code, detail}, ...}` with instructive detail — the primary
caller is an LLM that self-corrects given a good message. The MCP layer
(server.py) is thin wiring over this class.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

from . import render as RD
from . import rhythm as RH
from . import store as ST
from . import theory as TH

TOP_N = 8
INLINE_THRESHOLD = 64  # describe_workspace inline cap (open question 4)

_INTERVAL_LABEL = ["R", "b2", "2", "b3", "3", "4", "b5", "5", "b6", "6",
                   "b7", "7"]


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class GripService:
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else ST.project_root()
        self.project: str | None = None

    # -- envelope helpers ---------------------------------------------------

    def _env(self, payload: dict, stored: bool | None = None,
             warnings: list | None = None) -> dict:
        out = {"project": self.project}
        out.update(payload)
        if stored is not None:
            out["stored"] = stored
        if warnings is not None:
            out["warnings"] = warnings
        return out

    def _err(self, code: str, detail: str, mutating: bool = False) -> dict:
        out = {"project": self.project, "error": {"code": code,
                                                  "detail": detail}}
        if mutating:
            out["stored"] = False
        return out

    def _store(self) -> ST.Store:
        if self.project is None:
            raise ST.StoreError(
                "no_project", "no active project; call set_project first"
            )
        return ST.Store(self.root, self.project)

    def _shape(self, result_candidates: list, top_n: int = TOP_N) -> dict:
        return {
            "candidates": result_candidates[:top_n],
            "truncated": max(0, len(result_candidates) - top_n),
        }

    # ------------------------------------------------------------------ §6.2

    def list_projects(self) -> dict:
        scan = ST.list_projects(self.root)
        return self._env(scan)

    def set_project(self, name: str, create: bool = False) -> dict:
        try:
            ST.validate_slug(name, "project name")
        except ST.StoreError as e:
            return self._err(e.code, e.detail)
        existing = [
            p.name for p in self.root.iterdir() if p.is_dir()
        ] if self.root.exists() else []
        if name in existing:
            self.project = name
            return self._env({"opened": True, "created": False})
        if not create:
            matches = ST.close_matches(name, existing)
            return self._err(
                "unknown_project",
                f"project {name!r} does not exist and create is false. "
                + (f"Close matches: {matches}. " if matches else "")
                + "Pass create=true only after the user confirms a NEW "
                  "project is intended.",
            )
        self.project = name  # directories defer to first write
        return self._env({"opened": False, "created": True})

    def update_project_defaults(self, default_tuning: str) -> dict:
        try:
            st = self._store()
            lib = st.load()
            ST.resolve_tuning(lib, default_tuning)  # must exist and resolve
            lib["default_tuning"] = default_tuning
            st.save(lib, op={"tool": "update_project_defaults",
                             "detail": {"default_tuning": default_tuning}})
        except ST.StoreError as e:
            return self._err(e.code, e.detail, mutating=True)
        return self._env({"default_tuning": default_tuning}, stored=True,
                         warnings=[])

    def describe_workspace(self) -> dict:
        try:
            st = self._store()
            lib = st.load()
        except ST.StoreError as e:
            return self._err(e.code, e.detail)
        flags = ST.tuning_flags(lib) + ST.rhythm_flags(lib)
        n = len(lib["grips"])
        base = {
            "default_tuning": lib["default_tuning"],
            "instrument": ST.current_declaration(lib),
            "tunings": lib["tunings"],
            "flags": flags,
            "counts": {"grips": n, "sequences": len(lib["sequences"]),
                       "rhythms": len(lib.get("rhythms") or {})},
            # Recent observations resume with the workspace (feedback:
            # a journal like cdp-mcp's).
            "journal_recent": st.read_jsonl(st.journal_path, limit=3),
        }
        if n > INLINE_THRESHOLD:
            base["note"] = (
                f"{n} grips exceeds the inline threshold "
                f"({INLINE_THRESHOLD}); call list_grips"
            )
            return self._env(base)
        derived = st.load_derived()
        grips = {}
        dirty = False
        for gid, grip in lib["grips"].items():
            entry = {
                "label": grip.get("label"),
                "tags": grip.get("tags", []),
                "chosen": grip.get("chosen"),
                # A label with no chosen is a WORKING title — the name is
                # still being negotiated (feedback: formalized).
                "named": grip.get("chosen") is not None,
            }
            if grip.get("chosen"):
                try:
                    before = derived["grips"].get(gid)
                    d = st.derive_grip(lib, derived, gid)
                    dirty = dirty or (d is not before)
                    names = {c["name"] for c in d["candidates"]}
                    entry["stale"] = grip["chosen"] not in names
                except ST.StoreError:
                    entry["stale"] = None  # dangling tuning; flagged above
            grips[gid] = entry
        if dirty:
            try:
                st.save(lib, derived)
            except ST.StoreError:
                pass  # cache refresh is best-effort on a read path
        base["grips"] = grips
        base["sequences"] = lib["sequences"]
        return self._env(base)

    # ------------------------------------------------------------------ §6.1

    def _resolve_tuning_arg(self, lib: dict, tuning: str | None) -> tuple:
        name = tuning if tuning is not None else lib["default_tuning"]
        res = ST.resolve_tuning(lib, name)
        return name, res

    def identify(self, strings: list, tuning: str | None = None,
                 context_key: str | None = None, render: bool = False,
                 labels: str = "notes", interval_root: str = "auto",
                 theme: str = "light", orientation: str = "chart") -> dict:
        try:
            st = self._store()
            lib = st.load()
            tname, res = self._resolve_tuning_arg(lib, tuning)
            r = TH.identify(strings, res["pitches"], context_key)
        except (ST.StoreError, TH.TheoryError) as e:
            code = getattr(e, "code", "bad_input")
            return self._err(code, str(e))
        payload = {
            "tuning": tname,
            "resolved_pitches": res["pitches"],
            "capo": res["capo"],
            "mode": r["mode"],
            "midi": r["midi"],
            "decided_at": r["decided_at"],
        }
        if r["candidates"]:
            payload.update(self._shape(r["candidates"]))
            payload["top"] = r["candidates"][0]["name"]
        else:
            payload["pitch_report"] = r["pitch_report"]
            payload["candidates"] = []
            payload["truncated"] = 0
        warnings = []
        if render and r["candidates"]:
            rr = self._do_render_grips(
                st,
                [self._renderable(strings, res, r["candidates"], None,
                                  labels, interval_root, None)],
                {"labels": labels, "theme": theme,
                 "orientation": orientation},
                prefix="adhoc",
            )
            if "error" in rr:
                warnings.append({"code": "render_failed",
                                 "detail": rr["error"]["detail"]})
            else:
                payload["render"] = rr
        return self._env(payload, warnings=warnings or None)

    def _validate_fingers(self, strings, fingers):
        if fingers is None:
            return
        if len(fingers) != len(strings):
            raise TH.TheoryError(
                f"fingers length {len(fingers)} does not match strings "
                f"length {len(strings)}"
            )
        for f, d in zip(strings, fingers):
            if d is None:
                continue
            if not isinstance(d, int) or not 0 <= d <= 4:
                raise TH.TheoryError(
                    f"bad finger {d!r} (null, 0=thumb, 1-4=index..pinky)"
                )
            if f is None or f == 0:
                raise TH.TheoryError(
                    "fingers must be null on muted/open strings (§5.1)"
                )

    def add_grip(self, id: str, strings: list, tuning: str | None = None,
                 fingers: list | None = None, label: str | None = None,
                 tags: list | None = None, chosen: str | None = None,
                 render: bool = False) -> dict:
        warnings: list[dict] = []
        try:
            st = self._store()
            lib = st.load()
            ST.validate_slug(id, "grip id")
            if id in lib["grips"]:
                raise ST.StoreError(
                    "grip_exists",
                    f"grip {id!r} already exists; use update_grip to edit "
                    "or rename_grip/remove_grip first",
                )
            tname, res = self._resolve_tuning_arg(lib, tuning)
            self._validate_fingers(strings, fingers)
            r = TH.identify(strings, res["pitches"])  # validates lengths
        except (ST.StoreError, TH.TheoryError) as e:
            return self._err(getattr(e, "code", "bad_input"), str(e),
                             mutating=True)
        grip = {
            "strings": list(strings),
            "tuning": tname,  # always concrete (decision 52)
            "created": _now(),
        }
        if fingers is not None:
            grip["fingers"] = list(fingers)
        if label is not None:
            grip["label"] = label
        if tags:
            grip["tags"] = list(tags)
        chosen_result = None
        if chosen is not None:
            chosen_result = TH.resolve_chosen(chosen, r["candidates"])
            if chosen_result["status"] == "resolved":
                grip["chosen"] = chosen_result["name"]
            else:
                warnings.append({
                    "code": "chosen_miss",
                    "detail": {
                        "input": chosen,
                        "status": chosen_result["status"],
                        "suggestions": chosen_result.get(
                            "suggestions", chosen_result.get("matches", [])
                        ),
                        "repair": "follow up with set_reading, never re-send",
                    },
                })
        lib["grips"][id] = grip
        derived = st.load_derived()
        try:
            st.derive_grip(lib, derived, id)
            st.save(lib, derived,
                    op={"tool": "add_grip",
                        "detail": {"id": id, "chosen": grip.get("chosen"),
                                   "tuning": tname}})
        except ST.StoreError as e:
            return self._err(e.code, e.detail, mutating=True)
        payload = {
            "id": id,
            "tuning": tname,
            "resolved_pitches": res["pitches"],  # low->high echo (§6.1)
            "capo": res["capo"],
            "midi": r["midi"],
            "top": r["candidates"][0]["name"] if r["candidates"] else None,
            "chosen": grip.get("chosen"),
            "decided_at": r["decided_at"],
        }
        if r["candidates"]:
            payload.update(self._shape(r["candidates"]))
        if render:
            rr = self.render(ids=[id], labels="notes")
            if "error" in rr:
                warnings.append({"code": "render_failed",
                                 "detail": rr["error"]["detail"]})
            elif rr.get("warnings"):
                warnings.extend(rr["warnings"])
            else:
                payload["render"] = {k: rr[k] for k in
                                     ("files", "render_hash") if k in rr}
        return self._env(payload, stored=True, warnings=warnings)

    def get_grip(self, id: str) -> dict:
        try:
            st = self._store()
            lib = st.load()
            if id not in lib["grips"]:
                return self._err_unknown_grip(id, lib)
            grip = lib["grips"][id]
            res = ST.resolve_tuning(lib, grip["tuning"])
            derived = st.load_derived()
            d = st.derive_grip(lib, derived, id)
            st.save(lib, derived)
        except ST.StoreError as e:
            return self._err(e.code, e.detail)
        names = {c["name"] for c in d["candidates"]}
        payload = {
            "id": id, "grip": grip,
            "resolved_pitches": res["pitches"], "capo": res["capo"],
            "midi": d["midi"], "decided_at": d["decided_at"],
            "chosen": grip.get("chosen"),
            "chosen_stale": (
                grip.get("chosen") is not None
                and grip["chosen"] not in names
            ),
        }
        payload.update(self._shape(d["candidates"]))
        return self._env(payload)

    def _err_unknown_grip(self, id: str, lib: dict, mutating=False) -> dict:
        matches = ST.close_matches(id, list(lib["grips"]))
        return self._err(
            "unknown_grip",
            f"grip {id!r} not found"
            + (f"; close matches: {matches}" if matches else "")
            + f"; {len(lib['grips'])} grips in project",
            mutating=mutating,
        )

    def list_grips(self) -> dict:
        try:
            st = self._store()
            lib = st.load()
        except ST.StoreError as e:
            return self._err(e.code, e.detail)
        return self._env({
            "grips": {
                gid: {"label": g.get("label"), "chosen": g.get("chosen"),
                      "named": g.get("chosen") is not None,
                      "tags": g.get("tags", []), "tuning": g["tuning"]}
                for gid, g in lib["grips"].items()
            }
        })

    def update_grip(self, id: str, patch: dict) -> dict:
        warnings: list[dict] = []
        try:
            st = self._store()
            lib = st.load()
            if id not in lib["grips"]:
                return self._err_unknown_grip(id, lib, mutating=True)
            if not isinstance(patch, dict):
                raise ST.StoreError("bad_patch", "patch must be an object")
            for banned in ("id", "created"):
                if banned in patch:
                    raise ST.StoreError(
                        "immutable_field",
                        f"{banned!r} cannot be patched (use rename_grip for "
                        "ids)",
                    )
            old = lib["grips"][id]
            old_chosen = old.get("chosen")
            merged = dict(old)
            for k, v in patch.items():
                if v is None:
                    if k in ("strings", "tuning"):
                        raise ST.StoreError(
                            "required_field",
                            f"{k!r} is required and cannot be deleted",
                        )
                    merged.pop(k, None)
                else:
                    merged[k] = v
            # Re-validate as a complete grip (§5.1).
            res = ST.resolve_tuning(lib, merged["tuning"])
            self._validate_fingers(merged["strings"],
                                   merged.get("fingers"))
            r = TH.identify(merged["strings"], res["pitches"])
            if "chosen" in patch and patch["chosen"] is not None:
                cr = TH.resolve_chosen(patch["chosen"], r["candidates"])
                if cr["status"] == "resolved":
                    merged["chosen"] = cr["name"]
                else:
                    merged.pop("chosen", None)
                    warnings.append({"code": "chosen_miss", "detail": {
                        "input": patch["chosen"], "status": cr["status"],
                        "suggestions": cr.get("suggestions",
                                              cr.get("matches", [])),
                    }})
            lib["grips"][id] = merged
            derived = st.load_derived()
            d = st.derive_grip(lib, derived, id)
            names = {c["name"] for c in d["candidates"]}
            kept = merged.get("chosen")
            if kept and kept == old_chosen and kept not in names:
                warnings.append({
                    "code": "chosen_staled",
                    "detail": {
                        "chosen": kept,
                        "new_top": d["candidates"][0]["name"]
                        if d["candidates"] else None,
                    },
                })
            st.save(lib, derived,
                    op={"tool": "update_grip",
                        "detail": {"id": id,
                                   "fields": sorted(patch)}})
        except (ST.StoreError, TH.TheoryError) as e:
            return self._err(getattr(e, "code", "bad_input"), str(e),
                             mutating=True)
        return self._env({"id": id, "grip": merged}, stored=True,
                         warnings=warnings)

    def rename_grip(self, id: str, new_id: str) -> dict:
        try:
            st = self._store()
            lib = st.load()
            ST.validate_slug(new_id, "grip id")
            if id not in lib["grips"]:
                return self._err_unknown_grip(id, lib, mutating=True)
            if new_id in lib["grips"]:
                raise ST.StoreError("grip_exists",
                                    f"grip {new_id!r} already exists")
            lib["grips"] = {
                (new_id if k == id else k): v
                for k, v in lib["grips"].items()
            }
            rewritten = 0
            for name, seq in lib["sequences"].items():
                new_steps = []
                for s in RH.seq_steps(seq):
                    if RH.step_item(s) == id:
                        rewritten += 1
                        new_steps.append(
                            new_id if isinstance(s, str)
                            else {**s, "item": new_id})
                    else:
                        new_steps.append(s)
                if isinstance(seq, dict):
                    seq["steps"] = new_steps
                else:
                    lib["sequences"][name] = new_steps
            derived = st.load_derived()
            if id in derived["grips"]:
                derived["grips"][new_id] = derived["grips"].pop(id)
            st.save(lib, derived,
                    op={"tool": "rename_grip",
                        "detail": {"was": id, "id": new_id}})
        except ST.StoreError as e:
            return self._err(e.code, e.detail, mutating=True)
        return self._env({"id": new_id, "was": id,
                          "sequence_occurrences_rewritten": rewritten},
                         stored=True, warnings=[])

    def remove_grip(self, id: str, force: bool = False) -> dict:
        try:
            st = self._store()
            lib = st.load()
            if id not in lib["grips"]:
                return self._err_unknown_grip(id, lib, mutating=True)
            refs = {}
            for name, seq in lib["sequences"].items():
                c = sum(1 for s in RH.seq_steps(seq)
                        if RH.step_item(s) == id)
                if c:
                    refs[name] = c
            if refs and not force:
                return self._err(
                    "grip_referenced",
                    f"grip {id!r} is referenced by sequences {refs} "
                    "(every occurrence counts); pass force=true to remove "
                    "it and its occurrences",
                    mutating=True,
                )
            for name in refs:
                seq = lib["sequences"][name]
                kept = [s for s in RH.seq_steps(seq)
                        if RH.step_item(s) != id]
                if isinstance(seq, dict):
                    seq["steps"] = kept
                else:
                    lib["sequences"][name] = kept
            del lib["grips"][id]
            derived = st.load_derived()
            derived["grips"].pop(id, None)
            st.save(lib, derived,
                    op={"tool": "remove_grip", "detail": {"id": id}})
        except ST.StoreError as e:
            return self._err(e.code, e.detail, mutating=True)
        return self._env({"id": id, "removed_occurrences": refs},
                         stored=True, warnings=[])

    def set_reading(self, id: str, chosen: str) -> dict:
        try:
            st = self._store()
            lib = st.load()
            if id not in lib["grips"]:
                return self._err_unknown_grip(id, lib, mutating=True)
            derived = st.load_derived()
            d = st.derive_grip(lib, derived, id)  # FULL cached set (§7.5)
        except ST.StoreError as e:
            return self._err(e.code, e.detail, mutating=True)
        result = TH.resolve_chosen(chosen, d["candidates"])
        if result["status"] == "ambiguous":
            return self._err(
                "chosen_ambiguous",
                f"{chosen!r} matches multiple candidates: "
                f"{result['matches']}; ask the user, don't guess",
                mutating=True,
            )
        if result["status"] == "miss":
            return self._err(
                "chosen_miss",
                f"{chosen!r} matches no candidate; suggestions: "
                f"{result['suggestions']}",
                mutating=True,
            )
        lib["grips"][id]["chosen"] = result["name"]
        try:
            st.save(lib, derived,
                    op={"tool": "set_reading",
                        "detail": {"id": id, "chosen": result["name"]}})
        except ST.StoreError as e:
            return self._err(e.code, e.detail, mutating=True)
        return self._env(
            {"id": id, "chosen": result["name"], "tier": result["tier"]},
            stored=True, warnings=[],
        )

    def transpose(self, semitones: int, id: str | None = None,
                  strings: list | None = None, tuning: str | None = None,
                  save_as: str | None = None, render: bool = False) -> dict:
        if (id is None) == (strings is None):
            return self._err(
                "exactly_one_of",
                "pass exactly one of id (a stored grip) or strings (a raw "
                "shape); tuning applies only with strings",
                mutating=save_as is not None,
            )
        warnings: list[dict] = []
        try:
            st = self._store()
            lib = st.load()
            if id is not None:
                if id not in lib["grips"]:
                    return self._err_unknown_grip(id, lib,
                                                  mutating=save_as is not None)
                src = lib["grips"][id]
                base_strings = src["strings"]
                fingers = src.get("fingers")
                tname = src["tuning"]
                old_chosen = src.get("chosen")
            else:
                base_strings = strings
                fingers = None
                tname = tuning if tuning is not None else lib["default_tuning"]
                old_chosen = None
            res = ST.resolve_tuning(lib, tname)
            new_strings = []
            for f in base_strings:
                if f is None:
                    new_strings.append(None)
                    continue
                nf = f + semitones
                if nf < 0:
                    detail = (
                        f"transposing by {semitones} takes fret {f} below "
                        + ("the capo" if res["capo"] else "the nut")
                        + f" (to {nf}, capo-relative)"
                        if res["capo"]
                        else f"transposing by {semitones} takes fret {f} "
                             f"below fret 0 (to {nf})"
                    )
                    raise ST.StoreError("below_fret_0", detail)
                new_strings.append(nf)
            new_fingers = None
            opens_fretted = 0
            if fingers is not None:
                new_fingers = []
                for old_f, new_f, d in zip(base_strings, new_strings,
                                           fingers):
                    if old_f == 0 and new_f and new_f > 0:
                        opens_fretted += 1
                        new_fingers.append(None)
                    elif new_f == 0:
                        new_fingers.append(None)  # now open: no finger
                    else:
                        new_fingers.append(d)
            if opens_fretted:
                warnings.append({
                    "code": "opens_fretted",
                    "detail": {"count": opens_fretted,
                               "note": "correct pitches, changed hand "
                                       "shape — not 'the same grip moved "
                                       "up'"},
                })
            r_new = TH.identify(new_strings, res["pitches"])
        except (ST.StoreError, TH.TheoryError) as e:
            return self._err(getattr(e, "code", "bad_input"), str(e),
                             mutating=save_as is not None)
        payload = {
            "strings": new_strings,
            "fingers": new_fingers,
            "tuning": tname,
            "semitones": semitones,
            "resolved_pitches": res["pitches"],
            "midi": r_new["midi"],
            "top": (r_new["candidates"][0]["name"]
                    if r_new["candidates"] else None),
            "decided_at": r_new["decided_at"],
        }
        stored = None
        if save_as is not None:
            try:
                ST.validate_slug(save_as, "grip id")
                if save_as in lib["grips"]:
                    raise ST.StoreError("grip_exists",
                                        f"grip {save_as!r} already exists")
                new_grip = {
                    "strings": new_strings,
                    "tuning": tname,
                    "created": _now(),
                }
                if new_fingers is not None:
                    new_grip["fingers"] = new_fingers
                if id is not None:
                    new_grip["derived_from"] = {"id": id,
                                                "semitones": semitones}
                if old_chosen:
                    derived = st.load_derived()
                    d_old = st.derive_grip(lib, derived, id)
                    cov = TH.covariant_chosen(
                        d_old["candidates"], old_chosen,
                        r_new["candidates"], semitones,
                    )
                    if cov:
                        new_grip["chosen"] = cov
                        payload["chosen"] = cov
                    else:
                        warnings.append({
                            "code": "chosen_miss",
                            "detail": {"input": old_chosen,
                                       "status": "not_covariant"},
                        })
                lib["grips"][save_as] = new_grip
                derived = st.load_derived()
                st.derive_grip(lib, derived, save_as)
                st.save(lib, derived,
                        op={"tool": "transpose",
                            "detail": {"save_as": save_as, "from": id,
                                       "semitones": semitones}})
                payload["id"] = save_as
                stored = True
            except ST.StoreError as e:
                return self._err(e.code, e.detail, mutating=True)
        if render:
            g = self._renderable(new_strings, res, r_new["candidates"],
                                 new_fingers, "notes", "auto",
                                 payload.get("chosen"))
            rr = self._do_render_grips(
                st, [g], {"labels": "notes"},
                prefix=save_as if save_as else "adhoc",
            )
            if "error" in rr:
                warnings.append({"code": "render_failed",
                                 "detail": rr["error"]["detail"]})
            else:
                payload["render"] = rr
        return self._env(payload, stored=stored, warnings=warnings)

    # ------------------------------------------------------------ sequences

    def _check_rhythm_assignments(self, lib: dict, names: list,
                                  meter: list) -> None:
        """Assignment-time refusal (§5): assigned user patterns must
        exist and match the governing meter — no silent
        reinterpretation."""
        rhythms = lib.get("rhythms") or {}
        for rname in names:
            if rname in RH.BUILTINS:
                continue
            pat = rhythms.get(rname)
            if pat is None:
                raise ST.StoreError(
                    "unknown_rhythm",
                    f"rhythm {rname!r} is not defined; known: "
                    f"{sorted(rhythms)} + built-ins {list(RH.BUILTINS)}",
                )
            if pat.get("meter") != list(meter):
                raise ST.StoreError(
                    "meter_mismatch",
                    f"rhythm {rname!r} is in meter {pat.get('meter')} "
                    f"but this sequence is in {list(meter)}; refused at "
                    "assignment (RHYTHM_DESIGN §5)",
                )

    def set_sequence(self, name: str, grips: list, meter: list | None = None,
                     tempo: int | None = None, swing=None,
                     rhythm: str | None = None,
                     grouping: list | None = None) -> dict:
        """Items are grip ids, "@other-sequence" references, or step
        objects {item, rhythm, repeat}. Rhythm context (RHYTHM_DESIGN
        §5): meter [num, denom], tempo (BPM of the meter beat), swing
        ({subdivision, ratio} | "straight" to force straight under a
        swung parent), default rhythm, grouping override. Any rhythm
        field requires meter."""
        try:
            st = self._store()
            lib = st.load()
            ST.validate_slug(name, "sequence name")
            if not grips:
                raise ST.StoreError("empty_sequence",
                                    "a sequence needs at least one item")
            steps: list = []
            step_rhythms: list[str] = []
            for i, g in enumerate(grips):
                if isinstance(g, str):
                    steps.append(g)
                    continue
                if not isinstance(g, dict) or not isinstance(
                        g.get("item"), str):
                    raise ST.StoreError(
                        "bad_step",
                        f"step {i} must be a grip id, an '@sequence' "
                        "reference, or {item, rhythm?, repeat?}",
                    )
                s = {"item": g["item"]}
                if g.get("rhythm") is not None:
                    s["rhythm"] = g["rhythm"]
                    step_rhythms.append(g["rhythm"])
                if g.get("repeat") is not None:
                    r = g["repeat"]
                    if (not isinstance(r, int) or isinstance(r, bool)
                            or not 1 <= r <= RH.MAX_REPEAT):
                        raise ST.StoreError(
                            "bad_repeat",
                            f"step {i} repeat {r!r} must be "
                            f"1-{RH.MAX_REPEAT}",
                        )
                    s["repeat"] = r
                if s["item"].startswith("@") and len(s) > 1:
                    raise ST.StoreError(
                        "bad_step",
                        f"step {i}: '@' references take no per-step "
                        "rhythm/repeat — set them on the referenced "
                        "sequence",
                    )
                steps.append(s["item"] if len(s) == 1 else s)
            missing = [
                RH.step_item(s) for s in steps
                if not RH.step_item(s).startswith("@")
                and RH.step_item(s) not in lib["grips"]
            ]
            if missing:
                raise ST.StoreError(
                    "unknown_grip",
                    f"sequence references unknown grips {missing}; "
                    f"known: {sorted(lib['grips'])}",
                )
            missing_seqs = [
                RH.step_item(s)[1:] for s in steps
                if RH.step_item(s).startswith("@")
                and RH.step_item(s)[1:] not in lib["sequences"]
                and RH.step_item(s)[1:] != name
            ]
            if missing_seqs:
                raise ST.StoreError(
                    "unknown_sequence",
                    f"sequence references unknown sequences "
                    f"{missing_seqs}; known: {sorted(lib['sequences'])}",
                )
            fields: dict = {}
            rhythm_fields = [v for v in (tempo, swing, rhythm, grouping)
                             if v is not None] or step_rhythms
            if meter is None and rhythm_fields:
                raise ST.StoreError(
                    "rhythm_requires_meter",
                    "any rhythm context (tempo/swing/rhythm/grouping or "
                    "per-step rhythm) requires meter on this sequence "
                    "(RHYTHM_DESIGN §5)",
                )
            if meter is not None:
                fields["meter"] = RH.validate_meter(meter)
                if tempo is not None:
                    fields["tempo"] = RH.validate_tempo(tempo)
                if grouping is not None:
                    fields["grouping"] = RH.validate_grouping(
                        grouping, fields["meter"][0])
                if swing is not None:
                    fields["swing"] = (None if swing == "straight"
                                       else RH.validate_swing(swing))
                if rhythm is not None:
                    fields["rhythm"] = rhythm
                self._check_rhythm_assignments(
                    lib, ([rhythm] if rhythm else []) + step_rhythms,
                    fields["meter"])
            if fields or any(isinstance(s, dict) for s in steps):
                lib["sequences"][name] = RH.canonical_sequence(
                    {**fields, "steps": steps})
            else:
                lib["sequences"][name] = list(steps)
            flat = ST.flatten_sequence(lib, name)  # cycle check
            RH.walk_sequence(lib, name)  # child-meter-requires-tempo
            st.save(lib, op={"tool": "set_sequence",
                             "detail": {"name": name,
                                        "items": len(steps),
                                        "meter": fields.get("meter")}})
        except (ST.StoreError, RH.RhythmError) as e:
            return self._err(e.code, e.detail, mutating=True)
        return self._env({"name": name,
                          "sequence": lib["sequences"][name],
                          "flattened": flat}, stored=True, warnings=[])

    def list_sequences(self) -> dict:
        try:
            st = self._store()
            lib = st.load()
        except ST.StoreError as e:
            return self._err(e.code, e.detail)
        out = {}
        for name, items in lib["sequences"].items():
            entry = {"items": items}
            try:
                entry["flattened"] = ST.flatten_sequence(lib, name)
            except ST.StoreError as e:
                entry["flags"] = [{"code": e.code, "detail": e.detail}]
            out[name] = entry
        return self._env({"sequences": out})

    def remove_sequence(self, name: str, force: bool = False) -> dict:
        try:
            st = self._store()
            lib = st.load()
            if name not in lib["sequences"]:
                raise ST.StoreError(
                    "unknown_sequence",
                    f"sequence {name!r} not found; known: "
                    f"{sorted(lib['sequences'])}",
                )
            refs = ST.sequence_references(lib, name)
            if refs and not force:
                raise ST.StoreError(
                    "sequence_referenced",
                    f"sequence {name!r} is referenced (as @{name}) by "
                    f"{refs}; pass force=true to remove it and its "
                    "references",
                )
            for r in refs:
                seq = lib["sequences"][r]
                kept = [s for s in RH.seq_steps(seq)
                        if RH.step_item(s) != "@" + name]
                if isinstance(seq, dict):
                    seq["steps"] = kept
                else:
                    lib["sequences"][r] = kept
            del lib["sequences"][name]
            st.save(lib, op={"tool": "remove_sequence",
                             "detail": {"name": name}})
        except ST.StoreError as e:
            return self._err(e.code, e.detail, mutating=True)
        return self._env({"name": name, "dereferenced": refs},
                         stored=True, warnings=[])

    # -------------------------------------------------------------- tunings

    def define_tuning(self, name: str, pitches: list | None = None,
                      from_: str | None = None,
                      capo: int | None = None) -> dict:
        try:
            st = self._store()
            lib = st.load()
            ST.validate_slug(name, "tuning name")
            if name == "standard":
                raise ST.StoreError("immutable_tuning",
                                    "the built-in 'standard' is immutable")
            if (pitches is None) == (from_ is None):
                raise ST.StoreError(
                    "exactly_one_of",
                    "pass exactly one of pitches=[...] or from_=name "
                    "(+ capo)",
                )
            if name in lib["tunings"]:
                referenced = (
                    name == lib["default_tuning"]
                    or any(g["tuning"] == name
                           for g in lib["grips"].values())
                )
                if referenced:
                    raise ST.StoreError(
                        "tuning_referenced",
                        f"tuning {name!r} is referenced by grips or "
                        "default_tuning and cannot be redefined",
                    )
            entry = (
                list(pitches) if pitches is not None
                else {"from": from_, "capo": int(capo or 0)}
            )
            lib["tunings"][name] = entry
            resolved = ST.resolve_tuning(lib, name)  # cycles, parses, chains
            st.save(lib, op={"tool": "define_tuning",
                             "detail": {"name": name}})
        except (ST.StoreError, TH.TheoryError) as e:
            return self._err(getattr(e, "code", "bad_input"), str(e),
                             mutating=True)
        return self._env(
            {"name": name, "resolved_pitches": resolved["pitches"],
             "capo": resolved["capo"]},
            stored=True, warnings=[],
        )

    def remove_tuning(self, name: str) -> dict:
        try:
            st = self._store()
            lib = st.load()
            if name == "standard":
                raise ST.StoreError("immutable_tuning",
                                    "the built-in 'standard' is immutable")
            if name not in lib["tunings"]:
                raise ST.StoreError(
                    "unknown_tuning",
                    f"tuning {name!r} not found; known: "
                    f"{sorted(lib['tunings'])}",
                )
            decl = ST.current_declaration(lib)
            if decl and decl["tuning"] == name:
                raise ST.StoreError(
                    "tuning_referenced",
                    f"tuning {name!r} is the declared instrument tuning; "
                    "declare another via set_instrument_tuning first",
                )
            if name == lib["default_tuning"]:
                raise ST.StoreError(
                    "tuning_referenced",
                    f"tuning {name!r} is the default_tuning; change it "
                    "first via update_project_defaults",
                )
            users = [gid for gid, g in lib["grips"].items()
                     if g["tuning"] == name]
            if users:
                raise ST.StoreError(
                    "tuning_referenced",
                    f"tuning {name!r} is referenced by grips {users}",
                )
            chained = [
                t for t, e in lib["tunings"].items()
                if isinstance(e, dict) and e.get("from") == name
            ]
            if chained:
                raise ST.StoreError(
                    "tuning_referenced",
                    f"tuning {name!r} is the base of derived tunings "
                    f"{chained}",
                )
            del lib["tunings"][name]
            st.save(lib, op={"tool": "remove_tuning",
                             "detail": {"name": name}})
        except ST.StoreError as e:
            return self._err(e.code, e.detail, mutating=True)
        return self._env({"name": name}, stored=True, warnings=[])

    # ------------------------------------------------------- Phase 3

    def analyze(self, sequence: str, keys: list | None = None) -> dict:
        """Analysis over a sequence (docs/PHASE3_DESIGN.md): the user's
        vocabulary first (display candidate = chosen else top),
        read-only, recomputed per call. With a rhythm context (meter),
        the timeline appears and key scores gain tick weighting
        (RHYTHM_DESIGN §6); without one, Phase-3 behavior unchanged."""
        from . import analysis as AN
        warnings: list[dict] = []
        try:
            st = self._store()
            lib = st.load()
            gids = ST.flatten_sequence(lib, sequence)
            derived = st.load_derived()
            steps = []
            for gid in gids:
                grip = lib["grips"][gid]
                d = st.derive_grip(lib, derived, gid)
                disp = self._display_candidate(
                    d["candidates"], grip.get("chosen")
                )
                if disp is None:  # single-PC grip: pitch report only
                    pr = d.get("pitch_report") or {}
                    steps.append({
                        "grip": gid, "name": None, "named": False,
                        "midi": d["midi"],
                        "pitches": pr.get("pitches", []),
                        "root_pc": None, "quality": None, "bass_pc": None,
                    })
                    continue
                steps.append({
                    "grip": gid,
                    "name": grip.get("chosen") or disp["name"],
                    "named": grip.get("chosen") is not None,
                    "midi": d["midi"],
                    "pitches": disp["pitches"],
                    "root_pc": TH._pc_of_name(disp["root"]),
                    "quality": disp["quality"],
                    "bass_pc": TH._pc_of_name(disp["bass"]),
                })
            st.save(lib, derived)  # cache refresh only; no history op
            # Rhythm context: a missing meter degrades to Phase-3
            # behavior; a broken context (dangling rhythm, mismatch,
            # child-meter-without-tempo) errors instructively.
            ctxs = RH.walk_sequence(lib, sequence)
            timeline = None
            spans = None
            if ctxs and all(c["meter"] is not None for c in ctxs):
                rz = self._realize(st, lib, derived, sequence)
                spans = [s["span"] for s in rz["steps"]]
                warnings.extend(rz["warnings"])
                timeline = {
                    "ticks_per_beat": RH.TICKS_PER_BEAT,
                    "total_ticks": rz["total_ticks"],
                    "sections": self._clean_sections(rz["sections"]),
                    "steps": rz["steps"],
                }
            result = AN.analyze(steps, keys, spans=spans)
        except (ST.StoreError, TH.TheoryError, RH.RhythmError) as e:
            return self._err(getattr(e, "code", "bad_input"), str(e))
        payload = {"sequence": sequence, **result}
        if timeline is not None:
            payload["timeline"] = timeline
        return self._env(payload, warnings=warnings or None)

    # ---------------------------------------------------- rhythm (rev 3)

    @staticmethod
    def _clean_sections(sections: list[dict]) -> list[dict]:
        return [
            {k: s[k] for k in ("at", "meter", "tempo", "swing",
                               "grouping")}
            for s in sections
        ]

    def _realize(self, st: ST.Store, lib: dict, derived: dict,
                 sequence: str) -> dict:
        """Build grips_info (physical sounding order — 1 = lowest
        physical sounding string; §3) and realize the sequence."""
        gids = ST.flatten_sequence(lib, sequence)
        canon = TH.load_table()["_canonical_lof"]
        grips_info = {}
        for gid in gids:
            if gid in grips_info:
                continue
            if gid not in lib["grips"]:
                raise ST.StoreError(
                    "unknown_grip",
                    f"sequence {sequence!r} references unknown grip "
                    f"{gid!r}",
                )
            grip = lib["grips"][gid]
            res = ST.resolve_tuning(lib, grip["tuning"])
            d = st.derive_grip(lib, derived, gid)
            disp = self._display_candidate(d["candidates"],
                                           grip.get("chosen"))
            spelled = {}
            if disp is not None:
                spelled = dict(zip(sorted(d["midi"]), disp["pitches"]))
            else:
                pr = d.get("pitch_report") or {}
                spelled = dict(zip(sorted(d["midi"]),
                                   pr.get("pitches", [])))
            opens = [TH.parse_pitch(p) for p in res["pitches"]]
            sounding = []
            for o, f in zip(opens, grip["strings"]):
                if f is None:
                    continue
                m = o + f
                sounding.append({
                    "string": len(sounding) + 1,
                    "midi": m,
                    "pitch": spelled.get(m,
                                         TH.pitch_str(canon[m % 12], m)),
                })
            grips_info[gid] = {
                "sounding": sounding,
                "name": grip.get("chosen")
                or (disp["name"] if disp else None),
            }
        return RH.realize(lib, sequence, grips_info)

    def set_rhythm(self, name: str, meter: list, length,
                   events: list, swing=None,
                   grouping: list | None = None) -> dict:
        """Define/replace a rhythm pattern — authoring macros (verbs,
        accent-map velocities, let-ring durations) expand at definition;
        storage is fully expanded, integer ticks (RHYTHM_DESIGN §5)."""
        try:
            st = self._store()
            lib = st.load()
            ST.validate_slug(name, "rhythm name")
            if name in RH.BUILTINS:
                raise ST.StoreError(
                    "builtin_rhythm",
                    f"{name!r} is a built-in (meter-parametric spec "
                    "function) and is immutable",
                )
            m = RH.validate_meter(meter)
            g = (RH.validate_grouping(grouping, m[0])
                 if grouping is not None else RH.default_grouping(m[0]))
            length_ticks = RH.snap_ticks(length, "length")
            if length_ticks < 1:
                raise RH.RhythmError("bad_beats",
                                     "length must be positive")
            expanded = RH.expand_events(events, length_ticks, m, g)
            pat: dict = {"length_ticks": length_ticks, "meter": m}
            if swing is not None:
                pat["swing"] = (None if swing == "straight"
                                else RH.validate_swing(swing))
            if grouping is not None:
                pat["grouping"] = g
            pat["events"] = expanded
            # Redefinition guard: every sequence assigning this name
            # must still meter-match (no silent reinterpretation).
            conflicts = [
                sname for sname, seq in lib["sequences"].items()
                if isinstance(seq, dict)
                and name in RH.assigned_rhythms(seq)
                and seq.get("meter") is not None
                and list(seq["meter"]) != m
            ]
            if conflicts:
                raise ST.StoreError(
                    "meter_mismatch",
                    f"redefining {name!r} in meter {m} would mismatch "
                    f"sequences {conflicts}; change those assignments "
                    "first",
                )
            lib.setdefault("rhythms", {})[name] = RH.canonical_pattern(pat)
            st.save(lib, op={"tool": "set_rhythm",
                             "detail": {"name": name, "meter": m,
                                        "events": len(expanded)}})
        except (ST.StoreError, RH.RhythmError) as e:
            return self._err(e.code, e.detail, mutating=True)
        return self._env({"name": name,
                          "rhythm": lib["rhythms"][name]},
                         stored=True, warnings=[])

    def list_rhythms(self) -> dict:
        try:
            st = self._store()
            lib = st.load()
        except ST.StoreError as e:
            return self._err(e.code, e.detail)
        return self._env({
            "rhythms": lib.get("rhythms") or {},
            "builtins": {
                "note": "meter-parametric spec functions, instantiated "
                        "against the governing meter at realization; "
                        "immutable (RHYTHM_DESIGN §5)",
                "whole": "one strum spanning the bar",
                "quarters": "a strum on every beat",
                "bass-strum": "symbolic bass on group starts, strum on "
                              "other beats",
                "arp-up": "one bar-spanning arp",
            },
        })

    def remove_rhythm(self, name: str, force: bool = False) -> dict:
        try:
            st = self._store()
            lib = st.load()
            if name in RH.BUILTINS:
                raise ST.StoreError(
                    "builtin_rhythm",
                    f"{name!r} is a built-in and cannot be removed",
                )
            rhythms = lib.get("rhythms") or {}
            if name not in rhythms:
                raise ST.StoreError(
                    "unknown_rhythm",
                    f"rhythm {name!r} not found; known: "
                    f"{sorted(rhythms)}",
                )
            refs = {
                sname: RH.assigned_rhythms(seq).count(name)
                for sname, seq in lib["sequences"].items()
                if name in RH.assigned_rhythms(seq)
            }
            if refs and not force:
                raise ST.StoreError(
                    "rhythm_assigned",
                    f"rhythm {name!r} is assigned by sequences {refs}; "
                    "pass force=true to remove it and drop the "
                    "assignments",
                )
            for sname in refs:
                seq = lib["sequences"][sname]
                if seq.get("rhythm") == name:
                    del seq["rhythm"]
                seq["steps"] = [
                    (s["item"] if isinstance(s, dict)
                     and s.get("rhythm") == name and len(s) == 2 else
                     ({k: v for k, v in s.items() if not (
                         k == "rhythm" and v == name)}
                      if isinstance(s, dict) else s))
                    for s in seq["steps"]
                ]
            del lib["rhythms"][name]
            st.save(lib, op={"tool": "remove_rhythm",
                             "detail": {"name": name}})
        except ST.StoreError as e:
            return self._err(e.code, e.detail, mutating=True)
        return self._env({"name": name, "dereferenced": refs},
                         stored=True, warnings=[])

    def export_timeline(self, sequence: str) -> dict:
        """The bus (RHYTHM_DESIGN §6): JSON carrying BOTH events_stored
        (straight grid + swing parameter) and events (realized, swing
        applied); content hash over the realized form. The primary
        artifact for cdp-mcp."""
        import json as _json
        try:
            st = self._store()
            lib = st.load()
            derived = st.load_derived()
            rz = self._realize(st, lib, derived, sequence)
            st.save(lib, derived)  # cache refresh only
            h = RH.content_hash(rz["events"])
            doc = {
                "schema_version": 1,
                "kind": "grip_timeline",
                "sequence": sequence,
                "engine_version": TH.ENGINE_VERSION,
                "table_version": TH.table_version(),
                "content_hash": h,
                "ticks_per_beat": RH.TICKS_PER_BEAT,
                "total_ticks": rz["total_ticks"],
                "sections": self._clean_sections(rz["sections"]),
                "steps": rz["steps"],
                "events_stored": RH.export_events(rz["events_stored"]),
                "events": RH.export_events(rz["events"]),
            }
            st.exports_dir.mkdir(parents=True, exist_ok=True)
            path = st.exports_dir / f"{sequence}__{h[:8]}.json"
            path.write_text(
                _json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8")
        except (ST.StoreError, TH.TheoryError, RH.RhythmError) as e:
            return self._err(getattr(e, "code", "bad_input"), str(e))
        return self._env({
            "sequence": sequence,
            "file": str(path),
            "content_hash": h,
            "total_ticks": rz["total_ticks"],
            "events": len(rz["events"]),
            "sections": self._clean_sections(rz["sections"]),
        }, warnings=rz["warnings"])

    def export_midi(self, sequence: str) -> dict:
        """Format-1 SMF at fixed PPQ 3840 (RHYTHM_DESIGN §6). Note:
        DAWs display quarter-note BPM, which for compound meters matches
        neither `tempo` (denom-note BPM) nor the felt dotted beat —
        inherent to MIDI, not an export bug."""
        from . import midi as MI
        try:
            st = self._store()
            lib = st.load()
            derived = st.load_derived()
            rz = self._realize(st, lib, derived, sequence)
            st.save(lib, derived)
            RH.require_tempo(rz, "export_midi")
            smf = MI.write_smf(rz["sections"], rz["events"],
                               rz["total_ticks"])
            h = RH.content_hash(rz["events"])
            st.exports_dir.mkdir(parents=True, exist_ok=True)
            path = st.exports_dir / f"{sequence}__{h[:8]}.mid"
            path.write_bytes(smf)
        except (ST.StoreError, TH.TheoryError, RH.RhythmError) as e:
            return self._err(getattr(e, "code", "bad_input"), str(e))
        return self._env({
            "sequence": sequence,
            "file": str(path),
            "content_hash": h,
            "ppq": RH.SMF_PPQ,
            "bytes": len(smf),
        }, warnings=rz["warnings"])

    def render_audio(self, sequence: str) -> dict:
        """Deterministic Karplus-Strong audition (RHYTHM_DESIGN §6):
        one file per sequence, overwritten — a deliberate exception to
        the renders hash convention (overwrite semantics are the no-GC
        answer). Pure-Python synthesis: seconds of latency accepted."""
        from . import audio as AU
        try:
            st = self._store()
            lib = st.load()
            derived = st.load_derived()
            rz = self._realize(st, lib, derived, sequence)
            st.save(lib, derived)
            RH.require_tempo(rz, "render_audio")
            wav = AU.synthesize(rz["sections"], rz["events"],
                                rz["total_ticks"])
            st.renders_dir.mkdir(parents=True, exist_ok=True)
            path = st.renders_dir / f"{sequence}__audition.wav"
            path.write_bytes(wav)
            secs = AU.duration_seconds(rz["sections"], rz["total_ticks"])
        except (ST.StoreError, TH.TheoryError, RH.RhythmError) as e:
            return self._err(getattr(e, "code", "bad_input"), str(e))
        return self._env({
            "sequence": sequence,
            "file": str(path),
            "seconds": round(float(secs), 3),
            "sample_rate": AU.SAMPLE_RATE,
            "voices": len(rz["events"]),
        }, warnings=rz["warnings"])

    # -------------------------------------------- journal + history (log)

    def journal(self, entry: str, tags: list | None = None) -> dict:
        """Record an observation/context note on the project (cdp-mcp
        style): 'the pass grip wants to resolve down', 'try the bridge in
        open C'. Surfaced on resume; the accumulating context that turns
        working titles into settled names."""
        try:
            st = self._store()
            if not entry or not isinstance(entry, str):
                raise ST.StoreError("bad_input", "entry must be text")
            if not st.library_path.exists():
                st.save(st.load())  # bootstrap the namespace consistently
            rec = {"entry": entry}
            if tags:
                rec["tags"] = list(tags)
            written = st.append_jsonl(st.journal_path, rec)
        except ST.StoreError as e:
            return self._err(e.code, e.detail, mutating=True)
        return self._env({"journal": written}, stored=True, warnings=[])

    def list_journal(self, limit: int = 10,
                     tag: str | None = None) -> dict:
        try:
            st = self._store()
            entries = st.read_jsonl(st.journal_path)
        except ST.StoreError as e:
            return self._err(e.code, e.detail)
        if tag is not None:
            entries = [e for e in entries if tag in e.get("tags", [])]
        return self._env({"entries": entries[:max(1, limit)],
                          "total": len(entries)})

    def history(self, limit: int = 20) -> dict:
        """The project's mutation log — every stored change, newest
        first. The progress record source control would give you,
        without leaving the conversation."""
        try:
            st = self._store()
            entries = st.read_jsonl(st.history_path, limit=max(1, limit))
        except ST.StoreError as e:
            return self._err(e.code, e.detail)
        return self._env({"entries": entries})

    # ------------------------------------------------------- Phase 2a (§9)

    def find_voicings(self, chord: str, key: str | None = None,
                      near_fret: int | None = None,
                      tuning: str | None = None,
                      constraints: dict | None = None,
                      render: bool = False, top: int = TOP_N) -> dict:
        from . import voicings as V
        try:
            st = self._store()
            lib = st.load()
            tname, res = self._resolve_tuning_arg(lib, tuning)
            if key is not None:
                TH.Key.parse(key)  # validate early, instructively
            result = V.find_voicings(res["pitches"], chord, key, near_fret,
                                     constraints)
        except (ST.StoreError, TH.TheoryError, V.VoicingError) as e:
            return self._err(getattr(e, "code", "bad_input"), str(e))
        ranked = result["voicings"]
        payload = {
            "chord": result["chord"],
            "quality": result["quality"],
            "tones": result["tones"],
            "tuning": tname,
            "resolved_pitches": res["pitches"],
            "capo": res["capo"],
            "constraints": result["constraints"],
            "voicings": ranked[:top],
            "truncated": max(0, len(ranked) - top),
        }
        warnings = []
        if render and ranked:
            cards = [
                {
                    "frets": v["strings"],
                    "fingers": v["fingers"],
                    "string_labels": list(v["string_pitches"]),
                    "name": result["chord"],
                    "capo": res["capo"],
                }
                for v in ranked[:min(top, 4)]
            ]
            rr = self._do_render_grips(
                st, cards,
                {"labels": "notes", "title": result["chord"]},
                prefix="adhoc",
            )
            if "error" in rr:
                warnings.append({"code": "render_failed",
                                 "detail": rr["error"]["detail"]})
            else:
                payload["render"] = rr
        return self._env(payload, warnings=warnings or None)


    def render_neck(self, overlay_key: str | None = None,
                    overlay_pitches: list | None = None,
                    tuning: str | None = None, frets: int = 12,
                    labels: str = "notes", theme: str = "light") -> dict:
        if (overlay_key is None) == (overlay_pitches is None):
            return self._err(
                "exactly_one_of",
                "pass exactly one of overlay_key ('e-minor') or "
                "overlay_pitches (['E','G','B']; first entry is "
                "emphasized)",
            )
        try:
            st = self._store()
            lib = st.load()
            tname, res = self._resolve_tuning_arg(lib, tuning)
            frets = max(4, min(int(frets), 15))
            tbl = TH.load_table()
            if overlay_key is not None:
                k = TH.Key.parse(overlay_key)
                pcs = {pc: TH.lof_str(k.spell(pc)) for pc in k.scale_pcs}
                emphasis = k.tonic_pc
                title = overlay_key
            else:
                lofs = [TH.parse_note(p) for p in overlay_pitches]
                if not lofs:
                    raise TH.TheoryError("overlay_pitches is empty")
                pcs = {TH.lof_pc(l): TH.lof_str(l) for l in lofs}
                emphasis = TH.lof_pc(lofs[0])
                title = " ".join(TH.lof_str(l) for l in lofs)
            opens = [TH.parse_pitch(p) for p in res["pitches"]]
            positions = []
            for si, om in enumerate(opens):
                for f in range(0, frets + 1):
                    pc = (om + f) % 12
                    if pc in pcs:
                        positions.append({
                            "string": si, "fret": f, "label": pcs[pc],
                            "emphasis": pc == emphasis,
                        })
            spec = {
                "tuning_pitches": res["pitches"],
                "positions": positions,
                "title": title,
                "capo": res["capo"],
                "frets": frets,
            }
            out = RD.render_neck_overlay(spec, {"labels": labels,
                                                "theme": theme})
            png = RD.to_png(out["svg"], out["width"])
            st.renders_dir.mkdir(parents=True, exist_ok=True)
            png_path = st.renders_dir / f"neck__{out['hash']}.png"
            png_path.write_bytes(png)
        except (ST.StoreError, TH.TheoryError, RD.RenderError) as e:
            return self._err(getattr(e, "code", "bad_input"), str(e))
        return self._env({
            "tuning": tname,
            "capo": res["capo"],
            "overlay": title,
            "files": {"png": str(png_path)},
            "render_hash": out["hash"],
        })

    # ------------------------------------------------------- Phase 2b (§9)

    UPTUNE_AGGRESSIVE = 3    # semitones; direction + magnitude only —
    DOWNTUNE_SLACK = 4       # per-string-set accuracy would need gauge data

    def _retune(self, lib: dict, from_name: str, to_name: str) -> dict:
        a = ST.resolve_tuning(lib, from_name)
        b = ST.resolve_tuning(lib, to_name)
        if len(a["pitches"]) != len(b["pitches"]):
            raise ST.StoreError(
                "length_mismatch",
                f"{from_name!r} has {len(a['pitches'])} strings, "
                f"{to_name!r} has {len(b['pitches'])}; a retune plan needs "
                "matching string counts",
            )
        strings = []
        warnings = []
        for i, (pa, pb) in enumerate(zip(a["pitches"], b["pitches"])):
            delta = TH.parse_pitch(pb) - TH.parse_pitch(pa)
            direction = "hold" if delta == 0 else ("up" if delta > 0
                                                  else "down")
            strings.append({
                "string": i + 1,  # 1 = lowest
                "from": pa, "to": pb,
                "semitones": delta, "direction": direction,
            })
            if delta >= self.UPTUNE_AGGRESSIVE:
                warnings.append({
                    "code": "large_delta",
                    "detail": {
                        "string": i + 1, "direction": "up",
                        "semitones": delta,
                        "note": f"up {delta} semitones is aggressive "
                                "(direction + magnitude heuristic only — "
                                "the server cannot know the string set)",
                    },
                })
            elif -delta >= self.DOWNTUNE_SLACK:
                warnings.append({
                    "code": "large_delta",
                    "detail": {
                        "string": i + 1, "direction": "down",
                        "semitones": delta,
                        "note": f"down {-delta} semitones will be slack; "
                                "expect intonation drift and buzz",
                    },
                })
        # Suggested order: release tension first (downs, low->high), then
        # come up TO pitch (ups, low->high). Deterministic, documented.
        order = (
            [s["string"] for s in strings if s["direction"] == "down"]
            + [s["string"] for s in strings if s["direction"] == "up"]
        )
        plan = {
            "from": from_name, "to": to_name,
            "strings": strings,
            "suggested_order": order,
            "order_rule": "downs first (release tension), then ups "
                          "(approach pitch from below), each low to high",
        }
        if a["capo"] or b["capo"]:
            plan["capo_note"] = (
                f"deltas compare sounding open pitches; capo accounts for "
                f"{from_name!r}: {a['capo']}, {to_name!r}: {b['capo']} "
                "semitones of that — a capo change is not a peg turn"
            )
        return plan, warnings

    def _tuning_card(self, lib: dict, name: str) -> dict:
        res = ST.resolve_tuning(lib, name)
        return {
            "frets": [0] * len(res["pitches"]),
            "fingers": None,
            "string_labels": list(res["pitches"]),
            "name": name,
            "capo": res["capo"],
        }

    def set_instrument_tuning(self, name: str, render: bool = False) -> dict:
        """Project-scoped declaration with history (question 5's lean):
        'this project's instrument is in <name> as of now'. Supersedes the
        bare default_tuning (capture defaults follow the declaration)."""
        warnings: list[dict] = []
        try:
            st = self._store()
            lib = st.load()
            res = ST.resolve_tuning(lib, name)  # must exist and resolve
            prev = ST.current_declaration(lib)
            entry = {"tuning": name, "since": _now()}
            lib.setdefault("instrument", {"declarations": []})
            lib["instrument"]["declarations"].append(entry)
            lib["default_tuning"] = name  # superseding bare default_tuning
            st.save(lib, op={"tool": "set_instrument_tuning",
                             "detail": {"tuning": name}})
        except ST.StoreError as e:
            return self._err(e.code, e.detail, mutating=True)
        payload = {
            "declared": entry,
            "resolved_pitches": res["pitches"],
            "capo": res["capo"],
            "default_tuning": name,
            "declarations": len(lib["instrument"]["declarations"]),
        }
        if prev and prev["tuning"] != name:
            try:
                plan, plan_warnings = self._retune(lib, prev["tuning"], name)
                payload["retune"] = plan
                warnings.extend(plan_warnings)
            except ST.StoreError:
                pass  # prior declaration dangling; flagged elsewhere
        if render:
            rr = self._do_render_grips(
                st, [self._tuning_card(lib, name)],
                {"labels": "notes"}, prefix=name,
            )
            if "error" in rr:
                warnings.append({"code": "render_failed",
                                 "detail": rr["error"]["detail"]})
            else:
                payload["render"] = rr
        return self._env(payload, stored=True, warnings=warnings)

    def retune_plan(self, to: str, from_: str | None = None,
                    render: bool = False) -> dict:
        """Per-string deltas from -> to. `from_` defaults to the declared
        instrument tuning, else default_tuning."""
        try:
            st = self._store()
            lib = st.load()
            if from_ is None:
                decl = ST.current_declaration(lib)
                from_ = decl["tuning"] if decl else lib["default_tuning"]
            plan, warnings = self._retune(lib, from_, to)
        except ST.StoreError as e:
            return self._err(e.code, e.detail)
        payload = dict(plan)
        if render:
            cards = [self._tuning_card(lib, from_),
                     self._tuning_card(lib, to)]
            rr = self._do_render_grips(
                st, cards,
                {"labels": "notes", "title": f"retune: {from_} -> {to}",
                 "columns": 2},
                prefix="retune",
            )
            if "error" in rr:
                warnings.append({"code": "render_failed",
                                 "detail": rr["error"]["detail"]})
            else:
                payload["render"] = rr
        return self._env(payload, warnings=warnings)

    # -------------------------------------------------------------- render

    def _display_candidate(self, candidates: list, chosen: str | None):
        """Display spelling follows chosen if set, else the top candidate
        (§5.2.3)."""
        if chosen:
            for c in candidates:
                if c["name"] == chosen:
                    return c
        return candidates[0] if candidates else None

    def _renderable(self, strings, res, candidates, fingers, labels,
                    interval_root, chosen, name=None) -> dict:
        disp = self._display_candidate(candidates, chosen)
        opens = [TH.parse_pitch(p) for p in res["pitches"]]
        string_labels = [None] * len(strings)
        if disp is not None and labels in ("notes", "intervals"):
            if labels == "notes":
                # Full pitch names with octave numbers (user feedback:
                # D5, not D).
                spelled = {}
                midis = sorted(
                    o + f for o, f in zip(opens, strings) if f is not None
                )
                for m, p in zip(midis, disp["pitches"]):
                    spelled[m] = p
                string_labels = [
                    None if f is None else spelled[o + f]
                    for o, f in zip(opens, strings)
                ]
            else:
                if interval_root == "auto":
                    root_pc = TH._pc_of_name(disp["root"])
                else:
                    root_pc = TH._pc_of_name(interval_root)
                string_labels = [
                    None if f is None
                    else _INTERVAL_LABEL[((o + f) - root_pc) % 12]
                    for o, f in zip(opens, strings)
                ]
        return {
            "frets": list(strings),
            "fingers": list(fingers) if fingers else None,
            "string_labels": string_labels,
            "name": name if name is not None
            else (chosen or (disp["name"] if disp else "")),
            "capo": res["capo"],
        }

    def _do_render_grips(self, st: ST.Store, grips: list, options: dict,
                         prefix: str) -> dict:
        try:
            out = RD.render_chart(grips, options)
            png = RD.to_png(out["svg"], out["width"])
            st.renders_dir.mkdir(parents=True, exist_ok=True)
            png_path = st.renders_dir / f"{prefix}__{out['hash']}.png"
            png_path.write_bytes(png)  # PNG only (user feedback);
        except (RD.RenderError, Exception) as e:  # render failure = partial
            code = getattr(e, "code", "render_error")
            return {"error": {"code": code, "detail": str(e)}}
        return {
            "files": {"png": str(png_path)},
            "render_hash": out["hash"],
            "width": out["width"], "height": out["height"],
        }

    def render(self, ids: list | None = None, sequence: str | None = None,
               labels: str = "notes", interval_root: str = "auto",
               orientation: str = "chart", theme: str = "light",
               columns: int | None = None, title: str | None = None) -> dict:
        if (ids is None) == (sequence is None):
            return self._err(
                "exactly_one_of",
                "pass exactly one of ids=[...] or sequence=name",
            )
        try:
            st = self._store()
            lib = st.load()
            if sequence is not None:
                gids = ST.flatten_sequence(lib, sequence)
                prefix = sequence
            else:
                gids = list(ids)
                if not gids:
                    raise ST.StoreError("bad_input",
                                        "ids must name at least one grip")
                missing = [g for g in gids if g not in lib["grips"]]
                if missing:
                    raise ST.StoreError(
                        "unknown_grip",
                        f"unknown grips {missing}; known: "
                        f"{sorted(lib['grips'])}",
                    )
                prefix = gids[0] if len(gids) == 1 else "strip"
            derived = st.load_derived()
            renderables = []
            for gid in gids:
                grip = lib["grips"][gid]
                res = ST.resolve_tuning(lib, grip["tuning"])
                d = st.derive_grip(lib, derived, gid)
                renderables.append(self._renderable(
                    grip["strings"], res, d["candidates"],
                    grip.get("fingers"), labels, interval_root,
                    grip.get("chosen"),
                ))
            st.save(lib, derived)
            options = {"labels": labels, "orientation": orientation,
                       "theme": theme}
            if columns:
                options["columns"] = columns
            if title:
                options["title"] = title
            rr = self._do_render_grips(st, renderables, options, prefix)
            if "error" in rr:
                return self._env(
                    {"error": rr["error"]}, warnings=[
                        {"code": "render_failed",
                         "detail": rr["error"]["detail"]}
                    ])
        except (ST.StoreError, TH.TheoryError, RD.RenderError) as e:
            return self._err(getattr(e, "code", "bad_input"), str(e))
        return self._env({**rr, "grips": gids}, warnings=[])

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
            st.save(lib)
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
        flags = ST.tuning_flags(lib)
        n = len(lib["grips"])
        base = {
            "default_tuning": lib["default_tuning"],
            "tunings": lib["tunings"],
            "flags": flags,
            "counts": {"grips": n, "sequences": len(lib["sequences"])},
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
                 render: bool = True) -> dict:
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
            st.save(lib, derived)
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
            st.save(lib, derived)
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
                lib["sequences"][name] = [
                    new_id if g == id else g for g in seq
                ]
                rewritten += seq.count(id)
            derived = st.load_derived()
            if id in derived["grips"]:
                derived["grips"][new_id] = derived["grips"].pop(id)
            st.save(lib, derived)
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
            refs = {
                name: seq.count(id)
                for name, seq in lib["sequences"].items() if id in seq
            }
            if refs and not force:
                return self._err(
                    "grip_referenced",
                    f"grip {id!r} is referenced by sequences {refs} "
                    "(every occurrence counts); pass force=true to remove "
                    "it and its occurrences",
                    mutating=True,
                )
            for name in refs:
                lib["sequences"][name] = [
                    g for g in lib["sequences"][name] if g != id
                ]
            del lib["grips"][id]
            derived = st.load_derived()
            derived["grips"].pop(id, None)
            st.save(lib, derived)
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
            st.save(lib, derived)
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
                st.save(lib, derived)
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

    def set_sequence(self, name: str, grips: list) -> dict:
        try:
            st = self._store()
            lib = st.load()
            ST.validate_slug(name, "sequence name")
            missing = [g for g in grips if g not in lib["grips"]]
            if missing:
                raise ST.StoreError(
                    "unknown_grip",
                    f"sequence references unknown grips {missing}; "
                    f"known: {sorted(lib['grips'])}",
                )
            if not grips:
                raise ST.StoreError("empty_sequence",
                                    "a sequence needs at least one grip id")
            lib["sequences"][name] = list(grips)
            st.save(lib)
        except ST.StoreError as e:
            return self._err(e.code, e.detail, mutating=True)
        return self._env({"name": name, "grips": list(grips)}, stored=True,
                         warnings=[])

    def list_sequences(self) -> dict:
        try:
            st = self._store()
            lib = st.load()
        except ST.StoreError as e:
            return self._err(e.code, e.detail)
        return self._env({"sequences": lib["sequences"]})

    def remove_sequence(self, name: str) -> dict:
        try:
            st = self._store()
            lib = st.load()
            if name not in lib["sequences"]:
                raise ST.StoreError(
                    "unknown_sequence",
                    f"sequence {name!r} not found; known: "
                    f"{sorted(lib['sequences'])}",
                )
            del lib["sequences"][name]
            st.save(lib)
        except ST.StoreError as e:
            return self._err(e.code, e.detail, mutating=True)
        return self._env({"name": name}, stored=True, warnings=[])

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
            st.save(lib)
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
            st.save(lib)
        except ST.StoreError as e:
            return self._err(e.code, e.detail, mutating=True)
        return self._env({"name": name}, stored=True, warnings=[])

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
                spelled = {}
                midis = sorted(
                    o + f for o, f in zip(opens, strings) if f is not None
                )
                for m, p in zip(midis, disp["pitches"]):
                    spelled[m] = "".join(ch for ch in p
                                         if not ch.isdigit() and ch != "-")
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
            base = f"{prefix}__{out['hash']}"
            svg_path = st.renders_dir / f"{base}.svg"
            png_path = st.renders_dir / f"{base}.png"
            svg_path.write_text(out["svg"], encoding="utf-8")
            png_path.write_bytes(png)  # identical requests overwrite
        except (RD.RenderError, Exception) as e:  # render failure = partial
            code = getattr(e, "code", "render_error")
            return {"error": {"code": code, "detail": str(e)}}
        return {
            "files": {"svg": str(svg_path), "png": str(png_path)},
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
                if sequence not in lib["sequences"]:
                    raise ST.StoreError(
                        "unknown_sequence",
                        f"sequence {sequence!r} not found; known: "
                        f"{sorted(lib['sequences'])}",
                    )
                gids = lib["sequences"][sequence]
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

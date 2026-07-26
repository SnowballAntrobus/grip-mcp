"""Versioned presentation contract (DESIGN §6.3).

MCP tool descriptions and the server-level `instructions` field are
first-class, reviewed design artifacts: all of §7's rigor produces output
the musician never sees — the client LLM mediates — so what these strings
instruct is part of the product. The contract test
(tests/test_descriptions_contract.py) is honestly scoped: a keyword check
that catches deleted text, not ignored text.

Closing doctrine: wherever a description asks the LLM to do the right
thing, first check whether the API can make the wrong thing impossible
(the `create` gate on set_project is the worked example).
"""

DESCRIPTIONS_VERSION = "0.6.0"

SERVER_INSTRUCTIONS = """\
grip-mcp is a deterministic fretboard engine: identify, library, render.
The musician's own vocabulary comes first.

Presenting identifications:
- The top candidate is the most literal complete reading, not "the answer."
  Present it alongside other high-ranked and contextual readings, and above
  all the user's stored `chosen` names. When a grip matches the library,
  LEAD with the user's name for it; the theory comes second.
- Calibrate on `decided_at`: "tiebreak" means maximally ambiguous (present
  alternatives as peers); "unique" means no contest; R1/R2/R3 sit between.
  The server reports where the ordering was decided, never confidence.
- Promotion is your job: the server ranks by published rules; you decide
  what to foreground (e.g. a dominant-function hearing the ranking places
  below a literal reading) and record the user's choice with set_reading.

Capture:
- One call in the common case: add_grip with the user's name in `chosen`.
  A chosen miss or render failure is PARTIAL success - the grip stored;
  repair with a follow-up set_reading, never a re-send.
- Echo-verify: the response's resolved pitches (low->high) are the
  self-check for reversed string arrays and octave/tuning errors. Read
  them back before confirming to the user.
- Renders are on request only (render=true, or the render tool) - don't
  render every capture; one strip of a sequence beats per-grip charts.
- Working titles: when the user hasn't settled what to call a chord,
  store their working name in `label` and leave `chosen` unset (the grip
  lists as unnamed); record the surrounding context in the journal, and
  settle it later with set_reading as context accumulates.
- Journal liberally: observations like "this voicing wants to resolve
  down" or "try the bridge in open C" belong in journal entries - they
  resume with the workspace.

Name->shape: find_voicings computes shapes exactly - never propose a shape
from your own knowledge when it can search (the old name->shape bridge is
retired). identify remains the verifier for shapes the USER plays; VERIFY
any fretting you did not get from find_voicings before presenting it.

Projects: set_project refuses to create unless create=true; before passing
create=true, confirm with the user that a NEW project is intended (say
whether you created or opened it in your reply). Every response envelope
carries the project name - surface it if it isn't what the user expects.
"""

TOOL_DESCRIPTIONS = {
    "list_projects": (
        "List every project under MUSIC_PROJECT_ROOT, ecosystem-wide (the "
        "user's mental model is 'my projects', not 'my grip projects'). "
        "Projects without a grip/ namespace report grips: 0; malformed "
        "entries are skipped with a warning, never a crash."
    ),
    "set_project": (
        "Switch the active project. With create=false (the default) this "
        "REFUSES to create a missing project and lists close-match existing "
        "names in the refusal - a typo must never fork a library. Pass "
        "create=true only after the user confirms a new project is "
        "intended, and tell them whether you created or opened it. Nothing "
        "touches disk until the first write."
    ),
    "update_project_defaults": (
        "Set the project's default_tuning (single field in V1). Validates "
        "the tuning exists; refusals are instructive. The default resolves "
        "at call time - grips always store a concrete tuning name."
    ),
    "describe_workspace": (
        "Resume a session in one call: inlines the grip list (ids, labels, "
        "chosen names with stale flags, tags), sequences, and the tunings "
        "table including default_tuning and any dangling-reference flags, "
        "up to a size threshold; above it, counts plus a prompt to "
        "list_grips. Speak the user's chosen vocabulary from your first "
        "reply."
    ),
    "identify": (
        "Preview a fretting without storing it: ranked candidate readings "
        "over the resolved tuning (default_tuning when omitted), optionally "
        "under a context_key. The top candidate is the most literal "
        "complete reading, not 'the answer' - present alternatives and "
        "calibrate on decided_at. interval_root='auto' follows THIS call's "
        "ranking. Also the verification half of the name->shape bridge: "
        "check shapes you proposed before showing them."
    ),
    "add_grip": (
        "Capture a grip - one call in the common case. strings is LOW to "
        "HIGH (a reversed array is the one error validation can't catch: "
        "verify via the echoed pitches). chosen resolves the user's own "
        "name against the full candidate set (three tiers, "
        "enharmonic-safe); a miss stores the grip anyway with a "
        "chosen_miss warning and suggestions - repair with set_reading, "
        "never re-send. No settled name yet? Put the working title in "
        "label and leave chosen unset. Hammer-ons/pull-offs: capture "
        "BOTH shapes as separate grips and sequence them adjacently - "
        "each gets a real identity and the transition becomes ordinary "
        "voice-leading, which is what analysis wants; note the "
        "technique in tags or the journal. Renders are opt-in "
        "(render=true); prefer one strip render per sequence. "
        "Fingerings may differ per context: the same shape refingered to "
        "ease the reach into the next chord is a separate grip or an "
        "update_grip away."
    ),
    "get_grip": (
        "Fetch one grip: definition, resolved pitches, cached candidate "
        "readings, chosen (with stale flag if the engine no longer "
        "produces it)."
    ),
    "list_grips": (
        "List grips (ids, labels, chosen names, tags). Use the user's "
        "chosen names when talking about them."
    ),
    "update_grip": (
        "Patch a grip (shallow merge; explicit null deletes an optional "
        "field; id and created are immutable). The merged result is "
        "re-validated whole, caches re-derive, and a newly-staled chosen "
        "is surfaced immediately with the new top candidate."
    ),
    "rename_grip": (
        "Rename a grip id, rewriting every sequence occurrence atomically."
    ),
    "remove_grip": (
        "Delete a grip. Refuses while any sequence references it (every "
        "occurrence counts) unless force=true."
    ),
    "set_reading": (
        "Record the user's name for a grip ('that's my Gm'). Resolves "
        "against the FULL cached candidate set in three tiers (exact "
        "canonical; root + quality; root + family) with enharmonic and "
        "Unicode-accidental normalization; ambiguity errors list the "
        "matches - ask the user, don't guess. This is the repair path "
        "after a chosen_miss."
    ),
    "transpose": (
        "Transpose a stored grip (id=...) XOR a raw shape (strings=..., "
        "tuning resolving via default_tuning when omitted) by semitones. "
        "Fingers carry verbatim for closed shapes; previously-open "
        "now-fretted strings get null fingers and an opens_fretted warning "
        "whose detail carries the count - the pitches are right but the "
        "hand shape changed, so don't present it as 'the same grip moved "
        "up'. Below-fret-0 errors speak capo-relative. With save_as, "
        "chosen transposes covariantly by re-derivation and derived_from "
        "records provenance."
    ),
    "set_sequence": (
        "Create or replace a named sequence. Items are grip ids or "
        "'@other-sequence' references, so song structures compose "
        "without duplication: verse and chorus stay single sources of "
        "truth and song = ['@verse', '@chorus', '@verse'] follows their "
        "edits. Repeats allowed; cycles refused; mixed tunings render "
        "per-grip."
    ),
    "list_sequences": (
        "List sequences: raw items (incl. @references) plus the "
        "flattened grip ids."
    ),
    "remove_sequence": (
        "Delete a sequence. Refuses while another sequence references it "
        "as @name unless force=true (which also drops the references)."
    ),
    "render": (
        "Render grips (ids=[...]) XOR a sequence (sequence=..., "
        "@references flattened) to a chart strip (PNG only, on disk). "
        "Finger digits draw inside the dots automatically (T = thumb); "
        "labels beneath carry full pitches with octaves: "
        "notes/intervals/none. interval_root 'auto' follows chosen's "
        "root, else the top candidate's. Identical requests overwrite "
        "idempotently."
    ),
    "analyze": (
        "Analyze a sequence (@references flattened): Roman numerals in "
        "the top candidate keys (all 24 scored by the frozen R0 rule; "
        "pass keys=[...] to override), bass line with motion, common "
        "tones, per-pair voice leading (minimal monotone matching - "
        "crossings impossible by construction), and modulation "
        "segmentation by key membership. The user's chosen readings "
        "drive every step (display candidate = chosen else top). "
        "Numerals are null where a step is chromatic to that key - "
        "stated, not judged; segmentation is membership, not cadence "
        "inference. YOU narrate what the segments and motions suggest; "
        "the server never asserts a hearing. Read-only."
    ),
    "journal": (
        "Record an observation or context note on the project - the "
        "accumulating context that turns working titles into settled "
        "names ('the pass grip wants to resolve down', 'bridge feels "
        "like it needs open C'). Recent entries resume with "
        "describe_workspace. Journal liberally."
    ),
    "list_journal": "Read journal entries, newest first; filter by tag.",
    "history": (
        "The project's mutation log, newest first: every stored change "
        "(tool + detail + timestamp) - the progress record without "
        "leaving the conversation."
    ),
    "define_tuning": (
        "Define a tuning by explicit pitches (low to high) or as "
        "from+capo (capo-relative frets; absolute pitch = open + capo + "
        "fret). Refuses to redefine 'standard' or any name referenced by "
        "grips or default_tuning; from-chains resolve recursively with "
        "cycle detection."
    ),
    "remove_tuning": (
        "Delete a tuning. Refuses while any grip references it, while it "
        "is the default_tuning, or while it is the declared instrument "
        "tuning."
    ),
    "find_voicings": (
        "Search playable voicings of a chord in any tuning (frets are "
        "capo-relative automatically). chord is root + a specific quality "
        "suffix, optional /bass as a hard bass constraint (a family like "
        "'sus' is refused with the member list). Playability model: span "
        "<= 4 frets (cap 5), <= 4 fingers with barre detection, optional "
        "thumb-over via constraints.allow_thumb. Ranking is deterministic "
        "and documented (root-in-bass, near_fret closeness, fewer inner "
        "mutes, fuller, fewer fretted, tighter span, lower position) - "
        "never tuned weights. Results are exact by construction; no "
        "identify verification needed. render=true adds a chart strip of "
        "the top results. Fingerings are suggestions."
    ),
    "render_neck": (
        "Render the neck with an overlay: every position of a key "
        "(overlay_key, context_key grammar) or an explicit pitch set "
        "(overlay_pitches, first entry emphasized) across a fret range, "
        "in any tuning. The tonic/root draws filled, other members as "
        "rings, spelled as the key spells them."
    ),
    "set_instrument_tuning": (
        "Declare what tuning this project's instrument is in, with "
        "history ('in dadgad since ...'). Supersedes the bare "
        "default_tuning: capture defaults follow the declaration. The "
        "server tracks declarations, not guitars - two projects can "
        "disagree about one physical instrument, deliberately. When a "
        "previous declaration exists, the response includes the retune "
        "plan from it. render=true adds a tuning card."
    ),
    "retune_plan": (
        "Per-string semitone deltas between two tunings with direction "
        "and a suggested order (downs first to release tension, then ups "
        "to approach pitch from below, each low to high). from_ defaults "
        "to the declared instrument tuning. Warnings are direction + "
        "magnitude heuristics ONLY - the server cannot know the string "
        "set, so 'up 5 semitones is aggressive' is as far as it goes; "
        "don't present them as string-break predictions. Capo-derived "
        "tunings compare sounding pitches (a capo change is not a peg "
        "turn). render=true adds from/to tuning cards via the strip "
        "machinery."
    ),
}

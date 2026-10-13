# Plugin UI contracts 0.3.1 — validation report

Evidence record for the commissioned-preset firmware gate (issue #444; design
`.claude/deep-review/2026-10-12-issue444-commissioned-preset-firmware-design.md`,
committed on the branch before any acceptance test landed, with its
pre-committed acceptance rule §7). The 0.3.0 increment's evidence record
remains in `standards/plugin-ui/0.3.0/validation-report.md`, digest-frozen
with its tree.

## What moved

plugin-ui 0.3.0 → 0.3.1, PATCH (additive machine errata — the
backwards-compatible row; the mirror image of the #62 MINOR, which
tightened valid→invalid where this loosens invalid→valid with nothing
removed or retyped). Copy, never move: 4 new corpus rows citing
`standards/plugin-ui/0.3.0/*` as `source`, digests moved only by
`benchweave.standards repin`; the predecessor tree is untouched and its
rows verified frozen by the same command.

Validator semantics (`src/benchweave/presentation/contracts.py`,
`validate_preset`): the firmware gate becomes policy-aware as three rules —
(1) the preset's own `supported_firmware` list always applies to a supplied
value; (2) `firmware is None` is admissible only under
`firmware_policy: "commissioned"`; (3) a descriptor-DECLARED list is
enforced regardless of policy (None is not a member). The unreachable
`"any"` arm is removed (`firmware_policy` is `["listed", "commissioned"]`
in every OTDP schema version in this tree, and the gate only sees
OTDP-validated descriptors). The refusal is byte-identical where it fires:
code `incompatible_firmware`, path `preset.supported_firmware`, message
"A known firmware compatible with the descriptor and preset is required" —
so every consumer, including the standalone apply path's conflict mapping,
is unchanged.

Version sweep: all THREE version-literal sites in the corpus-owned code
row move 0.3.0 → 0.3.1 (the path-shaped `SCHEMA_ROOT` literal and the two
bare `contract_version` consts); the zero-literal register row's
`expected_sites` stays 3, its reason text records the motion.

Range motion (G-3 territory; coordinator ruling referenced in the PR body
at landing): the served range slides narrow `>=0.3.0,<0.4.0` →
`>=0.3.1,<0.4.0`, forced by the one-live-object rule (the bundle lists
`contracts.py` in every carried version's row). 0.3.0 pins re-stamp to
0.3.1. In-tree re-stamps: the sim_scope presentation documents (5 files:
envelope, manifest, catalogue, 2 presets) with the digest chain re-derived
(preset bytes → manifest asset pins → presentation manifest pin; the
descriptor and settings-schema bytes are unchanged), and the SDK fixture
plugins (setpoint, binary_frames) plus the scaffold byte-parity fixtures
(regenerated through the release-cut regen arm at SDK 0.11.0).

SDK-side riding pieces: the `benchweave_sdk_server` authoring helper
(`_validated_preset`) gains the commissioned arm — an empty firmware
candidate list under commissioned policy validates once with
`firmware=None` instead of refusing "no firmware to judge the preset
against" (that refusal keeps its force for non-commissioned policies);
`_preset_firmwares`' docstring records the division. The apply path
(`seam.py::_op_preset_apply`) is unchanged by design: it refuses
`not_ready` before the gate when no firmware is established, and with an
established firmware rule 1 governs.

## Evidence (design §7, pre-committed acceptance)

- **Commissioned-admit arms, RED pre-fix (gateway, junitxml counts).**
  `tests/unit/test_presentation_presets.py`: tests=22 failures=2 —
  `test_commissioned_policy_admits_missing_firmware` and
  `test_commissioned_policy_admits_preset_listed_firmware` each failed with
  exactly `Finding(code='incompatible_firmware',
  path='preset.supported_firmware', message='A known firmware compatible
  with the descriptor and preset is required')` (the issue's quoted
  refusal, reproduced synthetically against a commissioned fixture
  descriptor carrying the corpus's reference-can pattern). Post-fix the
  same file is tests=22 failures=0.
- **RED, SDK twin arms.** `tests/test_presentation_cli.py` +
  `tests/server/test_authoring.py`: tests=43 failures=3 pre-fix (the two
  twin admit arms plus
  `test_preset_put_commissioned_project_validates_without_a_firmware_source`,
  which failed at `_preset_put` with "the preset would not validate: 1
  finding(s)" — the same gate finding). Post-fix tests=67 failures=0 over
  the three files including the apply-path pins.
- **G3 RED-sanity (acceptance ii).** With ONLY the gate restructure
  reverted (cp backup, version sweep left in place), the gateway preset
  file returns to tests=22 failures=2 with exactly the two admit arms
  failing; restored, tests=22 failures=0. The proof is not vacuous.
- **Negative controls (acceptance iii).** C2 (listed-policy mismatch)
  stays pinned by the untouched `test_requires_known_compatible_firmware`
  [None/2.0]. C3 (commissioned preset-list mismatch), C4 (listed + None),
  and the two declared-list enforcement arms (rule 3) each refuse with the
  exact `(code, path, message)` triple, in both repos, before and after.
- **Widening-only proof (acceptance iv).**
  `test_listed_policy_corpus_admits_with_no_findings[fast-survey/low-noise-pair]`
  validates the shipped sim_scope corpus (N=2) through the live gate with
  the corpus action catalogue resolved — `report.findings == ()` before
  and after (the tuple was empty under the predecessor gate for exactly
  these documents and stays empty).
- **Copy-never-move (0.3.0's row set unchanged).** `repin` re-pinned
  exactly 4 rows, all `plugin-ui/0.3.1/*`; the frozen-row discipline
  verified the predecessor bytes in the same run. The standards-manifest
  keeps 0.3.0's migration-note entry beside 0.3.1's (both retained
  versions carry from-predecessor notes).
- **Gates.** Zero-literal gate green over gateway/plugins/docs/scripts
  (register row count stays 3); docs baseline refresh diff is exactly the
  project-index link swap (2 rows). `benchweave.standards check` and the
  `tests/standards/test_check` mirror/anchor lanes are red on this branch
  BY THE LANDING SPLIT: they compare a fresh export against the SDK
  submodule's lock, and the pointer does not move until the landing
  train's same-commit advance (issue #408's rule). The same class covers
  the shipped-package sim_scope lanes in `tests/sdk/` that drive the
  submodule CLI against the re-stamped presets.
- **Real-consumer evidence.** The design's pre-fix measurement named the
  owner's commissioned consumer descriptor; it was not available to this
  build pass, so the mechanism ships on synthetic + corpus evidence per
  the design's UNDERPOWERED clause — the issue stays open with the closing
  claim downgraded to "mechanism verified on fixtures; operator
  confirmation pending", and the owner's check run is the reopen evidence.

## Honest interim

None on the gate itself. Render-time firmware resolution for commissioned
devices stays deferred (design D1): the read-only UI renders all
structurally-valid presets and availability is decided at apply, where the
established-firmware gate refuses before any write.

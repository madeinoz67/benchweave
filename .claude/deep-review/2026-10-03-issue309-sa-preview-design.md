# Issue #309 — PRD 11/12 SA-PREVIEW: the standalone host as the author's preview, carrying the 2026-10-02 packaging rulings: design record

**Date:** 2026-10-03 · **Tracker:** madeinoz67/benchweave #309 (sub-issue of #282; raised from PRD 12 §11 dependency 4a)
**PRDs:** `docs/implementation-planning/11-standalone-web-ui-prd.md` v0.2 (§6 h, §7 NFR-P/NFR-O3, §8 Q1 — see §13 stale-prose flags), `docs/implementation-planning/12-gateway-web-ui-prd.md` (§8 R-5/R-9/R-10, §9 Q4/Q5 rulings, §11 dependency 4a)
**Owner rulings carried (2026-10-02, issue #309 comment — design inside these, not re-litigated):** (1) `benchweave_standalone` → `benchweave_sdk_server`; (2) one `src/` tree (`src/benchweave_sdk/` + `src/benchweave_sdk_server/`); (3) distribution `benchweave-sdk[server]` optional extra — one install surface, PKG-1/PKG-2 hold via the minimal default install, REVERSING PRD 11 §8 Q1's "option 2"; (4) publishing/maintenance stay low-friction — one package; (5) no separate I1 retrofit — the rename/unification IS this slice.
**Evidence baseline:** gateway `origin/main` `46410da`; SDK `main` `d932bea` (the standalone checkout at `~/Documents/src/benchweave-sdk`, read-only for this design). PyPI facts checked 2026-10-03: `benchweave-standalone` **never published** (no matching distribution); `benchweave-ui-html 0.1.0` published (ships `benchweave_ui_html/assets/{tokens,themes,globals}.css` + its own `inventory.json`, deps jinja2/markupsafe); `fastmcp 4.0.3` extras are `anthropic, apps, azure, code-mode, gemini, openai, tasks` — **no `server` extra** (confirms the I1 accepted-risk).
**Files read for this record:** SDK `standalone/src/benchweave_standalone/{session,transport,seam,web,cli,assets}.py` + `templates/{base,device,readings}.html` + `standalone/pyproject.toml` + `.github/workflows/{standalone,ci}.yml`; SDK `src/benchweave_sdk/{scaffold.py ADAPTER/PROTOCOL, preview_models.py, fixtures.py generate_baselines, pyproject.toml}`; SDK `tests/test_zero_literal_gate.py` + `scripts/count_version_literals.py` (scope `src/benchweave_sdk` only); gateway `docs/internal/{invariants,review-rubric}.md`, PRD 11, PRD 12 §8–11, `.claude/deep-review/2026-10-01-issue283-i1-skeleton-design.md` (the I1 record — placement provisional pending exactly this ruling); a descriptor fixture's parameter rows (`type`, `range`, `unit`, `access`).

---

## 1. Problem and root cause

Two things are missing at once, and the 2026-10-02 rulings fuse them into one train:

1. **The packaging premise I1 shipped under is now wrong.** I1 landed `standalone/` as a sibling distribution (`benchweave-standalone` 0.1.0, own pyproject/lock/wheel/CI) explicitly as a *relocation-cheap throwaway path* pending Q1's formal ruling (I1 record §2: "Q1's formal ruling is scoped to I3… this is the PRD's own 'throwaway package path' note"). The ruling arrived 2026-10-02 and chose the shape the PRD ranked option 1: the SDK distribution itself, as an optional extra. The ruling also re-names the thing: "standalone" names a mode, "server" names the thing — `benchweave_sdk_server`.
2. **The author's preview does not exist as a live pipeline.** PRD 12 Q4 (ruled 2026-10-01): *there is no separate preview tool* — the standalone host IS the preview. Today the host serves only the author's own plugin over a vectors-derived mock script whose readings are always quality `valid` (root cause, verified: the scaffold adapter template hardcodes the read envelope — `scaffold.py:82` `"quality": "valid"`; the transport bytes carry only the value, so **no transfer script can drive `stale`/`critical`/`trip` through the author's adapter — the adapter launders every response to `valid`**). The nine baseline states the React preview showed (generated presentation documents, no adapter, no transport — `fixtures.py::generate_baselines` rows: normal, loading, stale, disconnected, warning, critical, trip, recovery, request-rejected) have no live-pipeline expression, and a project whose adapter fails to import refuses startup entirely (`session.py load_plugin_project` raises before any port binds), so an author with a broken adapter sees nothing.

This slice makes the host the author's preview per dependency 4a and lands the packaging rulings as the same motion (ruling 5).

## 2. Verdict and shape — two stacked slices, one train

**BUILD, as two stacked slices** merging bottom-up under issue #309:

- **Slice A — packaging restructure (the rulings).** Pure motion + packaging: rename, unify under `src/`, fold the sibling distribution into `benchweave-sdk[server]`, fold CI, extend the version-literal gate scope, graceful-degrade console entry. No behavior change beyond packaging and names. Shippable alone as the SDK's 0.6.0 (the extra is additive; the never-published sibling distribution means zero external breakage — verified on PyPI).
- **Slice B — preview semantics (dependency 4a).** Transport selection as a seam concept, the nine scenario scripts + the scenario adapter, the `simulated` banner rule, the no-write-on-load proof, the adapter-failure layout render, and consumption of the published `benchweave-ui-html` wheel at a pinned version (the issue's "Ready when" trigger names #302's release as *the host consumes the published wheel*; PRD 12 Q5 rules the mechanism).

**Why split (the recommendation asked for):** (i) review-signal isolation — slice A's diff is dominated by `git mv` + packaging metadata; slice B is all behavior; interleaving them buries the behavior review in rename noise, and the #254/stacked-PR doctrine exists for exactly this; (ii) independent shippability — A alone is a releasable packaging event that fixes two I1 accepted-risks (`fastmcp[server]` names a non-existent extra; the wheel lacks an SDK floor — both dissolve when the sibling distribution dies) and closes the `standalone.yml` path-filter hole (the workflow dies); (iii) #308 (the `preview-ui` shim) is blocked on knowing the final entry-point name — A landing first unblocks its design; (iv) if B's scenario mechanism hits an honest wall, the rulings are not hostage to it. **B's base = A's branch**; the stack is the #309 exit gate.

## 3. Slice A — the packaging restructure

### 3.1 Move map (SDK repo, `~/Documents/src/benchweave-sdk`)

| From | To | Nature |
|---|---|---|
| `standalone/src/benchweave_standalone/` | `src/benchweave_sdk_server/` | `git mv` (history-preserving); all intra-package imports are already relative — only docstring references (`web.py` names `benchweave_standalone.security.GuardPolicy`) and the module docstrings' self-naming change |
| `standalone/tests/` (9 files + conftest) | `tests/server/` | `git mv`; flat SDK `tests/` has no name collisions (checked), but the subdirectory keeps the generic names (`test_cli.py` etc.) from colliding as the tree grows |
| `standalone/pyproject.toml` | — deleted | dependencies fold into the root `[project.optional-dependencies] server` (below); `[project.scripts]`/`[tool.uv.sources]`/hatch packages fold likewise |
| `standalone/uv.lock`, `standalone/venv/`, `standalone/.gitignore`, `standalone/README.md` | — deleted | one lock/venv per repo again; the README's content folds into the SDK README (§3.5) |
| `.github/workflows/standalone.yml` | — deleted; `ci.yml` gates job extended | `uv sync --locked --extra test` → `uv sync --locked --extra test --extra server`; one tree, one gate — closes the I1 accepted-risk "standalone.yml path filter skips gates for SDK-src-only PRs" by construction |

### 3.2 The root `pyproject.toml` (the exact edits)

```toml
[project.optional-dependencies]
test = ["pytest>=8.0", "httpx>=0.27"]          # httpx folds in from the subtree's test extra
server = [
  "fastapi>=0.141.1",
  "fastmcp==4.0.3",                             # NO [server] extra — fastmcp 4.0.3 publishes none
  "jinja2>=3.1",
  "uvicorn>=0.52.4",
]
[project.scripts]
benchweave-sdk = "benchweave_sdk.cli:main"
benchweave-sdk-server = "benchweave_sdk_server.cli:main"
[tool.hatch.build.targets.wheel]
packages = ["src/benchweave_sdk", "src/benchweave_sdk_server"]
```

- **`fastmcp==4.0.3` plain** fixes the I1 accepted-risk (`fastmcp[server]` named a non-existent extra; its base install already requires `fastmcp-slim[client,server]` — verified from the wheel METADATA).
- **`benchweave-ui-html==0.1.0` is NOT in slice A** — the pin lands in slice B with the code that consumes it, so no slice ships a dependency nothing uses.
- The `[server]` extra is aligned with the gateway's shared pins (NFR-P2) exactly as the subtree declared them; the SDK-floor accepted-risk dissolves (the distribution is its own floor).
- `sdist` include `/src` already covers both trees; `force-include` standards-lock unchanged; templates and the remaining vendored assets ride inside the package directory (hatchling includes package data by default) — pinned by the fresh-venv wheel census in the acceptance rule.

### 3.3 The unconditional console script and the graceful degrade

Python extras cannot gate console scripts, so a default (`pip install benchweave-sdk`) install *gets* a `benchweave-sdk-server` command. The design adopts the PRD's own R-9 shim pattern as the precedent (exit non-zero with a `snake_case:` prefixed error naming the install command): `cli.py`'s command bodies already import the heavy stacks lazily (`serve` does `from .web import build_app` inside the body); slice A completes that — the `serve` and `mcp` bodies wrap their imports in an `ImportError` guard that prints `benchweave_sdk_server_extras_missing: install 'benchweave-sdk[server]'` and exits 2. `--help` works on a default install (click is a base dependency; the CLI module itself imports nothing from the extra set). The honest negative is first-class: the base install *can* name what it lacks.

### 3.4 The version-literal zero gate inherits the duty (I1 record §6 said so)

`scripts/count_version_literals.py` scopes to `SOURCE_ROOT = src/benchweave_sdk` only. The I1 record recorded that "folding the tree into a scope is part of Q1's ruling, recorded here so that ruling inherits the duty." Slice A extends the counter to walk `src/benchweave_sdk_server/` as a second source root with an **empty register** (the tree is literal-free: the SDK version is derived via `importlib.metadata`, never a literal — the I1 rule carried forward), and updates `tests/test_zero_literal_gate.py`'s scope assertion. `docs/development.md`'s packaging census and the drift obligations walk name no new rows for A beyond this scope extension.

### 3.5 Docs surfaces (A)

- SDK README gains the server section (folded from the subtree README): what `[server]` installs, the entry point, the mock-transport posture. **This is published user-facing documentation — ASD-STE100 register; the build brief dispatches `document-writer` for it** (CLAUDE.md's documentation register rule).
- CHANGELOG: rendered by git-cliff from conventional commits — the rename is recorded as breaking for subtree users of `benchweave_standalone` (the distribution was never published; the audience is in-tree only, disclosed as such).
- **PRD 11 stale prose (gateway side)** — verified stale against the ruling, flagged per the brief; the fix is a one-commit PRD-11 v0.3 amendment riding this train's gateway-side motion: Summary headline 4 ("Not in the SDK wheel… Recommended home: a sibling distribution") — reversed by ruling 3; §8 Q1 (recommends option 2) — ruled option 1's extra; NFR-P1 ("Web, MCP and serial dependencies live in the standalone distribution") — now "in the `[server]` extra; the default dependency set is unchanged"; SW-02's `benchweave-standalone serve` — `benchweave-sdk-server serve`; §9 I1's "throwaway package path" note — mark resolved by the ruling. PRD 12 needs no amendment (its Q5 already rules the wheel consumption).

## 4. Slice B — the preview semantics (dependency 4a)

### 4.1 Transport selection — the difference is the transport, not the server

The seam already carries `transport_kind` (`StandaloneSeam(session, transport_kind=…)`; `host_info` reports it). Slice B makes the selection a first-class composition step instead of a hardcoded literal in `_build_seam`:

- A `services_factory` stays the seam's only notion of a transport; the CLI's `--transport` (choices `["mock"]` today; `serial` is I3's D3) selects which factory is built. `serve <project>` without a device remains the mock path — **selectable without hardware is already the default; what B adds is that nothing server-side knows or cares which transport is bound** (the acceptance proves it with a second, non-mock transport kind).
- The **real-transport arm is I3** (the serial provider backend is I1-deferral D3; no real transport exists SDK-side — the SDK dependency set has no serial library). Slice B's honest proof of transport-invariance: the banner rule and the no-write rule are pinned as pure functions of `transport_kind` / the read-only catalogue path, exercised over **two** transport kinds in tests — the shipped mock and a test-only non-mock recording double (a `HostServices` wrapper, never shipped). The design states plainly: *real-hardware discrimination becomes exercisable at I3; this slice proves the mechanism, not the metal.*

### 4.2 The nine baseline scenarios — definitions shipped, scripts derived, states through the pipeline

The load-bearing fact (§1): the author's adapter cannot express the states (quality laundering). Therefore the states arrive through a **host-shipped scenario adapter**, and the scripts are **derived per plugin from declared data** — exactly `mock_exchanges`' precedent (I1: "the script is derived from the plugin's declared data, not hardcoded host knowledge of any one plugin"). A canned script cannot know an arbitrary plugin's parameter names; derivation from the descriptor is the only shape that works for "a plugin from anywhere."

- `benchweave_sdk_server/scenarios.py`: the nine scenario definitions **shipped as data** — the ids, titles and state policies verbatim from `fixtures.generate_baselines`' rows (`normal, loading, stale, disconnected, warning, critical, trip, recovery, request-rejected` — the parity suite NFR-Q2's baseline set). A scenario's policy says, per readable parameter: what quality string the device reports, whether the value is present, and whether the exchange is refused.
- `ScenarioAdapter` (host-shipped, implements the SDK `Adapter` lifecycle — REG-1 discipline: fresh instance per session, no import side effects): speaks a scenario protocol `R:<parameter>\n → <value>,<quality>\n` (establishment `ID?\n → <identity>` when `identify` is declared). Read envelopes carry `{parameter, value, unit (from the descriptor), quality (from the script), observed_at, age_ms: 0, source: "scenario"}` — the quality is a device-declared string rendered verbatim (ui-contract ST-3's channel; the readings table's quality column already renders it).
- `scenario_exchanges(plugin, scenario_id)` derives the transfer script: per readable parameter, the value is **derived from the descriptor's own declaration** — midpoint of the declared `range` when present, else a type-canonical finite value keyed on the parameter's `type` (float/int/string/bool) — the A02 posture (the descriptor's declared data; the host invents no envelope).
- Scenario-by-scenario honest translation through the live pipeline (what the page shows): `normal` → value + quality `valid`; `loading` → value absent + quality `loading`; `stale` → quality `stale` (visible in the quality slot; the computed staleness verdict is I2's §B.4 work — two channels, ST-3, never laundered); `disconnected` → the establishment exchange refuses — connect fails `not_ready`, the page renders the refused state (through the pipeline, disconnected IS a refused connection — the honest negative); `warning`/`critical`/`trip` → in-range value + the state's quality string; `recovery` → quality `recovering`; `request-rejected` → the scripted exchange yields a `DEVICE_REJECTED` envelope (dispatch_state `dispatched`) on the read path — the refusal renders as the readings refused state carrying the adapter code verbatim (SW-12 distinctness), the live-pipeline analog of the old `SimulatedReceipt`.
- **Selection:** `serve <project> --scenario <id>` (initial selection; refused with a prefixed error when `--transport` is not `mock` — scenarios do not exist on real hardware, the banner rule's sibling) and a scenario `<select>` on the device page (HTML POST + CSRF, the connect-button idiom; mutates the mock factory's *next-connection* script — the M1 fold's per-connection services means the swap takes effect on reconnect, honestly). Scenario switching is NOT a catalogue operation in this slice (the SW-10 closed set stays untouched) — the deferral carries it (§9 D-B3).
- The scenario adapter is also the vehicle for the adapter-failure story (§4.5): scenario mode never imports the author's adapter at all, so an author with a broken adapter still sees their own descriptor's pages in all nine states — the tightest reading of dependency 4a's last bullet.

### 4.3 The `simulated` banner — on mock only, never on real hardware

- `base.html` gains a second banner element, rendered **iff `seam.transport_kind == "mock"`** — a pure function of the transport kind, evaluated once per render from `app.state.seam`. Copy: `SIMULATED — mock transport` (PRD 12 §D.1's rule, visible). The persistent `STANDALONE — no gateway` banner (SW-27) renders on **both** transports, unchanged.
- Scenario mode implies mock (enforced), so scenario runs carry the simulated banner — correct: they are simulated.
- Tests: the mock app's pages contain the element; a test app built over a **non-mock transport kind** does not contain it (asserted absent — the discrimination arm); a template test refuses the element when the flag is false.

### 4.4 No write on page load (NFR-O3) — proven, not presumed

Page-load paths already call only read-side catalogue operations (`device_discover`, `device_get`, `parameter_read`; connect/disconnect are explicit POSTs). The proof: a test-only **verb-recording wrapper** at the adapter boundary (records every `execute()` verb) plus the transport's exact-match discipline at the frame boundary (an unexpected write frame `ConformanceError`s). Arms: (1) full page load + 3 poll cycles on the mock transport → recorded verb set ⊆ {`identify`, `read`}; (2) the same over the non-mock recording double → ⊆ {`identify`, `read`}; (3) **instrument control**: drive a write verb through the recorder directly (`session.execute("write", …)`) and watch it recorded — proving the instrument can hear writes (a deaf recorder passes everything; the control kills that false pass).

### 4.5 Adapter-failure layout render (SW-73) — the loader splits

`load_plugin_project` currently refuses startup on ANY failure (SW-05). Dependency 4a requires: *presentation validates but the adapter fails to import or load → pages render their layout, device operations `not_ready`, load diagnostic shown.* The split:

- **Document failures** (missing `src/`, unreadable/invalid descriptor, invalid presentation) — refuse startup exactly as today (SW-05 unchanged; SRF-2/R-10's refusal agreement is not weakened).
- **Adapter failures** (`ImportError`/`AttributeError` on the entry point, a missing/invalid entry point string) — become a **degraded load**: the result carries `adapter_factory=None` + the prefixed load diagnostic (`standalone_plugin_import:` etc. — the existing prefixes, kept verbatim under the new module's naming). `PluginSession.connect()` refuses `not_ready` carrying the diagnostic; the seam's device operations answer `not_ready` with a `load_diagnostic` detail; `_render_device` renders the layout (parameter rows, connect control, banners) with the diagnostic in the existing refused-state notice — the author sees a UI before the adapter works. `serve` prints the diagnostic to stderr and binds the port (exit 0); `--scenario` on the same project serves the nine states (§4.2) — the two mechanisms compose.
- REG-2 discipline unchanged: the degraded state is honest (`not_ready`), never a fabricated empty device.

### 4.6 Consuming the published `benchweave-ui-html` wheel (Q5, NFR-P2, I1-D5's closure)

- Slice B's pyproject edit: `server` extra += `benchweave-ui-html==0.1.0` — an **exact pin**: PRD 12 Q5 rules that "a contract change reaches standalone through a package release and a pin bump in the SDK repository, never through a copied template." The exact pin IS the mechanism; a range would re-open silent drift.
- `assets.py` re-points `tokens.css`/`themes.css` at the installed `benchweave_ui_html` package (its own `assets/` tree with its own `inventory.json`; the package's own verification API is the authority — the host calls it rather than re-hashing, one verifier per byte set). `htmx.min.js`, `sse.js`, `standalone.css` stay host-vendored under the host's inventory (they are the host's, not the renderer package's). The host's copied `tokens.css`/`themes.css` are deleted — **closing I1 deferral D5** (the cross-repo freshness gate is superseded by the ruling's shape: freshness arrives by release + pin bump; the digest-verify-at-serve discipline is kept for tamper detection). `globals.css` and the component partials ride with I2's SW-22 adoption (not this slice — the shell templates are the host's own until then).
- The gateway-side drift row for the renderer surface (obligation 12) gains the SDK pin as a named motion surface (a ui-html release must be followed by an SDK pin bump) — a one-row docs amendment in this train's gateway-side commit, alongside the PRD-11 amendment.

## 5. Precedent table (principle 9 — extend, don't invent)

| Piece | Proven in-tree mechanism being extended |
|---|---|
| The `[server]` extra, one distribution | the SDK's existing optional extras (`test`, `signing` — the `signing` extra is the same "optional so the default never loads the stack" pattern, owner-ruled 2026-10-02 on #223) |
| Graceful-degrade console entry | PRD 12 R-9's shim pattern (prefixed error naming the install command), adopted one slice early |
| Scripted transport derivation from declared data | `session.py mock_exchanges` (vectors.json → script); scenarios derive from the descriptor the same way |
| The scenario adapter | the SDK `Adapter` protocol lifecycle as the scaffold template implements it (`scaffold.py` ADAPTER — the conforming client shape, re-implemented host-side) |
| The nine scenario definitions | `fixtures.py generate_baselines`' rows, carried verbatim as the baseline set NFR-Q2 checks |
| Banner-as-data | `web.py BANNER` + `base.html`'s banner element (I1); the simulated banner is the same mechanism keyed on transport kind |
| Loader split (documents fatal, adapter degraded) | the existing `PluginLoadError` prefix discipline + the refused-state notice rendering (`web.py` M1 fold) |
| Wheel-consumed assets with verification | `benchweave_ui_html`'s own inventory + verifier (the `bundled_assets`/`verify_ui_assets` family, NFR-P3 posture — the authority moves from a local copy to the installed package) |
| CI fold | the SDK's existing gates job (one tree, one gate); deleting `standalone.yml` rather than renaming it |

New architecture introduced by this design: **none.** The scenario adapter is new code, but it is the scaffold-adapter shape with a different protocol — not a new architectural element.

## 6. Invariant impacts (walk of `docs/internal/invariants.md`)

- **CTL-\*, STO-\***: untouched — no gateway control/state code moves; standalone deliberately has no protective transition, leases or store (PRD non-goals). A04-relevant property remains *honesty*: `host_info` + banners state the mode and the absent guarantees.
- **CON-4/PKG-1/PKG-2**: reframed by ruling 3, not violated — the **default** install's dependency set is unchanged (acceptance A-E proves it in a fresh venv); the wheel's *contents* now include the server package's bytes (extras are dependency sets, not file sets — the ruling's stated basis). The standards lock, vendored tree and `check-sdk-standards` are untouched; the standards tripwire (`git diff origin/main...HEAD -- standards/`) is reported empty in the acceptance.
- **CON-5 (A13)**: the seam stays the only device path; the scenario select route mutates host state (the mock factory), not device state — the same class of host-side mutation the I1 review already classified (authoring writes), disclosed here the same way. No catalogue growth in this slice.
- **REG-1/REG-2**: the scenario adapter follows the lifecycle (fresh instance, `open` binds, per-op contexts, idempotent-tolerant `close`); envelopes pass through with codes preserved; the degraded-load state is `not_ready`, never a fabricated device.
- **Obligation 12 (renderer surface)**: the pin becomes the reach mechanism — the drift row amendment names the SDK pin as a motion surface (§4.6).
- **Version-literal zero gate (obligation-20 family)**: scope extended to `src/benchweave_sdk_server/`, empty register (§3.4) — the duty I1's record made this ruling inherit.
- **Frozen `preview_assets` bundle (PRD 12 R-5)**: unchanged by this slice — its deletion is #308, whose start this ship authorizes. The exception's exit is recorded as this train's merge.
- **No new invariant rows.** Promotion candidate for I2: the banner-follows-transport rule (a renderer-neutral contract row, at home in `ui-contract.md` with the ST rows).

## 7. Acceptance rule — pre-committed (written before any measurement below ran)

Deterministic functional pass/fail; no timing claims. All commands run in the SDK checkout on the implementation branches; `UV_PROJECT_ENVIRONMENT=venv`; exit codes read unpiped; counts from `--junitxml` attributes or exit codes, never an output-filter summary. Each gate's commands and outputs land in the PR body (whose measurements they are).

### Slice A gates

- **A-E (install surface — the ruling's own proof).** Build the wheel; in **fresh venv 1**: `pip install <wheel>` → `pip list` contains **none** of fastapi/fastmcp/uvicorn/jinja2 (the default stays minimal — PKG-1/PKG-2 as ruled); `benchweave-sdk-server --help` works; `benchweave-sdk-server serve <proj>` exits 2 printing `benchweave_sdk_server_extras_missing:` naming `benchweave-sdk[server]`. In **fresh venv 2**: `pip install '<wheel>[server]'` → the four deps present; `serve` reaches port-binding on a scaffolded project. **KILL if the default install gains any new runtime dependency.**
- **A-W (wheel census).** The installed `benchweave_sdk_server/` tree is byte-compared both directions against the source tree (every file, including `templates/` and `ui_assets/`) — packaging config that drops a template reds here.
- **A-G (static + suite, one tree).** `uv sync --locked --extra test --extra server`; bare `uv run ruff check .` exit 0; fresh-cache (`rm -rf .mypy_cache`) bare `uv run mypy` exit 0; `uv run pytest -q --junitxml=…` exit 0 with collected count ≥ the pre-move count + the moved tests (a collected count of 0 is a FAILED gate — rubric G3).
- **A-R (rename completeness).** `grep -rn "benchweave_standalone" src/ tests/ .github/ README.md` returns **zero** hits (docstring references included); `standalone/` no longer exists; `git diff origin/main...HEAD --name-only -- standards/ src/benchweave_sdk/` is **empty** (tripwire: no standards bytes, no SDK-core bytes move in A).
- **A-Z (zero-literal scope).** `python3 scripts/count_version_literals.py` exits 0 over the extended scope; the count output names the server tree.

### Slice B gates

- **B-S (the nine through the real surface — both arms).** For **each** of the nine ids: build the app on a freshly scaffolded `plugin_new --with-ui` project with `--scenario <id>`; connect; then assert **over HTTP** (the HTML readings partial AND `POST /v1/parameter_read`): the scenario's expected observation — normal → value present (range-midpoint) + quality `valid`; loading → value absent + `loading`; stale → `stale`; disconnected → connect refused `not_ready` + the refused state rendered; warning/critical/trip → the state's quality string; recovery → `recovering`; request-rejected → refused readings with the adapter's `DEVICE_REJECTED` code visible. **RED control:** delete the scenario's script rows → the reads surface `unavailable`/`not_ready` honestly (never template constants) — proving the states come from the transport. Both arms (HTML + REST) assert the same values — the no-laundering pin.
- **B-B (banner discrimination — both transports).** Mock-built app: every page contains `SIMULATED — mock transport` AND `STANDALONE — no gateway`. Test app over a **non-mock** transport kind (the recording double): pages contain `STANDALONE — no gateway` and **do not contain** the simulated banner (asserted absent). Real-hardware discrimination is exercised at I3 (disclosed, §4.1).
- **B-W (no write on page load — both transports + instrument control).** Full load + 3 poll cycles on each transport → recorded verbs ⊆ {`identify`, `read`}; control: a write verb driven through the recorder is recorded (a deaf recorder is a FAILED gate).
- **B-F (adapter-failure render).** A project whose `entry_point` names a missing module (and one with a malformed entry point): `serve` binds (exit 0, diagnostic on stderr); `GET /` and `GET /devices/<id>` render layout 200 with the load diagnostic visible; `POST /v1/device_connect` and `device_get` answer `not_ready` with the diagnostic; **RED:** restoring the I1 loader (documents-and-adapter both fatal) makes `serve` exit 2 — the test catches the regression. Document-failure refusals unchanged (SRF-2 arm: an invalid presentation still refuses startup with the SDK diagnostic).
- **B-U (published-wheel consumption).** In a fresh venv with only `benchweave-sdk[server]` installed (no checkout): `serve` → `GET /assets/tokens.css` bytes **equal** the installed `benchweave_ui_html/assets/tokens.css` bytes (same for themes); tamper control: a corrupted package copy refuses startup (the verifier's discipline holds from the installed location). The host's copied tokens/themes are gone (`ui_assets/` inventory lists only host-owned files).
- **B-G/B-T**: the same static/suite gates as A, on B's branch.

**Ship it if:** every gate above holds on the implementing agent's run with outputs recorded, CI green on both pushed SDK branches, and the gateway-side commits (design record + PRD-11 amendment + drift row) merged per §8's order. #309 closes when the stack is merged — which authorizes #308's start and records R-5's exit condition as met.

**Kill it (the mechanism, not a test defect):** the scenario states cannot be expressed through the pipeline without template constants (B-S's RED control fails in the wrong direction); the wheel assets cannot be served verified from an installed location (B-U unachievable); the extra leaks into the default install (A-E) — stop and re-report rather than warping the design.

**Underpowered, not conclusive:** failures confined to environment (pip/network, port allocation, font/locale rendering) — fix the environment, re-run; no verdict until a clean run. A CI-red on a pushed branch is a hold pending triage, not a kill.

## 8. Landing order (two-repo discipline — recorded, not executed by this design)

1. Slice A SDK branch off `origin/main` (rebase note: open SDK PR #87 `issue347-doctor` touches `src/benchweave_sdk/cli.py` — disjoint from A's `pyproject.toml`/`standalone/`/`src/benchweave_sdk_server/` surface; either merge order works, rebase A if #87 lands first). Full battery before push; SDK PR opened immediately (stacked base: none for A), PR body noting no SDK-side issue exists by design (single stream, gateway #309).
2. Slice B SDK branch with **base = A's branch** (stacked; reviews see only B's delta).
3. Merge bottom-up: A then B (each on the full `gh pr checks` rollup — zero fail, zero pending, `scripts/merge-verified.sh`).
4. Gateway-side commits on this branch (`feat/issue309-sa-preview`): the design record (this file, already first), the PRD-11 v0.3 amendment (§3.5), the obligation-12 drift row amendment (§4.6) — gateway PR after the SDK merges, linked to #309; #309 closes on the full set.

## 9. Deferrals (each with home + observable reopen trigger)

| id | deferred | home | reopen trigger |
|---|---|---|---|
| D-A1 | Serial/real transport kind (`--transport serial`, discovery, the provider backend) | I1's D3, unchanged | the I3 design record committed on its branch |
| D-A2 | SDK release event (version bump to 0.6.0, release-review matrix walk, PyPI publish of the extra-bearing wheel) | the release process (`docs/internal/release-review-matrix.md` walked by the `release-review` skill) | the owner's release call after the stack merges |
| D-B1 | Scenario switching over REST/MCP (a catalogue op pair) — UI select + CLI flag only in B | this record | the I2 design record, or a parity-suite need for scripted switching, whichever first |
| D-B2 | Computed staleness verdicts, severity derivation from readings, manifest-driven rendering (the ST rows' computed channel vs the device-declared quality kept separate) | I1's D2, unchanged | the I2 design record committed on its branch |
| D-B3 | `globals.css` + component partials adoption from `benchweave-ui-html` (SW-22) | I1's D2 | the I2 design record committed on its branch |
| D-B4 | The banner-follows-transport rule promoted to a renderer-neutral `ui-contract.md` row | this record (§6 promotion candidate) | the I2 design record, or a second consumer (the gateway G2 UI) naming the need, whichever first |
| D-B5 | ui-html pin-bump motion beyond 0.1.0 (the obligation-12 amendment names it; the first ui-html release after this slice exercises it) | the drift row | the first `benchweave-ui-html` release > 0.1.0 |

The I1 NIT list (hardening pass) remains deferred as recorded — trigger unchanged (a dedicated standalone hardening increment before I3's real-device surface); the packaging-adjacent NITs die with the subtree (`standalone.yml` path filter, `.reports/` at root, unanchored `dist/` ignore).

## 10. Review tier (Step-1 call, rubric #254) and keyword scan

**Both slices: TIER 3** — the maximum across each slice's expected diff. Triggers: **A** — (i) adds/re-pins dependencies (`pyproject.toml` + `uv.lock`: the `server` extra); (ii) keyword hits (below). **B** — (i) touches `pyproject.toml` again (the ui-html pin) + keyword hits. Consequence: the mandatory independent adversarial refute (G6) runs **per slice** — two lanes each per the 2026-09-24 retro R3 rule (Tier-3 increments run two independent adversary lanes deliberately). The **standards-governor mandate does not fire** for either slice: no `standards/` bytes, no SDK vendored-tree edits, no standard-version strings (versions derived); the tripwire is reported in A-R/B gates.

Keyword scan over each slice's **expected** diff text (docs and code alike — the record itself, the pyproject/CI diffs, the expected module edits, and B's new scenario code; estimates re-derived over the real diff at review):

| keyword | A expected | B expected | where |
|---|---|---|---|
| `sha256` | ~4 | ~3 | A: assets.py docstring edits, this record; B: verifier wiring, record |
| `hashlib` | ~2 | ~2 | same files |
| `asyncio` | ~3 | ~6 | seam/web touchups (A), scenario adapter + tests (B), record prose |
| `threading` | 0 | 0 | none introduced |
| `subprocess` | 0 | 0 | none (plugin_test subprocess is I2's D6) |
| `migrate` | 0 | 0 | none |
| `recovery` | 0 | ~5 | **B's scenario table carries the `recovery` scenario id natively** |
| `protection` | ~1 | ~2 | record prose only (tier/invariant discussion) |

## 11. Top risks, each with its falsifier

- **R1 — packaging regression drops server payload from the wheel** (templates/assets not shipped). Falsifier: A-W's both-directions byte census + A-E venv-2 serve smoke. Mitigation: the census is the gate, not a hope.
- **R2 — the extra leaks into the default install** (the ruling's own PKG basis). Falsifier: A-E venv-1's `pip list` assertion. This is the gate the ruling turns on.
- **R3 — scenario laundering** (states rendered from template constants, not the pipeline). Falsifier: B-S's RED control (script removal ⇒ honest refusal) + the HTML/REST equal-values pin. The §1 quality-laundering fact is the design's reason the scenario adapter must exist — a reviewer should attack exactly here.
- **R4 — the unconditional console script on a default install is a crash surface.** Falsifier: A-E's serve-without-extra arm (prefixed refusal, exit 2 — never a traceback). Precedent: R-9's shim pattern.
- **R5 — the ui-html exact pin lags the gateway's workspace tree** (the gateway consumes unreleased path-dep changes; standalone sits at 0.1.0 until release + pin bump). This is Q5's designed behavior, not a defect — but forgetting the bump is the real risk. Mitigation: the obligation-12 drift row amendment names the pin as a motion surface (D-B5's trigger).
- **R6 — rebase collision with SDK PR #87** — disjoint files (their `cli.py`, ours pyproject/new tree/CI); any unexpected overlap reds A's own tripwire (A-R asserts no `src/benchweave_sdk/` bytes move). Order recorded in §8.
- **R7 — scenario canonical values read as device truth** (a safety-relevant parameter shown at a range midpoint). Mitigation: scenario mode is mock-only, banner-marked simulated, never touches a transport that isn't a script; values derive from the descriptor's own declared range. Accepted and recorded.

## 12. CI cost

Net **negative-to-neutral**: `standalone.yml` (one job, ~1–2 min) is deleted; the SDK gates job's sync gains `--extra server` (dependency download slightly longer, same triple). No new lanes. The zero-literal counter's scope grows by one tree (negligible). Gateway CI unchanged (docs-only commits).

## 13. Stale prose found and carried (verified, per the brief)

PRD 11 v0.2 (revised 2026-10-01 — the revision predates the 2026-10-02 rulings and does NOT reflect them): Summary headline 4; §8 Q1's "Recommend 2"; NFR-P1's "live in the standalone distribution"; SW-02's `benchweave-standalone serve`; §9's I1 "throwaway package path" note. All amended by this train's gateway-side commit (§3.5). PRD 12: no stale prose found (Q4/Q5/R-5/R-9 already rule this slice's posture). The I1 design record is frozen history (never retrofitted); its §2 placement and D5 are superseded by this record, disclosed here rather than edited there.

## 14. What this record does not decide

The SDK 0.6.0 release event itself (D-A2 — the owner's call); the I2+ scopes (D1–D4, D6 carried); #308's shim mechanics (its own design, unblocked by A); whether the scenario select later becomes a catalogue op (D-B1). Nothing here moves standards bytes, the SDK core package, or the submodule pointer — slice A's tripwire asserts it.

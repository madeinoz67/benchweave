"""Device presentation pages through the gateway's OWN validator (G2b).

The device page resolves the plugin's presentation attachment from
ADMITTED DOCUMENTS — the envelope, its manifest, the binding catalogue
and the manifest's assets, all content-addressed in the store — and
validates the attachment through
``presentation.admission.validate_attachment``: the same bytes the SDK
host validates with, against the resolution-relevant subset of the SDK
host's document set — the ACTIVE plugin-ui schemas JOINED with every
carried OTDP version's documents (``_presentation_documents``, issue
#446's parity fix; the profile rows and action-schema urns an
invoke-kind target binds resolve identically on both hosts — a strict
subset, not a set identity: the standard families this page never
resolves are absent, and the keys the two sets share come from the same
committed corpus bytes). Every served corpus file is digest-verified
against its corpus-manifest row at build time — the
``corpus_pin_mismatch`` gate (#446 slice-1 fold): a tampered or
unrecorded file refuses the build, never silently becomes the schema an
attachment validates against. Nothing plugin-authored reaches the page
unvalidated:
plugin presentation content is data (NFR-S9) — no plugin HTML/JS/CSS is
ever rendered.

Honest absence: a device with no admitted envelope renders "no
presentation attachment" (the fixture devices carry none); an envelope
whose catalogue or resources are not admitted renders the unvalidatable
state rather than a partial validation. The gateway declares NO custom
panels and NO named UI features (``SUPPORTED_PANELS``/
``SUPPORTED_FEATURES``): built-in page kinds render; a custom
``panel_id`` the registry has no panel for is the validator's own
``panel_unavailable`` finding — rendered as SW-41's refusal when the
page is required, and as an unavailable note when optional.

Readings are observations (GW-22): tiles populate ONLY from
gateway-reported data. Interface 0.1.0 carries no live observation read
(six state-only event kinds; no reading values in projections — the
design's §1 finding, owner fork F1'), so a G2 tile renders
``Unavailable`` — never a submitted, staged or fabricated value, and no
optimistic copy exists anywhere. Staleness (GW-23) is
``staleness.staleness`` applied to the OBSERVATION's own age against the
parameter's commissioned ``max_age_ms`` — with no observation there is
no verdict (ST-3), which is exactly what the tile renders.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from benchweave_ui_html.data import ReadingData
from benchweave_ui_html.partials import render_reading
from benchweave_ui_html.staleness import staleness
from markupsafe import Markup

from benchweave.content.store import ContentStore
from benchweave.presentation.admission import validate_attachment
from benchweave.standards.manifest import (
    StandardsError,
    active_version_from_corpus,
    load_dependency_policy_from_corpus,
    retained_versions_from_corpus,
)
from benchweave.vendoring import corpus_root

#: GW-23: the composition's staleness IS the contract predicate (ST-2),
#: computed from the observation's own age — re-exported under the name
#: the device page documents so the seam is greppable and pinnable.
reading_staleness = staleness

#: The gateway host declares NO custom panels: a manifest page carrying
#: a ``panel_id`` names a registry panel this host does not serve, which
#: is the validator's ``panel_unavailable`` finding (SW-41 — rendered as
#: a refusal when required, unavailable when optional).
SUPPORTED_PANELS: frozenset[str] = frozenset()

#: The gateway host declares NO named UI features beyond the built-in
#: page kinds; a manifest requiring a feature is an honest
#: ``unsupported_feature`` finding, never a guessed yes.
SUPPORTED_FEATURES: frozenset[str] = frozenset()

_ENVELOPE_SCHEMA_SUFFIX = "presentation-envelope.schema.json"
_CATALOGUE_SCHEMA_SUFFIX = "binding-catalogue.schema.json"
_SCHEMA_ID_PREFIX = "https://benchweave.dev/contracts/plugin-ui/"


_OTDP = "otdp"


def _corpus_state(corpus: Path) -> tuple[str, str]:
    """Digests of the two committed files the document set derives from —
    the VR-19 key discipline (``control.documents._corpus_state_token``'s
    shape, kept local rather than importing a private control symbol):
    the cache key moves when the policy block or the retained version set
    moves, so a mid-process corpus change serves the NEXT composition from
    the new bytes. The key binds the two MANIFEST files, not per-document
    bytes — the cache's true invalidation semantics (#446 slice-1 fold
    F3): a warm process keeps serving the build-time-VERIFIED document set
    until a manifest moves (an unrepinned in-place edit cannot smuggle
    different bytes into a warm entry, but a COLD build of that tree
    refuses with ``corpus_pin_mismatch``); the sanctioned edit flow is a
    repin, which rewrites corpus-manifest.json and therefore the key.
    Absence follows the loaders' own typed semantics: a missing
    standards-manifest raises the same ``StandardsError``
    (``standards_manifest_absent:``) the active-version read will; a
    missing corpus-manifest contributes the empty-bytes sentinel
    (retained == () — an empty OTDP phase, the plugin-ui-only document
    set, never a crash)."""

    def _digest(name: str, *, absent_as_empty: bool = False) -> str:
        path = corpus / name
        if path.is_file():
            return hashlib.sha256(path.read_bytes()).hexdigest()
        if absent_as_empty:
            # The loader's own absent state (retained == ()): a key no
            # real digest can collide with, so absence and a present
            # (even empty) file never share a cache entry.
            return ""
        # F4 (#446 slice-1 fold): match the loader's typed refusal —
        # ``_read_corpus_manifest`` wraps the same miss as StandardsError,
        # and a raw FileNotFoundError here would name a class no caller
        # greps for.
        try:
            raw = path.read_bytes()
        except FileNotFoundError as exc:
            raise StandardsError(
                f"standards_manifest_absent: {path} ({exc})"
            ) from exc
        return hashlib.sha256(raw).hexdigest()

    return _digest("standards-manifest.json"), _digest(
        "corpus-manifest.json", absent_as_empty=True
    )


def _corpus_pin_rows(corpus: Path) -> dict[str, str] | None:
    """The corpus manifest's ``{path: sha256}`` digest rows, or ``None``
    when the manifest is absent — the tolerance ``_corpus_state``
    documents (no rows exist to verify against; retained == () empties
    the OTDP phase). Same row shape as ``standards.manifest._corpus_pins``,
    kept local rather than importing a private symbol (the
    ``_corpus_state`` discipline)."""
    path = corpus / "corpus-manifest.json"
    if not path.is_file():
        return None
    document = json.loads(path.read_bytes())
    return {
        str(row["path"]): str(row["sha256"]) for row in document.get("files", [])
    }


def _verify_corpus_pin(raw: bytes, key: str, pins: dict[str, str] | None) -> None:
    """The #446 slice-1 fold's digest gate (adversary F1): every file the
    composition walks is verified against its corpus-manifest row BEFORE
    it is parsed — the gateway's mirror of the SDK host's
    ``vendored_digest_mismatch`` load refusal (#215 F1). ``pins`` is
    ``None`` only under the absent-manifest tolerance; with the manifest
    present the gate is mandatory and fail-closed: an unrecorded file and
    a digest mismatch both refuse with ``corpus_pin_mismatch`` naming the
    path, so a planted document cannot displace a corpus schema at a
    shared ``$id``/urn key (the refute's hijack shape)."""
    if pins is None:
        return
    pinned = pins.get(key)
    if pinned is None:
        raise StandardsError(
            f"corpus_pin_mismatch: {key} is present in the corpus tree "
            "but not recorded by the corpus manifest; record it through "
            "a standards bump or restore the tree"
        )
    digest = hashlib.sha256(raw).hexdigest()
    if digest != pinned:
        raise StandardsError(
            f"corpus_pin_mismatch: {key} hashes to {digest} but the "
            f"manifest pins {pinned}"
        )


def _serve_otdp_documents(
    documents: dict[str, dict[str, Any]],
    directory: Path,
    prefix: str,
    pins: dict[str, str] | None,
) -> None:
    """Install one served OTDP directory into the composition set: every
    ``*.json`` under it (recursively — the examples walk the SDK's
    ``contract_documents`` performs) keyed by its path-shaped
    ``otdp/<version>/<file>`` name, aliased by ``$id`` when it carries
    one, plus the per-action ``input_schema``/``output_schema`` subschema
    expansion the SDK's ``schemas()`` performs. Every file is digest-
    verified against its corpus-manifest row before it is parsed
    (``_verify_corpus_pin`` — the #446 slice-1 fold's gate; a direct
    caller owns the rows it passes). Keys are overwritten within the OTDP
    phase: versions install in ascending carried order, so an action urn
    shared across carried versions resolves to the highest version's
    rows — the SDK host's own last-wins."""
    for path in sorted(directory.iterdir(), key=lambda item: item.name):
        key = f"{prefix}/{path.name}"
        if path.is_dir():
            _serve_otdp_documents(documents, path, key, pins)
            continue
        if not path.name.endswith(".json"):
            continue
        raw = path.read_bytes()
        _verify_corpus_pin(raw, key, pins)
        document = json.loads(raw)
        documents[key] = document
        identifier = document.get("$id")
        if isinstance(identifier, str):
            documents[identifier] = document
        actions = document.get("actions")
        if not isinstance(actions, dict):
            continue
        for action in actions.values():
            if not isinstance(action, dict):
                continue
            for name in ("input_schema", "output_schema"):
                schema = action.get(name)
                if isinstance(schema, dict) and isinstance(schema.get("$id"), str):
                    documents[schema["$id"]] = schema


def _install_plugin_ui_schemas(
    documents: dict[str, dict[str, Any]], corpus: Path, pins: dict[str, str] | None
) -> None:
    """The ACTIVE plugin-ui corpus schemas keyed by ``$id`` (derived from
    the manifest, never a version literal), each digest-verified against
    its corpus-manifest row (``_verify_corpus_pin`` — the same gate the
    OTDP walk runs; a tampered schema file refuses the build rather than
    becoming the attachment's validating schema) — installed AFTER the
    OTDP phase so the attachment's own validating schemas cannot be
    displaced: a served document whose ``$id`` collides with a plugin-ui
    schema id loses the key; it never becomes the schema the envelope
    validates against."""
    version = active_version_from_corpus(corpus, "plugin-ui")
    for path in sorted((corpus / "plugin-ui" / version).glob("*.schema.json")):
        raw = path.read_bytes()
        _verify_corpus_pin(raw, f"plugin-ui/{version}/{path.name}", pins)
        schema = json.loads(raw)
        documents[str(schema["$id"])] = schema


@lru_cache(maxsize=8)
def _presentation_documents_cached(
    corpus_text: str, state: tuple[str, str]
) -> dict[str, dict[str, Any]]:
    # ``state`` is cache-KEY material only (see ``_corpus_state``); the
    # corpus path plus the two manifest digests bind the cached set to the
    # corpus state it was computed from.
    corpus = Path(corpus_text)
    policy = load_dependency_policy_from_corpus(corpus)
    row = policy.standards.get(_OTDP)
    if row is None:
        # Fail closed, mirroring ``control.documents._classify_cached``: a
        # tree whose policy block carries no OTDP row has broken
        # governance data — the document set is not a guess.
        raise StandardsError(
            f"dependency_policy_invalid: no policy row for standard {_OTDP!r}"
        )
    documents: dict[str, dict[str, Any]] = {}
    # The digest rows every walked file verifies against (None under the
    # absent-manifest tolerance) — the #446 slice-1 fold's gate, inside
    # the cached build so a serve never outlives its verification.
    pins = _corpus_pin_rows(corpus)
    # The CARRIED set (retained ∧ in-range, yanked included) — the same
    # byte set the SDK lock carries: a descriptor pinning an older or a
    # yanked-in-interval OTDP version has version-suffixed urns that must
    # resolve identically on both hosts (SW-41).
    for version in (
        candidate
        for candidate in retained_versions_from_corpus(corpus, _OTDP)
        if row.in_range(candidate)
    ):
        _serve_otdp_documents(
            documents, corpus / _OTDP / version, f"{_OTDP}/{version}", pins
        )
    _install_plugin_ui_schemas(documents, corpus, pins)
    return documents


def _presentation_documents() -> dict[str, dict[str, Any]]:
    """The trusted document set the device page validates against: the
    ACTIVE plugin-ui schemas JOINED with every carried OTDP version's
    documents — the resolution-relevant SUBSET of the SDK host's
    ``schemas()`` set (SW-41's parity rule read as a resolution rule, not
    a set identity: the families this page never resolves are absent, and
    the keys the two sets share come from the same committed corpus
    bytes), so an invoke-kind target's profile rows and action-schema
    urns resolve identically on both hosts. Every walked file is
    digest-verified against its corpus-manifest row inside the cached
    build (``corpus_pin_mismatch`` refuses a tampered or unrecorded
    file). Callers treat the set as read-only; the fresh shallow copy
    guards the cache's key structure."""
    corpus = corpus_root()
    return dict(_presentation_documents_cached(str(corpus), _corpus_state(corpus)))


def _documents_by_schema_suffix(
    content: ContentStore, suffix: str, descriptor_digest: str
) -> list[dict[str, Any]]:
    """Admitted documents whose ``schema_id`` ends with ``suffix`` and
    whose content pins THIS descriptor — the attachment-resolution
    query (version-agnostic on purpose: the schema id is the document's
    own declaration)."""
    matched: list[dict[str, Any]] = []
    for row in content.documents_by_schema_suffix(suffix):
        if str(row["content"].get("descriptor_sha256", "")) == descriptor_digest:
            matched.append(row)
    return matched


@dataclass(frozen=True)
class PresentationTile:
    """One readings tile — GW-22's rule renders in the data: the value is
    ``Unavailable`` unless a gateway-reported observation supplied it.
    Rendered through the PACKAGE's reading-tile partial (the §E.1
    component), so the contract's tile rules (no glow, staleness marker,
    severity icon+label) apply to it like every host's."""

    label: str
    unit: str
    value: str = "Unavailable"
    quality: str = "unknown"
    freshness: str = "Unavailable"
    stale_verdict: Literal["stale", "fresh", "no-verdict"] = "no-verdict"
    #: The observation target's ``parameter_id`` — the key the
    #: reading-tile join (#369) attributes retained readings by. Never
    #: rendered: it is the tile's identity, not its content.
    parameter_id: str | None = None

    @property
    def html(self) -> Markup:
        return Markup(  # noqa: S704 - the package partial over this dataclass
            render_reading(
                ReadingData(
                    label=self.label,
                    severity="neutral",
                    value=self.value,
                    unit=self.unit,
                    quality=self.quality,
                    freshness=self.freshness,
                    stale_verdict=self.stale_verdict,
                )
            )
        )


@dataclass(frozen=True)
class PresentationPage:
    """One manifest page, composed for rendering.

    ``available`` is False for pages the host cannot render (the
    validator's ``unavailable_pages``); ``refused`` is True only for the
    REQUIRED unavailable page (SW-41's ``panel_unavailable`` refusal).
    """

    page_id: str
    title: str
    kind: str
    required: bool
    available: bool
    refused: bool
    tiles: tuple[PresentationTile, ...] = field(default=())
    plot_summaries: tuple[str, ...] = field(default=())
    preset_ids: tuple[str, ...] = field(default=())


@dataclass(frozen=True)
class PresentationState:
    """Everything the device page renders about the attachment."""

    envelope_sha256: str | None
    valid: bool
    findings: tuple[tuple[str, str, str], ...]  # (code, path, message)
    pages: tuple[PresentationPage, ...]
    #: ``absence`` names the honest-absence reason when there is nothing
    #: to validate: no envelope admitted, or the attachment is not
    #: validatable (its catalogue or resources are not admitted).
    absence: str | None


def compose_device_presentation(
    content: ContentStore | None, descriptor_raw: bytes
) -> PresentationState:
    """Resolve and validate the device's presentation attachment.

    ``content`` is the composition's content store (``create_app`` always
    passes it); ``None`` is the routing-test posture, which renders the
    honest absence rather than inventing an attachment.
    """
    # The device row's descriptor bytes are the admission-verified bytes;
    # digest them here — the envelope pins exactly this digest.
    descriptor_digest = hashlib.sha256(descriptor_raw).hexdigest()
    if content is None:
        return PresentationState(
            envelope_sha256=None, valid=False, findings=(), pages=(),
            absence="no-store",
        )
    envelopes = _documents_by_schema_suffix(
        content, _ENVELOPE_SCHEMA_SUFFIX, descriptor_digest
    )
    if not envelopes:
        return PresentationState(
            envelope_sha256=None,
            valid=False,
            findings=(),
            pages=(),
            absence="no-attachment",
        )
    envelope_row = envelopes[0]
    envelope = envelope_row["content"]
    manifest_ref = envelope.get("manifest", {})
    manifest_row = content.get_document(str(manifest_ref.get("sha256", "")))
    catalogues = _documents_by_schema_suffix(
        content, _CATALOGUE_SCHEMA_SUFFIX, descriptor_digest
    )
    if manifest_row is None or not catalogues:
        # Honest unvalidatable: the envelope pins bytes that are not
        # admitted (or the trusted catalogue is absent) — no partial
        # validation, no guessed rendering.
        return PresentationState(
            envelope_sha256=envelope_row["sha256"],
            valid=False,
            findings=(),
            pages=(),
            absence="attachment-incomplete",
        )
    manifest = manifest_row["content"]
    resources = {str(manifest_ref.get("path", "manifest.json")): manifest_row["raw_bytes"]}
    for asset in manifest.get("assets", []):
        row = content.get_document(str(asset.get("sha256", "")))
        if row is not None:
            resources[str(asset.get("path", ""))] = row["raw_bytes"]
    descriptor = json.loads(descriptor_raw)
    identity = descriptor.get("identity", {})
    firmware_values = identity.get("supported_firmware") or []
    report = validate_attachment(
        envelope_row["raw_bytes"],
        descriptor_raw=descriptor_raw,
        verified_resources=resources,
        binding_catalogue=catalogues[0]["content"],
        schema_documents=_presentation_documents(),
        supported_features=SUPPORTED_FEATURES,
        supported_panels=SUPPORTED_PANELS,
        # The descriptor's OWN declared-supported firmware (a
        # descriptor-declared fact — the read interface carries no
        # runtime firmware value; None when the descriptor lists none).
        firmware=str(firmware_values[0]) if firmware_values else None,
    )
    unavailable = set(report.unavailable_pages)
    targets = {
        str(row["id"]): row
        for row in catalogues[0]["content"].get("targets", [])
    }
    bindings = {
        str(row["id"]): row for row in manifest.get("bindings", [])
    }
    pages: list[PresentationPage] = []
    for page in manifest.get("pages", []):
        page_id = str(page["id"])
        required = bool(page.get("required"))
        is_available = page_id not in unavailable
        tiles: tuple[PresentationTile, ...] = ()
        plot_summaries: tuple[str, ...] = ()
        preset_ids: tuple[str, ...] = ()
        if is_available:
            kind = str(page.get("kind", ""))
            if kind == "readings":
                tiles = tuple(
                    _tiles_for_page(page, bindings, targets)
                )
            elif kind == "dataset":
                plot_summaries = tuple(
                    f"{plot.get('kind', 'plot')}: "
                    f"{', '.join(str(name) for name in plot.get('y', []))}"
                    for plot in page.get("plots", [])
                )
            elif kind == "configuration":
                for name in page.get("bindings", []):
                    binding = bindings.get(str(name), {})
                    target = targets.get(str(binding.get("target_id", "")), {})
                    preset_ids = tuple(
                        str(value) for value in target.get("preset_asset_ids", [])
                    )
        pages.append(
            PresentationPage(
                page_id=page_id,
                title=str(page.get("title", page_id)),
                kind=str(page.get("kind", "")),
                required=required,
                available=is_available,
                refused=required and not is_available,
                tiles=tiles,
                plot_summaries=plot_summaries,
                preset_ids=preset_ids,
            )
        )
    return PresentationState(
        envelope_sha256=envelope_row["sha256"],
        valid=report.valid,
        findings=tuple(
            (finding.code, finding.path, finding.message)
            for finding in report.findings
        ),
        pages=tuple(pages),
        absence=None,
    )


def _tiles_for_page(
    page: dict[str, Any],
    bindings: dict[str, dict[str, Any]],
    targets: dict[str, dict[str, Any]],
) -> list[PresentationTile]:
    """One tile per bound observation target's VALUE variable — value
    ``Unavailable`` until a gateway-reported observation supplies it
    (GW-22: the composition never receives request data, so no submitted
    value can reach a tile; ST-3 renders no staleness verdict)."""
    tiles: list[PresentationTile] = []
    for name in page.get("bindings", []):
        binding = bindings.get(str(name), {})
        target = targets.get(str(binding.get("target_id", "")), {})
        for variable in target.get("variables", []):
            if variable.get("axis_role") == "value":
                tiles.append(
                    PresentationTile(
                        label=str(variable.get("id", name)),
                        unit=str(variable.get("unit", "")),
                        parameter_id=str(target.get("parameter_id", "")) or None,
                    )
                )
    return tiles

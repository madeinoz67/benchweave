"""Device presentation pages through the gateway's OWN validator (G2b).

The device page resolves the plugin's presentation attachment from
ADMITTED DOCUMENTS — the envelope, its manifest, the binding catalogue
and the manifest's assets, all content-addressed in the store — and
validates the attachment through
``presentation.admission.validate_attachment``: the same bytes the SDK
host validates with (SW-41's parity rule). Nothing plugin-authored
reaches the page unvalidated: plugin presentation content is data
(NFR-S9) — no plugin HTML/JS/CSS is ever rendered.

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
from typing import Any

from benchweave_ui_html.staleness import staleness

from benchweave.content.store import ContentStore
from benchweave.presentation.admission import validate_attachment
from benchweave.standards.manifest import active_version_from_corpus
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


def _plugin_ui_schemas() -> dict[str, dict[str, Any]]:
    """The ACTIVE plugin-ui corpus schemas keyed by ``$id`` — the trusted
    schema documents the validator validates against (derived from the
    manifest, never a version literal)."""
    version = active_version_from_corpus(corpus_root(), "plugin-ui")
    directory = corpus_root() / "plugin-ui" / version
    documents: dict[str, dict[str, Any]] = {}
    for path in directory.glob("*.schema.json"):
        schema = json.loads(path.read_bytes())
        documents[str(schema["$id"])] = schema
    return documents


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
    ``Unavailable`` unless a gateway-reported observation supplied it."""

    label: str
    unit: str
    value: str = "Unavailable"
    quality: str = "unavailable"
    freshness: str = ""
    stale_verdict: str = "no-verdict"


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
        schema_documents=_plugin_ui_schemas(),
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
                    )
                )
    return tiles

"""Validate presentation candidates after existing package admission.

This is an explicit, non-activating attachment boundary. The caller supplies
resources from the envelope's exact resource_root in the admitted package.
Nothing here scans folders, imports panel code, acquires devices or approves runs.
"""

from collections.abc import Mapping
from typing import Any

from .contracts import ValidationReport, validate_presentation


def validate_attachment(
    envelope_raw: bytes,
    *,
    descriptor_raw: bytes,
    verified_resources: Mapping[str, bytes],
    binding_catalogue: Mapping[str, Any],
    schema_documents: Mapping[str, dict[str, Any]],
    supported_features: frozenset[str],
    supported_panels: frozenset[str],
    firmware: str | None,
) -> ValidationReport:
    """Check UI compatibility; successful validation grants no execution authority."""
    return validate_presentation(
        envelope_raw,
        descriptor_raw=descriptor_raw,
        resources=verified_resources,
        binding_catalogue=binding_catalogue,
        schema_documents=schema_documents,
        supported_features=supported_features,
        supported_panels=supported_panels,
        firmware=firmware,
    )

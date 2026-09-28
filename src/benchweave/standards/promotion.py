"""Promotion records: the promotion audit trail and its gates (issue #218).

#203 slice 4 (design §3.6, owner Q7): ``standards/promotion-records.json``
is governance data OUTSIDE the corpus, like the dependency-policy block —
no corpus-manifest rows, repin untouched (CON-7 unamended). One record per
promotion: standard, target version, dev-head name, ``dev_edit_sha``,
``dev_tree_digest`` (sha256 over the sorted normative path+digest list of
the final dev state — written at PR time by the authoring helper
:func:`dev_tree_digest_at`), and ``landing_sha`` — the squash/merge commit
on main, filled by an immediate post-landing append because the landing
commit does not exist when the promotion PR is authored; until filled the
record is ``pending``.

The gates (:func:`validate_promotion_records`, run by the standards suite):

(a) DIGEST — the record's ``dev_tree_digest`` equals the digest of the dev
    tree at ``dev_edit_sha`` read through the object store;
(b) SWEEP-AWARE DIFF — the diff between the dev tree at ``dev_edit_sha``
    and the promoted directory on main contains ONLY version-transition
    lines: the design's tokens (the ``<target>-dev`` string, the target,
    the pre-dev active version derived from the promoted rows' ``lineage``)
    plus the three classes the FOUNDING RECORD proved the real sweep
    mechanically produces — verified digest re-stamps (VR-36a), identity
    re-stamps (the same line with version numbers moved), and the
    regenerated ``validation-report.md``; any other changed line refuses
    ``promotion_sweep_violation:`` — the sweep-laundry mitigation (design
    risk 6);
(c) PENDING-SUCCESSOR — a pending record refuses once a SUCCESSOR version
    of the same standard exists on main (pendingness must not outlive a
    train); the drift-check lane (:func:`pending_warning_lines`, wired into
    ``check.run_check``) prints pending records as a warning line on every
    run.
plus the NO-RECORD gate: a retained version whose corpus rows cite a
``-dev`` source (the promotion's own signature — GOVERNANCE's "its corpus
rows cite the dev path as source") must carry a record.

D4 (VR-8 as amended by owner Q7): NO ``merge-base --is-ancestor``
requirement on any branch tip — squash landings are the practice, so the
gate's existence checks are the LANDING SHA and the DEV-EDIT SHA resolving
in the object store, never branch topology. Disclosed limit: both reads
need the objects present locally (the coordinator's clone or a CI runner
carrying the dev branch); a fresh clone whose history squashed the dev
branch away cannot verify the digest — the gate fails loudly there, it
never silently passes.

Carrier semantics: the file's ABSENCE is an empty history, not a refusal —
a tree before its first recorded promotion. This tree's founding record
(execution 0.2.0 — the pre-mechanism promotion recovered from history by
the coordinator directive of 2026-09-28, option (a); both shas are main
ancestors, so every fresh clone verifies it) landed with the mechanism;
the gates run in the standards suite against fixtures AND the founded real
tree, and the tamper arm pins that a corrupted founding record still
refuses — the gates stay armed on the real tree, never grandfathered.

Refusal prefixes: ``promotion_record_invalid:``, ``promotion_record_absent:``,
``promotion_dev_edit_unresolved:``, ``promotion_landing_unresolved:``,
``promotion_digest_mismatch:``, ``promotion_sweep_violation:`` (design-
named), ``promotion_pending_stale:``.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .export import canonical_json
from .manifest import StandardsError, _load_dev_head, retained_versions

#: The records document's validating schema (governance data, validated
#: exactly like the policy block: shape errors fail closed at load).
PROMOTION_RECORDS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "promotion_record_version": {"const": 1},
        "records": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "standard": {"type": "string", "pattern": "^[a-z][a-z0-9-]*$"},
                    "target": {
                        "type": "string",
                        "pattern": r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$",
                    },
                    "dev_head": {
                        "type": "string",
                        "pattern": (
                            r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\."
                            r"(?:0|[1-9]\d*)-dev$"
                        ),
                    },
                    "dev_edit_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                    "dev_tree_digest": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                    "landing_sha": {
                        "type": ["string", "null"],
                        "pattern": "^[0-9a-f]{40}$",
                    },
                    "evidence": {"type": "string", "minLength": 1},
                },
                "required": [
                    "standard",
                    "target",
                    "dev_head",
                    "dev_edit_sha",
                    "dev_tree_digest",
                    "landing_sha",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["promotion_record_version", "records"],
    "additionalProperties": False,
}

_VALIDATOR = Draft202012Validator(
    PROMOTION_RECORDS_SCHEMA, format_checker=FormatChecker()
)

#: The warning prefix the drift-check lane prints for pending records —
#: tolerated by ``check.count_failures`` exactly like the deprecation
#: warning prefix (a pending record inside its train is a state to finish,
#: not a failure).
PENDING_WARNING_PREFIX = "promotion_pending_warning"

_DEV_SOURCE = re.compile(
    r"^standards/(?P<id>[a-z][a-z0-9-]*)/(?P<version>\d+\.\d+\.\d+-dev)/"
)


@dataclass(frozen=True)
class PromotionRecord:
    """One recorded promotion (the landing-time audit trail, VR-8)."""

    standard: str
    target: str
    dev_head: str
    dev_edit_sha: str
    dev_tree_digest: str
    landing_sha: str | None

    @property
    def pending(self) -> bool:
        """Pending until the immediate post-landing append fills the sha."""
        return self.landing_sha is None


def load_promotion_records(root: Path) -> tuple[PromotionRecord, ...]:
    """Load ``standards/promotion-records.json``; absent file = no records.

    An absent file is an EMPTY HISTORY (the mechanism's first promotion
    authors it), not a refusal — the no-record gate, not the loader, owns
    unrecorded promotions. A present-but-malformed file fails closed with
    ``promotion_record_invalid:``.
    """
    path = root / "standards" / "promotion-records.json"
    if not path.is_file():
        return ()
    document = json.loads(path.read_bytes())
    error = next(iter(_VALIDATOR.iter_errors(document)), None)
    if error is not None:
        raise StandardsError(
            f"promotion_record_invalid: {path.name} {error.json_path}: {error.message}"
        )
    records: list[PromotionRecord] = []
    seen: set[tuple[str, str]] = set()
    for row in document["records"]:
        key = (str(row["standard"]), str(row["target"]))
        if key in seen:
            # Refute fold, lane B F2 (#218): duplicate rows shadow silently
            # (the callers' dict build takes the last) — a flipped record
            # followed by an honest one would launder the flip. Loading
            # refuses instead of ordering.
            raise StandardsError(
                f"promotion_record_invalid: duplicate row for {key[0]}@{key[1]}"
            )
        seen.add(key)
        records.append(
            PromotionRecord(
                standard=str(row["standard"]),
                target=str(row["target"]),
                dev_head=str(row["dev_head"]),
                dev_edit_sha=str(row["dev_edit_sha"]),
                dev_tree_digest=str(row["dev_tree_digest"]),
                landing_sha=row["landing_sha"],
            )
        )
    return tuple(records)


def _git_show(root: Path, ref: str) -> bytes | None:
    """One object-store read (the resolver's own precedent); ``None`` on
    any git failure — the caller refuses by name."""
    result = subprocess.run(  # noqa: S603 — fixed argv
        ["git", "-C", str(root), "show", ref],  # noqa: S607 — PATH git is the supported invocation
        capture_output=True,
        check=False,
    )
    return result.stdout if result.returncode == 0 else None


def _git_object_type(root: Path, sha: str) -> str | None:
    """The object's type (``commit``/``tree``/``blob``/``tag``), or ``None``
    when the sha does not resolve — the landing check's identity half
    (refute fold, lane B F3: existence alone admits any object)."""
    result = subprocess.run(  # noqa: S603 — fixed argv
        ["git", "-C", str(root), "cat-file", "-t", sha],  # noqa: S607 — PATH git is the supported invocation
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _head_normative_at(root: Path, standard_id: str, label: str, sha: str) -> list[str]:
    """The dev block's normative paths as declared by the manifest AT the
    sha (the head's normative list evolves with the head; the record's
    digest is over the tree the SHA names, so the manifest read is the sha's
    too). Reuses the loader's own ``_load_dev_head`` vetting so a malformed
    historical block refuses identically."""
    raw = _git_show(root, f"{sha}:standards/standards-manifest.json")
    if raw is None:
        raise StandardsError(
            f"promotion_dev_edit_unresolved: {sha} does not name "
            "standards/standards-manifest.json in the object store"
        )
    document = json.loads(raw)
    for entry in document.get("standards", []):
        if str(entry.get("id")) != standard_id:
            continue
        head = _load_dev_head(entry.get("dev"), standard_id, str(entry["version"]))
        if head is None:
            raise StandardsError(
                f"promotion_dev_edit_unresolved: the manifest at {sha} declares "
                f"no dev head for {standard_id}"
            )
        if head.version != label:
            raise StandardsError(
                f"promotion_record_invalid: {standard_id} dev_head {label} but "
                f"the manifest at {sha} declares {head.version}"
            )
        return list(head.normative)
    raise StandardsError(
        f"promotion_dev_edit_unresolved: the manifest at {sha} carries no "
        f"{standard_id} entry"
    )


def dev_tree_digest_at(root: Path, standard_id: str, label: str, sha: str) -> str:
    """The dev tree's digest at a sha — the WRITER-side helper (the record's
    ``dev_tree_digest`` at PR time) and the gate's comparison in one
    formula: sha256 over the canonical JSON of the sorted normative
    (path, digest) list, paths repo-relative as declared."""
    pairs = []
    for normative in sorted(_head_normative_at(root, standard_id, label, sha)):
        raw = _git_show(root, f"{sha}:{normative}")
        if raw is None:
            raise StandardsError(
                f"promotion_dev_edit_unresolved: {normative} does not resolve "
                f"at {sha}"
            )
        pairs.append([normative, hashlib.sha256(raw).hexdigest()])
    if not pairs:
        raise StandardsError(
            f"promotion_record_invalid: {standard_id} dev_head {label} at {sha} "
            "names no normative files"
        )
    return hashlib.sha256(canonical_json(pairs)).hexdigest()


def _lineage_version(
    corpus_rows: list[dict[str, Any]], standard_id: str, target: str
) -> str | None:
    """The pre-dev active version from the promoted rows' ``lineage`` paths
    (``standards/<id>/<version>/<file>``) — the third sweep token."""
    versions = set()
    prefix = f"{standard_id}/{target}/"
    for row in corpus_rows:
        relative = str(row.get("path", ""))
        if not relative.startswith(prefix):
            continue
        # ``lineage`` (like ``source``) is repo-relative — strip the
        # standards/ prefix so the version segment parses.
        lineage = str(row.get("lineage") or "").removeprefix("standards/")
        match = re.fullmatch(rf"{standard_id}/(\d+\.\d+\.\d+)/.+", lineage)
        if match is not None:
            versions.add(match.group(1))
    if len(versions) == 1:
        return versions.pop()
    return None


def _corpus_rows(root: Path) -> list[dict[str, Any]]:
    path = root / "standards" / "corpus-manifest.json"
    if not path.is_file():
        return []
    return [
        {"path": str(row.get("path")), **{k: v for k, v in row.items() if k != "path"}}
        for row in json.loads(path.read_bytes()).get("files", [])
    ]


#: The machine-written report regenerated at promotion (GOVERNANCE's
#: promotion flow: "regenerate the validation report"; its dev-proof lane:
#: "machine-written reports are a property of released versions" — which is
#: why it is absent from every dev tree by rule). Only the file's ADDITION
#: at landing is sanctioned here: a report present in the dev tree and
#: EDITED at landing still goes through the line rules below.
_LANDING_REGENERATED = "validation-report.md"

#: A version-like substring (three components, optional ``-dev``) — the
#: identity re-stamp rule's strip unit.
_VERSIONISH = re.compile(r"\d+\.\d+\.\d+(?:-dev)?")
#: A bare sha256 hex digest — the digest re-stamp rule's unit.
_HEXDIGEST = re.compile(r"\b[a-f0-9]{64}\b")


def _line_offends(
    line: str, tokens: list[str], stripped_opposite: set[str], known_digests: set[str]
) -> str | None:
    """Whether one changed line is unexplained by the transition rules.

    ``None`` when the line admits (a version token, an identity re-stamp,
    or a VERIFIED digest re-stamp); else the detail to quote — the
    unexplained digest when that rule is what failed (refute fold, lane B
    F6: every digest-shaped token on a re-stamped line must name a real
    file of the right tree — one real digest no longer launders fakes
    beside it)."""
    if any(token in line for token in tokens):
        return None
    if _VERSIONISH.sub("", line) in stripped_opposite:
        return None
    digests = _HEXDIGEST.findall(line)
    if digests:
        unknown = [digest for digest in digests if digest not in known_digests]
        if not unknown:
            return None
        return f" [unexplained digest: {unknown[0]}]"
    return ""


def _sweep_check(
    root: Path,
    record: PromotionRecord,
    corpus_rows: list[dict[str, Any]],
) -> None:
    """Gate (b): only version-transition lines may differ between the dev
    tree at ``dev_edit_sha`` and the promoted directory.

    The design names the version transition tokens (the ``<target>-dev``
    label, the target, the pre-dev active version from the promoted rows'
    ``lineage``). The FOUNDING RECORD (execution 0.2.0, coordinator
    directive 2026-09-28) surfaced three further classes the real sweep
    mechanically produces, each admitted by its own verifiable rule rather
    than a widened token list:

    - DIGEST RE-STAMP (VR-36a's "URN/digest restamp"): a changed line
      carrying bare sha256s admits when EVERY digest on the line NAMES A
      REAL FILE — removed side a file of the dev tree at the sha, added
      side a file of the promoted tree (bidirectional set membership; an
      invented digest matches nothing and refuses — refute fold F6: one
      real digest no longer launders fakes beside it). Verified on the
      founding record: every one of its 10 changed digest lines maps,
      10/10, removed→dev-tree and added→promoted-tree.
    - IDENTITY RE-STAMP: a changed line admits when the OPPOSITE side of
      the same file's diff carries a line equal after stripping every
      version-like substring — the same sentence/URN with its version
      numbers moved (the founding record's pre-reset ``1.0.0`` URNs and the
      prose title both ride this rule). KNOWN FALSE-ACCEPT CLASS, disclosed
      (the slice-2 comparator's R4 class): a version-string motion in a
      non-version SEMANTIC field admits; the planted-wording control keeps
      the teeth — any non-version text difference still refuses.
    - The regenerated ``validation-report.md``, absent from the dev tree,
      is the sanctioned landing artifact (``_LANDING_REGENERATED``).
    """
    tokens = [record.dev_head, record.target]
    pre_dev = _lineage_version(corpus_rows, record.standard, record.target)
    if pre_dev is not None:
        tokens.append(pre_dev)
    promoted_dir = root / "standards" / record.standard / record.target
    if not promoted_dir.is_dir():
        raise StandardsError(
            f"promotion_record_invalid: {record.standard}@{record.target} names "
            "no promoted directory on this tree"
        )
    listing = subprocess.run(  # noqa: S603 — fixed argv
        [  # noqa: S607 — PATH git is the supported invocation
            "git",
            "-C",
            str(root),
            "ls-tree",
            "-r",
            "--name-only",
            record.dev_edit_sha,
            "--",
            f"standards/{record.standard}/{record.dev_head}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if listing.returncode != 0:
        raise StandardsError(
            f"promotion_dev_edit_unresolved: {record.dev_edit_sha} does not "
            f"list standards/{record.standard}/{record.dev_head}/ in the object "
            "store"
        )
    prefix = f"standards/{record.standard}/{record.dev_head}/"
    names = {
        line.removeprefix(prefix)
        for line in listing.stdout.splitlines()
        if line
    }
    on_disk = {
        str(path.relative_to(promoted_dir))
        for path in promoted_dir.rglob("*")
        if path.is_file()
    }
    # The digest re-stamp rule's two name-sets: every file's digest in each
    # tree, so membership is the whole verification.
    dev_digests: set[str] = set()
    for relative in listing.stdout.splitlines():
        if not relative:
            continue
        raw = _git_show(root, f"{record.dev_edit_sha}:{relative}")
        if raw is not None:
            dev_digests.add(hashlib.sha256(raw).hexdigest())
    promoted_digests = {
        hashlib.sha256(path.read_bytes()).hexdigest()
        for path in promoted_dir.rglob("*")
        if path.is_file()
    }
    for name in sorted(names | on_disk):
        old = _git_show(root, f"{record.dev_edit_sha}:{prefix}{name}")
        path = promoted_dir / name
        new = path.read_bytes() if path.is_file() else None
        if old == new:
            continue
        if old is None and name == _LANDING_REGENERATED:
            # The sanctioned regeneration: absent from the dev tree by the
            # dev-proof lane's own rule, machine-written at landing.
            continue
        old_lines = (old or b"").decode("utf-8", "replace").splitlines(keepends=True)
        new_lines = (new or b"").decode("utf-8", "replace").splitlines(keepends=True)
        removed: list[str] = []
        added: list[str] = []
        for line in difflib.unified_diff(old_lines, new_lines, n=0):
            if line.startswith(("+++", "---")):
                continue
            if line.startswith("-"):
                removed.append(line[1:])
            elif line.startswith("+"):
                added.append(line[1:])
        # The identity re-stamp rule's comparison set: the opposite side's
        # lines with every version-like substring stripped.
        stripped_added = {_VERSIONISH.sub("", line) for line in added}
        stripped_removed = {_VERSIONISH.sub("", line) for line in removed}
        offending: list[str] = []
        for line in removed:
            detail = _line_offends(line, tokens, stripped_added, dev_digests)
            if detail is not None:
                offending.append(f"{detail}-" + line.strip()[:100])
        for line in added:
            detail = _line_offends(line, tokens, stripped_removed, promoted_digests)
            if detail is not None:
                offending.append(f"{detail}+" + line.strip()[:100])
        if offending:
            raise StandardsError(
                f"promotion_sweep_violation: {record.standard}/{record.target}/"
                f"{name} differs from the dev tree at {record.dev_edit_sha} on "
                f"non-transition lines ({len(offending)} line(s), first: "
                f"{offending[0][:160]!r}) — the promotion sweep may carry only "
                f"the version transition (tokens {', '.join(tokens)}, verified "
                "digest re-stamps, identity re-stamps); move the change "
                "through the dev head or a new version, never under cover of "
                "the sweep"
            )


def validate_promotion_records(root: Path) -> None:
    """Run the promotion gates over the committed tree; refuse on any arm.

    The no-record gate first (a dev-sourced promotion with no record), then
    per record: the dev-edit sha resolves, the landing sha resolves when
    filled, the digest matches the sha's tree, the sweep is token-only, and
    pendingness has not outlived a successor. Every refusal names the
    standard, the target and the arm's own evidence.
    """
    corpus_rows = _corpus_rows(root)
    records = {
        (record.standard, record.target): record
        for record in load_promotion_records(root)
    }
    dev_sourced: dict[tuple[str, str], str] = {}
    for row in corpus_rows:
        source = str(row.get("source") or "")
        match = _DEV_SOURCE.match(source)
        if match is None:
            continue
        relative = str(row["path"])
        version = relative.split("/")[1] if "/" in relative else ""
        key = (match.group("id"), version)
        dev_sourced.setdefault(key, source)
    for (standard_id, target), source in sorted(dev_sourced.items()):
        if target in ("", None) or (standard_id, target) in records:
            continue
        raise StandardsError(
            f"promotion_record_absent: {standard_id}@{target} is a dev-sourced "
            f"promotion (row source {source}) with no record in "
            "standards/promotion-records.json — the promotion's audit trail "
            "(dev_edit_sha, dev_tree_digest, landing_sha) is not optional"
        )
    for record in sorted(records.values(), key=lambda r: (r.standard, r.target)):
        where = f"{record.standard}@{record.target}"
        computed = dev_tree_digest_at(
            root, record.standard, record.dev_head, record.dev_edit_sha
        )
        if computed != record.dev_tree_digest:
            raise StandardsError(
                f"promotion_digest_mismatch: {where} records dev_tree_digest "
                f"{record.dev_tree_digest} but the dev tree at "
                f"{record.dev_edit_sha} digests to {computed}"
            )
        if record.landing_sha is not None:
            kind = _git_object_type(root, record.landing_sha)
            if kind is None:
                raise StandardsError(
                    f"promotion_landing_unresolved: {where} records landing_sha "
                    f"{record.landing_sha}, which does not resolve in the "
                    "object store"
                )
            if kind != "commit":
                # Refute fold, lane B F3: the landing is a COMMIT — a blob
                # or tree sha resolves and would pass an existence-only
                # check while naming no landing at all.
                raise StandardsError(
                    f"promotion_landing_invalid: {where} records landing_sha "
                    f"{record.landing_sha}, a {kind} object, not the promotion "
                    "landing commit"
                )
            listing = subprocess.run(  # noqa: S603 — fixed argv
                [  # noqa: S607 — PATH git is the supported invocation
                    "git",
                    "-C",
                    str(root),
                    "ls-tree",
                    "-r",
                    "--name-only",
                    record.landing_sha,
                    "--",
                    f"standards/{record.standard}/{record.target}",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if listing.returncode != 0 or not listing.stdout.splitlines():
                raise StandardsError(
                    f"promotion_landing_invalid: {where} records landing_sha "
                    f"{record.landing_sha}, whose tree carries no "
                    f"standards/{record.standard}/{record.target}/ — the "
                    "landing commit must contain the promotion it records"
                )
        _sweep_check(root, record, corpus_rows)
        if record.pending:
            successors = [
                version
                for version in retained_versions(root, record.standard)
                if _version_tuple(version) > _version_tuple(record.target)
            ]
            if successors:
                raise StandardsError(
                    f"promotion_pending_stale: {where} is still pending (no "
                    f"landing_sha) while {record.standard}@{successors[0]} "
                    "already exists — pendingness must not outlive a train; "
                    "fill the post-landing append"
                )


def _version_tuple(version: str) -> tuple[int, int, int]:
    major, minor, patch = version.split(".")
    return int(major), int(minor), int(patch)


def pending_warning_lines(root: Path) -> list[str]:
    """The drift-check lane's warning line per pending record (design §3.6:
    printed on every run — a state to finish, never a failure)."""
    lines = []
    for record in load_promotion_records(root):
        if record.pending:
            lines.append(
                f"{PENDING_WARNING_PREFIX}: {record.standard} {record.target} "
                "landed but its record is pending (no landing_sha) — fill "
                "the post-landing append"
            )
    return lines

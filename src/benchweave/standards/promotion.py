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
    lines, each admitted by a rule with its own verification: an identity
    re-stamp (the same line with its version-like substrings moved — the
    transition vocabulary of the ``<target>-dev`` label, the target and
    the pre-dev active version is exactly what the strip rule removes;
    issue #288 M1: NO line admits by token presence alone — the tokens are
    remediation vocabulary, never admission), a VERIFIED digest re-stamp
    whose (residual -> digest-path-sequence) binding matches per hunk
    (every digest names a real file of the right tree, in the same
    in-line position, under the same field text — the #288 refute-slate
    overhaul: reordering, intra-line swaps, payload renames, count-changing
    deletions and ``--``/``++``-initial content lines all refuse), or the
    regenerated ``validation-report.md``; any other changed line refuses
    ``promotion_sweep_violation:`` — the sweep-laundry mitigation (design
    risk 6, tightened by #288 M1 and its refute slate);
(c) PENDING-SUCCESSOR — a pending record refuses once a SUCCESSOR version
    of the same standard exists on main (pendingness must not outlive a
    train); the drift-check lane (:func:`pending_warning_lines`, wired into
    ``check.run_check``) prints pending records as a warning line on every
    run.
plus the NO-RECORD gate, with TWO derivations (issue #288 M2 — the first
    is the landing's own self-declaration, the second is history): a
    retained version whose corpus rows cite a ``-dev`` source (the
    promotion's own signature — GOVERNANCE's "its corpus rows cite the dev
    path as source") must carry a record; AND a retained version whose
    introducing commit's parent — located through the object store —
    declared the standard's dev head at ``<version>-dev`` must carry a
    record even when its rows cite a released predecessor (a laundered
    source). History that cannot resolve in an existing git root refuses
    ``promotion_history_unavailable:`` — the gate fails loudly on
    amputated history, never silently passes; a root that is not a git
    repository has no history to consult, and the current-tree derivation
    still governs there.

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
named), ``promotion_pending_stale:``, ``promotion_history_unavailable:``
(issue #288 M2).
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import subprocess
from collections import Counter
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


#: A line whose non-digest payload is nothing but JSON/markdown wrapping
#: — the disclosed shape of an unpaired digest-bearing APPEND (its only
#: payload is the digest; it is visible as an added line in the promotion
#: PR, which is the review surface, and cannot pair with — hence cannot
#: launder an edit of — any removed line).
_TRIVIAL_PAYLOAD = re.compile(r"^[\s\"'{}\[\],:]*$")


def _line_facts(
    line: str, digest_names: dict[str, set[str]]
) -> tuple[str, list[str], tuple[frozenset[str], ...]]:
    """One changed line's facts for the sweep's binding rule (the issue
    #288 refute-slate overhaul): the versionish+digest-stripped RESIDUAL
    (the non-digest payload, constrained like any other text), the
    line's digest SEQUENCE (order within a line is meaningful — the
    fields' positions name their files), and the path-set SEQUENCE those
    digests name in the line's own tree. Admission is the per-hunk
    multiset equality of (residual -> path-sequence) bindings: order
    across lines is free (a reordered hunk of honest re-stamps admits),
    order within a line and the payload text are not (an intra-line swap
    or a key rename refuses)."""
    digests = _HEXDIGEST.findall(line)
    residual = _VERSIONISH.sub("", _HEXDIGEST.sub("", line))
    return (
        residual,
        digests,
        tuple(frozenset(digest_names.get(d, set())) for d in digests),
    )


def _hunk_offences(
    hunk_removed: list[str],
    hunk_added: list[str],
    dev_digests: set[str],
    dev_digest_names: dict[str, set[str]],
    promoted_digests: set[str],
    promoted_digest_names: dict[str, set[str]],
) -> list[str]:
    """One hunk's offences under the binding rule (the issue #288
    refute-slate overhaul of the sweep's digest lane).

    The hunk admits when the MULTISET of (residual -> path-sequence)
    bindings is equal on both sides — order across lines is free, order
    within a line and the non-digest payload are not. Leftover removed
    bindings are offences (a re-stamp without its counterpart is a
    deletion; a plain unmatched removal is an unexplained edit). Leftover
    added bindings are offences EXCEPT the disclosed residual: a
    digest-bearing append whose non-digest payload is nothing but
    wrapping (its only payload is real digests; visible in the promotion
    PR, the review surface). The F6 membership rule runs first: an
    invented digest refuses naming it, on either side. When both sides
    carry leftover digest lines they are paired index-wise as REASSIGNED
    digests in the detail, quoting one digest from each side. Disclosed
    residual (mech-F9): two files with IDENTICAL content in one tree
    share a digest, making the digest->path mapping one-to-many — the
    binding's path-set then names both files and a re-stamp between them
    admits; measured zero duplicate-content files within any of the 18
    retained version directories on today's corpus (the cross-version
    sharing copy-never-move produces lives in OTHER trees and never
    enters one tree's map)."""
    offending: list[str] = []
    removed_facts = [_line_facts(line, dev_digest_names) for line in hunk_removed]
    added_facts = [_line_facts(line, promoted_digest_names) for line in hunk_added]
    for facts, line in zip(removed_facts, hunk_removed, strict=True):
        unknown = [digest for digest in facts[1] if digest not in dev_digests]
        if unknown:
            offending.append(
                f" [unexplained digest: {unknown[0]}]-" + line.strip()[:100]
            )
    for facts, line in zip(added_facts, hunk_added, strict=True):
        unknown = [digest for digest in facts[1] if digest not in promoted_digests]
        if unknown:
            offending.append(
                f" [unexplained digest: {unknown[0]}]+" + line.strip()[:100]
            )
    removed_counts = Counter((facts[0], facts[2]) for facts in removed_facts)
    added_counts = Counter((facts[0], facts[2]) for facts in added_facts)
    missing = removed_counts - added_counts
    extra = added_counts - removed_counts
    unmatched_removed: list[tuple[tuple[str, list[str], tuple[frozenset[str], ...]], str]] = []
    for facts, line in zip(removed_facts, hunk_removed, strict=True):
        binding = (facts[0], facts[2])
        if missing.get(binding, 0) > 0:
            missing[binding] -= 1
            unmatched_removed.append((facts, line))
    unmatched_added: list[tuple[tuple[str, list[str], tuple[frozenset[str], ...]], str]] = []
    for facts, line in zip(added_facts, hunk_added, strict=True):
        binding = (facts[0], facts[2])
        if extra.get(binding, 0) > 0:
            extra[binding] -= 1
            unmatched_added.append((facts, line))
    leftover_removed_digest = [(facts, line) for facts, line in unmatched_removed if facts[1]]
    leftover_added_digest = [(facts, line) for facts, line in unmatched_added if facts[1]]
    paired = min(len(leftover_removed_digest), len(leftover_added_digest))
    for index in range(paired):
        removed_facts_pair, removed_line = leftover_removed_digest[index]
        added_facts_pair, _added_line = leftover_added_digest[index]
        offending.append(
            f" [reassigned digest: {removed_facts_pair[1][0]} -> "
            f"{added_facts_pair[1][0]}]-" + removed_line.strip()[:100]
        )
    for facts, line in leftover_removed_digest[paired:]:
        offending.append(
            f" [digest re-stamp without its counterpart: {facts[1][0]}]-"
            + line.strip()[:100]
        )
    for facts, line in unmatched_removed:
        if not facts[1]:
            offending.append("-" + line.strip()[:100])
    for facts, line in unmatched_added:
        if facts[1] and _TRIVIAL_PAYLOAD.fullmatch(facts[0]):
            # The disclosed append residual: digest-only payload, real
            # digests (the membership precheck refused unknowns above).
            continue
        offending.append("+" + line.strip()[:100])
    return offending


def _sweep_check(
    root: Path,
    record: PromotionRecord,
    corpus_rows: list[dict[str, Any]],
) -> None:
    """Gate (b): only version-transition lines may differ between the dev
    tree at ``dev_edit_sha`` and the promoted directory.

    The design names the version transition tokens (the ``<target>-dev``
    label, the target, the pre-dev active version from the promoted rows'
    ``lineage``) — the VOCABULARY of a legitimate transition, demoted to
    remediation text since issue #288 M1: no line admits by containing a
    token. The ADMISSION RULE (the issue #288 refute-slate overhaul) is
    the per-hunk multiset equality of (residual -> path-sequence)
    bindings, computed by ``_line_facts`` and judged by
    ``_hunk_offences``:

    - IDENTITY RE-STAMP: a changed line admits when the same hunk's
      opposite side carries a line equal after stripping every version-like
      substring — the same sentence/URN with its version numbers moved
      (the founding record's pre-reset ``1.0.0`` URNs and the prose title
      both ride this rule). Disclosed (the slice-2 comparator's R4 class):
      a version-string motion in a non-version SEMANTIC field admits; the
      planted-wording control keeps the teeth.
    - DIGEST RE-STAMP (VR-36a's "URN/digest restamp"): a changed line
      carrying bare sha256s admits when every digest names a real file of
      the right tree (bidirectional membership; an invented digest matches
      nothing and refuses — refute fold F6) AND its binding matches: the
      same residual, and the same SEQUENCE of digest->path assignments —
      a re-stamp moves a file's citation to that same file's new digest,
      never onto a different file's digest, a different position in the
      line, or a renamed field. Verified on the founding record: every
      one of its changed digest pairs maps same-relative-path with stable
      payloads, 9/9 pairs (DESIGN-MEASURED).
    - REMOVED-side bindings without counterparts refuse (a deletion is
      not a transition); ADDED-side bindings without counterparts refuse
      unless the line's only payload is real digests (the disclosed
      visible-append residual).
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
    # The digest re-stamp rule's two name-maps: every file's digest in each
    # tree, keyed back to the within-directory relative name — membership
    # AND assignment (issue #288 M1) are the verification.
    dev_digests: set[str] = set()
    dev_digest_names: dict[str, set[str]] = {}
    for relative in listing.stdout.splitlines():
        if not relative:
            continue
        raw = _git_show(root, f"{record.dev_edit_sha}:{relative}")
        if raw is not None:
            digest = hashlib.sha256(raw).hexdigest()
            dev_digests.add(digest)
            dev_digest_names.setdefault(digest, set()).add(
                relative.removeprefix(prefix)
            )
    promoted_digests: set[str] = set()
    promoted_digest_names: dict[str, set[str]] = {}
    for path in promoted_dir.rglob("*"):
        if not path.is_file():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        promoted_digests.add(digest)
        promoted_digest_names.setdefault(digest, set()).add(
            str(path.relative_to(promoted_dir))
        )
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
        hunks: list[tuple[list[str], list[str]]] = []
        removed: list[str] = []
        added: list[str] = []
        in_hunk = False
        for line in difflib.unified_diff(old_lines, new_lines, n=0):
            if line.startswith("@@"):
                in_hunk = True
                if removed or added:
                    hunks.append((removed, added))
                    removed, added = [], []
                continue
            if not in_hunk and line.startswith(("+++", "---")):
                # The file headers precede the first hunk ONLY — inside a
                # hunk a content line starting with "--"/"++" is content
                # (the refute slate's shape 5: prefix filtering made such
                # lines invisible to every rule).
                continue
            if line.startswith("-"):
                removed.append(line[1:])
            elif line.startswith("+"):
                added.append(line[1:])
        if removed or added:
            hunks.append((removed, added))
        offending: list[str] = []
        for hunk_removed, hunk_added in hunks:
            # The refute-slate admission rule: the per-hunk multiset of
            # (residual -> path-sequence) bindings must be equal on both
            # sides — see _hunk_offences for the offences and residuals.
            offending.extend(
                _hunk_offences(
                    hunk_removed,
                    hunk_added,
                    dev_digests,
                    dev_digest_names,
                    promoted_digests,
                    promoted_digest_names,
                )
            )
        if offending:
            raise StandardsError(
                f"promotion_sweep_violation: {record.standard}/{record.target}/"
                f"{name} differs from the dev tree at {record.dev_edit_sha} on "
                f"non-transition lines ({len(offending)} line(s), first: "
                f"{offending[0][:160]!r}) — the promotion sweep may carry only "
                f"the version transition (tokens {', '.join(tokens)} are "
                "remediation vocabulary; the residual/path bindings must "
                "match per hunk, digest re-stamps must keep their paths "
                "and payloads); move the change "
                "through the dev head or a new version, never under cover of "
                "the sweep"
            )


def _git_root(root: Path) -> bool:
    """Whether ``root`` sits inside a git work tree. The history-derived
    no-record trigger consults the object store; a root with none has no
    history to consult and the current-tree derivation governs."""
    result = subprocess.run(  # noqa: S603 — fixed argv
        [  # noqa: S607 — PATH git is the supported invocation
            "git",
            "-C",
            str(root),
            "rev-parse",
            "--show-toplevel",
        ],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def _is_shallow(root: Path) -> bool:
    """Whether the repository is depth-limited (a graft boundary — CI
    checkout shapes default here). A grafted introducing commit answers
    the parent query with NOTHING, masquerading as a root-commit organic
    introduction; the gate refuses on shallowness rather than trust it
    (issue #288 refute slate)."""
    result = subprocess.run(  # noqa: S603 — fixed argv
        [  # noqa: S607 — PATH git is the supported invocation
            "git",
            "-C",
            str(root),
            "rev-parse",
            "--is-shallow-repository",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def _introducing_commit(root: Path, git_path: str) -> tuple[str, list[str]] | None:
    """``(sha, parents)`` of the FIRST commit touching ``git_path`` — ALL
    parent shas (a merge landing's second parent is where a sanctioned
    flow declares the head), an empty list for a root-commit introduction
    (an organic founding). ``None`` when no introduction resolves (a git
    error, or an empty history for a path that exists on disk) — the
    caller refuses loudly, never silently passes (issue #288 M2, hardened
    by its refute slate)."""
    result = subprocess.run(  # noqa: S603 — fixed argv
        [  # noqa: S607 — PATH git is the supported invocation
            "git",
            "-C",
            str(root),
            "log",
            "--format=%H %P",
            "--reverse",
            "--",
            git_path,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    first = next((line for line in result.stdout.splitlines() if line.strip()), "")
    if not first:
        return None
    shas = first.split()
    return shas[0], shas[1:]


def _history_no_record_gate(
    root: Path,
    corpus_rows: list[dict[str, Any]],
    records: dict[tuple[str, str], PromotionRecord],
) -> None:
    """Issue #288 M2's derivation of the no-record trigger: the landing's
    INTRODUCING COMMIT's parent, not the landing's own citation. A
    promotion's dev head was declared on main before the landing
    (GOVERNANCE's OPEN is a PR adding the block to main); when the parent
    of the commit that introduced ``standards/<id>/<version>/`` declared
    that standard's dev head at exactly ``<version>-dev`` (strict match —
    an organic bump landing while an unrelated head is open does not
    fire), the landing was a promotion and needs its record even with
    laundered row sources.

    Root-commit introductions are organic (no parent, no declaration). A
    parent whose manifest is absent declares nothing (a history predating
    the standards system — conservative in the false-refusal direction);
    a parent whose manifest BYTES do not parse refuses
    ``promotion_history_unavailable:`` naming the parent (issue #288
    refute slate: a bare JSONDecodeError is a crash, not a refusal). ALL
    parents of the introducing commit are consulted (a merge landing's
    second parent is where the sanctioned flow declares the head). A
    SHALLOW repository with unrecorded retained versions refuses
    ``promotion_history_unavailable:`` outright — a graft boundary
    masquerades as a root-commit organic introduction, and CI checkout
    shapes default there (issue #288 refute slate). An unresolvable
    introduction refuses the same prefix. A root that is not a git
    repository skips the derivation (no object store to consult — the
    current-tree trigger still governs). Disclosed residual: a dev head
    that never landed on main leaves no main-history evidence — bytes-wise
    that landing IS an organic bump; GOVERNANCE's OPEN/EDIT flow plus the
    mandatory governor lane are the process gate for that shape.
    """
    if not _git_root(root):
        return
    retained: set[tuple[str, str]] = set()
    for row in corpus_rows:
        parts = str(row.get("path", "")).split("/")
        if len(parts) >= 2 and re.fullmatch(r"\d+\.\d+\.\d+", parts[1]):
            retained.add((parts[0], parts[1]))
    pending = [pair for pair in sorted(retained) if pair not in records]
    if pending and _is_shallow(root):
        standard_id, version = pending[0]
        raise StandardsError(
            f"promotion_history_unavailable: {standard_id}@{version} is "
            "retained with no record and this repository is SHALLOW (a graft "
            "boundary — depth-limited history cannot evidence an introducing "
            "commit's parents, and a grafted landing masquerades as a "
            "root-commit organic introduction); verify on a full clone or "
            "fetch unshallow"
        )
    parent_manifests: dict[str, dict[str, Any] | None] = {}
    for standard_id, version in pending:
        found = _introducing_commit(root, f"standards/{standard_id}/{version}/")
        if found is None:
            raise StandardsError(
                f"promotion_history_unavailable: {standard_id}@{version} is "
                "retained on this tree but no introducing commit resolves in "
                "the object store (shallow or amputated history) — the "
                "history-derived no-record gate fails loudly rather than "
                "pass silently"
            )
        _sha, parents = found
        if not parents:
            continue  # a root-commit introduction: organic
        for parent in parents:
            # ALL parents, not only the first (issue #288 refute slate): a
            # merge landing's second parent is exactly where a sanctioned
            # flow declares the head, and the strict <version>-dev match
            # guards the false-refusal direction.
            if parent not in parent_manifests:
                raw = _git_show(root, f"{parent}:standards/standards-manifest.json")
                if raw is None:
                    parent_manifests[parent] = None
                else:
                    try:
                        parent_manifests[parent] = json.loads(raw)
                    except json.JSONDecodeError as exc:
                        raise StandardsError(
                            f"promotion_history_unavailable: the manifest at "
                            f"parent {parent} of {standard_id}@{version}'s "
                            f"introducing commit is not valid JSON ({exc.msg} "
                            f"at line {exc.lineno}) — the history-derived "
                            "no-record gate refuses rather than guess at a "
                            "malformed parent"
                        ) from None
            document = parent_manifests[parent]
            if document is None:
                continue  # this parent predates the standards system
            for entry in document.get("standards", []):
                if str(entry.get("id")) != standard_id:
                    continue
                dev = entry.get("dev")
                label = dev.get("version") if isinstance(dev, dict) else None
                if isinstance(label, str) and label == f"{version}-dev":
                    raise StandardsError(
                        f"promotion_record_absent: {standard_id}@{version} landed "
                        f"a promotion whose introducing commit's parent ({parent}) "
                        f"declared dev head {label} — the landing required a "
                        "record in standards/promotion-records.json even though "
                        "its corpus rows cite a released predecessor as source; "
                        "the promotion's audit trail (dev_edit_sha, "
                        "dev_tree_digest, landing_sha) is not optional"
                    )
                break


def validate_promotion_records(root: Path) -> None:
    """Run the promotion gates over the committed tree; refuse on any arm.

    The no-record gate first (a dev-sourced promotion with no record — the
    current-tree citation trigger, then the history-derived trigger), then
    per record: the dev-edit sha resolves, the landing sha resolves when
    filled, the digest matches the sha's tree, the sweep is transition-
    only under the paired rules, and pendingness has not outlived a
    successor. Every refusal names the standard, the target and the arm's
    own evidence.
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
    # The second, non-self-declared derivation of the same trigger (issue
    # #288 M2): what history says the landing was, regardless of citation.
    _history_no_record_gate(root, corpus_rows, records)
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

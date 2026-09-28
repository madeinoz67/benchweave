"""Promotion records and their three gates (issue #218, #203 slice 4).

Design §3.6 (owner Q7): ``standards/promotion-records.json`` is governance
data outside the corpus (like the policy block — no corpus-manifest rows,
repin untouched). One record per promotion — standard, target, dev-head
name, ``dev_edit_sha``, ``dev_tree_digest`` (sha256 over the sorted
normative path+digest list of the final dev state, written at PR time),
``landing_sha`` (filled by the immediate post-landing append; until filled
the record is ``pending``). The gates (D3): a dev-sourced promotion with no
record refuses; a digest that does not match the sha's tree refuses; a
planted NON-version edit between the dev tree and the promoted tree refuses
``promotion_sweep_violation:``; a pending record with a successor version
refuses. D4 (VR-8 as amended by Q7): no ``merge-base --is-ancestor``
requirement on any branch tip — the fixture's dev-edit sha is UNREACHABLE
from main (the squash-landing shape) and the record gate still passes via
the landing-sha + object-store checks.

The fixture builds the squash-landing shape literally: the head is opened
and edited on a branch main never carries; the landing commit on main adds
the promoted directory whose corpus rows cite the dev path as ``source``
(the promotion's own signature) and the pre-dev active path as ``lineage``.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from benchweave.standards.export import canonical_json
from benchweave.standards.manifest import StandardsError
from benchweave.standards.promotion import (
    PromotionRecord,
    dev_tree_digest_at,
    load_promotion_records,
    validate_promotion_records,
)

ROOT = Path(__file__).resolve().parents[2]

TARGET = "0.4.0"
LABEL = f"{TARGET}-dev"
PRE_DEV_ACTIVE = "0.2.2"


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"git {args} failed:\n{result.stderr}"
    return result.stdout.strip()


def _commit(root: Path, message: str) -> str:
    _git(root, "add", "-A")
    _git(
        root,
        "-c",
        "user.name=fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-q",
        "-m",
        message,
    )
    return _git(root, "rev-parse", "HEAD")


def _plant_head(root: Path) -> None:
    """Open the head on the working tree: a copy of the active 0.2.2 whose
    descriptor schema carries the dev label (the one version-token a real
    head's first edit makes), rows citing the active path as source, and
    the manifest's dev block."""
    active = root / "standards" / "otdp" / PRE_DEV_ACTIVE
    head = root / "standards" / "otdp" / LABEL
    shutil.copytree(active, head)
    schema_path = head / "otdp-device-descriptor.schema.json"
    schema = json.loads(schema_path.read_bytes())
    schema["properties"]["otdp_version"]["const"] = LABEL
    schema_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")

    manifest_path = root / "standards" / "standards-manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    names = sorted(path.name for path in head.iterdir() if path.is_file())
    for entry in manifest["standards"]:
        if entry["id"] == "otdp":
            entry["dev"] = {
                "version": LABEL,
                "opened": "2026-09-28",
                "normative": [f"standards/otdp/{LABEL}/{name}" for name in names],
            }
    manifest_path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")

    corpus_path = root / "standards" / "corpus-manifest.json"
    corpus = json.loads(corpus_path.read_bytes())
    for name in names:
        raw = (head / name).read_bytes()
        corpus["files"].append(
            {
                "path": f"otdp/{LABEL}/{name}",
                "source": f"standards/otdp/{PRE_DEV_ACTIVE}/{name}",
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    corpus_path.write_text(json.dumps(corpus, indent=1), encoding="utf-8")


def _landing_tree(root: Path, *, sweep_edit: bool, successor: bool) -> None:
    """Build main's landing state: the promoted directory (the dev tree's
    files with the version tokens swept to the target), corpus rows citing
    the dev path as ``source`` and the pre-dev active path as ``lineage``
    (GOVERNANCE's promotion shape), and optionally a successor 0.4.1 (a
    normal bump, no dev source — pendingness must not outlive a train)."""
    promoted = root / "standards" / "otdp" / TARGET
    promoted.mkdir(parents=True)
    corpus_path = root / "standards" / "corpus-manifest.json"
    corpus = json.loads(corpus_path.read_bytes())
    head_prefix = f"standards/otdp/{LABEL}/"
    listing = _git(
        root, "ls-tree", "-r", "--name-only", "dev-train", "--",
        f"standards/otdp/{LABEL}",
    ).splitlines()
    names = sorted(
        line.removeprefix(head_prefix)
        for line in listing
        if line and "/" not in line.removeprefix(head_prefix)
    )
    for relative in listing:
        if not relative:
            continue
        name = relative.removeprefix(head_prefix)
        if "/" in name:
            (promoted / name).parent.mkdir(parents=True, exist_ok=True)
        raw = subprocess.run(
            ["git", "-C", str(root), "show", f"dev-train:{relative}"],
            capture_output=True,
            check=False,
        ).stdout
        swept = raw.replace(LABEL.encode(), TARGET.encode())
        (promoted / name).write_bytes(swept)
    if sweep_edit:
        # The planted NON-version edit: a line the sweep tokens cannot
        # explain, smuggled into the promoted tree.
        schema_path = promoted / "otdp-device-descriptor.schema.json"
        schema = json.loads(schema_path.read_bytes())
        schema["properties"]["display_name"]["description"] = (
            "sweep-smuggled wording change"
        )
        schema_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
    for name in names:
        raw = (promoted / name).read_bytes()
        corpus["files"].append(
            {
                "path": f"otdp/{TARGET}/{name}",
                "source": f"standards/otdp/{LABEL}/{name}",
                "lineage": f"standards/otdp/{PRE_DEV_ACTIVE}/{name}",
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    if successor:
        successor_dir = root / "standards" / "otdp" / "0.4.1"
        successor_dir.mkdir()
        for name in names:
            raw = (promoted / name).read_bytes()
            swept = raw.replace(TARGET.encode(), b"0.4.1")
            (successor_dir / name).write_bytes(swept)
            corpus["files"].append(
                {
                    "path": f"otdp/0.4.1/{name}",
                    "source": f"standards/otdp/{TARGET}/{name}",
                    "sha256": hashlib.sha256(swept).hexdigest(),
                }
            )
    corpus_path.write_text(json.dumps(corpus, indent=1), encoding="utf-8")


def _fixture(
    tmp_path: Path,
    *,
    sweep_edit: bool = False,
    successor: bool = False,
    record: dict[str, Any] | None | object = ...,
) -> tuple[Path, dict[str, str]]:
    """The squash-landing fixture: base on main, head opened+edited on
    ``dev-train``, landing committed on main WITHOUT the branch's commits
    (the dev-edit sha is unreachable from main by construction)."""
    root = tmp_path / "repo"
    root.mkdir()
    shutil.copytree(ROOT / "standards", root / "standards")
    # The copied tree's PRE-MECHANISM dev-sourced promotion (execution 0.2.0,
    # promoted 2026-09-24 before this slice) would fire the no-record gate
    # ahead of every planted arm — and its founding record cites shas this
    # fresh repository does not carry. The fixture's tree carries ONLY the
    # promotion it plants: rows read as ordinary lineage-sourced copies and
    # the founding record is dropped. The real tree's own posture is pinned
    # separately below.
    (root / "standards" / "promotion-records.json").unlink(missing_ok=True)
    corpus_path = root / "standards" / "corpus-manifest.json"
    corpus = json.loads(corpus_path.read_bytes())
    for row in corpus["files"]:
        source = str(row.get("source") or "")
        if "-dev/" in source:
            if row.get("lineage"):
                row["source"] = row.pop("lineage")
            else:
                row.pop("source", None)
                row.pop("lineage", None)
    corpus_path.write_text(json.dumps(corpus, indent=1), encoding="utf-8")
    _git(root, "init", "-q", "-b", "main")
    _commit(root, "base")
    _git(root, "checkout", "-q", "-b", "dev-train")
    _plant_head(root)
    _commit(root, "open head")
    # The dev edit: a real content change to the head (the target-titled
    # const ride is already in; touch a prose companion so the final dev
    # state differs from the open state).
    prose = root / "standards" / "otdp" / LABEL / "device-classes.md"
    prose.write_bytes(prose.read_bytes() + b"\nA dev-stage companion edit.\n")
    corpus_path = root / "standards" / "corpus-manifest.json"
    corpus = json.loads(corpus_path.read_bytes())
    for row in corpus["files"]:
        if row["path"] == f"otdp/{LABEL}/device-classes.md":
            row["sha256"] = hashlib.sha256(prose.read_bytes()).hexdigest()
    corpus_path.write_text(json.dumps(corpus, indent=1), encoding="utf-8")
    dev_edit_sha = _commit(root, "dev edit")
    _git(root, "checkout", "-q", "main")
    _landing_tree(root, sweep_edit=sweep_edit, successor=successor)
    landing_sha = _commit(root, "promotion landing")
    facts = {"dev_edit_sha": dev_edit_sha, "landing_sha": landing_sha}
    if isinstance(record, (dict, type(None))):
        _write_records(root, record)
    return root, facts


def _write_records(root: Path, record: dict[str, Any] | None) -> None:
    document = {
        "promotion_record_version": 1,
        "records": [record] if record is not None else [],
    }
    (root / "standards" / "promotion-records.json").write_bytes(
        canonical_json(document)
    )


def _honest_record(root: Path, facts: dict[str, str]) -> dict[str, Any]:
    return {
        "standard": "otdp",
        "target": TARGET,
        "dev_head": LABEL,
        "dev_edit_sha": facts["dev_edit_sha"],
        "dev_tree_digest": dev_tree_digest_at(
            root, "otdp", LABEL, facts["dev_edit_sha"]
        ),
        "landing_sha": facts["landing_sha"],
    }


# --- the honest record passes, and D4 holds --------------------------------------


def test_the_honest_record_passes_all_gates(tmp_path: Path) -> None:
    """The GREEN spine: a record whose digest matches the sha's tree, whose
    landing sha resolves, over a token-only sweep — validates clean."""
    root, facts = _fixture(tmp_path, record=None)
    _write_records(root, _honest_record(root, facts))
    validate_promotion_records(root)


def test_d4_the_dev_edit_sha_is_unreachable_from_main_and_still_passes(
    tmp_path: Path,
) -> None:
    """D4 (VR-8 as amended by owner Q7): NO merge-base --is-ancestor
    requirement on any branch tip. The fixture's dev-edit sha is provably
    NOT an ancestor of main (asserted against git itself), and the record
    gate still passes — the landing sha and the object-store reads are the
    checks, never branch topology."""
    root, facts = _fixture(tmp_path, record=None)
    _write_records(root, _honest_record(root, facts))
    is_ancestor = subprocess.run(
        ["git", "-C", str(root), "merge-base", "--is-ancestor",
         facts["dev_edit_sha"], "main"],
        capture_output=True,
        check=False,
    ).returncode
    assert is_ancestor != 0, "the fixture must build the squash shape (unreachable)"
    validate_promotion_records(root)


# --- D3: the four refusal arms ----------------------------------------------------


def test_d3_no_record_refuses(tmp_path: Path) -> None:
    """A dev-sourced promotion (corpus rows citing a ``-dev`` source) with
    NO record refuses — the promotion's audit trail is not optional."""
    root, _facts = _fixture(tmp_path)
    with pytest.raises(StandardsError) as raised:
        validate_promotion_records(root)
    message = str(raised.value)
    assert message.startswith("promotion_record_absent:"), message
    assert "otdp" in message and TARGET in message


def test_d3_dev_tree_digest_mismatch_refuses(tmp_path: Path) -> None:
    """The digest gate: a record whose dev_tree_digest does not equal the
    digest of the dev tree at dev_edit_sha (read through the object store)
    refuses."""
    root, facts = _fixture(tmp_path, record=None)
    honest = _honest_record(root, facts)
    flipped = ("0" if honest["dev_tree_digest"][0] != "0" else "1") + honest[
        "dev_tree_digest"
    ][1:]
    _write_records(root, {**honest, "dev_tree_digest": flipped})
    with pytest.raises(StandardsError) as raised:
        validate_promotion_records(root)
    message = str(raised.value)
    assert message.startswith("promotion_digest_mismatch:"), message
    assert flipped in message


def test_d3_planted_non_version_edit_refuses_sweep_violation(tmp_path: Path) -> None:
    """The sweep gate: the diff between the dev tree at dev_edit_sha and
    the promoted directory may contain ONLY lines carrying the version
    transition tokens (the <target>-dev string, the target, the pre-dev
    active version) — a planted wording change refuses
    ``promotion_sweep_violation:`` naming the file."""
    root, facts = _fixture(tmp_path, sweep_edit=True, record=None)
    _write_records(root, _honest_record(root, facts))
    with pytest.raises(StandardsError) as raised:
        validate_promotion_records(root)
    message = str(raised.value)
    assert message.startswith("promotion_sweep_violation:"), message
    assert "otdp-device-descriptor.schema.json" in message


def test_d3_pending_record_with_a_successor_refuses(tmp_path: Path) -> None:
    """Pendingness must not outlive a train: a pending record (landing_sha
    unfilled) refuses once a SUCCESSOR version of the same standard exists
    on main; the successor's rows need no record of their own (a normal
    bump's source is the predecessor, not a dev head)."""
    root, facts = _fixture(tmp_path, successor=True, record=None)
    honest = _honest_record(root, facts)
    _write_records(root, {**honest, "landing_sha": None})
    with pytest.raises(StandardsError, match="promotion_pending_stale:"):
        validate_promotion_records(root)


def test_a_pending_record_without_a_successor_only_warns(tmp_path: Path) -> None:
    """The immediate post-landing window (the append not yet made): a
    pending record with NO successor validates — the drift-check lane
    prints it as a warning line, not a failure."""
    from benchweave.standards.promotion import pending_warning_lines

    root, facts = _fixture(tmp_path, record=None)
    honest = _honest_record(root, facts)
    _write_records(root, {**honest, "landing_sha": None})
    validate_promotion_records(root)
    warnings = pending_warning_lines(root)
    assert warnings == [
        f"promotion_pending_warning: otdp {TARGET} landed but its record is "
        "pending (no landing_sha) — fill the post-landing append"
    ]


# --- the record carrier ------------------------------------------------------------


def test_an_absent_records_file_is_an_empty_history_not_a_refusal(
    tmp_path: Path,
) -> None:
    """Before the first recorded promotion the file need not exist (the
    mechanism's own first promotion authors it); an EMPTY history is
    legitimate, and the no-record gate is what refuses unrecorded
    dev-sourced promotions — exercised against a promotion-free tree here
    (the real tree carries one: pinned below)."""
    root = tmp_path / "bare"
    root.mkdir()
    shutil.copytree(ROOT / "standards", root / "standards")
    (root / "standards" / "promotion-records.json").unlink(missing_ok=True)
    corpus_path = root / "standards" / "corpus-manifest.json"
    corpus = json.loads(corpus_path.read_bytes())
    for row in corpus["files"]:
        if "-dev/" in str(row.get("source") or ""):
            if row.get("lineage"):
                row["source"] = row.pop("lineage")
            else:
                row.pop("source", None)
                row.pop("lineage", None)
    corpus_path.write_text(json.dumps(corpus, indent=1), encoding="utf-8")
    assert load_promotion_records(root) == ()
    validate_promotion_records(root)


def test_the_founded_real_tree_validates() -> None:
    """The PERMANENT posture (was: ``test_the_real_tree_refuses_until_the_
    founding_record_lands`` — the temporary pre-founding state). The
    founding record (coordinator directive 2026-09-28, option (a))
    recovered execution 0.2.0's pre-mechanism promotion from history —
    dev_edit_sha 53d700d17ec2 (the final dev state), landing_sha 54a59fab364a
    — and the real tree now VALIDATES: the digest matches the tree at the
    sha by construction (dev_tree_digest_at derived it), the sweep is
    transition-only under the refined rules, and both shas are main
    ancestors, so every fresh clone verifies the record forever."""
    validate_promotion_records(ROOT)
    records = {
        (record.standard, record.target): record
        for record in load_promotion_records(ROOT)
    }
    founding = records[("execution", "0.2.0")]
    assert founding.dev_edit_sha.startswith("53d700d17ec2")
    assert founding.landing_sha is not None and founding.landing_sha.startswith(
        "54a59fab364a"
    )
    assert founding.pending is False


def test_a_tampered_founding_record_still_refuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The gates stay armed on the real tree, never grandfathered: the
    founding record with ONE flipped digest digit refuses
    ``promotion_digest_mismatch:`` naming both values — audited by the same
    machinery as every future record, over the REAL tree and object store
    (the loader is patched to hand the gate the tampered record; nothing on
    disk is touched)."""
    from dataclasses import replace

    import benchweave.standards.promotion as promotion_module

    (honest_record,) = load_promotion_records(ROOT)
    assert honest_record.dev_tree_digest[0] != "0"  # the flip below changes it
    tampered = replace(
        honest_record, dev_tree_digest="0" + honest_record.dev_tree_digest[1:]
    )
    monkeypatch.setattr(
        promotion_module, "load_promotion_records", lambda root: (tampered,)
    )
    with pytest.raises(StandardsError) as raised:
        validate_promotion_records(ROOT)
    message = str(raised.value)
    assert message.startswith("promotion_digest_mismatch:"), message
    assert honest_record.dev_tree_digest in message
    assert tampered.dev_tree_digest in message


def test_a_malformed_record_refuses_typed(tmp_path: Path) -> None:
    """The carrier fails closed: a record missing its dev_edit_sha or
    carrying a non-hex sha refuses with the document prefix, never a
    KeyError downstream."""
    root, facts = _fixture(tmp_path, record=None)
    honest = _honest_record(root, facts)
    _write_records(root, {**honest, "dev_edit_sha": "not-a-sha"})
    with pytest.raises(StandardsError, match="promotion_record_invalid:"):
        validate_promotion_records(root)


def test_an_unresolvable_landing_sha_refuses(tmp_path: Path) -> None:
    """The landing-sha half of D4's checks: the recorded landing commit
    must resolve in the object store — a fabricated sha refuses."""
    root, facts = _fixture(tmp_path, record=None)
    honest = _honest_record(root, facts)
    _write_records(root, {**honest, "landing_sha": "f" * 40})
    with pytest.raises(StandardsError, match="promotion_landing_unresolved:"):
        validate_promotion_records(root)


def test_the_digest_formula_is_the_sorted_normative_path_digest_list(
    tmp_path: Path,
) -> None:
    """The writer-side helper and the gate share ONE formula: sha256 over
    the canonical JSON of the sorted normative (path, digest) list at the
    sha — pinned by hand-computing it here from the object-store bytes."""
    root, facts = _fixture(tmp_path, record=None)
    manifest = json.loads(
        subprocess.run(
            ["git", "-C", str(root), "show",
             f"{facts['dev_edit_sha']}:standards/standards-manifest.json"],
            capture_output=True,
            check=False,
        ).stdout
    )
    entry = next(e for e in manifest["standards"] if e["id"] == "otdp")
    pairs = []
    for normative in sorted(entry["dev"]["normative"]):
        raw = subprocess.run(
            ["git", "-C", str(root), "show",
             f"{facts['dev_edit_sha']}:{normative}"],
            capture_output=True,
            check=False,
        ).stdout
        pairs.append([normative, hashlib.sha256(raw).hexdigest()])
    expected = hashlib.sha256(canonical_json(pairs)).hexdigest()
    assert dev_tree_digest_at(root, "otdp", LABEL, facts["dev_edit_sha"]) == expected


def test_records_parse_into_the_carrier(tmp_path: Path) -> None:
    root, facts = _fixture(tmp_path, record=None)
    honest = _honest_record(root, facts)
    _write_records(root, honest)
    (record,) = load_promotion_records(root)
    assert isinstance(record, PromotionRecord)
    assert record.standard == "otdp"
    assert record.target == TARGET
    assert record.pending is False

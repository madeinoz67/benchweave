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


def _plant_cross_refs(root: Path, *, one_line: bool = False) -> None:
    """M1's pairing fixture (issue #288): two example files whose bytes
    carry the dev label — so the landing sweep MOVES their digests — and a
    commissioning document citing those digests. The honest landing
    re-stamps the citation to the promoted digests (same relative paths in
    both trees); the attack swaps the two values (both digests real
    members of the promoted tree — only the pairing rule refuses).
    ``one_line`` writes the citation as ONE compact line (the refute
    slate's intra-line swap arm: both digests on a single line)."""
    examples = root / "standards" / "otdp" / LABEL / "examples"
    examples.mkdir(exist_ok=True)
    for name, role in (("bench.json", "bench"), ("report.json", "report")):
        (examples / name).write_text(
            json.dumps({"otdp_version": LABEL, "role": role}, indent=2) + "\n",
            encoding="utf-8",
        )
    commissioning = {
        "bench_sha256": hashlib.sha256(
            (examples / "bench.json").read_bytes()
        ).hexdigest(),
        "report_sha256": hashlib.sha256(
            (examples / "report.json").read_bytes()
        ).hexdigest(),
    }
    citation = (
        json.dumps(commissioning, separators=(",", ":")) + "\n"
        if one_line
        else json.dumps(commissioning, indent=2) + "\n"
    )
    (root / "standards" / "otdp" / LABEL / "commissioning.json").write_text(
        citation, encoding="utf-8"
    )


def _landing_tree(
    root: Path,
    *,
    sweep_edit: bool,
    successor: bool,
    laundered: bool = False,
    close_head: bool = False,
    cross_refs: bool = False,
    one_line_commissioning: bool = False,
    drop_dash_line: bool = False,
) -> None:
    """Build main's landing state: the promoted directory (the dev tree's
    files with the version tokens swept to the target), corpus rows citing
    the dev path as ``source`` and the pre-dev active path as ``lineage``
    (GOVERNANCE's promotion shape), and optionally a successor 0.4.1 (a
    normal bump, no dev source — pendingness must not outlive a train).
    ``laundered`` cites the RELEASED predecessor as ``source`` instead (the
    organic-bump shape on a landing that was a promotion); ``close_head``
    removes the head, its corpus rows and the manifest's dev block (the
    sanctioned close); ``cross_refs`` re-stamps the commissioning citation
    to the promoted digests (the honest paired re-stamp)."""
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
    if cross_refs:
        # The honest paired digest re-stamp: the citation moves to the
        # promoted examples' digests (same relative paths, both trees).
        citation = {
            "bench_sha256": hashlib.sha256(
                (promoted / "examples" / "bench.json").read_bytes()
            ).hexdigest(),
            "report_sha256": hashlib.sha256(
                (promoted / "examples" / "report.json").read_bytes()
            ).hexdigest(),
        }
        text = (
            json.dumps(citation, separators=(",", ":")) + "\n"
            if one_line_commissioning
            else json.dumps(citation, indent=2) + "\n"
        )
        (promoted / "commissioning.json").write_text(text, encoding="utf-8")
    if drop_dash_line:
        # The landing DROPS the planted dash-dash line: the diff's removed
        # content line "-- SAFETY: ..." masquerades as a file header under
        # prefix filtering (the refute slate's shape 5).
        safety = promoted / "device-classes.md"
        kept = [
            line
            for line in safety.read_bytes().splitlines(keepends=True)
            if not line.startswith(b"-- SAFETY: envelope retained")
        ]
        safety.write_bytes(b"".join(kept))
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
        row: dict[str, Any] = {
            "path": f"otdp/{TARGET}/{name}",
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
        if laundered:
            # M2's laundered citation (issue #288): the released predecessor
            # as source — the organic bump's shape on a promotion landing.
            row["source"] = f"standards/otdp/{PRE_DEV_ACTIVE}/{name}"
        else:
            row["source"] = f"standards/otdp/{LABEL}/{name}"
            row["lineage"] = f"standards/otdp/{PRE_DEV_ACTIVE}/{name}"
        corpus["files"].append(row)
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
    if close_head:
        # The sanctioned close (issue #288's on-main variant): the promotion
        # landing removes the head directory, its corpus rows and the
        # manifest's dev block — what a real promotion PR carries.
        manifest_path = root / "standards" / "standards-manifest.json"
        manifest = json.loads(manifest_path.read_bytes())
        for entry in manifest["standards"]:
            if entry["id"] == "otdp":
                entry.pop("dev", None)
        manifest_path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
        corpus["files"] = [
            row
            for row in corpus["files"]
            if not str(row.get("path", "")).startswith(f"otdp/{LABEL}/")
        ]
        shutil.rmtree(root / "standards" / "otdp" / LABEL)
    corpus_path.write_text(json.dumps(corpus, indent=1), encoding="utf-8")


def _fixture(
    tmp_path: Path,
    *,
    sweep_edit: bool = False,
    successor: bool = False,
    record: dict[str, Any] | None | object = ...,
    head_on_main: bool = False,
    laundered: bool = False,
    cross_refs: bool = False,
    one_line_commissioning: bool = False,
    drop_dash_line: bool = False,
) -> tuple[Path, dict[str, str]]:
    """The squash-landing fixture: base on main, head opened+edited on
    ``dev-train``, landing committed on main WITHOUT the branch's commits
    (the dev-edit sha is unreachable from main by construction). Issue
    #288's variants: ``head_on_main`` opens the head ON MAIN first (the
    sanctioned GOVERNANCE flow — M2's history evidence), ``laundered`` makes
    the landing's corpus rows cite the RELEASED predecessor as ``source``
    (M2's bypass shape), ``cross_refs`` plants M1's digest-pairing files."""
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
    base_sha = _commit(root, "base")
    head_open_sha = ""
    if head_on_main:
        # M2's sanctioned-flow variant (issue #288): the OPEN lands on main
        # (GOVERNANCE's PR shape); only the dev edit rides the train branch.
        _plant_head(root)
        if cross_refs:
            _plant_cross_refs(root, one_line=one_line_commissioning)
        head_open_sha = _commit(root, "open head on main")
        _git(root, "checkout", "-q", "-b", "dev-train")
    else:
        _git(root, "checkout", "-q", "-b", "dev-train")
        _plant_head(root)
        if cross_refs:
            _plant_cross_refs(root, one_line=one_line_commissioning)
        _commit(root, "open head")
    # The dev edit: a real content change to the head (the target-titled
    # const ride is already in; touch a prose companion so the final dev
    # state differs from the open state). ``drop_dash_line`` also PLANTS a
    # "-- "-initial line here that the landing removes — the refute slate's
    # header-filter arm (a removed dash-dash content line masquerades as a
    # diff header under prefix filtering).
    prose = root / "standards" / "otdp" / LABEL / "device-classes.md"
    prefix = b"-- SAFETY: envelope retained\n" if drop_dash_line else b""
    prose.write_bytes(prefix + prose.read_bytes() + b"\nA dev-stage companion edit.\n")
    corpus_path = root / "standards" / "corpus-manifest.json"
    corpus = json.loads(corpus_path.read_bytes())
    for row in corpus["files"]:
        if row["path"] == f"otdp/{LABEL}/device-classes.md":
            row["sha256"] = hashlib.sha256(prose.read_bytes()).hexdigest()
    corpus_path.write_text(json.dumps(corpus, indent=1), encoding="utf-8")
    dev_edit_sha = _commit(root, "dev edit")
    _git(root, "checkout", "-q", "main")
    _landing_tree(
        root,
        sweep_edit=sweep_edit,
        successor=successor,
        laundered=laundered,
        close_head=head_on_main,
        cross_refs=cross_refs,
        one_line_commissioning=one_line_commissioning,
        drop_dash_line=drop_dash_line,
    )
    landing_sha = _commit(root, "promotion landing")
    facts = {
        "dev_edit_sha": dev_edit_sha,
        "landing_sha": landing_sha,
        "base_sha": base_sha,
        "head_open_sha": head_open_sha,
    }
    if isinstance(record, (dict, type(None))):
        _write_records(root, record)
    return root, facts


def _write_records(root: Path, record: dict[str, Any] | None) -> None:
    _write_records_many(root, [record] if record is not None else [])


def _write_records_many(root: Path, records: list[dict[str, Any]]) -> None:
    document = {"promotion_record_version": 1, "records": records}
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


# --- refute fold (lane B): duplicate rows, landing-sha identity, re-stamp teeth ----


def test_duplicate_rows_refuse_rather_than_shadow(tmp_path: Path) -> None:
    """F2: two records for one (standard, target) shadow silently — the
    dict build takes the LAST, so a flipped-digest record followed by an
    honest one launders the flip. Loading must refuse
    ``promotion_record_invalid:`` naming the duplicate (lane B's P1 arm:
    [BAD-flipped-digest, HONEST] passed)."""
    root, facts = _fixture(tmp_path, record=None)
    honest = _honest_record(root, facts)
    flipped = dict(honest)
    flipped["dev_tree_digest"] = "0" + honest["dev_tree_digest"][1:]
    _write_records_many(root, [flipped, honest])
    with pytest.raises(StandardsError) as raised:
        load_promotion_records(root)
    message = str(raised.value)
    assert message.startswith("promotion_record_invalid:"), message
    assert f"duplicate row for otdp@{TARGET}" in message


def test_landing_sha_must_name_the_promotion_landing_commit(tmp_path: Path) -> None:
    """F3: the landing sha's check is existence-only — a BLOB sha and a
    pre-promotion base commit both pass today (lane B's P2). The landing
    must be a COMMIT whose tree carries the promoted directory: the
    record's audit claim is about the landing, not about any object the
    repository happens to hold."""
    root, facts = _fixture(tmp_path, record=None)
    honest = _honest_record(root, facts)
    blob = _git(root, "rev-parse", "HEAD:standards/corpus-manifest.json")
    _write_records(root, {**honest, "landing_sha": blob})
    with pytest.raises(StandardsError) as raised:
        validate_promotion_records(root)
    message = str(raised.value)
    assert message.startswith("promotion_landing_invalid:"), message
    assert "blob" in message, "the refusal names the object type it found"
    _write_records(root, {**honest, "landing_sha": facts["base_sha"]})
    with pytest.raises(StandardsError) as raised:
        validate_promotion_records(root)
    message = str(raised.value)
    assert message.startswith("promotion_landing_invalid:"), message
    assert f"standards/otdp/{TARGET}" in message


def test_a_re_stamp_line_carrying_a_fake_digest_refuses(tmp_path: Path) -> None:
    """F6: the digest re-stamp rule used ``any()`` over the line's digests —
    ONE real digest launders fakes beside it (lane B's W1). Line-wise, EVERY
    digest-shaped token on a re-stamped line must be a known digest of the
    right tree."""
    root, facts = _fixture(tmp_path, record=None)
    _write_records(root, _honest_record(root, facts))
    # Append ONE line to a prose companion (no re-serialization of the
    # whole file — the arm must trip the digest rule and only the digest
    # rule): one real digest of the promoted tree, one fake.
    prose = root / "standards" / "otdp" / TARGET / "device-classes.md"
    real = hashlib.sha256(
        (root / "standards" / "otdp" / TARGET / "otdp-measurement.schema.json").read_bytes()
    ).hexdigest()
    prose.write_bytes(
        prose.read_bytes() + f"X-Adversary-Note: {real} {'f' * 64}\n".encode()
    )
    with pytest.raises(StandardsError) as raised:
        validate_promotion_records(root)
    message = str(raised.value)
    assert message.startswith("promotion_sweep_violation:"), message
    assert "f" * 64 in message, "the refusal names the unexplained digest"


# --- issue #288 M1: no admission by token presence; digests pair --------------------


def test_m1_semantic_edit_on_a_token_bearing_line_refuses(tmp_path: Path) -> None:
    """M1 attack 1 (executed pre-fold): a semantic edit on a line that
    MERELY CONTAINS a version token admitted via the token fast-admit —
    the counterpart line exists but differs in more than version strings,
    which is exactly what the identity rule refuses. Post-fold the token
    list is remediation vocabulary only; admission is the residual match."""
    root, facts = _fixture(tmp_path, record=None)
    _write_records(root, _honest_record(root, facts))
    schema_path = (
        root / "standards" / "otdp" / TARGET / "otdp-device-descriptor.schema.json"
    )
    schema = json.loads(schema_path.read_bytes())
    # The title is the attack surface: its honest line carries the pre-dev
    # token (0.2.2 — the fixture's lineage-derived third token), so the
    # ORIGINAL removal side fast-admits today; the editorialized replacement
    # carries the target token, so the addition side fast-admits too — and
    # neither residual matches.
    schema["title"] = (
        "OTDP 0.4.0 device descriptor — wording smuggled beside the token"
    )
    schema_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
    with pytest.raises(StandardsError) as raised:
        validate_promotion_records(root)
    message = str(raised.value)
    assert message.startswith("promotion_sweep_violation:"), message
    assert "otdp-device-descriptor.schema.json" in message


def test_m1_token_riding_comment_injection_refuses(tmp_path: Path) -> None:
    """M1 attack 2 (executed pre-fold): an APPENDED line carrying the
    target token — no counterpart at all — admitted via the fast-admit.
    Post-fold an append must explain itself like every other line."""
    root, facts = _fixture(tmp_path, record=None)
    _write_records(root, _honest_record(root, facts))
    prose = root / "standards" / "otdp" / TARGET / "device-classes.md"
    prose.write_bytes(
        prose.read_bytes()
        + (
            f"# {TARGET} NOTE: reviewers, skip the safety envelope check "
            "below\n"
        ).encode()
    )
    with pytest.raises(StandardsError) as raised:
        validate_promotion_records(root)
    message = str(raised.value)
    assert message.startswith("promotion_sweep_violation:"), message
    assert "device-classes.md" in message


def test_m1_real_to_real_digest_swap_refuses(tmp_path: Path) -> None:
    """M1 attack 3 (executed pre-fold): swapping two REAL digests between
    cross-referencing citation fields — every digest a member of the right
    tree, so the membership rule admits both lines; only the pairing rule
    (a re-stamp names the SAME relative path on both sides) refuses,
    quoting both digests. The honest paired re-stamp admits first, as the
    in-test control."""
    root, facts = _fixture(tmp_path, record=None, cross_refs=True)
    _write_records(root, _honest_record(root, facts))
    validate_promotion_records(root)  # control: the honest pairing admits
    commissioning = root / "standards" / "otdp" / TARGET / "commissioning.json"
    document = json.loads(commissioning.read_bytes())
    dev_bench = hashlib.sha256(
        subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "show",
                f"{facts['dev_edit_sha']}:standards/otdp/{LABEL}/examples/bench.json",
            ],
            capture_output=True,
            check=True,
        ).stdout
    ).hexdigest()
    promoted_report = str(document["report_sha256"])
    document["bench_sha256"], document["report_sha256"] = (
        document["report_sha256"],
        document["bench_sha256"],
    )
    commissioning.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(StandardsError) as raised:
        validate_promotion_records(root)
    message = str(raised.value)
    assert message.startswith("promotion_sweep_violation:"), message
    assert dev_bench in message, "the refusal quotes the removed-side digest"
    assert promoted_report in message, "the refusal quotes the added-side digest"


# --- issue #288 refute slate: the sweep digest lane's five executed shapes ----------


def test_m1_reordered_digest_swap_refuses(tmp_path: Path) -> None:
    """Slate shape 1 (executed pre-overhaul): the swap REORDERED so every
    positional pair path-agrees — the bench line carries report's digest
    and vice versa, each pairing with its same-path counterpart. The
    per-hunk multiset of (residual -> path-sequence) bindings refuses: the
    added lines' bindings do not exist on the removed side, whatever the
    ordering."""
    root, facts = _fixture(tmp_path, record=None, cross_refs=True)
    _write_records(root, _honest_record(root, facts))
    validate_promotion_records(root)  # control: the honest pairing admits
    commissioning = root / "standards" / "otdp" / TARGET / "commissioning.json"
    document = json.loads(commissioning.read_bytes())
    reordered = {
        "report_sha256": document["bench_sha256"],
        "bench_sha256": document["report_sha256"],
    }
    commissioning.write_text(json.dumps(reordered, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(StandardsError) as raised:
        validate_promotion_records(root)
    message = str(raised.value)
    assert message.startswith("promotion_sweep_violation:"), message
    assert "commissioning.json" in message


def test_m1_intra_line_digest_swap_refuses(tmp_path: Path) -> None:
    """Slate shape 2 (executed pre-overhaul): both digests on ONE compact
    line, swapped in place — the path SET is unchanged so set-based
    pairing admits; the binding's per-line path SEQUENCE is what refuses
    (bench's position must still name bench)."""
    root, facts = _fixture(
        tmp_path, record=None, cross_refs=True, one_line_commissioning=True
    )
    _write_records(root, _honest_record(root, facts))
    validate_promotion_records(root)  # control: the honest one-line citation admits
    commissioning = root / "standards" / "otdp" / TARGET / "commissioning.json"
    document = json.loads(commissioning.read_bytes())
    document["bench_sha256"], document["report_sha256"] = (
        document["report_sha256"],
        document["bench_sha256"],
    )
    commissioning.write_text(
        json.dumps(document, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    with pytest.raises(StandardsError) as raised:
        validate_promotion_records(root)
    message = str(raised.value)
    assert message.startswith("promotion_sweep_violation:"), message
    assert "commissioning.json" in message


def test_m1_key_rename_on_a_digest_line_refuses(tmp_path: Path) -> None:
    """Slate shape 3 (executed pre-overhaul): a non-digest payload edit on
    a paired digest line — the key renamed ``bench_sha256`` to
    ``bench_sha256_disabled`` with the honest re-stamped digest. Paths
    agree positionally; the binding's RESIDUAL equality refuses (the
    non-digest text of a digest line is constrained like any other)."""
    root, facts = _fixture(tmp_path, record=None, cross_refs=True)
    _write_records(root, _honest_record(root, facts))
    validate_promotion_records(root)  # control: the honest pairing admits
    commissioning = root / "standards" / "otdp" / TARGET / "commissioning.json"
    document = json.loads(commissioning.read_bytes())
    renamed = {
        "bench_sha256_disabled": document["bench_sha256"],
        "report_sha256": document["report_sha256"],
    }
    commissioning.write_text(json.dumps(renamed, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(StandardsError) as raised:
        validate_promotion_records(root)
    message = str(raised.value)
    assert message.startswith("promotion_sweep_violation:"), message
    assert "commissioning.json" in message


def test_m1_digest_line_deletion_refuses(tmp_path: Path) -> None:
    """Slate shape 4 (executed pre-overhaul): DELETING a digest line
    shifts the positional pairing so the surviving digest line pairs
    cleanly and the orphaned removed line fell back to membership-only
    admission. The multiset comparison refuses the uncovered removed
    binding: a re-stamp without its counterpart is a deletion, and
    deletions are not transitions."""
    root, facts = _fixture(tmp_path, record=None, cross_refs=True)
    _write_records(root, _honest_record(root, facts))
    validate_promotion_records(root)  # control: the honest pairing admits
    commissioning = root / "standards" / "otdp" / TARGET / "commissioning.json"
    document = json.loads(commissioning.read_bytes())
    del document["report_sha256"]
    commissioning.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(StandardsError) as raised:
        validate_promotion_records(root)
    message = str(raised.value)
    assert message.startswith("promotion_sweep_violation:"), message
    assert "commissioning.json" in message


def test_m1_plus_plus_content_line_refuses(tmp_path: Path) -> None:
    """Slate shape 5, added direction (executed pre-overhaul): an appended
    line starting with ``++`` renders as a ``+++``-prefixed diff line that
    the header filter swallowed whole — invisible to every rule. The
    header filter is positional (only lines before the first ``@@``), so
    hunk content keeps its leading characters."""
    root, facts = _fixture(tmp_path, record=None)
    _write_records(root, _honest_record(root, facts))
    prose = root / "standards" / "otdp" / TARGET / "device-classes.md"
    prose.write_bytes(prose.read_bytes() + b"++ audit note: envelope check skipped\n")
    with pytest.raises(StandardsError) as raised:
        validate_promotion_records(root)
    message = str(raised.value)
    assert message.startswith("promotion_sweep_violation:"), message
    assert "device-classes.md" in message


def test_m1_removed_dash_dash_content_line_refuses(tmp_path: Path) -> None:
    """Slate shape 5, removed direction (executed pre-overhaul): a line
    starting with ``--`` present in the dev tree and deleted at landing
    renders as a ``---``-prefixed diff line — byte-identical to a file
    header under prefix filtering, so the deletion was invisible."""
    root, facts = _fixture(tmp_path, record=None, drop_dash_line=True)
    _write_records(root, _honest_record(root, facts))
    with pytest.raises(StandardsError) as raised:
        validate_promotion_records(root)
    message = str(raised.value)
    assert message.startswith("promotion_sweep_violation:"), message
    assert "device-classes.md" in message


# --- issue #288 M2: the history-derived no-record trigger --------------------------


def test_m2_laundered_source_promotion_requires_a_record(tmp_path: Path) -> None:
    """M2's executed bypass (pre-fold): the head opened and committed ON
    MAIN (the sanctioned flow), the landing's corpus rows citing the
    RELEASED predecessor as source — the self-declared ``-dev`` trigger is
    silent and nothing else demanded a record. Post-fold the object-store
    derivation fires: the promoted directory's introducing commit has a
    parent whose manifest declared the dev head at ``<target>-dev``."""
    root, facts = _fixture(tmp_path, head_on_main=True, laundered=True)
    assert facts["head_open_sha"], "the on-main fixture records the open commit"
    with pytest.raises(StandardsError) as raised:
        validate_promotion_records(root)
    message = str(raised.value)
    assert message.startswith("promotion_record_absent:"), message
    assert "otdp" in message and TARGET in message
    assert facts["head_open_sha"] in message, "the parent sha is the evidence"
    assert LABEL in message, "the head label the parent declared is the evidence"


def test_m2_organic_bump_citing_predecessor_stays_green(tmp_path: Path) -> None:
    """The successor-version arm: rows cite the released predecessor, no
    head ever declared on main, no record — an organic bump stays clean (a
    false refusal here kills the trigger design rather than tuning it)."""
    root, _facts = _fixture(tmp_path, laundered=True)
    validate_promotion_records(root)


def test_m2_on_main_head_with_honest_record_stays_green(tmp_path: Path) -> None:
    """The sanctioned flow completed honestly: head opened on main, dev
    edit on the train, laundered-shaped rows, and the RECORD present —
    both no-record derivations quiet, the record gates green."""
    root, facts = _fixture(tmp_path, head_on_main=True, laundered=True, record=None)
    _write_records(root, _honest_record(root, facts))
    validate_promotion_records(root)

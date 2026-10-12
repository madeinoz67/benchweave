import copy
import hashlib
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from benchweave.measurement.derivation import (
    DerivationRefused,
    DerivationRejected,
    check_derived_variables,
    derive_dataset_variables,
)

"Document/schema conformance checks, not instrument implementation."
DOCS = globals().get("DOCS", Path(__file__).resolve().parents[2] / "docs")
STANDARDS = globals().get("STANDARDS", Path(__file__).resolve().parents[2] / "standards")


# runpy.run_path does not put the script's directory on sys.path (measured:
# the sibling import fails there), so the shared report writer needs the
# bootstrap. __file__ is set in both execution modes (direct python and
# runpy.run_path with init_globals).
_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import _validation_report  # noqa: E402

OTDP_VERSION = _validation_report.active_standard_version(STANDARDS, "otdp")
# Resolved once: the pinned check compares .resolve()d contract paths against
# OUT, and an unresolved OUT (macOS /var→/private/var TMPDIR, symlinked
# roots) fails every pinned check (24 today) vacuously on a clean tree (#119).
# corpus_directory resolves the manifest-active tree, or the declared dev
# head when --corpus names it (the dev-proof lane) — read-only either way.
OUT = _validation_report.corpus_directory(STANDARDS, "otdp")


def load(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


checks = []


def check(name, truth):
    checks.append((name, bool(truth)))


formats = FormatChecker()


@formats.checks("date-time")
def date(value):
    if not isinstance(value, str):
        return True
    if not re.fullmatch(
        "\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(?:\\.\\d+)?(?:Z|\\+00:00)", value
    ):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


schemas = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in OUT.glob("*.schema.json")}
registry = Registry()
for name, s in schemas.items():
    Draft202012Validator.check_schema(s)
    check(name + " meta-schema", True)
    registry = registry.with_resource(s["$id"], Resource.from_contents(s))
catalog = load("device-profile-catalog.json")
for aid, a in catalog["actions"].items():
    for direction in ("input_schema", "output_schema"):
        s = a[direction]
        Draft202012Validator.check_schema(s)
        check(aid + " " + direction + " meta-schema", True)
        registry = registry.with_resource(s["$id"], Resource.from_contents(s))


def validator(s):
    return Draft202012Validator(s, registry=registry, format_checker=formats)


dv = validator(schemas["otdp-device-descriptor.schema.json"])
rv = validator(schemas["otdp-runtime.schema.json"])
mv = validator(schemas["otdp-measurement.schema.json"])
check(
    "Catalog structure", validator(schemas["device-profile-catalog.schema.json"]).is_valid(catalog)
)
profile_map = {p["id"]: p for p in catalog["profiles"]}
check("Twelve distinct profiles", len(profile_map) == 12)
known_features = {
    "otdp.core/0.1.0",
    "otdp.adapter/0.1.0",
    "otdp.passive_can/0.1.0",
    "otdp.measurement/0.1.0",
    "otdp.profile_actions/0.1.0",
} | set(profile_map)

# Transport providers (0.2.1): every pinned provider contract is loaded and
# hash-verified before descriptor validation, so a provider feature id is
# "known" exactly when a verified corpus contract registers it — the
# admission shape of extension-contract section 6 (hosts know otdp.transport.*
# ids by admitting contracts, never by list).
def provider_identity_errors(doc):
    """The three identity equalities (transport-providers.md section 1): the
    urn-embedded version equals ``version``, the feature_id-embedded version
    equals ``version``, and the feature_id name segment equals the urn's name
    segment. A contract whose fields name two providers or two revisions is
    refused at admission; this is the corpus-side arm of that rule.
    """
    errors = []
    urn = doc["id"].removeprefix("urn:otdp:transport-provider:")
    name, _, urn_version = urn.rpartition(":")
    feature_name, _, feature_version = doc["feature_id"].rpartition("/")
    if urn_version != doc["version"]:
        errors.append("urn version disagrees")
    if feature_version != doc["version"]:
        errors.append("feature version disagrees")
    if feature_name.removeprefix("otdp.transport.") != name:
        errors.append("provider name disagrees")
    return errors


PROVIDER_FEATURE_RE = re.compile(r"^otdp\.transport\.[a-z][a-z0-9-]*/[0-9]+\.[0-9]+(?:\.[0-9]+)?$")
# The generic transfer kinds a provider grammar extends additively and never
# shadows (specification section 8.1; disjointness is admission-refusable).
GENERIC_TRANSFER_KINDS = frozenset(
    {
        "stream_send",
        "stream_receive",
        "stream_exchange",
        "can_receive",
        "can_send",
        "i2c_transfer",
        "spi_transfer",
    }
)
provider_schema_name = "otdp-transport-provider.schema.json"
provider_validator = (
    validator(schemas[provider_schema_name]) if provider_schema_name in schemas else None
)
provider_docs = {}
provider_pin_failures = {}
for p in sorted((OUT / "examples").glob("*.json")):
    if provider_validator is None:
        break  # active corpus predates transport providers; nothing to check
    probe = json.loads(p.read_text(encoding="utf-8"))
    pin = probe.get("transport", {}).get("provider")
    if not pin:
        continue
    doc_path = (p.parent / pin["path"]).resolve()
    pinned = (
        doc_path.is_relative_to(OUT)
        and doc_path.is_file()
        and hashlib.sha256(doc_path.read_bytes()).hexdigest() == pin["sha256"]
    )
    check(p.name + " pinned provider " + pin["id"], pinned)
    if not pinned:
        provider_pin_failures[p.name] = ["provider contract missing"]
        continue
    doc = json.loads(doc_path.read_text(encoding="utf-8"))
    doc_errors = list(provider_validator.iter_errors(doc))
    check(p.name + " provider contract structure", not doc_errors)
    for transfer in doc["transaction_grammar"]:
        for side in ("request_schema", "result_schema"):
            Draft202012Validator.check_schema(transfer[side])
            check(doc["id"] + " " + transfer["kind"] + " " + side + " meta-schema", True)
    identity_errors = provider_identity_errors(doc)
    check(p.name + " provider identity coherence", not identity_errors)
    namespace_error = not PROVIDER_FEATURE_RE.match(doc["feature_id"])
    check(p.name + " provider feature namespace", not namespace_error)
    shadowed = sorted(
        {t["kind"] for t in doc["transaction_grammar"]} & GENERIC_TRANSFER_KINDS
    )
    check(p.name + " provider grammar disjoint from generic kinds", not shadowed)
    if not doc_errors and not identity_errors and not namespace_error and not shadowed:
        provider_docs[pin["id"]] = doc
known_features |= {doc["feature_id"] for doc in provider_docs.values()}


# Protocol decoders (OTDP 0.2.3): decoder declarations are digest-pinned
# corpus documents validated by otdp-decoder.schema.json. The census loads
# the declaration examples directly (they are corpus documents in their own
# right) and every descriptor's ``decoders`` pins resolve before the vector
# checks, so a declaration is admitted exactly when its pinned bytes pass
# its schema and the PD2 coherence rules — the offline half of PD1
# (protocol-decoders.md). The gateway's admission-seam mirrors are the
# named slice-2 follow-on (design record section 3.2).
decoder_schema_name = "otdp-decoder.schema.json"
decoder_validator = (
    validator(schemas[decoder_schema_name]) if decoder_schema_name in schemas else None
)
check("Decoder declaration schema present", decoder_validator is not None)
DECODER_EXAMPLES = (
    "decoder-i2c.json",
    "decoder-onewire-link.json",
    "decoder-spi.json",
    "decoder-uart.json",
)
decoder_docs: dict[str, dict] = {}


def _json_type_name(value):
    """The JSON type name an option value carries (PD4's type arm).

    ``bool`` is checked before the numeric branch because ``True`` is an
    ``int`` in Python — without the order, a boolean option value would
    type-check against a numeric default and the PD4 arm would be vacuous
    for exactly one of the three declared types.
    """
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    return "other"


def decoder_declaration_errors(doc):
    """Declaration self-coherence (protocol-decoders.md PD2): annotation
    rows reference declared annotation ids BY ID, no annotation id appears
    in two rows, and the identifier spaces (classes, rows, options,
    channels) are unique. Binary classes are shape-carried by the schema
    alone this revision — emission is out of scope (PD6's disclosure, not
    a check).
    """
    errors = []
    annotation_ids = [a["id"] for a in doc["annotations"]]
    if len(set(annotation_ids)) != len(annotation_ids):
        errors.append("duplicate annotation id")
    row_ids = [row["id"] for row in doc["annotation_rows"]]
    if len(set(row_ids)) != len(row_ids):
        errors.append("duplicate row id")
    row_classes = [c for row in doc["annotation_rows"] for c in row["annotation_ids"]]
    for annotation_id in row_classes:
        if annotation_id not in annotation_ids:
            errors.append("row class unresolved")
    if len(set(row_classes)) != len(row_classes):
        errors.append("annotation in two rows")
    if len({o["id"] for o in doc["options"]}) != len(doc["options"]):
        errors.append("duplicate option id")
    channel_ids = [c["id"] for c in doc["channels"]] + [
        c["id"] for c in doc.get("optional_channels", [])
    ]
    if len(set(channel_ids)) != len(channel_ids):
        errors.append("duplicate channel id")
    return errors


present_decoders = sorted(p.name for p in (OUT / "examples").glob("decoder-*.json"))
check("Decoder declaration examples census", present_decoders == list(DECODER_EXAMPLES))
for name in present_decoders:
    if decoder_validator is None:
        break  # the schema-present check above failed by name already
    doc = json.loads((OUT / "examples" / name).read_text(encoding="utf-8"))
    check(name + " declaration structure", not list(decoder_validator.iter_errors(doc)))
    check(name + " declaration rows/coherence", not decoder_declaration_errors(doc))


def decoder_pin_errors(d, base):
    """PD1's descriptor half: every ``decoders`` pin resolves inside the
    corpus, digest-matches its document, the document is schema-valid and
    coherent, and its identity agrees with the pin. Returns the error list
    plus the admitted documents keyed by decoder id.
    """
    errors = []
    docs = {}
    for pin in d.get("decoders", []):
        doc_path = (base / pin["path"]).resolve()
        if not doc_path.is_relative_to(OUT) or not doc_path.is_file():
            errors.append("decoder declaration missing")
            continue
        if hashlib.sha256(doc_path.read_bytes()).hexdigest() != pin["sha256"]:
            errors.append("decoder digest disagrees")
            continue
        doc = json.loads(doc_path.read_text(encoding="utf-8"))
        if decoder_validator is None or list(decoder_validator.iter_errors(doc)):
            errors.append("decoder declaration invalid")
            continue
        if decoder_declaration_errors(doc):
            errors.append("decoder rows incoherent")
            continue
        if doc["id"] != pin["id"]:
            errors.append("decoder identity disagrees")
            continue
        docs[pin["id"]] = doc
    return errors, docs


def decoder_errors(d, docs):
    """Decoder declaration consistency (protocol-decoders.md PD1): pin ids
    are unique across the descriptor's ``decoders`` array and every pin
    resolved to an admitted document whose ``id`` agrees. Pin resolution
    itself (containment, digest, schema) is ``decoder_pin_errors`` above.
    """
    errors = []
    ids = [pin["id"] for pin in d.get("decoders", [])]
    if len(set(ids)) != len(ids):
        errors.append("duplicate decoder id")
    for pin in d.get("decoders", []):
        doc = docs.get(pin["id"])
        if doc is None:
            errors.append("decoder declaration missing")
        elif doc.get("id") != pin["id"]:
            errors.append("decoder identity disagrees")
    return errors


def decode_annotated_errors(inp, declaration, descriptor):
    """PD3/PD4: the named decoder is declared, ``channel_map`` covers every
    required declaration channel, mapped targets exist in the descriptor's
    channels, and options resolve against the declaration's option specs
    (existence, JSON type, declared values). Unmapped OPTIONAL channels are
    legal — the spi/uart posture (protocol-decoders.md section 3).
    """
    errors = []
    required = {c["id"] for c in declaration["channels"]}
    mapped = inp.get("channel_map", {})
    for channel_id in sorted(required - set(mapped)):
        errors.append("required channel unmapped: " + channel_id)
    device_channels = {c["id"] for c in descriptor.get("channels", [])}
    for source, target in sorted(mapped.items()):
        if target not in device_channels:
            errors.append("channel map target absent: " + source)
    specs = {o["id"]: o for o in declaration["options"]}
    for key in sorted(set(inp.get("options", {})) - set(specs)):
        errors.append("unknown option: " + key)
    for key, value in sorted(inp.get("options", {}).items()):
        spec = specs.get(key)
        if spec is None:
            continue
        if _json_type_name(value) != _json_type_name(spec["default"]):
            errors.append("option type disagrees: " + key)
        elif "values" in spec and value not in spec["values"]:
            errors.append("option value undeclared: " + key)
    return errors


def annotation_dataset_errors(dataset, declaration):
    """PD5: kind event_log, the annotation variable set present, every
    ``class`` value resolves against the declaration, event-axis length
    equals the variable lengths (M02's shape), and start_s <= end_s.
    """
    errors = []
    if dataset.get("kind") != "event_log":
        errors.append("kind is not event_log")
    variables = {v["id"]: v for v in dataset.get("variables", [])}
    for variable_id in ("start_s", "end_s", "class", "text"):
        if variable_id not in variables:
            errors.append("annotation variable absent: " + variable_id)
    annotation_ids = {a["id"] for a in declaration["annotations"]}
    for value in variables.get("class", {}).get("values", []):
        if value not in annotation_ids:
            errors.append("class unresolved: " + str(value))
    lengths = {
        variable_id: len(v.get("values", []))
        for variable_id, v in variables.items()
        if v.get("dimensions") == ["event"]
    }
    if len(set(lengths.values())) > 1:
        errors.append("variable lengths disagree")
    axes = {a["id"]: a for a in dataset.get("axes", [])}
    if "event" in axes and lengths and axes["event"]["length"] not in lengths.values():
        errors.append("event axis length disagrees")
    if "start_s" in variables and "end_s" in variables:
        for start, end in zip(
            variables["start_s"]["values"], variables["end_s"]["values"], strict=False
        ):
            if start > end:
                errors.append("event end precedes start")
                break
    return errors


def provider_errors(d, docs):
    """Provider declaration consistency (S04 extension, transport-providers.md).

    Offline-refusable rows only: the declared feature id must be required, an
    otdp.transport.* feature must be declared by a matching provider object,
    and the pinned document's identity must agree with the declaration.
    Connection-to-grant resolution needs commissioned state and stays
    gateway-side (disclosed limitation, not checked here).
    """
    errors = []
    transport = d.get("transport", {})
    provider = transport.get("provider")
    required = set(d.get("required_features", []))
    if provider is not None:
        if provider["feature_id"] not in required:
            errors.append("provider feature missing")
        if transport.get("type") != "custom":
            errors.append("provider on non-custom transport")
        doc = docs.get(provider["id"])
        if doc is None:
            errors.append("provider contract missing")
        else:
            if doc["feature_id"] != provider["feature_id"] or doc["id"] != provider["id"]:
                errors.append("provider identity disagrees")
            kinds = [t["kind"] for t in doc["transaction_grammar"]]
            if len(set(kinds)) != len(kinds):
                errors.append("duplicate grammar kind")
    for feature in sorted(required):
        if feature.startswith("otdp.transport.") and (
            provider is None or provider["feature_id"] != feature
        ):
            errors.append("provider transport undeclared")
    return errors


def class_errors(d):
    errors = []
    if not set(d["required_features"]) <= known_features:
        errors.append("unknown feature")
    if len({c["id"] for c in d.get("channels", [])}) != len(d.get("channels", [])):
        errors.append("duplicate channel")
    declared = set(d.get("actions", {}))
    allowed = set()
    for pid in d.get("profiles", []):
        if pid not in profile_map:
            errors.append("unknown profile")
            continue
        if pid not in d["required_features"]:
            errors.append("missing profile feature")
        p = profile_map[pid]
        allowed.update(p["required_actions"] + p["optional_actions"])
        if not set(p["required_actions"]) <= declared:
            errors.append("missing required action")
    if declared - allowed:
        errors.append("unclaimed action")
    sweep = {"otdp.smu." + v + "/1.0.0" for v in ("configure_sweep", "arm", "fetch", "abort")}
    if declared & sweep and (not sweep <= declared):
        errors.append("incomplete sweep group")
    for aid, a in d.get("actions", {}).items():
        if aid not in catalog["actions"]:
            continue
        if catalog["actions"][aid]["side_effect"] == "state_change" and a["side_effect"] == "none":
            errors.append("downgraded effect")
    return errors


descriptors = {}
for p in sorted((OUT / "examples").glob("*.json")):
    d = json.loads(p.read_text(encoding="utf-8"))
    if "otdp_version" not in d:
        continue
    descriptors[p.name] = d
    errors = list(dv.iter_errors(d))
    check(p.name + " descriptor structure", not errors)
    check(p.name + " known required features", set(d["required_features"]) <= known_features)
    if "profiles" in d:
        check(p.name + " class membership/effects", not class_errors(d))
        for c in d["contracts"]:
            path = (OUT / c["path"]).resolve()
            check(
                p.name + " pinned " + c["id"],
                path.is_relative_to(OUT)
                and path.is_file()
                and (hashlib.sha256(path.read_bytes()).hexdigest() == c["sha256"]),
            )
    for entry in d["provenance"]["test_vectors"]:
        check(p.name + " vector file resolves", (p.parent / entry["path"]).is_file())
    check(
        p.name + " provider declaration",
        not provider_errors(d, provider_docs) + provider_pin_failures.get(p.name, []),
    )
    for pin in d.get("decoders", []):
        doc_path = (p.parent / pin["path"]).resolve()
        pinned = (
            doc_path.is_relative_to(OUT)
            and doc_path.is_file()
            and hashlib.sha256(doc_path.read_bytes()).hexdigest() == pin["sha256"]
        )
        check(p.name + " pinned decoder " + pin["id"], pinned)
        if not pinned:
            continue
        doc = json.loads(doc_path.read_text(encoding="utf-8"))
        doc_errors = (
            list(decoder_validator.iter_errors(doc)) if decoder_validator else ["absent"]
        )
        check(p.name + " decoder document " + pin["id"] + " structure", not doc_errors)
        check(
            p.name + " decoder document " + pin["id"] + " rows/coherence",
            not decoder_declaration_errors(doc),
        )
        if not doc_errors and doc.get("id") == pin["id"]:
            decoder_docs[pin["id"]] = doc
    check(p.name + " decoder declaration", not decoder_errors(d, decoder_docs))


def dataset_errors(d):
    e = []
    axes = {a["id"]: a for a in d["axes"]}
    if len(axes) != len(d["axes"]):
        e.append("duplicate axis")
    if len({v["id"] for v in d["variables"]}) != len(d["variables"]):
        e.append("duplicate variable")
    for a in d["axes"]:
        c = a["coordinates"]
        if c["kind"] == "explicit" and len(c["values"]) != a["length"]:
            e.append("coordinate count")
        if c["kind"] == "regular" and a["length"] > 1 and (c["step"] == 0):
            e.append("zero axis step")
    for v in d["variables"]:
        if any(dim not in axes for dim in v["dimensions"]):
            e.append("unknown dimension")
            continue
        count = math.prod(axes[dim]["length"] for dim in v["dimensions"])
        if "values" in v:
            if len(v["values"]) != count:
                e.append("element count")
            if v["status"] == "valid" and any(x is None for x in v["values"]):
                e.append("unmarked null")
            if v["dtype"] in ("int64", "uint64"):
                for x in v["values"]:
                    if x is None:
                        continue
                    n = int(x)
                    low = -(2**63) if v["dtype"] == "int64" else 0
                    high = 2**63 - 1 if v["dtype"] == "int64" else 2**64 - 1
                    if not low <= n <= high or x == "-0":
                        e.append("integer bounds")
        else:
            widths = {
                "f64le": 8,
                "i64le": 8,
                "u64le": 8,
                "u8": 1,
                "bool_u8": 1,
                "logic_u8": 1,
                "complex_f64le": 16,
            }
            a = v["artifact"]
            if a["encoding"] in widths and a["byte_length"] != count * widths[a["encoding"]]:
                e.append("artifact size")
        if v["unit"] in ("dB", "dBm") and "log_reference" not in v:
            e.append("missing log reference")
        if v["uncertainty"]["status"] != "known" and "absolute" in v["uncertainty"]:
            e.append("unknown uncertainty value")
    if d["kind"] == "network_parameters":
        if not any(a["quantity"] == "frequency" for a in d["axes"]):
            e.append("frequency axis")
        for v in d["variables"]:
            if v["dtype"] != "complex128" or "port_pair" not in v:
                e.append("network parameters meaning")
    return e


census = load("examples/derivation-vectors.json")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def census_row_ok(row):
    derived = row.get("derived")
    if derived is None:
        derived = [
            {
                "id": "probe0",
                "quantity": "probe",
                "unit": "1",
                "expression": row["expression"],
            }
        ]
    if row["expect"] == "refused":
        try:
            derive_dataset_variables(copy.deepcopy(row["dataset"]), derived)
        except DerivationRefused as error:
            return str(error).startswith(row["reason_prefix"])
        return False
    if row["expect"] == "reject":
        try:
            check_derived_variables(derived)
        except DerivationRejected as error:
            return str(error).startswith(row["reason_prefix"])
        return False
    if row["expect"] == "accept":
        try:
            check_derived_variables(derived)
            return True
        except DerivationRejected:
            return False
    output = derive_dataset_variables(copy.deepcopy(row["dataset"]), derived)
    appended = output["variables"][len(row["dataset"]["variables"]) :]
    return [canonical(v) for v in appended] == [canonical(v) for v in row["expected"]]


for row in census["grammar"] + census["static"] + census["evaluation"]:
    check(row["id"] + " derivation census", census_row_ok(row))
check(
    "derivation census meets the minimum row counts",
    len(census["grammar"]) >= 30
    and sum(1 for r in census["grammar"] if r["expect"] == "accept") >= 15
    and sum(1 for r in census["grammar"] if r["expect"] == "reject") >= 15
    and len(census["evaluation"]) >= 12,
)
for name, descriptor in sorted(descriptors.items()):
    if "derived_variables" in descriptor:
        try:
            check_derived_variables(descriptor["derived_variables"])
            check(name + " derived declarations", True)
        except DerivationRejected as error:
            check(name + " derived declarations: " + str(error), False)


data = load("examples/measurement-vectors.json")["datasets"]
for name, d in data.items():
    errors = list(mv.iter_errors(d))
    check(name + " measurement structure", not errors)
    check(name + " shape/selected metrology rules", not dataset_errors(d))
for name, d in data.items():
    recorded = [v for v in d["variables"] if "derivation" in v]
    if not recorded:
        continue
    # Replay through the public API: strip the derived variables, re-derive
    # them from the recorded markers, and require the exact recorded
    # variables back — the corpus example IS what the evaluator produces.
    operands_only = copy.deepcopy(d)
    operands_only["variables"] = [
        v for v in operands_only["variables"] if "derivation" not in v
    ]
    declarations = [
        {
            "id": v["id"],
            "quantity": v["quantity"],
            "unit": v["unit"],
            "expression": v["derivation"]["expression"],
        }
        for v in recorded
    ]
    try:
        replayed = derive_dataset_variables(operands_only, declarations)
        appended = replayed["variables"][len(operands_only["variables"]) :]
        check(
            name + " derived example replays exactly",
            [canonical(v) for v in appended] == [canonical(v) for v in recorded],
        )
    except (DerivationRefused, DerivationRejected) as error:
        check(name + " derived example replays: " + str(error), False)


vectors = load("examples/class-action-vectors.json")["vectors"]
covered = set()
for v in vectors:
    req = v["request"]
    res = v["result"]
    aid = req["arguments"]["action_id"]
    covered.add(aid)
    contract = catalog["actions"][aid]
    check(v["id"] + " request envelope", rv.is_valid(req))
    check(v["id"] + " result envelope", rv.is_valid(res))
    ins = validator(contract["input_schema"])
    outs = validator(contract["output_schema"])
    check(v["id"] + " action input", ins.is_valid(req["arguments"]["input"]))
    check(v["id"] + " action output", outs.is_valid(res["data"]["result"]))
    check(
        v["id"] + " correlated identity",
        req["operation_id"] == res["operation_id"] and aid == res["data"]["action_id"],
    )
    if aid == "otdp.logic_analyser.decode_annotated/1.0.0":
        inp = req["arguments"]["input"]
        declaration = decoder_docs.get(inp.get("decoder", ""))
        check(v["id"] + " decoder declared", declaration is not None)
        descriptor = descriptors.get(v.get("descriptor", ""))
        if declaration is not None and descriptor is not None:
            check(
                v["id"] + " decode_annotated semantics",
                not decode_annotated_errors(inp, declaration, descriptor),
            )
            check(
                v["id"] + " annotation dataset semantics",
                not annotation_dataset_errors(res["data"]["result"], declaration),
            )
check(
    "Every standard action has a positive contract vector",
    covered == set(catalog["actions"]) and len(covered) == 51,
)
base = descriptors["class-dc_psu.json"]
d = copy.deepcopy(base)
d["actions"].pop("otdp.dc_psu.output/1.0.0")
check("Reject missing base action semantically", "missing required action" in class_errors(d))
d = copy.deepcopy(base)
d["profiles"] = ["vendor.unknown/1.0.0"]
check("Reject unknown required profile", "unknown profile" in class_errors(d))
d = copy.deepcopy(base)
d["required_features"].append("vendor.unknown/1.0.0")
check("Reject unknown feature despite valid syntax", "unknown feature" in class_errors(d))
d = copy.deepcopy(base)
d["actions"]["otdp.dc_psu.output/1.0.0"]["side_effect"] = "none"
check("Reject downgraded source action", "downgraded effect" in class_errors(d))
d = copy.deepcopy(base)
d["required_features"].remove("otdp.profile_actions/0.1.0")
check("Reject absent action feature structurally", not dv.is_valid(d))
d = copy.deepcopy(base)
d["required_features"].remove("otdp.dc_psu/1.0.0")
check("Reject absent profile feature semantically", "missing profile feature" in class_errors(d))
d = copy.deepcopy(descriptors["class-smu.json"])
d["actions"].pop("otdp.smu.abort/1.0.0")
check("Reject incomplete optional sweep group", "incomplete sweep group" in class_errors(d))
d = copy.deepcopy(base)
d["channels"].append(copy.deepcopy(d["channels"][0]))
check("Reject duplicate channel", "duplicate channel" in class_errors(d))
hid_provider_id = "urn:otdp:transport-provider:reference-hid:1.0.0"
hid = descriptors.get("reference-hid-meter.json")
if provider_validator is None:
    pass  # active corpus predates transport providers; the arms have no subject
elif hid is None or hid_provider_id not in provider_docs:
    # The corpus's own reference pin is broken (or the example moved): the
    # fault-injection arms below would KeyError on the missing document, so
    # they degrade to this named failure instead of crashing the suite.
    check("Reference provider contract admitted", False)
else:
    hid_feature = "otdp.transport.reference-hid/1.0.0"
    d = copy.deepcopy(hid)
    if hid_feature not in d["required_features"]:
        # The self-arm's literal follows the corpus: a rename that leaves it
        # behind fails by name here instead of crashing on remove().
        check("Self-arm provider feature literal present", False)
    else:
        d["required_features"].remove(hid_feature)
        check(
            "Reject provider without required feature entry",
            "provider feature missing" in provider_errors(d, provider_docs),
        )
    d = copy.deepcopy(hid)
    d["required_features"].append("otdp.transport.ghost/1.0.0")
    check(
        "Reject orphan transport feature",
        "provider transport undeclared" in provider_errors(d, provider_docs),
    )
    d = copy.deepcopy(hid)
    d["transport"]["provider"]["sha256"] = "0" * 63
    check("Reject malformed provider digest", not dv.is_valid(d))
    d = copy.deepcopy(hid)
    d["transport"]["settings"] = copy.deepcopy(
        descriptors["class-daq.json"]["transport"]["settings"]
    )
    d["transport"]["type"] = "serial"
    check("Reject provider on scoped transport", not dv.is_valid(d))
    d = copy.deepcopy(hid)
    d["transport"]["provider"]["extra"] = True
    check("Reject provider additional properties", not dv.is_valid(d))
    d = copy.deepcopy(hid)
    mismatched_docs = dict(provider_docs)
    mismatched_docs[hid_provider_id] = {
        **provider_docs[hid_provider_id],
        "feature_id": "otdp.transport.other/1.0.0",
    }
    check(
        "Reject provider identity disagreement",
        "provider identity disagrees" in provider_errors(d, mismatched_docs),
    )
    duplicated = copy.deepcopy(provider_docs[hid_provider_id])
    duplicated["transaction_grammar"].append(copy.deepcopy(duplicated["transaction_grammar"][0]))
    check(
        "Reject duplicate provider grammar kind",
        "duplicate grammar kind"
        in provider_errors(d, {hid_provider_id: duplicated}),
    )
    check(
        "Reject provider scope beyond commissioned connection",
        not provider_validator.is_valid({**duplicated, "security_scope": "filesystem"}),
    )
    approvalless = copy.deepcopy(provider_docs[hid_provider_id])
    approvalless["approval"].pop("evidence")
    check(
        "Reject provider approval without evidence", not provider_validator.is_valid(approvalless)
    )
    reversioned = copy.deepcopy(provider_docs[hid_provider_id])
    reversioned["version"] = "2.0.0"
    check(
        "Reject provider identity version disagreement",
        provider_identity_errors(reversioned)
        == ["urn version disagrees", "feature version disagrees"],
    )
    renamed = copy.deepcopy(provider_docs[hid_provider_id])
    renamed["id"] = "urn:otdp:transport-provider:reference-other-hid:1.0.0"
    check(
        "Reject provider identity name disagreement",
        provider_identity_errors(renamed) == ["provider name disagrees"],
    )
    reserved = copy.deepcopy(provider_docs[hid_provider_id])
    reserved["feature_id"] = "otdp.core/9.9.9"
    check(
        "Reject provider feature outside the transport namespace",
        not provider_validator.is_valid(reserved),
    )
    shadowing = copy.deepcopy(provider_docs[hid_provider_id])
    shadowing["transaction_grammar"][0]["kind"] = "stream_send"
    shadowed_kinds = sorted(
        {t["kind"] for t in shadowing["transaction_grammar"]} & GENERIC_TRANSFER_KINDS
    )
    check(
        "Reject provider grammar shadowing a generic kind",
        shadowed_kinds == ["stream_send"],
    )
logic_analyser = descriptors.get("class-logic_analyser.json")
if decoder_validator is None or not decoder_docs:
    # The corpus's own decoder declarations (or their schema) are absent:
    # the fault-injection arms below would KeyError on the missing
    # documents, so they degrade to this named failure instead of crashing
    # the suite — the reference-provider degrade pattern above.
    check("Reference decoder declarations admitted", False)
elif logic_analyser is None or not logic_analyser.get("decoders"):
    check("Reference decoder declarations admitted", False)
else:
    i2c_declaration = decoder_docs["i2c"]
    d = copy.deepcopy(logic_analyser)
    for entry in d["decoders"]:
        if entry["id"] == "i2c":
            entry["sha256"] = "0" * 63 + "1"
    pin_errors, _admitted = decoder_pin_errors(d, OUT / "examples")
    check("Reject broken decoder pin", "decoder digest disagrees" in pin_errors)
    d = copy.deepcopy(logic_analyser)
    d["decoders"].append(copy.deepcopy(d["decoders"][0]))
    check(
        "Reject duplicate decoder id",
        "duplicate decoder id" in decoder_errors(d, decoder_docs),
    )
    mutated_rows = copy.deepcopy(i2c_declaration)
    mutated_rows["annotation_rows"][0]["annotation_ids"].append("ghost-class")
    check(
        "Reject unresolved row class",
        "row class unresolved" in decoder_declaration_errors(mutated_rows),
    )
    base_input = {
        "acquisition_id": "acq-1",
        "decoder": "i2c",
        "channel_map": {"scl": "ch1", "sda": "ch2"},
        "options": {"address_format": "shifted"},
    }
    check(
        "decode_annotated base input admits",
        not decode_annotated_errors(base_input, i2c_declaration, logic_analyser),
    )
    check(
        "Reject unknown decode option",
        "unknown option: ghost_option"
        in decode_annotated_errors(
            {**base_input, "options": {"ghost_option": 1}}, i2c_declaration, logic_analyser
        ),
    )
    check(
        "Reject option value outside the declared set",
        "option value undeclared: address_format"
        in decode_annotated_errors(
            {**base_input, "options": {"address_format": "unshifted-x"}},
            i2c_declaration,
            logic_analyser,
        ),
    )
    check(
        "Reject unmapped required decoder channel",
        "required channel unmapped: sda"
        in decode_annotated_errors(
            {**base_input, "channel_map": {"scl": "ch1"}}, i2c_declaration, logic_analyser
        ),
    )
    annotated = next(
        (
            vector
            for vector in vectors
            if vector["request"]["arguments"]["action_id"]
            == "otdp.logic_analyser.decode_annotated/1.0.0"
            and vector["request"]["arguments"]["input"].get("decoder") == "i2c"
        ),
        None,
    )
    if annotated is None:
        check("Reference decode_annotated vector present", False)
    else:
        mutated_dataset = copy.deepcopy(annotated["result"]["data"]["result"])
        class_variable = next(
            v for v in mutated_dataset["variables"] if v["id"] == "class"
        )
        class_variable["values"][0] = "ghost-class"
        check(
            "Reject unresolvable dataset class",
            "class unresolved: ghost-class"
            in annotation_dataset_errors(mutated_dataset, i2c_declaration),
        )
        reordered = copy.deepcopy(annotated["result"]["data"]["result"])
        end_variable = next(v for v in reordered["variables"] if v["id"] == "end_s")
        end_variable["values"][0] = -1
        check(
            "Reject event end preceding start",
            "event end precedes start"
            in annotation_dataset_errors(reordered, i2c_declaration),
        )
for cls in ("dc_psu", "electronic_load", "smu", "function_generator"):
    v = validator(catalog["actions"][f"otdp.{cls}.output/1.0.0"]["input_schema"])
    check(cls + " enable requires config", not v.is_valid({"channel": "ch1", "enabled": True}))
    check(cls + " disable permits absent config", v.is_valid({"channel": "ch1", "enabled": False}))
d = copy.deepcopy(data["oscilloscope"])
d["variables"][0]["values"].pop()
check("Reject shape mismatch", "element count" in dataset_errors(d))
d = copy.deepcopy(data["oscilloscope"])
d["variables"][0]["dimensions"] = ["missing"]
check("Reject unknown dimension", "unknown dimension" in dataset_errors(d))
d = copy.deepcopy(data["oscilloscope"])
d["variables"][0]["values"][0] = None
check("Reject null hidden as valid", "unmarked null" in dataset_errors(d))
d = copy.deepcopy(data["spectrum_analyser"])
d["variables"][0].pop("log_reference")
check("Reject missing logarithmic reference", "missing log reference" in dataset_errors(d))
d = copy.deepcopy(data["vna"])
d["variables"][0].pop("port_pair")
check("Reject missing VNA port pair", "network parameters meaning" in dataset_errors(d))
d = copy.deepcopy(data["vna"])
d["variables"][0]["values"][0] = [1, 2, 3]
check("Reject malformed complex element", not mv.is_valid(d))
d = copy.deepcopy(data["logic_analyser"])
d["variables"][0]["values"][0] = "true"
check("Reject unknown logic token", not mv.is_valid(d))
d = copy.deepcopy(data["dmm"])
d["variables"][0]["uncertainty"] = {"status": "known"}
check("Reject known uncertainty without value", not mv.is_valid(d))
source_input = validator(catalog["actions"]["otdp.dc_psu.configure/1.0.0"]["input_schema"])
inp = {
    "configuration_id": "cfg-1",
    "channel": "ch1",
    "voltage_v": 3.3,
    "current_limit_a": 0.5,
    "ovp_v": 3.6,
    "ocp_a": 0.6,
    "raw_command": "OUTP ON",
}
check("Reject arbitrary command field", not source_input.is_valid(inp))
scope = validator(catalog["actions"]["otdp.oscilloscope.configure/1.0.0"]["input_schema"])
inp = copy.deepcopy(
    next(v["request"]["arguments"]["input"] for v in vectors if v["id"] == "oscilloscope-configure")
)
inp["trigger"] = {"kind": "edge"}
check("Reject incomplete edge trigger", not scope.is_valid(inp))
fg = validator(catalog["actions"]["otdp.function_generator.configure/1.0.0"]["input_schema"])
inp = copy.deepcopy(
    next(
        v["request"]["arguments"]["input"]
        for v in vectors
        if v["id"] == "function_generator-configure"
    )
)
inp["function"] = "arbitrary"
check("Reject arbitrary waveform without asset", not fg.is_valid(inp))
fg_constraints = {"properties": {"frequency_hz": {"maximum": 100}}}
inp["function"] = "sine"
check(
    "Device constraints narrow standard contract",
    fg.is_valid(inp) and (not validator(fg_constraints).is_valid(inp)),
)
CHECKS = checks

GENERATED_MARKER = _validation_report.marker("scripts/architecture/check_devices.py")
REPORT_TITLE = f"# OTDP {OTDP_VERSION} specification verification"
REPORT_COVERAGE = (
    f"{len(profile_map)} class profiles and {len(covered)} input/output action contracts "
    "were checked against Draft 2020-12. Each action has a positive vector. Descriptor "
    "declarations, pinned contract hashes, runtime envelopes, typed datasets and selected "
    "rejection/semantic boundaries were checked. Transport-provider declarations, their "
    "pinned contract documents and the provider grammar subschemas were checked; "
    "connection-to-grant resolution is commissioned state and stays gateway-side. "
    "Protocol-decoder declarations, their digest-pinned documents and the "
    "decode_annotated vectors were checked (PD1 through PD5); gateway admission mirrors "
    "and binary-class emission are the named follow-on slices."
)
REPORT_LIMIT = (
    "**Limit:** These are document/schema checks. No gateway, plugin, device simulator, "
    "hardware interaction or complete C01–C12/M01–M14 behavioural validator is claimed. "
    "Structural reference descriptors intentionally do not contain real manufacturer "
    "evidence or commissioned electrical limits."
)


def render_report(checks: list[tuple[str, bool]]) -> str:
    """Render the validation report markdown from a devices-suite check list.

    Pure and order-canonical: the ``## Checks`` list is emitted sorted by name
    because the suite's accumulation order is partly glob order
    (directory-entry order), which is not portable across platforms. The
    rendered bytes are a function of the check set only.
    """
    return _validation_report.render(
        [(str(name), bool(ok)) for name, ok in checks],
        marker=GENERATED_MARKER,
        title=REPORT_TITLE,
        coverage=REPORT_COVERAGE,
        limit=REPORT_LIMIT,
    )


if __name__ == "__main__":
    _validation_report.main(
        CHECKS,
        OUT / "validation-report.md",
        script="scripts/architecture/check_devices.py",
        title=REPORT_TITLE,
        coverage=REPORT_COVERAGE,
        limit=REPORT_LIMIT,
    )

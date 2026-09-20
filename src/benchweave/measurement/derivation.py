"""Derived variables: a fixed-grammar expression over dataset variables.

OTDP (since 0.1.2) lets a device descriptor declare that measurement datasets gain
variables computed from other variables (``derived_variables[]``;
measurement-model.md §8/M15, otdp-specification.md S19). This module is the
one implementation the gateway runs, at two seams: control admission
(:func:`check_derived_variables`, grammar and static checks) and the
executor invoke seam (:func:`derive_dataset_variables`, evaluation).

Sandboxing is structural, not advisory: a hand-written tokenizer and
recursive-descent parser over the closed token set ``+ - * / ( ) number
identifier`` (space is whitespace). ``eval``, ``compile`` and ``ast.parse``
appear nowhere in this module, identifiers are data looked up as dictionary
keys — never as code — and expression length (256) and parenthesis nesting
(32) are capped, so parse cost is bounded by construction (unary operator
chains recurse against the length cap rather than the parenthesis depth —
still bounded, microsecond-scale). The grammar,
the evaluation order and the failure semantics are pinned by the
digest-pinned census ``standards/otdp/0.2.0/examples/derivation-vectors.json``
and tested in ``tests/unit/test_derivation.py`` and
``tests/faults/test_derivation_faults.py``.

Determinism: evaluation is IEEE-754 binary64 over the AST's fixed operation
sequence (left-associative, ``*`` ``/`` binding tighter than ``+`` ``-``),
numeric literals are parsed once from their decimal digits at parse time,
and derivation order is declaration order with operands resolved only
against the dataset's original variables plus earlier-derived ones — the
admission acyclicity check makes that a total order. Re-evaluating a
recorded expression over the recorded operand values reproduces the
recorded values exactly (the replay rule, M15).

What the checks do NOT catch (claim discipline, M15): operand units live in
datasets, not descriptors, so admission cannot unit-check expressions —
``+``/``-`` unit agreement is enforced at evaluation, and only between
identifier-leaf operands (a numeric literal or a nested sub-expression
carries no trackable unit; ``*`` and ``/`` impose no operand-unit rule at
all, and the derived variable's declared quantity/unit is author
responsibility). An operand that resolves to no dataset variable is an
in-band invalid variable, not a refusal — datasets vary by action, so a
declaration is never rejected at admission for naming an operand the
plugin happens not to emit.
"""

from __future__ import annotations

import math
import re
from typing import Any

__all__ = [
    "DerivationRefused",
    "DerivationRejected",
    "MAX_EXPRESSION_LENGTH",
    "MAX_NESTING",
    "check_derived_variables",
    "derive_dataset_variables",
]

MAX_EXPRESSION_LENGTH = 256
MAX_NESTING = 32
#: Ints at or below 2^53 are exactly representable in binary64; above it,
#: conversion silently rounds (9007199254740993 -> 9007199254740992.0).
#: Ints beyond the boundary are refused rather than read through a
#: representation change the record never consented to. The boundary is
#: deliberately conservative — an int in (2^53, 2^63) that happens to be
#: exactly representable (even values) is still refused; "mechanically
#: checkable and total" beats "maximally permissive" at a data boundary.
MAX_EXACT_INT = 2**53
#: The grammar's ``digits`` are exactly ASCII 0-9 (the OTDP schema pattern's
#: class). ``str.isdigit`` would admit Unicode digit-class characters —
#: superscripts crash ``float()`` with an untyped ValueError, and Arabic-
#: Indic/fullwidth digits silently evaluate as their numeric values,
#: disagreeing with the schema lane on identical content.
_ASCII_DIGITS = frozenset("0123456789")

_IDENTIFIER = re.compile(r"[a-z][a-z0-9_]*")

# AST nodes: ("num", value, source_text) | ("id", name) |
# ("unary", op, child) | ("bin", op, left, right).
_Node = tuple[Any, ...]

_REQUIRED_FIELDS = ("id", "quantity", "unit", "expression")


class DerivationRejected(ValueError):
    """A ``derived_variables`` declaration failed a static check.

    The message starts with a machine-matchable ``derivation_*:`` prefix —
    the admission-seam twin of STD-4's prefix discipline.
    """


class DerivationRefused(ValueError):
    """The dataset structurally contradicts the derivation request.

    Raised by :func:`derive_dataset_variables` for structural lies (id
    collision, malformed dataset, unit/dtype/shape disagreement, a forged
    ``derivation`` marker). Elementwise quality losses (null propagation,
    division by zero, non-finite results, unresolved operands) are NOT
    refusals: they degrade in-band as partial/invalid variables.
    """


# --- tokenizer ----------------------------------------------------------------


def _tokenize(expression: str) -> list[tuple[str, str]]:
    """Split an expression into ``(kind, text)`` tokens.

    Kinds: ``num``, ``id``, and one of ``+ - * / ( )``. Whitespace is not a
    token. Anything else — uppercase letters, commas, ``$``, ``**``'s second
    star arriving as a factor — is refused as a grammar error here or by
    the parser's adjacency rules.
    """

    tokens: list[tuple[str, str]] = []
    index = 0
    length = len(expression)
    while index < length:
        char = expression[index]
        if char == " ":
            index += 1
            continue
        if char in "+-*/()":
            tokens.append((char, char))
            index += 1
            continue
        if char in _ASCII_DIGITS or char == ".":
            start = index
            if char in _ASCII_DIGITS:
                while index < length and expression[index] in _ASCII_DIGITS:
                    index += 1
            if index < length and expression[index] == ".":
                index += 1
                if index >= length or expression[index] not in _ASCII_DIGITS:
                    raise DerivationRejected(
                        f"derivation_grammar: malformed number at {start} "
                        f"in {expression!r} (digits required after the decimal point)"
                    )
                while index < length and expression[index] in _ASCII_DIGITS:
                    index += 1
            if index == start:  # a lone "." that never matched a digit
                raise DerivationRejected(
                    f"derivation_grammar: malformed number at {start} in {expression!r}"
                )
            tokens.append(("num", expression[start:index]))
            continue
        match = _IDENTIFIER.match(expression, index)
        if match is not None and match.start() == index:
            tokens.append(("id", match.group()))
            index = match.end()
            continue
        raise DerivationRejected(
            f"derivation_grammar: illegal character {char!r} at {index} in {expression!r}"
        )
    return tokens


# --- parser -------------------------------------------------------------------


class _Parser:
    """Recursive-descent parser for the §2.3 grammar.

    ``expression := term (("+" | "-") term)*``;
    ``term := factor (("*" | "/") factor)*``;
    ``factor := ("+" | "-") factor | atom``;
    ``atom := number | identifier | "(" expression ")"``.
    """

    def __init__(self, tokens: list[tuple[str, str]], expression: str) -> None:
        self._tokens = tokens
        self._expression = expression
        self._position = 0
        self._depth = 0

    def _peek(self) -> tuple[str, str] | None:
        if self._position < len(self._tokens):
            return self._tokens[self._position]
        return None

    def _take(self) -> tuple[str, str]:
        token = self._peek()
        if token is None:
            raise DerivationRejected(
                f"derivation_grammar: unexpected end of expression {self._expression!r}"
            )
        self._position += 1
        return token

    def parse(self) -> _Node:
        node = self._expression_rule()
        token = self._peek()
        if token is not None:
            raise DerivationRejected(
                f"derivation_grammar: unexpected {token[1]!r} after a complete "
                f"expression in {self._expression!r}"
            )
        return node

    def _expression_rule(self) -> _Node:
        node = self._term_rule()
        while (token := self._peek()) is not None and token[0] in ("+", "-"):
            self._take()
            node = ("bin", token[0], node, self._term_rule())
        return node

    def _term_rule(self) -> _Node:
        node = self._factor_rule()
        while (token := self._peek()) is not None and token[0] in ("*", "/"):
            self._take()
            node = ("bin", token[0], node, self._factor_rule())
        return node

    def _factor_rule(self) -> _Node:
        token = self._peek()
        if token is not None and token[0] in ("+", "-"):
            self._take()
            return ("unary", token[0], self._factor_rule())
        return self._atom_rule()

    def _atom_rule(self) -> _Node:
        token = self._take()
        kind, text = token
        if kind == "num":
            # One decimal-string -> binary64 conversion, at parse time: the
            # same literal text always yields the same value. ASCII-only
            # digit text cannot fail this conversion; the except is
            # defensive totality so no path out of the parser is untyped.
            try:
                return ("num", float(text), text)
            except (OverflowError, ValueError) as error:
                raise DerivationRejected(
                    f"derivation_grammar: number {text!r} is not convertible "
                    "to binary64"
                ) from error
        if kind == "id":
            return ("id", text)
        if kind == "(":
            self._depth += 1
            if self._depth > MAX_NESTING:
                raise DerivationRejected(
                    f"derivation_grammar: parenthesis nesting exceeds {MAX_NESTING} "
                    f"in {self._expression!r}"
                )
            node = self._expression_rule()
            closing = self._take()
            if closing[0] != ")":
                raise DerivationRejected(
                    f"derivation_grammar: expected ')' but found {closing[1]!r} "
                    f"in {self._expression!r}"
                )
            self._depth -= 1
            return node
        raise DerivationRejected(
            f"derivation_grammar: unexpected {text!r} where an operand was "
            f"expected in {self._expression!r}"
        )


def _parse(expression: str) -> _Node:
    if not isinstance(expression, str) or not expression:
        raise DerivationRejected("derivation_grammar: expression must be a non-empty string")
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise DerivationRejected(
            f"derivation_grammar: expression length {len(expression)} exceeds "
            f"{MAX_EXPRESSION_LENGTH}"
        )
    tokens = _tokenize(expression)
    if not tokens:
        raise DerivationRejected(
            f"derivation_grammar: expression {expression!r} carries no tokens"
        )
    return _Parser(tokens, expression).parse()


def _identifiers(node: _Node, ordered: list[str], seen: set[str]) -> None:
    """Collect identifier names in first-occurrence order."""

    if node[0] == "id":
        if node[1] not in seen:
            seen.add(node[1])
            ordered.append(node[1])
    elif node[0] == "num":
        return
    elif node[0] == "unary":
        _identifiers(node[2], ordered, seen)
    else:
        _identifiers(node[2], ordered, seen)
        _identifiers(node[3], ordered, seen)


def _describe(node: _Node) -> str:
    """Source-shaped description for failure reasons, e.g. ``num / den``."""

    kind = node[0]
    if kind == "num":
        return str(node[2])
    if kind == "id":
        return str(node[1])
    if kind == "unary":
        return f"{node[1]}{_describe(node[2])}"
    return f"{_describe(node[2])} {node[1]} {_describe(node[3])}"


def _element_is_readable(element: Any) -> bool:
    """True when an inline element can be read as an exact binary64 value.

    The guard this backs must be TOTAL (every element class decides — an
    untyped ``OverflowError`` from ``float(10**400)`` would escape the
    executor's typed handling and skip the protective transition) and
    EXACT (nulls are the unavailable marker; finite floats are read; ints
    only up to ``MAX_EXACT_INT``). Bools, strings and non-finite floats are
    not float64 elements and refuse with ``derivation_dtype_mismatch:``.
    """

    if element is None:
        return True
    if isinstance(element, bool):
        return False
    if isinstance(element, int):
        return -MAX_EXACT_INT <= element <= MAX_EXACT_INT
    if isinstance(element, float):
        return math.isfinite(element)
    return False


# --- static checks (admission seam) --------------------------------------------


def _check_declaration(entry: Any) -> tuple[str, str, _Node, list[str]]:
    if not isinstance(entry, dict):
        raise DerivationRejected(
            f"derivation_shape: declaration {entry!r} is not an object"
        )
    for field in _REQUIRED_FIELDS:
        value = entry.get(field)
        if not isinstance(value, str):
            raise DerivationRejected(
                f"derivation_shape: declaration requires string {field}"
            )
        if field != "expression" and not value:
            # An absent or non-string expression is a shape fault; a present
            # but empty/unparsable one is a grammar fault (the census's
            # whitespace-only row is the grammar class).
            raise DerivationRejected(
                f"derivation_shape: declaration requires non-empty string {field}"
            )
    identifier = entry["id"]
    if not re.fullmatch(r"[a-z][a-z0-9_]*", identifier):
        raise DerivationRejected(
            f"derivation_shape: derived id {identifier!r} must match "
            "^[a-z][a-z0-9_]*$"
        )
    node = _parse(entry["expression"])
    ordered: list[str] = []
    _identifiers(node, ordered, set())
    if not ordered:
        raise DerivationRejected(
            f"derivation_grammar: expression {entry['expression']!r} references no "
            "dataset variable (constant-only expressions cannot carry the "
            "derivation marker's operand_ids)"
        )
    return identifier, entry["expression"], node, ordered


def check_derived_variables(derived: list[dict[str, Any]]) -> None:
    """Grammar and static checks over a ``derived_variables`` array.

    Raises :class:`DerivationRejected` (machine prefix
    ``derivation_shape:`` / ``derivation_grammar:`` /
    ``derivation_duplicate_id:`` / ``derivation_self_reference:`` /
    ``derivation_cycle:``) for any violation; returns silently when the
    array is well formed. Checked: array/entry shape; id grammar and
    uniqueness; expression length, character surface, token formation and
    parenthesis nesting; at least one identifier per expression; no derived
    id inside its own expression; the derived-from-derived graph is
    acyclic in declaration order (an operand naming another derived
    variable must name an EARLIER declaration — declaration order is the
    evaluation order, which is what makes evaluation deterministic).

    NOT checked here (the residual): whether an operand id exists in any
    dataset (datasets vary by action — an unresolved operand degrades
    in-band at evaluation), and any unit agreement (operand units live in
    datasets; see the module docstring). The liar-check parses recorded
    markers only when the device carries derived declarations — a forged
    marker on a declaration-free device is never parsed (within
    provenance-not-authority: the marker grants nothing by
    existing). Extra object keys beyond the four
    required ones are ignored — the OTDP descriptor schema is the
    closed-world authority where one applies.
    """

    if not isinstance(derived, list):
        raise DerivationRejected(
            f"derivation_shape: derived_variables must be a list, got {type(derived).__name__}"
        )
    parsed: list[tuple[str, list[str]]] = []
    for entry in derived:
        identifier, _expression, _node, ordered = _check_declaration(entry)
        parsed.append((identifier, ordered))
    seen: set[str] = set()
    for index, (identifier, operands) in enumerate(parsed):
        if identifier in seen:
            raise DerivationRejected(
                f"derivation_duplicate_id: {identifier!r} declared more than once"
            )
        seen.add(identifier)
        if identifier in operands:
            raise DerivationRejected(
                f"derivation_self_reference: {identifier!r} appears in its own expression"
            )
        for operand in operands:
            for earlier in range(index):
                if parsed[earlier][0] == operand:
                    break
            else:
                for later in range(index + 1, len(parsed)):
                    if parsed[later][0] == operand:
                        raise DerivationRejected(
                            f"derivation_cycle: {identifier!r} references "
                            f"{operand!r}, declared later (declaration order is "
                            "the evaluation order)"
                        )


# --- evaluation (executor seam) -------------------------------------------------


def _check_recorded_marker(variable: dict[str, Any]) -> None:
    """Liar-check a ``derivation`` marker already present on a variable.

    The marker is provenance, not authority — an adapter may truthfully
    emit one for a code-computed variable — but its ``operand_ids`` must be
    the parsed projection of its own ``expression``. A disagreement is a
    forged record and refuses the whole derivation call.
    """

    marker = variable.get("derivation")
    if marker is None:
        return
    if not isinstance(marker, dict):
        raise DerivationRefused(
            f"derivation_marker_mismatch: variable {variable.get('id')!r} carries "
            "a non-object derivation marker"
        )
    expression = marker.get("expression")
    operand_ids = marker.get("operand_ids")
    if marker.get("kind") != "expression" or not isinstance(expression, str):
        raise DerivationRefused(
            f"derivation_marker_mismatch: variable {variable.get('id')!r} carries "
            "a marker that is not a closed expression record"
        )
    if (
        not isinstance(operand_ids, list)
        or not operand_ids
        or not all(isinstance(item, str) for item in operand_ids)
        or len(set(operand_ids)) != len(operand_ids)
        or any(not re.fullmatch(r"[a-z][a-z0-9_]*", str(item)) for item in operand_ids)
    ):
        # The schema's own bounds on operand_ids (minItems 1, uniqueItems,
        # id pattern) — the liar-check enforces them rather than trust a
        # record that already violates its declared shape.
        raise DerivationRefused(
            f"derivation_marker_mismatch: variable {variable.get('id')!r} carries "
            "operand_ids that are not a non-empty list of unique variable ids"
        )
    try:
        node = _parse(expression)
    except DerivationRejected as error:
        # A recorded marker whose expression does not parse is a forged
        # record — the refusal family of this check, not the declaration
        # path's grammar-rejection family.
        raise DerivationRefused(
            f"derivation_marker_mismatch: variable {variable.get('id')!r} records "
            f"an unparseable expression {expression!r}"
        ) from error
    ordered: list[str] = []
    _identifiers(node, ordered, set())
    # Set-based agreement: the schema declares uniqueItems, so order is not
    # semantic — the ids as a set must match the parsed projection exactly.
    if set(operand_ids) != set(ordered):
        raise DerivationRefused(
            f"derivation_marker_mismatch: variable {variable.get('id')!r} records "
            f"operand_ids {sorted(operand_ids)} but its expression parses to "
            f"{sorted(ordered)}"
        )


def _operand_arrays(
    node: _Node, operands: dict[str, dict[str, Any]], violations: list[str]
) -> None:
    """Collect ``+``/``-`` unit violations between identifier-leaf operands."""

    if node[0] != "bin":
        return
    _operand_arrays(node[2], operands, violations)
    _operand_arrays(node[3], operands, violations)
    if node[1] not in ("+", "-"):
        return
    left, right = node[2], node[3]
    if left[0] == "id" and right[0] == "id":
        left_unit = operands[left[1]].get("unit")
        right_unit = operands[right[1]].get("unit")
        if left_unit != right_unit:
            violations.append(
                f"derivation_unit_mismatch: {left[1]} ({left_unit!r}) {node[1]} "
                f"{right[1]} ({right_unit!r})"
            )


def _evaluate(
    node: _Node, values: dict[str, Any], causes: set[str]
) -> float | None:
    """Evaluate one element; ``None`` records a failed element with a cause."""

    kind = node[0]
    if kind == "num":
        return float(node[1])
    if kind == "id":
        value = values[node[1]]
        if value is None:
            return None
        try:
            return float(value)
        except (OverflowError, ValueError) as error:
            # Defensive totality: the operand guard already refused
            # non-convertible elements, so reaching here means the guard
            # was bypassed — refuse typed rather than let the conversion
            # exception escape the pure module.
            raise DerivationRefused(
                "derivation_dtype_mismatch: operand element of type "
                f"{type(value).__name__} is not convertible to binary64"
            ) from error
    if kind == "unary":
        child = _evaluate(node[2], values, causes)
        if child is None:
            return None
        return -child if node[1] == "-" else child
    left = _evaluate(node[2], values, causes)
    if left is None:
        return None
    right = _evaluate(node[3], values, causes)
    if right is None:
        return None
    operator = node[1]
    if operator == "+":
        result = left + right
    elif operator == "-":
        result = left - right
    elif operator == "*":
        result = left * right
    else:
        if right == 0.0:
            causes.add(f"derivation_division_by_zero: {_describe(node)}")
            return None
        result = left / right
    if not math.isfinite(result):
        causes.add(f"derivation_non_finite_result: {_describe(node)}")
        return None
    return result


def _null_cause(
    node: _Node, values: dict[str, Any], null_operands: set[str]
) -> None:
    """Record which identifier operands contributed nulls at this element."""

    if node[0] == "id":
        if values[node[1]] is None:
            null_operands.add(str(node[1]))
    elif node[0] == "unary":
        _null_cause(node[2], values, null_operands)
    elif node[0] == "bin":
        _null_cause(node[2], values, null_operands)
        _null_cause(node[3], values, null_operands)


def _derive_one(
    declaration: dict[str, Any],
    variables: list[dict[str, Any]],
    index_by_id: dict[str, int],
) -> dict[str, Any]:
    identifier = str(declaration["id"])
    expression = str(declaration["expression"])
    node = _parse(expression)
    ordered: list[str] = []
    _identifiers(node, ordered, set())

    missing = [operand for operand in ordered if operand not in index_by_id]
    if missing:
        # No element is fabricated for a shape that could not be established:
        # empty values and dimensions, invalid status, the reason naming the
        # operands (M15).
        return {
            "id": identifier,
            "quantity": declaration["quantity"],
            "unit": declaration["unit"],
            "channel_ids": [],
            "dtype": "float64",
            "dimensions": [],
            "values": [],
            "uncertainty": {"status": "unknown"},
            "calibration": {"status": "unknown"},
            "status": "invalid",
            "status_reason": "derivation_operand_missing: " + ", ".join(sorted(missing)),
            "derivation": {
                "kind": "expression",
                "expression": expression,
                "operand_ids": ordered,
            },
        }

    operands = {operand: variables[index_by_id[operand]] for operand in ordered}
    for operand, variable in operands.items():
        if variable.get("dtype") != "float64" or not isinstance(
            variable.get("values"), list
        ):
            # Increment 1 reads inline float64 only: artifact-backed or
            # non-float64 operands refuse loudly (deferred: artifact decode,
            # int/bool arithmetic and coercion semantics).
            raise DerivationRefused(
                f"derivation_dtype_mismatch: operand {operand!r} is not inline "
                f"float64 (dtype {variable.get('dtype')!r}, "
                f"inline {'values' in variable})"
            )
        for element in variable["values"]:
            if not _element_is_readable(element):
                raise DerivationRefused(
                    f"derivation_dtype_mismatch: operand {operand!r} carries a "
                    f"non-float64 or non-exactly-representable element "
                    f"({type(element).__name__})"
                )

    reference_dimensions = operands[ordered[0]].get("dimensions")
    reference_length = len(operands[ordered[0]]["values"])
    for operand, variable in operands.items():
        if variable.get("dimensions") != reference_dimensions:
            raise DerivationRefused(
                f"derivation_shape_mismatch: operand dimensions disagree: "
                f"{ordered[0]!r} {reference_dimensions!r} vs {operand!r} "
                f"{variable.get('dimensions')!r} (no broadcasting)"
            )
        if len(variable["values"]) != reference_length:
            raise DerivationRefused(
                f"derivation_shape_mismatch: operand value counts disagree: "
                f"{ordered[0]!r} has {reference_length}, {operand!r} has "
                f"{len(variable['values'])}"
            )

    unit_violations: list[str] = []
    _operand_arrays(node, operands, unit_violations)
    if unit_violations:
        raise DerivationRefused("; ".join(sorted(unit_violations)))

    channel_ids: list[str] = []
    for operand in ordered:
        for channel in operands[operand].get("channel_ids", []):
            if channel not in channel_ids:
                channel_ids.append(channel)

    results: list[float | None] = []
    causes: set[str] = set()
    for position in range(reference_length):
        row_values: dict[str, Any] = {
            operand: operands[operand]["values"][position] for operand in ordered
        }
        null_operands: set[str] = set()
        _null_cause(node, row_values, null_operands)
        value = _evaluate(node, row_values, causes)
        if value is None and null_operands:
            causes.add("derivation_null_operand: " + ", ".join(sorted(null_operands)))
        results.append(value)

    failed = sum(1 for value in results if value is None)
    derived: dict[str, Any] = {
        "id": identifier,
        "quantity": declaration["quantity"],
        "unit": declaration["unit"],
        "channel_ids": channel_ids,
        "dtype": "float64",
        "dimensions": list(reference_dimensions or []),
        "values": results,
        # Structurally unknown, always: a propagated bound would presume
        # operand-error independence the contract cannot evidence (A02), and
        # 'applied' calibration would fabricate a reference/method the
        # combination does not have. Operands keep their own records.
        "uncertainty": {"status": "unknown"},
        "calibration": {"status": "unknown"},
        "status": "valid",
        "derivation": {
            "kind": "expression",
            "expression": expression,
            "operand_ids": ordered,
        },
    }
    if failed:
        derived["status"] = "invalid" if failed == len(results) else "partial"
        derived["status_reason"] = "; ".join(sorted(causes))
    return derived


def derive_dataset_variables(
    dataset: dict[str, Any], derived: list[dict[str, Any]]
) -> dict[str, Any]:
    """Append declared derived variables to a copy of ``dataset``.

    Pure: returns a NEW dataset dict with a new ``variables`` list (original
    variable objects are shared, never mutated); the input is untouched —
    pinned by the census's no-mutation assertion on every evaluation row.
    No I/O, no clock, no plugins: caller-supplied inputs only (the STO-1
    purity discipline applied to a control path).

    Declaration order is the evaluation order; each expression's operands
    resolve against the dataset's original variables plus previously
    derived ones. Structural contradictions raise
    :class:`DerivationRefused` (malformed ``variables``, a derived id
    already present — a collision would launder the plugin variable's
    provenance — a forged recorded ``derivation`` marker, or operand
    unit/dtype/shape disagreement). Elementwise failures (null propagation,
    division by zero, non-finite results) and unresolved operands degrade
    in-band as partial/invalid variables; numeric failures are ``null``,
    never ``inf``/``NaN`` (measurement-model.md §3).
    """

    check_derived_variables(derived)
    variables = dataset.get("variables")
    if not isinstance(variables, list) or not all(
        isinstance(variable, dict) for variable in variables
    ):
        raise DerivationRefused(
            "derivation_dataset_malformed: dataset variables must be a list "
            "of objects"
        )
    for variable in variables:
        _check_recorded_marker(variable)

    working: list[dict[str, Any]] = list(variables)
    index_by_id: dict[str, int] = {
        str(variable.get("id")): position for position, variable in enumerate(working)
    }
    if len(index_by_id) != len(working):
        # M01 laundering: with duplicate ids, operand resolution would
        # silently read the LAST duplicate — mirroring the derived-id
        # collision stance for pre-existing duplicates refuses instead.
        counts: dict[str, int] = {}
        for variable in working:
            identifier = str(variable.get("id"))
            counts[identifier] = counts.get(identifier, 0) + 1
        duplicates = sorted(key for key, count in counts.items() if count > 1)
        raise DerivationRefused(
            f"derivation_duplicate_variable: dataset carries duplicate variable "
            f"id(s) {duplicates}; derivation reads refuse rather than resolve "
            "operands to an arbitrary duplicate"
        )
    for declaration in derived:
        identifier = str(declaration["id"])
        if identifier in index_by_id:
            raise DerivationRefused(
                f"derivation_id_collision: {identifier!r} is already present in "
                "the dataset (silently reusing the plugin's variable would "
                "launder its provenance)"
            )
        derived_variable = _derive_one(declaration, working, index_by_id)
        index_by_id[identifier] = len(working)
        working.append(derived_variable)

    updated = dict(dataset)
    updated["variables"] = working
    return updated

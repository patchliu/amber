"""Validation, identity and explainable matching for Amber Spec 0.1-mvp.

This subset supports exact computation graphs, dimension intervals and scalar
attribute constraints. It deliberately makes no floating-point equivalence claim.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import TypeAlias

JSON: TypeAlias = None | bool | int | str | list["JSON"] | dict[str, "JSON"]


class SpecError(ValueError):
    """A spec is outside the supported language subset."""


def _object(value: object, path: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise SpecError(f"{path} must be an object with string keys")
    return value


def _scalar(value: object, path: str) -> None:
    if not isinstance(value, (str, int, bool)) or isinstance(value, float):
        raise SpecError(f"{path} must be a string, integer or boolean")


def _dimensions(value: object) -> dict[str, tuple[int, int]]:
    dimensions = _object(value, "domain.dimensions")
    result: dict[str, tuple[int, int]] = {}
    for name, raw in dimensions.items():
        bounds = _object(raw, f"domain.dimensions.{name}")
        if set(bounds) != {"min", "max"}:
            raise SpecError(f"dimension {name} requires min and max")
        low, high = bounds["min"], bounds["max"]
        if type(low) is not int or type(high) is not int or low < 1 or low > high:
            raise SpecError(f"dimension {name} requires 1 <= min <= max")
        result[name] = (low, high)
    return result


def validate_spec(value: object, *, implementation: bool = False) -> dict[str, object]:
    spec = _object(value, "spec")
    required = {"language_version", "signature", "domain", "computation", "acceptance"}
    if set(spec) != required or spec["language_version"] != "0.1-mvp":
        raise SpecError("spec requires the five 0.1-mvp fields")
    dimensions = _dimensions(_object(spec["domain"], "domain").get("dimensions"))
    if set(_object(spec["domain"], "domain")) != {"dimensions"}:
        raise SpecError("only domain.dimensions is supported")
    signature = _object(spec["signature"], "signature")
    if set(signature) != {"inputs", "outputs"}:
        raise SpecError("signature requires inputs and outputs")
    names: set[str] = set()
    for side in ("inputs", "outputs"):
        tensors = _object(signature[side], f"signature.{side}")
        if not tensors:
            raise SpecError(f"signature.{side} cannot be empty")
        for name, raw in tensors.items():
            tensor = _object(raw, f"signature.{side}.{name}")
            if set(tensor) != {"dtype", "shape"} or not isinstance(tensor["dtype"], str):
                raise SpecError(f"tensor {name} requires dtype and shape")
            shape = tensor["shape"]
            if not isinstance(shape, list) or not shape:
                raise SpecError(f"tensor {name} requires a nonempty shape")
            for axis in shape:
                if type(axis) is int and axis > 0:
                    continue
                if isinstance(axis, str) and axis in dimensions:
                    continue
                raise SpecError(f"tensor {name} has an undeclared or invalid axis {axis!r}")
            names.add(name)
    computation = _object(spec["computation"], "computation")
    if set(computation) != {"nodes", "outputs"}:
        raise SpecError("computation requires nodes and outputs")
    nodes = computation["nodes"]
    if not isinstance(nodes, list) or not nodes:
        raise SpecError("computation.nodes must be nonempty")
    available = set(_object(signature["inputs"], "signature.inputs"))
    for raw in nodes:
        node = _object(raw, "node")
        if set(node) != {"id", "op", "inputs", "attributes"}:
            raise SpecError("each node requires id, op, inputs and attributes")
        node_id, op, inputs = node["id"], node["op"], node["inputs"]
        if not isinstance(node_id, str) or not node_id or node_id in available:
            raise SpecError(f"invalid or duplicate node id {node_id!r}")
        if not isinstance(op, str) or not op.startswith("amber."):
            raise SpecError(f"invalid operator {op!r}")
        if not isinstance(inputs, list) or not inputs or any(x not in available for x in inputs):
            raise SpecError(f"node {node_id} uses unavailable inputs")
        for key, raw_attr in _object(node["attributes"], f"node {node_id}.attributes").items():
            if implementation:
                _scalar(raw_attr, f"{node_id}.{key}")
            else:
                constraint = _object(raw_attr, f"{node_id}.{key}")
                if len(constraint) != 1 or next(iter(constraint)) not in {"exact", "one_of", "any"}:
                    raise SpecError(f"{node_id}.{key} needs exact, one_of or any")
                kind, operand = next(iter(constraint.items()))
                if kind == "any":
                    if operand is not True:
                        raise SpecError(f"{node_id}.{key}.any must be true")
                elif kind == "one_of":
                    if not isinstance(operand, list) or not operand:
                        raise SpecError(f"{node_id}.{key}.one_of must be nonempty")
                    for item in operand:
                        _scalar(item, f"{node_id}.{key}.one_of")
                else:
                    _scalar(operand, f"{node_id}.{key}.exact")
        available.add(node_id)
    outputs = _object(computation["outputs"], "computation.outputs")
    if set(outputs) != set(_object(signature["outputs"], "signature.outputs")):
        raise SpecError("computation outputs must match signature outputs")
    if any(value not in available for value in outputs.values()):
        raise SpecError("computation output references unavailable value")
    acceptance = _object(spec["acceptance"], "acceptance")
    if set(acceptance) != {"relation", "reference"} or acceptance["relation"] != "semantic_contract" or not isinstance(acceptance["reference"], str) or not acceptance["reference"]:
        raise SpecError("MVP requires semantic_contract with a reference identifier")
    return spec


def canonical_json(value: JSON) -> bytes:
    """Encode the supported JSON subset; floats are excluded to avoid ambiguous keys."""
    def check(item: JSON) -> None:
        if isinstance(item, float):
            raise SpecError("JSON floats are unsupported; use typed strings")
        if isinstance(item, list):
            for child in item:
                check(child)
        if isinstance(item, dict):
            for child in item.values():
                check(child)
    check(value)
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def digest(value: JSON, kind: str = "spec") -> str:
    payload = f"amber:{kind}:0.1-mvp\n".encode() + canonical_json(value)
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def match_spec(query: Mapping[str, object], candidate: Mapping[str, object]) -> dict[str, object]:
    """Return match, reject or unknown with field-level reasons.

    Candidate attributes are source declarations, not independently verified facts.
    """
    validate_spec(dict(query))
    validate_spec(dict(candidate), implementation=True)
    rejected: list[str] = []
    unknown: list[str] = []
    if query["signature"] != candidate["signature"]:
        rejected.append("signature differs")
    qcomp = _object(query["computation"], "computation")
    ccomp = _object(candidate["computation"], "computation")
    qnodes, cnodes = qcomp["nodes"], ccomp["nodes"]
    if len(qnodes) != len(cnodes) or qcomp["outputs"] != ccomp["outputs"]:
        rejected.append("computation graph differs")
    else:
        for qraw, craw in zip(qnodes, cnodes, strict=True):
            qnode, cnode = _object(qraw, "node"), _object(craw, "node")
            if any(qnode[key] != cnode[key] for key in ("id", "op", "inputs")):
                rejected.append(f"node {qnode['id']} structure differs")
                continue
            attrs = _object(cnode["attributes"], "attributes")
            for key, constraint_raw in _object(qnode["attributes"], "attributes").items():
                constraint = _object(constraint_raw, "constraint")
                kind, expected = next(iter(constraint.items()))
                if kind == "any":
                    continue
                if key not in attrs:
                    unknown.append(f"node {qnode['id']}.{key} is undeclared")
                elif (kind == "exact" and attrs[key] != expected) or (kind == "one_of" and attrs[key] not in expected):
                    rejected.append(f"node {qnode['id']}.{key} is {attrs[key]!r}; requires {expected!r}")
    qdims = _dimensions(_object(query["domain"], "domain")["dimensions"])
    cdims = _dimensions(_object(candidate["domain"], "domain")["dimensions"])
    for name, (low, high) in qdims.items():
        if name not in cdims or cdims[name][0] > low or cdims[name][1] < high:
            rejected.append(f"dimension {name} is not covered")
    if query["acceptance"] != candidate["acceptance"]:
        rejected.append("acceptance or reference differs")
    decision = "rejected" if rejected else "unknown" if unknown else "candidate"
    return {"decision": decision, "reasons": rejected + unknown}

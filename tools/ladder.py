"""Strict graph validation and reference lowering for the supported LD subset.

Contacts in series are AND; multiple incoming connections are OR. Execution
order is explicit. Unsupported elements fail closed instead of disappearing.
The executable ST is exported by the actual OpenPLC generator in
openplc_export.py. This independent walk rejects unsupported or broken graphs.
"""
import argparse
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
NS = {"p": "http://www.plcopen.org/xml/tc6_0201"}


def compile_ld(path):
    project = ET.parse(path).getroot()
    pou = project.find("p:types/p:pous/p:pou", NS)
    if pou is None or pou.get("name") != "FillingLine":
        raise ValueError("Expected FillingLine program")
    declarations = []
    names = set()
    blocks = {}
    for group in pou.find("p:interface", NS):
        if group.tag.split("}")[-1] not in {"inputVars", "outputVars", "localVars"}:
            raise ValueError("Unsupported variable group")
        rows = []
        for var in group:
            name = var.get("name")
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name or "") or name in names:
                raise ValueError("Invalid or duplicate variable")
            names.add(name)
            typ = var.find("p:type", NS)[0]
            kind = typ.tag.split("}")[-1]
            type_name = typ.get("name") if kind == "derived" else kind
            if type_name not in {"BOOL", "TON", "CTU", "R_TRIG"}:
                raise ValueError("Unsupported variable type")
            if kind == "derived":
                blocks[name] = type_name
            rows.append(f"  {name} : {type_name};")
        keyword = {"inputVars": "VAR_INPUT", "outputVars": "VAR_OUTPUT", "localVars": "VAR"}[group.tag.split("}")[-1]]
        declarations.extend([keyword, *rows, "END_VAR"])
    body = pou.find("p:body/p:LD", NS)
    if body is None:
        raise ValueError("Expected LD body")
    allowed = {"leftPowerRail", "rightPowerRail", "contact", "coil", "block", "inVariable", "comment"}
    nodes = {}
    for node in body:
        kind = node.tag.split("}")[-1]
        if kind not in allowed:
            raise ValueError(f"Unsupported LD element: {kind}")
        ident = node.get("localId")
        if ident in nodes:
            raise ValueError("Duplicate localId")
        nodes[ident] = node

    def variable(value):
        if value in names or value in {f"{n}.{field}" for n in blocks for field in ("Q", "CV")}:
            return value
        raise ValueError(f"Undeclared variable: {value}")

    def incoming(point, trail=()):
        if point is None:
            raise ValueError("Unconnected input")
        conns = point.findall("p:connection", NS)
        if not conns:
            raise ValueError("Unconnected input")
        return "(" + " OR ".join(power(c.get("refLocalId"), trail) for c in conns) + ")"

    def power(ident, trail=()):
        if ident in trail or ident not in nodes:
            raise ValueError("Cyclic or missing connection")
        node = nodes[ident]
        kind = node.tag.split("}")[-1]
        if kind == "leftPowerRail":
            return "TRUE"
        if kind == "inVariable":
            value = node.findtext("p:expression", namespaces=NS)
            if re.fullmatch(r"T#[0-9]+ms|[0-9]+|TRUE|FALSE", value or ""):
                return value
            return variable(value)
        if kind != "contact":
            raise ValueError(f"Unsupported connection source: {kind}")
        if node.get("edge", "none") != "none" or node.get("storage", "none") != "none":
            raise ValueError("Use an explicit R_TRIG block for edge detection")
        value = variable(node.findtext("p:variable", namespaces=NS))
        if node.get("negated", "false") == "true":
            value = f"NOT {value}"
        return f"({incoming(node.find('p:connectionPointIn', NS), trail + (ident,))} AND {value})"

    terminals = [n for n in body if n.tag.split("}")[-1] in {"coil", "block"}]
    orders = [int(n.get("executionOrderId", "0")) for n in terminals]
    if any(x <= 0 for x in orders) or len(orders) != len(set(orders)):
        raise ValueError("Terminals require unique positive executionOrderId")
    statements = []
    expected = {"TON": ["IN", "PT"], "CTU": ["CU", "R", "PV"], "R_TRIG": ["CLK"]}
    for node in sorted(terminals, key=lambda n: int(n.get("executionOrderId"))):
        kind = node.tag.split("}")[-1]
        if kind == "coil":
            if any(node.get(a, "false" if a == "negated" else "none") != default
                   for a, default in [("negated", "false"), ("storage", "none"), ("edge", "none")]):
                raise ValueError("Only normal coils supported")
            target = variable(node.findtext("p:variable", namespaces=NS))
            statements.append(f"{target} := {incoming(node.find('p:connectionPointIn', NS))};")
        else:
            name, typ = node.get("instanceName"), node.get("typeName")
            if blocks.get(name) != typ or typ not in expected:
                raise ValueError("Invalid function block")
            args = node.findall("p:inputVariables/p:variable", NS)
            if [a.get("formalParameter") for a in args] != expected[typ]:
                raise ValueError("Unsupported function block parameters")
            values = [f"{a.get('formalParameter')} := {incoming(a.find('p:connectionPointIn', NS))}" for a in args]
            statements.append(f"{name}({', '.join(values)});")
    return "\n".join(["(* Generated from plc/line.xml. Do not hand-edit. *)", "PROGRAM FillingLine", *declarations,
                       *statements, "END_PROGRAM", "", "CONFIGURATION LineConfig", "RESOURCE CPU ON PLC",
                       "TASK Scan(INTERVAL := T#50ms, PRIORITY := 0);", "PROGRAM Line WITH Scan : FillingLine;",
                       "END_RESOURCE", "END_CONFIGURATION", ""])


if __name__ == "__main__":
    compile_ld(ROOT / "plc/line.xml")
    print("Supported ladder graph validated")

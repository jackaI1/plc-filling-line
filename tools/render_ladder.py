"""Render the actual PLCopen coordinates and wires as an inspectable SVG."""
from html import escape
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
NS = {"p": "http://www.plcopen.org/xml/tc6_0201"}
ld = ET.parse(ROOT / "plc/line.xml").find(".//p:LD", NS)
width = max(int(n.find("p:position", NS).get("x")) + 260 for n in ld)
height = max(int(n.find("p:position", NS).get("y")) + int(n.get("height", 30)) + 60 for n in ld)
svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-label="Filling line ladder diagram">',
       '<style>text{font:15px sans-serif;fill:#243b53}path,polyline,line,rect{stroke:#47647b;stroke-width:2;fill:none}</style>',
       f'<rect width="{width}" height="{height}" fill="white" style="fill:white;stroke:none"/>']
for n in ld:
    kind = n.tag.split("}")[-1]
    pos = n.find("p:position", NS)
    x, y = int(pos.get("x")), int(pos.get("y"))
    w, h = int(n.get("width", 36)), int(n.get("height", 30))
    for c in n.findall(".//p:connection", NS):
        points = " ".join(f'{p.get("x")},{p.get("y")}' for p in c.findall("p:position", NS))
        svg.append(f'<polyline points="{points}"/>')
    if kind == "leftPowerRail":
        svg.append(f'<path d="M{x+10} {y}v{h}"/>')
    elif kind == "contact":
        svg.append(f'<path d="M{x} {y+15}h10m0 -12v24m16 -24v24m0 -12h10"/>')
        if n.get("negated") == "true":
            svg.append(f'<path d="M{x+8} {y+26}l20 -22"/>')
        svg.append(f'<text x="{x-2}" y="{y-7}">{escape(n.findtext("p:variable", namespaces=NS))}</text>')
    elif kind == "coil":
        svg.append(f'<path d="M{x} {y+15}h8m7 -12q-12 12 0 24m7 -24q12 12 0 24m7 -12h7"/>')
        svg.append(f'<text x="{x}" y="{y-7}">{escape(n.findtext("p:variable", namespaces=NS))}</text>')
    elif kind == "inVariable":
        svg.append(f'<text x="{x}" y="{y+12}">{escape(n.findtext("p:expression", namespaces=NS))}</text>')
    elif kind == "block":
        svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}"/>')
        svg.append(f'<text x="{x}" y="{y-8}">{escape(n.get("instanceName"))} : {escape(n.get("typeName"))}</text>')
        for v in n.findall("p:inputVariables/p:variable", NS):
            rel = v.find("p:connectionPointIn/p:relPosition", NS)
            svg.append(f'<text x="{x+7}" y="{y+int(rel.get("y"))+4}">{escape(v.get("formalParameter"))}</text>')
svg.append('</svg>')
(ROOT / "docs/ladder.svg").write_text("\n".join(svg))
print("Rendered docs/ladder.svg from PLCopen source")

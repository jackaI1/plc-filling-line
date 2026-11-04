"""Validate against the schema shipped with the pinned OpenPLC v3 editor."""
from pathlib import Path
from urllib.request import urlopen
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
EDITOR_REV = "6a8e930a914e4421e8fa05966b31eb371b439243"
path = ROOT / ".build/tc6_xml_v201.xsd"
if not path.exists():
    with urlopen(f"https://raw.githubusercontent.com/thiagoralves/editor/{EDITOR_REV}/plcopen/tc6_xml_v201.xsd", timeout=30) as response:
        data = response.read(400_000)
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(data)
schema = etree.XMLSchema(etree.parse(str(path)))
schema.assertValid(etree.parse(str(ROOT / "plc/line.xml")))
print("PLCopen TC6 2.01 schema validation passed")

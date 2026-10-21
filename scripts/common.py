"""Shared loading of pinned inputs for usdm-overlay scripts."""
from pathlib import Path

import openpyxl
import yaml
from rdflib import Graph, Namespace

ROOT = Path(__file__).resolve().parent.parent
DOWNLOADS = ROOT / "downloads"
USDM = Namespace("https://w3id.org/cdisc/usdm/v4/")
UO = Namespace("https://kerfors.github.io/usdm-overlay/")
NCIT = Namespace("http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl#")

CT_SHEET = "DDF Entities&Attributes"
CT_HEADER = (
    "Row #", "Entity Name", "Role", "Inherited From", "Logical Data Model Name", "NCI C-code",
    "CT Item Preferred Name", "Synonym(s)", "Definition", "Has Value List", "Codelist URL",
)


def load_usdm():
    return Graph().parse(DOWNLOADS / "usdm_v4.ttl")


def load_m11():
    return Graph().parse(DOWNLOADS / "m11-rdf" / "m11-rdf.ttl")


def load_ct():
    """Return USDM_CT.xlsx entity/attribute rows keyed by (entity, logical data model name)."""
    ws = openpyxl.load_workbook(DOWNLOADS / "USDM_CT.xlsx", read_only=True)[CT_SHEET]
    rows = list(ws.iter_rows(values_only=True))
    if tuple(rows[0]) != CT_HEADER:
        raise RuntimeError(f"Unexpected header in {CT_SHEET}: {rows[0]}")
    out = {}
    for r in rows[1:]:
        rec = dict(zip(CT_HEADER, r))
        key = (rec["Entity Name"], rec["Logical Data Model Name"])
        if key in out:
            raise RuntimeError(f"Duplicate CT row for {key}")
        out[key] = rec
    return out


def load_yaml():
    return yaml.safe_load((DOWNLOADS / "dataStructure.yml").read_text())


def example_files():
    files = sorted((DOWNLOADS / "examples").glob("*.json"))
    if not files:
        raise RuntimeError("No example files in downloads/examples")
    return files


def local(iri):
    return str(iri).split("/")[-1].split("#")[-1]

"""Run the test of every finding in authored/findings.ttl against the pinned inputs.

Output: derived/finding_results.ttl
        reports/findings.md
Exits with status 1 if any finding does not hold.
"""
import json
import re
import sys
from collections import Counter

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import DCTERMS, RDF, SKOS, XSD

from common import NCIT, ROOT, UO, USDM, example_files, load_ct, load_usdm, load_yaml, local

PINNED = {
    "usdm_v4.ttl": URIRef("https://raw.githubusercontent.com/kerfors/usdm-rdf/v0.7.1/usdm_v4.ttl"),
    "USDM_CT.xlsx": URIRef("https://github.com/cdisc-org/DDF-RA/blob/v4.0.0/Deliverables/CT/USDM_CT.xlsx"),
    "dataStructure.yml": URIRef("https://github.com/cdisc-org/DDF-RA/blob/v4.0.0/Deliverables/UML/dataStructure.yml"),
    "examples": URIRef("https://github.com/cdisc-org/DDF-RA/tree/v4.0.0/Documents/Examples"),
}

ISO_DURATION = re.compile(
    r"^-?P(?!$)(\d+(\.\d+)?Y)?(\d+(\.\d+)?M)?(\d+(\.\d+)?W)?(\d+(\.\d+)?D)?"
    r"(T(?=\d)(\d+(\.\d+)?H)?(\d+(\.\d+)?M)?(\d+(\.\d+)?S)?)?$"
)

SYNTAX_TEMPLATE_TYPES = {"Objective", "Endpoint", "EligibilityCriterionItem", "IntercurrentEvent", "Condition", "Characteristic"}


def abstract_class_attribute_ccodes(ctx):
    yml, ct, usdm = ctx["yaml"], ctx["ct"], ctx["usdm"]
    compared = 0
    mismatches = []
    for cls, body in yml.items():
        if not isinstance(body, dict):
            continue
        for attr, ab in (body.get("Attributes") or {}).items():
            code = ab.get("NCI C-Code")
            if not code:
                continue
            row = ct[(cls, attr)]
            compared += 1
            if row["NCI C-code"] != code:
                mismatches.append((cls, attr, code, row["NCI C-code"], body.get("Modifier")))
    abstract = {cls for cls, body in yml.items() if isinstance(body, dict) and body.get("Modifier") == "Abstract"}
    abstract_compared = sum(
        1 for cls in abstract for attr, ab in (yml[cls].get("Attributes") or {}).items() if ab.get("NCI C-Code")
    )
    all_on_abstract = all(m[4] == "Abstract" for m in mismatches)
    rendered = all((USDM[f"{c}-{a}"], SKOS.exactMatch, NCIT[y]) in usdm for c, a, y, _, _ in mismatches)
    example = (
        yml["SyntaxTemplate"]["Attributes"]["text"]["NCI C-Code"] == "C207478"
        and yml["SyntaxTemplate"]["Attributes"]["text"]["Preferred Term"] == "Characteristic Text"
        and ct[("SyntaxTemplate", "text")]["NCI C-code"] == "C207578"
        and ct[("SyntaxTemplate", "text")]["CT Item Preferred Name"] == "Syntax Template Text"
    )
    holds = bool(mismatches) and all_on_abstract and rendered and example
    by_class = Counter(m[0] for m in mismatches)
    obs = (
        f"{len(mismatches)} of {compared} C-coded attributes in dataStructure.yml differ from USDM_CT.xlsx. "
        f"All differences are on abstract classes ({', '.join(f'{c} {n}' for c, n in sorted(by_class.items()))}); "
        f"{abstract_compared} C-coded attributes are declared on abstract classes in total. "
        f"usdm-rdf skos:exactMatch follows the YAML code for all {len(mismatches)}."
    )
    return holds, obs, [PINNED["dataStructure.yml"], PINNED["USDM_CT.xlsx"], PINNED["usdm_v4.ttl"]]


def procedure_type_uncoded(ctx):
    ct = ctx["ct"]
    p = ct[("Procedure", "procedureType")]
    e = ct[("Endpoint", "level")]
    prefix = "A characterization or classification of"
    holds = (
        p["Definition"].startswith(prefix)
        and e["Definition"].startswith(prefix)
        and p["Has Value List"] == "N"
        and str(e["Has Value List"]).startswith("Y")
    )
    obs = (
        f"Procedure.procedureType ({p['NCI C-code']}): Has Value List {p['Has Value List']}. "
        f"Endpoint.level ({e['NCI C-code']}): Has Value List {e['Has Value List']}."
    )
    return holds, obs, [PINNED["USDM_CT.xlsx"]]


def population_summary_term_vs_definition(ctx):
    r = ctx["ct"][("Estimand", "populationSummary")]
    holds = (
        r["CT Item Preferred Name"] == "Population-Level Summary"
        and r["Definition"] == "A synopsis of the clinical endpoint of interest within the analysis target study population."
    )
    obs = f"{r['NCI C-code']} {r['CT Item Preferred Name']}: {r['Definition']} Has Value List {r['Has Value List']}."
    return holds, obs, [PINNED["USDM_CT.xlsx"]]


def intercurrent_event_strategy_textual(ctx):
    r = ctx["ct"][("IntercurrentEvent", "strategy")]
    holds = r["Definition"].startswith("A textual description") and r["Has Value List"] == "N"
    obs = f"{r['NCI C-code']} {r['CT Item Preferred Name']}: {r['Definition']} Has Value List {r['Has Value List']}."
    return holds, obs, [PINNED["USDM_CT.xlsx"]]


def narrative_references_by_markup(ctx):
    yml_text = (ROOT / "downloads" / "dataStructure.yml").read_text()
    in_yaml = "usdm:ref" in yml_text
    parts = []
    all_have = True
    for f in example_files():
        d = json.loads(f.read_text())
        items = [i for v in d["study"]["versions"] for i in v.get("narrativeContentItems", [])]
        klasses = Counter()
        for it in items:
            for m in re.finditer(r"<usdm:ref\s([^>]*)>", it["text"]):
                attrs = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
                klasses[attrs["klass"]] += 1
        total = sum(klasses.values())
        all_have = all_have and total > 0
        parts.append(f"{f.name}: {total} usdm:ref in {len(items)} narrative items, {len(klasses)} classes")
    holds = all_have and not in_yaml
    obs = "; ".join(parts) + f". dataStructure.yml mentions usdm:ref: {'yes' if in_yaml else 'no'}."
    return holds, obs, [PINNED["examples"], PINNED["dataStructure.yml"]]


def syntax_template_parameters_rarely_used(ctx):
    def walk(node, found):
        if isinstance(node, dict):
            if node.get("instanceType") in SYNTAX_TEMPLATE_TYPES:
                found.append(node)
            for v in node.values():
                walk(v, found)
        elif isinstance(node, list):
            for v in node:
                walk(v, found)

    parts = []
    total = with_dict = 0
    for f in example_files():
        found = []
        walk(json.loads(f.read_text()), found)
        n = len(found)
        k = sum(1 for x in found if x.get("dictionaryId"))
        total += n
        with_dict += k
        parts.append(f"{f.name}: {k} of {n}")
    holds = total > 0 and with_dict * 2 < total
    obs = f"Syntax-template instances with a dictionary: {with_dict} of {total}. Per example: " + "; ".join(parts) + "."
    return holds, obs, [PINNED["examples"]]


def instances(node, instance_type, found):
    if isinstance(node, dict):
        if node.get("instanceType") == instance_type:
            found.append(node)
        for v in node.values():
            instances(v, instance_type, found)
    elif isinstance(node, list):
        for v in node:
            instances(v, instance_type, found)
    return found


def timing_iso8601_convention(ctx):
    attrs = ("value", "windowLower", "windowUpper")
    counts = {a: [0, 0] for a in attrs}
    bad = []
    for f in example_files():
        for t in instances(json.loads(f.read_text()), "Timing", []):
            for a in attrs:
                v = t.get(a)
                if v in (None, ""):
                    continue
                counts[a][0] += 1
                if ISO_DURATION.match(v):
                    counts[a][1] += 1
                else:
                    bad.append(f"{f.name} {t['id']}.{a}={v}")
    in_yaml = "8601" in (ROOT / "downloads" / "dataStructure.yml").read_text()
    in_ct = any("8601" in str(r["Definition"]) for r in ctx["ct"].values())
    holds = not bad and all(n > 0 for n, _ in counts.values()) and not in_yaml and not in_ct
    obs = (
        "ISO 8601 durations among non-empty values: "
        + "; ".join(f"{a} {ok} of {n}" for a, (n, ok) in counts.items())
        + (". Not parsing: " + "; ".join(bad) if bad else "")
        + f". '8601' in dataStructure.yml: {'yes' if in_yaml else 'no'}; in USDM_CT.xlsx definitions: {'yes' if in_ct else 'no'}."
    )
    return holds, obs, [PINNED["examples"], PINNED["dataStructure.yml"], PINNED["USDM_CT.xlsx"]]


def parameter_reference_by_markup(ctx):
    total = markup = 0
    other = []
    for f in example_files():
        for m in instances(json.loads(f.read_text()), "ParameterMap", []):
            total += 1
            if m["reference"].startswith("<usdm:ref "):
                markup += 1
            else:
                other.append(f"{f.name} tag {m['tag']} = {m['reference']}")
    holds = total > 0 and markup * 2 > total
    obs = f"usdm:ref markup in {markup} of {total} ParameterMap.reference values." + (
        " Other values: " + "; ".join(other) + "." if other else ""
    )
    return holds, obs, [PINNED["examples"]]


def bc_property_datatype_names(ctx):
    names = Counter()
    empty = total = 0
    for f in example_files():
        for p in instances(json.loads(f.read_text()), "BiomedicalConceptProperty", []):
            total += 1
            v = p.get("datatype")
            if v in (None, ""):
                empty += 1
            else:
                names[v] += 1
    row = ctx["ct"][("BiomedicalConceptProperty", "datatype")]
    holds = "text" in names and "string" in names and row["Has Value List"] == "N"
    obs = (
        f"{total} BiomedicalConceptProperty instances, {empty} with empty datatype. Names used: "
        + ", ".join(f"{n} {c}" for n, c in names.most_common())
        + f". USDM_CT.xlsx Has Value List: {row['Has Value List']}."
    )
    return holds, obs, [PINNED["examples"], PINNED["USDM_CT.xlsx"]]


CHECKS = {
    "abstract_class_attribute_ccodes": abstract_class_attribute_ccodes,
    "procedure_type_uncoded": procedure_type_uncoded,
    "population_summary_term_vs_definition": population_summary_term_vs_definition,
    "intercurrent_event_strategy_textual": intercurrent_event_strategy_textual,
    "narrative_references_by_markup": narrative_references_by_markup,
    "syntax_template_parameters_rarely_used": syntax_template_parameters_rarely_used,
    "timing_iso8601_convention": timing_iso8601_convention,
    "parameter_reference_by_markup": parameter_reference_by_markup,
    "bc_property_datatype_names": bc_property_datatype_names,
}


def main():
    ctx = {"usdm": load_usdm(), "ct": load_ct(), "yaml": load_yaml()}
    findings_graph = Graph().parse(ROOT / "authored" / "findings.ttl")
    vocab = Graph().parse(ROOT / "usdm_overlay.ttl")

    out = Graph()
    out.bind("uo", UO)
    rows = []
    failed = []
    for f in sorted(findings_graph.subjects(RDF.type, UO.Finding), key=str):
        query = findings_graph.value(f, UO.testQuery)
        if query is not None:
            expected = findings_graph.value(f, UO.expectedResult).toPython()
            result = ctx["usdm"].query(str(query)).askAnswer
            holds = result == expected
            obs = f"ASK returned {str(result).lower()}, expected {str(expected).lower()}."
            against = [PINNED["usdm_v4.ttl"]]
        else:
            name = str(findings_graph.value(f, UO.checkFunction))
            if name not in CHECKS:
                raise RuntimeError(f"{local(f)}: unknown check function {name}")
            holds, obs, against = CHECKS[name](ctx)
        out.add((f, UO.holds, Literal(holds, datatype=XSD.boolean)))
        out.add((f, UO.observation, Literal(obs)))
        for a in against:
            out.add((f, UO.testedAgainst, a))
        if not holds:
            failed.append(local(f))
        tier = vocab.value(findings_graph.value(f, UO.evidenceTier), SKOS.prefLabel)
        rows.append((local(f), str(findings_graph.value(f, DCTERMS.title)), str(tier), holds,
                     str(findings_graph.value(f, UO.statement)), obs))

    (ROOT / "derived").mkdir(exist_ok=True)
    header = "# Derived by scripts/check_findings.py from the pinned inputs. Do not edit by hand.\n"
    (ROOT / "derived" / "finding_results.ttl").write_text(header + out.serialize(format="turtle"))

    lines = [
        "# Findings",
        "",
        "Generated by `scripts/check_findings.py` from the pinned inputs. Do not edit by hand.",
        "Statements are in `authored/findings.ttl`; this report adds what each test observed.",
        "",
        "| Finding | Evidence tier | Holds |",
        "| --- | --- | --- |",
    ]
    for fid, title, tier, holds, _, _ in rows:
        lines.append(f"| [{title}](#{fid}) | {tier} | {'yes' if holds else 'NO'} |")
    for fid, title, tier, holds, statement, obs in rows:
        lines += ["", f"## {title}", "", f'<a id="{fid}"></a>`{fid}` · {tier}', "", statement, "", f"**Observed:** {obs}"]
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "findings.md").write_text("\n".join(lines) + "\n")

    if failed:
        print("Findings that do not hold: " + ", ".join(failed))
        sys.exit(1)
    print(f"OK: all {len(rows)} findings hold")


if __name__ == "__main__":
    main()

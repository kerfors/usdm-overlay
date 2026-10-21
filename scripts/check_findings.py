"""Run the test of every finding in authored/findings.ttl against the pinned inputs.

Output: derived/finding_results.ttl
        reports/findings.md
Exits with status 1 if any finding does not hold.
"""
import json
import re
import sys
from collections import Counter, defaultdict

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import DCTERMS, RDF, RDFS, SKOS, XSD

from common import NCIT, ROOT, UO, USDM, example_files, load_ct, load_m11, load_usdm, load_yaml, local

PINNED = {
    "usdm_v4.ttl": URIRef("https://raw.githubusercontent.com/kerfors/usdm-rdf/v0.7.0/usdm_v4.ttl"),
    "USDM_CT.xlsx": URIRef("https://github.com/cdisc-org/DDF-RA/blob/v4.0.0/Deliverables/CT/USDM_CT.xlsx"),
    "dataStructure.yml": URIRef("https://github.com/cdisc-org/DDF-RA/blob/v4.0.0/Deliverables/UML/dataStructure.yml"),
    "examples": URIRef("https://github.com/cdisc-org/DDF-RA/tree/v4.0.0/Documents/Examples"),
    "m11-rdf.ttl": URIRef("https://raw.githubusercontent.com/kerfors/m11-rdf/v0.3.0/m11-rdf.ttl"),
}

# The pinned graphs a SPARQL test can run against, keyed by the IRI a finding
# names in dcterms:source: (context key, pinned file).
QUERY_GRAPHS = {
    URIRef("https://github.com/kerfors/usdm-rdf/blob/v0.7.0/usdm_v4.ttl"): ("usdm", "usdm_v4.ttl"),
    URIRef("https://github.com/kerfors/m11-rdf/blob/v0.3.0/m11-rdf.ttl"): ("m11", "m11-rdf.ttl"),
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


def study_amendment_number_not_numerals(ctx):
    row = ctx["ct"][("StudyAmendment", "number")]
    values = []
    for f in example_files():
        for a in instances(json.loads(f.read_text()), "StudyAmendment", []):
            values.append((f.name, a["number"]))
    non_numeral = [(f, v) for f, v in values if not v.isdigit()]
    holds = row["Definition"].startswith("A string of numerals") and bool(non_numeral)
    obs = f"{len(values)} StudyAmendment.number values; not all digits: " + "; ".join(f"{f} '{v}'" for f, v in non_numeral) + "."
    return holds, obs, [PINNED["examples"], PINNED["USDM_CT.xlsx"]]


def eligibility_identifier_needs_category(ctx):
    parts = []
    restart = 0
    within = 0
    for f in example_files():
        d = json.loads(f.read_text())
        designs = instances(d, "InterventionalStudyDesign", []) + instances(d, "ObservationalStudyDesign", [])
        for sd in designs:
            ecs = sd.get("eligibilityCriteria", [])
            by_id = Counter(e["identifier"] for e in ecs)
            by_id_cat = Counter((e["identifier"], e["category"]["code"]) for e in ecs)
            dup = sum(1 for n in by_id.values() if n > 1)
            dup_cat = sum(1 for n in by_id_cat.values() if n > 1)
            if dup:
                restart += 1
            within += dup_cat
            parts.append(f"{f.name} {sd['id']}: {len(ecs)} criteria, {dup} identifiers repeated, {dup_cat} repeated within a category")
    holds = restart > 0 and within == 0
    obs = "; ".join(parts) + "."
    return holds, obs, [PINNED["examples"]]


def template_tags_by_markup(ctx):
    tag_re = re.compile(r'<usdm:tag\s+name="([^"]*)"\s*/?>')
    texts = 0
    used = 0
    unresolved = []
    stored_with_bracket = 0

    def walk(node, out):
        if isinstance(node, dict):
            if isinstance(node.get("text"), str) and "usdm:tag" in node["text"]:
                out.append(node)
            for v in node.values():
                walk(v, out)
        elif isinstance(node, list):
            for v in node:
                walk(v, out)

    for f in example_files():
        d = json.loads(f.read_text())
        dictionaries = {}
        for x in instances(d, "SyntaxTemplateDictionary", []):
            tags = {m["tag"] for m in x["parameterMaps"]}
            stored_with_bracket += sum(1 for t in tags if "<" in t or ">" in t)
            dictionaries[x["id"]] = tags
        nodes = []
        walk(d, nodes)
        for n in nodes:
            texts += 1
            known = dictionaries.get(n.get("dictionaryId"), set())
            for t in tag_re.findall(n["text"]):
                used += 1
                if t not in known:
                    unresolved.append(f"{f.name} {n['id']} '{t}'")
    row = ctx["ct"][("ParameterMap", "tag")]
    holds = (
        used > 0
        and stored_with_bracket == 0
        and "angle brackets" in row["Definition"]
        and bool(unresolved)
    )
    obs = (
        f"{used} usdm:tag elements in {texts} texts; stored tags containing angle brackets: {stored_with_bracket}. "
        f"Unresolved: " + "; ".join(unresolved) + "."
    )
    return holds, obs, [PINNED["examples"], PINNED["USDM_CT.xlsx"]]


def timing_labels_restate_values(ctx):
    labels = defaultdict(set)
    for f in example_files():
        for t in instances(json.loads(f.read_text()), "Timing", []):
            labels[t["value"]].add(t["valueLabel"])
    multi = {v: sorted(ls) for v, ls in labels.items() if len(ls) > 1}
    holds = bool(multi)
    obs = (
        f"{len(labels)} distinct Timing.value values; {len(multi)} carry more than one valueLabel: "
        + "; ".join(f"{v}: " + ", ".join(f"'{l}'" for l in ls) for v, ls in sorted(multi.items()))
        + "."
    )
    return holds, obs, [PINNED["examples"]]


def code_system_free_strings(ctx):
    pairs = Counter()
    for f in example_files():
        for c in instances(json.loads(f.read_text()), "Code", []):
            pairs[(c["codeSystem"], c["codeSystemVersion"])] += 1
    systems = Counter()
    for (system, _), n in pairs.items():
        systems[system] += n
    url_like = [x for x in systems if x.startswith("http")]
    named = [x for x in systems if not x.startswith("http")]
    versions = {v for _, v in pairs}
    holds = bool(url_like) and bool(named) and len(versions) > 1
    obs = (
        f"{sum(pairs.values())} Code instances. codeSystem / codeSystemVersion pairs: "
        + "; ".join(f"'{s_}' / '{v}' {n}" for (s_, v), n in pairs.most_common())
        + "."
    )
    return holds, obs, [PINNED["examples"]]


def bc_reference_library_paths(ctx):
    refs = Counter()
    for f in example_files():
        for b in instances(json.loads(f.read_text()), "BiomedicalConcept", []):
            refs[b["reference"]] += 1
    dss = [r for r in refs if r.startswith("/mdr/specializations/sdtm/packages/") and "/datasetspecializations/" in r]
    bc = [r for r in refs if r.startswith("/mdr/bc/packages/") and "/biomedicalconcepts/" in r]
    others = [r for r in refs if r not in dss and r not in bc]
    holds = bool(dss) and bool(bc) and not others
    obs = (
        f"{sum(refs.values())} BiomedicalConcept instances, {len(refs)} distinct references: "
        f"{len(dss)} of the form /mdr/specializations/sdtm/packages/<date>/datasetspecializations/<name>, "
        f"{len(bc)} of the form /mdr/bc/packages/<date>/biomedicalconcepts/<C-code>."
        + (" Others: " + "; ".join(others) + "." if others else "")
    )
    return holds, obs, [PINNED["examples"]]


def extension_attributes_undefined(ctx):
    ct, usdm = ctx["ct"], ctx["usdm"]
    classes = ("ExtensionAttribute", "ExtensionClass")
    ct_rows = [k for k in ct if k[0] in classes]
    props = [p for p in usdm.subjects(RDFS.domain, None) if local(usdm.value(p, RDFS.domain)) in classes]
    defined = [local(p) for p in props if usdm.value(p, SKOS.definition) is not None]
    used = 0
    for f in example_files():
        d = json.loads(f.read_text())
        used += sum(len(instances(d, c, [])) for c in classes)
    holds = not ct_rows and not defined and used == 0 and bool(props)
    obs = (
        f"USDM_CT.xlsx rows for these classes: {len(ct_rows)}. usdm-rdf properties: {len(props)}, "
        f"with skos:definition: {len(defined)}. Instances in the published examples: {used}."
    )
    return holds, obs, [PINNED["USDM_CT.xlsx"], PINNED["usdm_v4.ttl"], PINNED["examples"]]


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
    "study_amendment_number_not_numerals": study_amendment_number_not_numerals,
    "eligibility_identifier_needs_category": eligibility_identifier_needs_category,
    "template_tags_by_markup": template_tags_by_markup,
    "timing_labels_restate_values": timing_labels_restate_values,
    "code_system_free_strings": code_system_free_strings,
    "bc_reference_library_paths": bc_reference_library_paths,
    "extension_attributes_undefined": extension_attributes_undefined,
}


def main():
    ctx = {"usdm": load_usdm(), "m11": load_m11(), "ct": load_ct(), "yaml": load_yaml()}
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
            named = sorted({QUERY_GRAPHS[s] for s in findings_graph.objects(f, DCTERMS.source) if s in QUERY_GRAPHS})
            if not named:
                raise RuntimeError(f"{local(f)}: a test query needs a pinned graph in dcterms:source")
            if len(named) == 1:
                graph = ctx[named[0][0]]
            else:
                graph = Graph()
                for key, _ in named:
                    graph += ctx[key]
            result = graph.query(str(query)).askAnswer
            holds = result == expected
            obs = f"ASK returned {str(result).lower()}, expected {str(expected).lower()}."
            against = [PINNED[name] for _, name in named]
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
        standing = findings_graph.value(f, UO.standing)
        rows.append((local(f), str(findings_graph.value(f, DCTERMS.title)), str(tier), holds,
                     str(findings_graph.value(f, UO.statement)), obs,
                     standing, str(findings_graph.value(f, UO.standingRationale))))

    (ROOT / "derived").mkdir(exist_ok=True)
    header = "# Derived by scripts/check_findings.py from the pinned inputs. Do not edit by hand.\n"
    (ROOT / "derived" / "finding_results.ttl").write_text(header + out.serialize(format="turtle"))

    lines = [
        "# Findings",
        "",
        "Generated by `scripts/check_findings.py` from the pinned inputs. Do not edit by hand.",
        "Statements are in `authored/findings.ttl`; this report adds what each test observed.",
        "",
    ]
    standings = [UO.ReadyToRaise, UO.ForDiscussion]
    for standing in standings:
        group = [r for r in rows if r[6] == standing]
        lines += [
            "",
            f"## {vocab.value(standing, SKOS.prefLabel)} ({len(group)})",
            "",
            str(vocab.value(standing, SKOS.definition)),
            "",
            "| Finding | Evidence tier | Holds | Why this standing |",
            "| --- | --- | --- | --- |",
        ]
        for fid, title, tier, holds, _, _, _, why in group:
            lines.append(f"| [{title}](#{fid}) | {tier} | {'yes' if holds else 'NO'} | {why} |")
    for standing in standings:
        for fid, title, tier, holds, statement, obs, st, why in rows:
            if st != standing:
                continue
            label = vocab.value(st, SKOS.prefLabel)
            lines += ["", f"### {title}", "", f'<a id="{fid}"></a>`{fid}` · {tier} · {label}', "", statement, "",
                      f"**Observed:** {obs}"]
    unplaced = [r[0] for r in rows if r[6] not in standings]
    if unplaced:
        raise RuntimeError(f"Findings without a known standing: {unplaced}")
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "findings.md").write_text("\n".join(lines) + "\n")

    if failed:
        print("Findings that do not hold: " + ", ".join(failed))
        sys.exit(1)
    print(f"OK: all {len(rows)} findings hold")


if __name__ == "__main__":
    main()

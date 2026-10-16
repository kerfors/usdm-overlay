"""Derive the content kind of every usdm-rdf property.

Input:  downloads/usdm_v4.ttl (pinned, see downloads/MANIFEST.md)
        usdm_overlay.ttl (vocabulary and rules)
Output: derived/content_kind.ttl
        reports/content_kind.md

Every property gets exactly one kind from the first matching rule. A property
that matches no rule stops the build.
"""
from collections import defaultdict
from pathlib import Path

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.collection import Collection
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SKOS, XSD

ROOT = Path(__file__).resolve().parent.parent
USDM = Namespace("https://w3id.org/cdisc/usdm/v4/")
UO = Namespace("https://kerfors.github.io/usdm-overlay/")
SOURCE = URIRef("https://github.com/kerfors/usdm-rdf/blob/v0.7.1/usdm_v4.ttl")

NAMING = {"name", "label", "description"}
CODE_RANGES = {USDM.Code, USDM.AliasCode}

# (rule local name, kind local name, evidence tier local name), in rule order.
RULES = [
    ("rule-identity", "Identity", "ModelStated"),
    ("rule-type-discriminator", "TypeDiscriminator", "ModelStated"),
    ("rule-extension-point", "ExtensionPoint", "ModelStated"),
    ("rule-naming", "Naming", "ModelStated"),
    ("rule-reference", "Reference", "ModelStated"),
    ("rule-coded", "Coded", "ModelStated"),
    ("rule-typed-value", "TypedValue", "ModelStated"),
    ("rule-composition", "Composition", "ModelStated"),
    ("rule-unstructured-text", "UnstructuredText", "DefinitionStated"),
    ("rule-structured-text", "StructuredText", "DefinitionStated"),
    ("rule-narrative-text", "NarrativeText", "DefinitionStated"),
    ("rule-unclassified-string", "UnclassifiedString", "ModelStated"),
]


def check_rules_match_vocabulary(vocab):
    declared = sorted(
        (int(vocab.value(r, UO.order)), str(r).split("/")[-1])
        for r in vocab.subjects(RDF.type, UO.Rule)
    )
    in_code = [(i + 1, rule) for i, (rule, _, _) in enumerate(RULES)]
    if declared != in_code:
        raise RuntimeError(f"Rule order differs between usdm_overlay.ttl and this script:\n{declared}\n{in_code}")


def first_rule(g, prop):
    local = str(prop).split("/")[-1]
    rel = g.value(prop, USDM.relationshipType)
    rng = g.value(prop, RDFS.range)
    definition = g.value(prop, SKOS.definition)
    text = str(definition).lower() if definition is not None else ""
    if rng is None:
        raise RuntimeError(f"No range on {local}")
    if rel is None:
        raise RuntimeError(f"No relationship type on {local}")
    is_string = rng == XSD.string

    attr = local.split("-", 1)[1]
    if attr == "id":
        return "rule-identity", None
    if local.endswith("-instanceType"):
        return "rule-type-discriminator", None
    if local.endswith("-extensionAttributes"):
        return "rule-extension-point", None
    if attr in NAMING:
        return "rule-naming", None
    if str(rel) == "Ref":
        return "rule-reference", None
    if rng in CODE_RANGES:
        return "rule-coded", None
    if str(rng).startswith(str(XSD)) and not is_string:
        return "rule-typed-value", None
    if (prop, RDF.type, OWL.ObjectProperty) in g and str(rel) == "Value":
        return "rule-composition", None
    if is_string and "unstructured text" in text:
        return "rule-unstructured-text", str(definition)
    if is_string and "structured text" in text:
        return "rule-structured-text", str(definition)
    if is_string and "narrative representation" in text:
        return "rule-narrative-text", str(definition)
    if is_string:
        return "rule-unclassified-string", None
    raise RuntimeError(f"No rule matches {local} (range {rng}, relationship {rel})")


def main():
    g = Graph().parse(ROOT / "downloads" / "usdm_v4.ttl")
    vocab = Graph().parse(ROOT / "usdm_overlay.ttl")
    check_rules_match_vocabulary(vocab)
    rule_table = {rule: (kind, tier) for rule, kind, tier in RULES}

    props = sorted(
        set(g.subjects(RDF.type, OWL.DatatypeProperty)) | set(g.subjects(RDF.type, OWL.ObjectProperty)),
        key=str,
    )
    props = [p for p in props if str(p).startswith(str(USDM)) and g.value(p, RDFS.domain) is not None]

    out = Graph()
    out.bind("uo", UO)
    out.bind("usdm", USDM)
    out.bind("dcterms", DCTERMS)
    by_kind = defaultdict(list)
    for prop in props:
        rule, quote = first_rule(g, prop)
        kind, tier = rule_table[rule]
        local = str(prop).split("/")[-1]
        a = UO[f"id/assessment/contentKind/{local}"]
        out.add((prop, UO.contentKind, UO[kind]))
        out.add((a, RDF.type, UO.Assessment))
        out.add((a, UO.about, prop))
        out.add((a, UO.assignedKind, UO[kind]))
        out.add((a, UO.evidenceTier, UO[tier]))
        out.add((a, UO.byRule, UO[rule]))
        out.add((a, DCTERMS.source, SOURCE))
        if quote is not None:
            out.add((a, UO.quote, Literal(quote)))
        domain = str(g.value(prop, RDFS.domain)).split("/")[-1]
        rng = g.value(prop, RDFS.range)
        if isinstance(rng, BNode):
            members = Collection(g, g.value(rng, OWL.unionOf))
            rng_local = " or ".join(sorted(str(m).split("/")[-1] for m in members))
        else:
            rng_local = str(rng).split("/")[-1].split("#")[-1]
        by_kind[kind].append((domain, local.split("-", 1)[1], rng_local, quote))

    (ROOT / "derived").mkdir(exist_ok=True)
    header = (
        "# Derived by scripts/build_content_kind.py from downloads/usdm_v4.ttl (usdm-rdf v0.7.1).\n"
        "# Do not edit by hand.\n"
    )
    (ROOT / "derived" / "content_kind.ttl").write_text(header + out.serialize(format="turtle"))

    order = [kind for _, kind, _ in RULES]
    lines = [
        "# Content kind of every usdm-rdf property",
        "",
        "Generated by `scripts/build_content_kind.py` from usdm-rdf v0.7.1. Do not edit by hand.",
        "",
        f"{len(props)} properties classified.",
        "",
        "| Content kind | Properties |",
        "| --- | ---: |",
    ]
    for kind in order:
        lines.append(f"| {kind} | {len(by_kind[kind])} |")
    for kind in order:
        if kind in ("Identity", "TypeDiscriminator", "ExtensionPoint"):
            continue
        lines += ["", f"## {kind}", ""]
        if kind in ("UnstructuredText", "StructuredText", "NarrativeText"):
            lines += ["| Class | Attribute | Definition (quoted) |", "| --- | --- | --- |"]
            for domain, attr, _, quote in sorted(by_kind[kind]):
                lines.append(f"| {domain} | {attr} | {quote} |")
        else:
            lines += ["| Class | Attribute | Range |", "| --- | --- | --- |"]
            for domain, attr, rng, _ in sorted(by_kind[kind]):
                lines.append(f"| {domain} | {attr} | {rng} |")
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "content_kind.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()

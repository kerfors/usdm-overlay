"""Derive the role of every usdm-rdf class from the content kinds of its attributes.

Input:  downloads/usdm_v4.ttl (pinned, see downloads/MANIFEST.md)
        usdm_overlay.ttl (vocabulary, text groups and rules)
        derived/content_kind.ttl, authored/content_kind.ttl (layer 1)
Output: derived/class_role.ttl
        reports/class_role.md

Attributes are counted on the class and its superclasses. Where an attribute
has an authored content kind, that kind is used; otherwise the derived one.
Every class gets exactly one role from the first matching rule.
"""
from collections import defaultdict
from pathlib import Path

from rdflib import Graph, Literal, URIRef
from rdflib.collection import Collection
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SKOS, XSD

from common import ROOT, UO, USDM, load_usdm, local

SOURCE = URIRef("https://github.com/kerfors/usdm-rdf/blob/v0.7.0/usdm_v4.ttl")

# (rule local name, role local name), in rule order.
RULES = [
    ("rule-role-extension", "ExtensionRole"),
    ("rule-role-templated-text", "TemplatedText"),
    ("rule-role-value-type", "ValueType"),
    ("rule-role-aggregate", "Aggregate"),
    ("rule-role-text-carrier", "TextCarrier"),
    ("rule-role-structured-entity", "StructuredEntity"),
    ("rule-role-unassigned", "UnassignedRole"),
]

COUNTS = ["read", "structure", "value", "reference", "part"]
COUNT_PROPS = {
    "read": UO.readTextCount,
    "structure": UO.stringStructureCount,
    "value": UO.valueCount,
    "reference": UO.referenceCount,
    "part": UO.partCount,
}


def check_rules_match_vocabulary(vocab):
    declared = sorted(
        (int(vocab.value(r, UO.order)), local(r))
        for r in vocab.subjects(RDF.type, UO.ClassRoleRule)
    )
    in_code = [(i + 1, rule) for i, (rule, _) in enumerate(RULES)]
    if declared != in_code:
        raise RuntimeError(f"Rule order differs between usdm_overlay.ttl and this script:\n{declared}\n{in_code}")


def top_kind(vocab, kind):
    while True:
        broader = vocab.value(kind, SKOS.broader)
        if broader is None:
            return kind
        kind = broader


def range_members(g, prop):
    rng = g.value(prop, RDFS.range)
    union = g.value(rng, OWL.unionOf)
    if union is not None:
        return list(Collection(g, union))
    return [rng]


def main():
    g = load_usdm()
    vocab = Graph().parse(ROOT / "usdm_overlay.ttl")
    check_rules_match_vocabulary(vocab)
    derived = Graph().parse(ROOT / "derived" / "content_kind.ttl")
    authored = Graph().parse(ROOT / "authored" / "content_kind.ttl")

    kind = dict(derived.subject_objects(UO.contentKind))
    if len(kind) != len(set(derived.subjects(UO.contentKind))):
        raise RuntimeError("A property has more than one derived content kind")
    for prop, k in authored.subject_objects(UO.contentKind):
        if prop not in kind:
            raise RuntimeError(f"Authored kind for {local(prop)}, which has no derived kind")
        kind[prop] = k

    read_kinds = set(vocab.objects(UO.ReadText, SKOS.member))
    structure_kinds = set(vocab.objects(UO.StructureInString, SKOS.member))

    classes = sorted(
        (c for c in g.subjects(RDF.type, OWL.Class) if str(c).startswith(str(USDM))),
        key=str,
    )
    class_set = set(classes)
    abstract = {c for c in classes if str(g.value(c, USDM.modifier)) == "Abstract"}
    supers = {c: [s for s in g.objects(c, RDFS.subClassOf) if s in class_set] for c in classes}

    def ancestors(c):
        out = []
        for s in supers[c]:
            out += [s] + ancestors(s)
        return out

    subclasses = {c: [s for s in classes if c in supers[s]] for c in classes}

    own = defaultdict(list)
    for prop in kind:
        domain = g.value(prop, RDFS.domain)
        if domain not in class_set:
            raise RuntimeError(f"Domain of {local(prop)} is not a usdm-rdf class")
        own[domain].append(prop)

    def effective(c):
        return own[c] + [p for s in ancestors(c) for p in own[s]]

    referenced = set()
    composers = defaultdict(set)
    extension_ranges = set()
    for prop in kind:
        rel = str(g.value(prop, USDM.relationshipType))
        domain = g.value(prop, RDFS.domain)
        for target in range_members(g, prop):
            if target not in class_set:
                continue
            reached = {target} | {s for s in classes if target in ancestors(s)}
            if rel == "Ref":
                referenced |= reached
            elif rel == "Value":
                for r in reached:
                    composers[r].add(domain)
            if kind[prop] == UO.ExtensionPoint:
                extension_ranges.add(target)

    # Rule 1: extension classes, until no more match.
    extension = set(extension_ranges)
    while True:
        more = {c for c in classes if c not in extension and composers[c] and composers[c] <= extension}
        if not more:
            break
        extension |= more

    def is_notes(prop):
        return local(prop).split("-", 1)[1] == "notes"

    def profile(c, value_types):
        counts = dict.fromkeys(COUNTS, 0)
        naming = False
        dictionary_ref = False
        for prop in effective(c):
            k = kind[prop]
            if top_kind(vocab, k) == UO.Housekeeping:
                continue
            if k == UO.Naming:
                naming = True
            elif k == UO.Composition and is_notes(prop):
                continue
            elif k in read_kinds:
                counts["read"] += 1
            elif k in structure_kinds:
                counts["structure"] += 1
            elif k in (UO.Coded, UO.TypedValue):
                counts["value"] += 1
            elif k == UO.Reference:
                counts["reference"] += 1
                if USDM.SyntaxTemplateDictionary in range_members(g, prop):
                    dictionary_ref = True
            elif k == UO.Composition:
                if all(t in value_types for t in range_members(g, prop)):
                    counts["value"] += 1
                else:
                    counts["part"] += 1
            else:
                raise RuntimeError(f"Content kind {local(k)} of {local(prop)} is not handled by the roll-up")
        return counts, naming, dictionary_ref

    # Rule 3: value types, until no more match.
    value_types = set()
    while True:
        more = set()
        for c in classes:
            if c in extension or c in value_types:
                continue
            counts, naming, dictionary_ref = profile(c, value_types)
            if dictionary_ref and counts["read"] > 0:
                continue
            if (
                not naming
                and c not in referenced
                and counts["reference"] == 0
                and counts["part"] == 0
                and counts["read"] == 0
                and counts["value"] + counts["structure"] > 0
            ):
                more.add(c)
            elif c in abstract and subclasses[c] and all(s in value_types for s in subclasses[c]):
                more.add(c)
        if not more:
            break
        value_types |= more

    out = Graph()
    out.bind("uo", UO)
    out.bind("usdm", USDM)
    out.bind("dcterms", DCTERMS)
    rows = []
    for c in classes:
        counts, naming, dictionary_ref = profile(c, value_types)
        others = sum(counts.values())
        if c in extension:
            rule = "rule-role-extension"
        elif dictionary_ref and counts["read"] > 0:
            rule = "rule-role-templated-text"
        elif c in value_types:
            rule = "rule-role-value-type"
        elif counts["part"] >= 2 and counts["part"] > others - counts["part"]:
            rule = "rule-role-aggregate"
        elif counts["read"] >= 1 and counts["read"] >= others - counts["read"]:
            rule = "rule-role-text-carrier"
        elif others > 0:
            rule = "rule-role-structured-entity"
        else:
            rule = "rule-role-unassigned"
        role = dict(RULES)[rule]

        a = UO[f"id/assessment/classRole/{local(c)}"]
        out.add((c, UO.classRole, UO[role]))
        out.add((a, RDF.type, UO.Assessment))
        out.add((a, UO.about, c))
        out.add((a, UO.assignedKind, UO[role]))
        out.add((a, UO.evidenceTier, UO.ModelStated))
        out.add((a, UO.byRule, UO[rule]))
        out.add((a, DCTERMS.source, SOURCE))
        out.add((a, UO.hasNaming, Literal(naming)))
        out.add((a, UO.isReferenced, Literal(c in referenced)))
        out.add((a, UO.composedInCount, Literal(len(composers[c]), datatype=XSD.integer)))
        for name in COUNTS:
            out.add((a, COUNT_PROPS[name], Literal(counts[name], datatype=XSD.integer)))
        rows.append((role, local(c), c in abstract, ", ".join(local(s) for s in supers[c]),
                     naming, c in referenced, len(composers[c]), counts))

    (ROOT / "derived").mkdir(exist_ok=True)
    header = (
        "# Derived by scripts/build_class_role.py from downloads/usdm_v4.ttl (usdm-rdf v0.7.0)\n"
        "# and the layer 1 content kinds. Do not edit by hand.\n"
    )
    (ROOT / "derived" / "class_role.ttl").write_text(header + out.serialize(format="turtle"))

    order = [role for _, role in RULES]
    by_role = defaultdict(list)
    for row in rows:
        by_role[row[0]].append(row)
    lines = [
        "# Role of every usdm-rdf class",
        "",
        "Generated by `scripts/build_class_role.py` from usdm-rdf v0.7.0 and the layer 1 content kinds. Do not edit by hand.",
        "",
        f"{len(rows)} classes classified. Attributes are counted on the class and its superclasses; "
        "payload excludes housekeeping, naming and notes.",
        "",
        "| Role | Classes |",
        "| --- | ---: |",
    ]
    for role in order:
        lines.append(f"| {role} | {len(by_role[role])} |")
    for role in order:
        if not by_role[role]:
            continue
        lines += [
            "",
            f"## {role}",
            "",
            "| Class | Abstract | Superclass | Naming | Referenced | Composed in | Read text | String structure | Value | Reference | Part |",
            "| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for _, name, is_abstract, sup, naming, ref, comp, counts in sorted(by_role[role], key=lambda r: r[1]):
            lines.append(
                f"| {name} | {'yes' if is_abstract else ''} | {sup} | {'yes' if naming else ''} | "
                f"{'yes' if ref else ''} | {comp} | " + " | ".join(str(counts[n]) for n in COUNTS) + " |"
            )
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "class_role.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()

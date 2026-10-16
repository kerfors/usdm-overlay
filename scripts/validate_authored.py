"""Validate the hand-maintained graphs in authored/ against the vocabulary and the pinned inputs.

Stops at the first problem.
"""
from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS

from common import ROOT, UO, USDM, load_ct, load_usdm, local


def one(g, s, p):
    values = list(g.objects(s, p))
    if len(values) != 1:
        raise RuntimeError(f"{local(s)}: expected exactly one {local(p)}, found {len(values)}")
    return values[0]


def check_class_role(a, about, authored, roles, derived_roles, ct):
    kind = one(authored, a, UO.assignedKind)
    if kind not in roles:
        raise RuntimeError(f"{local(a)}: {kind} is not in the class-role scheme")
    if one(authored, a, UO.evidenceTier) != UO.Authored:
        raise RuntimeError(f"{local(a)}: evidence tier must be Authored")
    if not str(one(authored, a, UO.rationale)).strip():
        raise RuntimeError(f"{local(a)}: empty rationale")
    refined = one(authored, a, UO.refines)
    if (refined, RDF.type, UO.Assessment) not in derived_roles or derived_roles.value(refined, UO.about) != about:
        raise RuntimeError(f"{local(a)}: refines {refined}, which is not the derived class-role assessment of {local(about)}")
    if derived_roles.value(refined, UO.assignedKind) == kind:
        raise RuntimeError(f"{local(a)}: assigns the same role as the derived assessment")
    if (about, UO.classRole, kind) not in authored:
        raise RuntimeError(f"{local(a)}: missing shortcut triple {local(about)} uo:classRole {local(kind)}")
    for p in (UO.companionOf, UO.labelOf, UO.syntax):
        if (a, p, None) in authored:
            raise RuntimeError(f"{local(a)}: {local(p)} not allowed on a class-role assessment")
    ct_row = ct.get((local(about), local(about)))
    quotes = list(authored.objects(a, UO.quote))
    if quotes and (ct_row is None or ct_row["Role"] != "Entity"):
        raise RuntimeError(f"{local(a)}: quotes given but no USDM_CT.xlsx entity row for {local(about)}")
    for q in quotes:
        if str(q) not in str(ct_row["Definition"]):
            raise RuntimeError(f"{local(a)}: quote not verbatim in USDM_CT.xlsx definition: {q}")


def main():
    usdm = load_usdm()
    ct = load_ct()
    vocab = Graph().parse(ROOT / "usdm_overlay.ttl")
    derived = Graph().parse(ROOT / "derived" / "content_kind.ttl")
    derived_roles = Graph().parse(ROOT / "derived" / "class_role.ttl")
    roles = set(vocab.subjects(SKOS.inScheme, UO.ClassRoleScheme))
    authored = Graph()
    for f in sorted((ROOT / "authored").glob("*.ttl")):
        authored.parse(f)

    kinds = set(vocab.subjects(SKOS.inScheme, UO.ContentKindScheme))

    text_kinds = set(vocab.transitive_subjects(SKOS.broader, UO.Text)) - {UO.Text}
    for k in sorted(text_kinds, key=str):
        groups = [c for c in (UO.ReadText, UO.StructureInString) if (c, SKOS.member, k) in vocab]
        if len(groups) != 1:
            raise RuntimeError(f"{local(k)}: must be a member of exactly one of ReadText, StructureInString, found {len(groups)}")
    for c in (UO.ReadText, UO.StructureInString):
        for k in vocab.objects(c, SKOS.member):
            if k not in text_kinds:
                raise RuntimeError(f"{local(c)} has member {local(k)}, which is not a narrower kind of Text")
    usdm_props = set(usdm.subjects(RDF.type, OWL.DatatypeProperty)) | set(usdm.subjects(RDF.type, OWL.ObjectProperty))
    usdm_classes = set(usdm.subjects(RDF.type, OWL.Class))

    seen = set()
    assessments = sorted(authored.subjects(RDF.type, UO.Assessment), key=str)
    for a in assessments:
        about = one(authored, a, UO.about)
        if about in usdm_classes:
            if about in seen:
                raise RuntimeError(f"{local(a)}: second authored assessment for {local(about)}")
            seen.add(about)
            check_class_role(a, about, authored, roles, derived_roles, ct)
            continue
        if about not in usdm_props:
            raise RuntimeError(f"{local(a)}: {about} is not a usdm-rdf property")
        if about in seen:
            raise RuntimeError(f"{local(a)}: second authored assessment for {local(about)}")
        seen.add(about)
        kind = one(authored, a, UO.assignedKind)
        if kind not in kinds:
            raise RuntimeError(f"{local(a)}: {kind} is not in the content-kind scheme")
        if one(authored, a, UO.evidenceTier) != UO.Authored:
            raise RuntimeError(f"{local(a)}: evidence tier must be Authored")
        if not str(one(authored, a, UO.rationale)).strip():
            raise RuntimeError(f"{local(a)}: empty rationale")
        refined = one(authored, a, UO.refines)
        if (refined, RDF.type, UO.Assessment) not in derived or derived.value(refined, UO.about) != about:
            raise RuntimeError(f"{local(a)}: refines {refined}, which is not the derived assessment of {local(about)}")
        if (about, UO.contentKind, kind) not in authored:
            raise RuntimeError(f"{local(a)}: missing shortcut triple {local(about)} uo:contentKind {local(kind)}")
        cls, attr = local(about).split("-", 1)
        ct_row = ct.get((cls, attr))
        quotes = list(authored.objects(a, UO.quote))
        if quotes and ct_row is None:
            raise RuntimeError(f"{local(a)}: quotes given but no USDM_CT.xlsx row for {cls}.{attr}")
        for q in quotes:
            if str(q) not in str(ct_row["Definition"]):
                raise RuntimeError(f"{local(a)}: quote not verbatim in USDM_CT.xlsx definition: {q}")
        companions = list(authored.objects(a, UO.companionOf))
        if kind == UO.CompanionText:
            if len(companions) != 1:
                raise RuntimeError(f"{local(a)}: companion text needs exactly one uo:companionOf")
            sib = companions[0]
            if sib not in usdm_props or usdm.value(sib, RDFS.domain) != usdm.value(about, RDFS.domain):
                raise RuntimeError(f"{local(a)}: companionOf {sib} is not a property of the same class")
            if sib == about:
                raise RuntimeError(f"{local(a)}: companionOf points to itself")
        elif companions:
            raise RuntimeError(f"{local(a)}: uo:companionOf only allowed on companion text")
        label_of = list(authored.objects(a, UO.labelOf))
        if kind == UO.DisplayLabel:
            if not label_of:
                raise RuntimeError(f"{local(a)}: display label needs uo:labelOf")
            for target in label_of:
                if target not in usdm_props or usdm.value(target, RDFS.domain) != usdm.value(about, RDFS.domain):
                    raise RuntimeError(f"{local(a)}: labelOf {target} is not a property of the same class")
                if target == about:
                    raise RuntimeError(f"{local(a)}: labelOf points to itself")
        elif label_of:
            raise RuntimeError(f"{local(a)}: uo:labelOf only allowed on display labels")
        syntaxes = list(authored.objects(a, UO.syntax))
        if kind == UO.EncodedValue:
            if len(syntaxes) != 1 or not str(syntaxes[0]).strip():
                raise RuntimeError(f"{local(a)}: encoded value needs exactly one uo:syntax")
        elif syntaxes:
            raise RuntimeError(f"{local(a)}: uo:syntax only allowed on encoded values")

    findings = sorted(authored.subjects(RDF.type, UO.Finding), key=str)
    for f in findings:
        for p in (URIRef("http://purl.org/dc/terms/title"), UO.statement, UO.evidenceTier):
            one(authored, f, p)
        tier = authored.value(f, UO.evidenceTier)
        if tier == UO.Authored and not str(authored.value(f, UO.rationale) or "").strip():
            raise RuntimeError(f"{local(f)}: authored finding needs a rationale")
        has_query = (f, UO.testQuery, None) in authored
        has_function = (f, UO.checkFunction, None) in authored
        if has_query == has_function:
            raise RuntimeError(f"{local(f)}: needs exactly one of uo:testQuery or uo:checkFunction")
        if has_query:
            one(authored, f, UO.expectedResult)
        subjects = list(authored.objects(f, URIRef("http://purl.org/dc/terms/subject")))
        if not subjects:
            raise RuntimeError(f"{local(f)}: no dcterms:subject")
        for s in subjects:
            if s not in usdm_classes:
                raise RuntimeError(f"{local(f)}: subject {s} is not a usdm-rdf class")

    print(f"OK: {len(assessments)} authored assessments, {len(findings)} findings")


if __name__ == "__main__":
    main()

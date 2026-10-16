"""Build the static GitHub Pages site for the overlay namespace.

Input:  usdm_overlay.ttl, derived/*.ttl, authored/*.ttl, reports/*.md,
        downloads/usdm_v4.ttl (labels, domains, superclasses),
        site/explorer.html (explorer page template), site/design-elements.html
        (plain-language page, hand-maintained), site/design-elements-in-usdm.pdf
        (the same content as slides, copied as is)
Output: docs/ (deleted and rebuilt on every run; do not edit by hand)

Every IRI the overlay mints under its namespace gets a page at its own path:
- the namespace itself: docs/index.html
- vocabulary terms: docs/<term>/index.html
- class-role assessments: docs/id/assessment/classRole/<Class>/index.html, the
  page for that USDM class, with one anchor per attribute assessment
- other assessments: a stub at their own path that forwards to the anchor on
  the class page
- findings: docs/id/finding/<id>/index.html
RDF is served as files only, the whole graph: GitHub Pages has no content
negotiation. Every page links to graphs/overlay.ttl as its RDF alternate.

Two reading pages sit beside the minted IRIs: docs/explorer/ (the graphs as
an explorable page, its data computed here on every build) and
docs/design-elements/ (a plain-language page). No minted IRI may start with
their path names.
"""
import html
import json
import shutil
from collections import Counter, defaultdict

import markdown
from rdflib import Graph, URIRef
from rdflib.collection import Collection
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SKOS

from common import ROOT, UO, USDM, load_usdm, local

NS = str(UO)
SITE = ROOT / "docs"
REPO = "https://github.com/kerfors/usdm-overlay"
SITE_SRC = ROOT / "site"
READING_PAGES = ("explorer", "design-elements")
OVERLAY_FILES = ["usdm_overlay.ttl"] + [
    f"{folder}/{name}"
    for folder in ("derived", "authored")
    for name in sorted(p.name for p in (ROOT / folder).glob("*.ttl"))
]

CSS = """
:root { --bg: #fdfdfb; --fg: #1d1d1b; --muted: #5f5f5a; --rule: #d9d9d2; --accent: #1f5c99; --code: #f1f1ec;
    --data-bg: #dce7f5; --data-fg: #1e4f8a; --words-bg: #f6e3d2; --words-fg: #7a3d10; --tint: #eef3fa; }
@media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) { --bg: #161615; --fg: #e8e8e3; --muted: #a3a39c; --rule: #3a3a36; --accent: #8ab8e6; --code: #23231f;
        --data-bg: #233a57; --data-fg: #b9d3f2; --words-bg: #4a3020; --words-fg: #f0c9a6; --tint: #1c2531; }
}
:root[data-theme="dark"] { --bg: #161615; --fg: #e8e8e3; --muted: #a3a39c; --rule: #3a3a36; --accent: #8ab8e6; --code: #23231f;
    --data-bg: #233a57; --data-fg: #b9d3f2; --words-bg: #4a3020; --words-fg: #f0c9a6; --tint: #1c2531; }
body { background: var(--bg); color: var(--fg); font: 16px/1.5 system-ui, sans-serif; margin: 0; }
main { max-width: 64rem; margin: 0 auto; padding: 1.5rem 1rem 4rem; }
a { color: var(--accent); }
nav { font-size: 0.9rem; color: var(--muted); margin-bottom: 1.5rem; }
h1 { font-size: 1.6rem; margin: 0 0 0.25rem; }
h2 { font-size: 1.2rem; margin-top: 2rem; border-bottom: 1px solid var(--rule); padding-bottom: 0.25rem; }
.iri { font-family: ui-monospace, monospace; font-size: 0.85rem; color: var(--muted); word-break: break-all; }
dl { display: grid; grid-template-columns: max-content 1fr; gap: 0.25rem 1rem; }
dt { color: var(--muted); }
dd { margin: 0; }
.scroll { overflow-x: auto; }
table { border-collapse: collapse; font-size: 0.9rem; width: 100%; }
th, td { text-align: left; vertical-align: top; padding: 0.35rem 0.5rem; border-bottom: 1px solid var(--rule); }
th { color: var(--muted); font-weight: 600; }
tr:target { background: var(--code); }
pre, code { font-family: ui-monospace, monospace; font-size: 0.85rem; background: var(--code); }
pre { padding: 0.75rem; overflow-x: auto; }
blockquote { margin: 0.5rem 0; padding-left: 0.75rem; border-left: 3px solid var(--rule); color: var(--muted); }
.note { color: var(--muted); font-size: 0.9rem; }
.eyebrow { font-size: 0.75rem; letter-spacing: 0.1em; text-transform: uppercase; color: var(--muted); font-weight: 600; margin: 0; }
.lede { font-size: 1.1rem; color: var(--muted); max-width: 42rem; }
.start { display: grid; grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr)); gap: 1rem; margin-top: 1rem; }
.start a { display: block; border: 1px solid var(--rule); border-radius: 10px; padding: 1rem; text-decoration: none; color: var(--fg); }
.start a b { color: var(--accent); }
.start a span { display: block; color: var(--muted); font-size: 0.9rem; margin-top: 0.25rem; }
.button { display: inline-block; background: var(--accent); color: var(--bg); font-weight: 600; text-decoration: none; padding: 0.55rem 1.1rem; border-radius: 8px; margin: 0.5rem 0; }
.button:hover, .button:focus-visible { filter: brightness(1.1); outline: 2px solid var(--accent); outline-offset: 2px; }
.chips { display: flex; flex-wrap: wrap; gap: 0.4rem; }
.chip { display: inline-block; font-size: 0.85rem; padding: 0.15rem 0.7rem; border-radius: 999px; font-weight: 600; }
.chip.data { background: var(--data-bg); color: var(--data-fg); }
.chip.words { background: var(--words-bg); color: var(--words-fg); }
.chip.none { border: 1px dashed var(--muted); color: var(--muted); }
.chip a { color: inherit; }
.de-two { display: grid; grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr)); gap: 1.5rem; align-items: center; }
.de-card { border: 1px solid var(--rule); border-radius: 14px; padding: 1.25rem; display: flex; flex-direction: column; gap: 0.75rem; }
.wordblock { background: var(--words-bg); color: var(--words-fg); padding: 0.75rem 1rem; border-radius: 10px; font-style: italic; margin: 0; }
.de-defs { display: flex; flex-direction: column; gap: 0.75rem; }
.de-defs p { margin: 0; }
.de-map { display: grid; grid-template-columns: repeat(auto-fit, minmax(17rem, 1fr)); gap: 1rem; }
.de-col { display: flex; flex-direction: column; gap: 1rem; min-width: 0; }
.de-box { border: 1px solid var(--rule); border-radius: 14px; padding: 1rem 1.1rem; display: flex; flex-direction: column; gap: 0.6rem; }
.de-box h3 { margin: 0; font-size: 1.05rem; }
.de-box.structured { background: var(--tint); border-color: var(--data-fg); }
.de-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.4rem; }
.de-grid span { text-align: center; font-size: 0.85rem; border: 1px solid var(--data-fg); color: var(--data-fg); border-radius: 6px; padding: 0.2rem; }
.de-gaps { display: grid; grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr)); gap: 1rem; }
.de-gap { border: 2px dashed var(--words-fg); border-radius: 14px; padding: 1rem 1.1rem; }
.de-gap h3 { margin: 0 0 0.4rem; font-size: 1.05rem; }
.de-gap p { margin: 0; }
.de-short { grid-template-columns: max-content 1fr; gap: 0.6rem 1rem; align-items: center; }
"""


def esc(text):
    return html.escape(str(text))


def rel(from_dir, to_path):
    """Relative URL from a page in site directory from_dir to site path to_path."""
    depth = len([p for p in from_dir.split("/") if p])
    return "../" * depth + to_path


def page(path_dir, title, body):
    up = rel(path_dir, "")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<link rel="alternate" type="text/turtle" href="{up}graphs/overlay.ttl">
<style>{CSS}</style>
</head>
<body>
<main>
<nav><a href="{up}">usdm-overlay</a> · <a href="{up}explorer/">explorer</a> · <a href="{up}design-elements/">design elements</a> · <a href="{up}reports/">reports</a> · <a href="{up}graphs/">graphs</a> · <a href="{REPO}">repository</a></nav>
{body}
</main>
</body>
</html>
"""


def write(path_dir, title, body):
    target = SITE / path_dir / "index.html" if path_dir else SITE / "index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(page(path_dir, title, body))


def stub(path_dir, target_dir, anchor, title):
    url = rel(path_dir, f"{target_dir}/#{anchor}")
    canonical = f"{NS}{target_dir}#{anchor}"
    target = SITE / path_dir / "index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{esc(title)}</title>
<meta http-equiv="refresh" content="0; url={url}">
<link rel="canonical" href="{esc(canonical)}">
</head>
<body><p>{esc(title)} is described on <a href="{url}">its class page</a>.</p></body>
</html>
""")


def site_path(iri):
    text = str(iri)
    if not text.startswith(NS):
        raise RuntimeError(f"{text} is not in the overlay namespace")
    return text[len(NS):]


def explorer_data(usdm, overlay):
    """The data the explorer page renders, computed from the graphs."""
    def label(term):
        return str(overlay.value(term, SKOS.prefLabel) or local(term))

    def top(kind):
        while overlay.value(kind, SKOS.broader) is not None:
            kind = overlay.value(kind, SKOS.broader)
        return kind

    def group(kind):
        if top(kind) == UO.Text:
            return "read" if (UO.ReadText, SKOS.member, kind) in overlay else "structure"
        return local(top(kind))

    assessments = set(overlay.subjects(RDF.type, UO.Assessment))
    refined_by = {overlay.value(a, UO.refines): a for a in assessments if overlay.value(a, UO.refines) is not None}
    derived = {overlay.value(a, UO.about): a for a in assessments if overlay.value(a, UO.refines) is None}

    def effective(term):
        d = derived[term]
        return refined_by.get(d, d), d

    classes = sorted((c for c in usdm.subjects(RDF.type, OWL.Class) if str(c).startswith(str(USDM))), key=str)
    class_set = set(classes)
    own = defaultdict(list)
    for term in derived:
        if term not in class_set:
            own[usdm.value(term, RDFS.domain)].append(term)
    findings_by_class = defaultdict(list)
    findings = sorted(overlay.subjects(RDF.type, UO.Finding), key=str)
    for f in findings:
        for s in overlay.objects(f, DCTERMS.subject):
            findings_by_class[s].append(local(f))
    profile_keys = ["hasNaming", "isReferenced", "composedInCount", "readTextCount", "stringStructureCount",
                    "valueCount", "referenceCount", "partCount"]
    out_classes = []
    for c in classes:
        e, d = effective(c)
        attrs = []
        for prop in sorted(own[c], key=str):
            pe, pd = effective(prop)
            kind = overlay.value(pe, UO.assignedKind)
            rng = usdm.value(prop, RDFS.range)
            union = usdm.value(rng, OWL.unionOf)
            rng_text = " or ".join(sorted(local(m) for m in Collection(usdm, union))) if union is not None else local(rng)
            attrs.append({
                "a": local(prop).split("-", 1)[1], "range": rng_text, "kind": label(kind), "group": group(kind),
                "tier": label(overlay.value(pe, UO.evidenceTier)),
                "derived": label(overlay.value(pd, UO.assignedKind)) if pe != pd else None,
                "why": str(overlay.value(pe, UO.rationale)) if overlay.value(pe, UO.rationale) is not None else None,
            })
        out_classes.append({
            "name": local(c), "abstract": str(usdm.value(c, USDM.modifier)) == "Abstract",
            "super": [local(s) for s in usdm.objects(c, RDFS.subClassOf) if s in class_set],
            "role": label(overlay.value(e, UO.assignedKind)),
            "derivedRole": label(overlay.value(d, UO.assignedKind)) if e != d else None,
            "rule": local(overlay.value(d, UO.byRule)),
            "why": str(overlay.value(e, UO.rationale)) if e != d else None,
            "profile": {k: overlay.value(d, UO[k]).toPython() for k in profile_keys},
            "attrs": attrs, "findings": sorted(findings_by_class[c]),
            "def": str(usdm.value(c, SKOS.definition) or ""),
        })
    out_findings = [{
        "id": local(f), "title": str(overlay.value(f, DCTERMS.title)),
        "standing": label(overlay.value(f, UO.standing)), "standingWhy": str(overlay.value(f, UO.standingRationale)),
        "tier": label(overlay.value(f, UO.evidenceTier)), "statement": str(overlay.value(f, UO.statement)),
        "obs": str(overlay.value(f, UO.observation)),
        "rationale": str(overlay.value(f, UO.rationale)) if overlay.value(f, UO.rationale) is not None else None,
        "subjects": sorted(local(s) for s in overlay.objects(f, DCTERMS.subject)),
    } for f in findings]
    all_attrs = [a for c in out_classes for a in c["attrs"]]
    summary = {
        "attributes": len(all_attrs), "classes": len(out_classes), "findings": len(out_findings),
        "groups": dict(Counter(a["group"] for a in all_attrs)),
        "kinds": dict(Counter(a["kind"] for a in all_attrs if a["group"] in ("read", "structure"))),
        "roles": dict(Counter(c["role"] for c in out_classes)),
    }
    return {"summary": summary, "classes": out_classes, "findings": out_findings}


def main():
    usdm = load_usdm()
    vocab = Graph().parse(ROOT / "usdm_overlay.ttl")
    overlay = Graph()
    for name in OVERLAY_FILES:
        overlay.parse(ROOT / name)

    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir()
    (SITE / ".nojekyll").write_text("")

    # ---------------------------------------------------------------- graphs
    graphs = SITE / "graphs"
    graphs.mkdir()
    for name in OVERLAY_FILES:
        target = graphs / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    merged = Graph()
    for prefix, ns in overlay.namespaces():
        merged.bind(prefix, ns)
    for t in overlay:
        merged.add(t)
    (graphs / "overlay.ttl").write_text(
        "# All usdm-overlay graphs merged: vocabulary, derived and authored. Generated by scripts/build_site.py.\n"
        + merged.serialize(format="turtle")
    )
    items = "".join(f'<li><a href="{n}">{esc(n)}</a></li>' for n in ["overlay.ttl"] + OVERLAY_FILES)
    write("graphs", "usdm-overlay graphs", f"""<h1>Graphs</h1>
<p>RDF is served as whole graphs. <code>overlay.ttl</code> merges all overlay graphs; the other files are the graphs as kept in the repository.
The overlay points at <a href="https://github.com/kerfors/usdm-rdf">usdm-rdf</a> IRIs; load <code>usdm_v4.ttl</code> from there alongside it to query both.</p>
<ul>{items}</ul>""")

    # ---------------------------------------------------------------- reports
    reports = sorted((ROOT / "reports").glob("*.md"))
    for md in reports:
        body = markdown.markdown(md.read_text(), extensions=["tables"])
        body = body.replace("<table>", '<div class="scroll"><table>').replace("</table>", "</table></div>")
        write(f"reports/{md.stem}", md.stem, body)
    items = "".join(f'<li><a href="{md.stem}/">{esc(md.stem)}</a></li>' for md in reports)
    write("reports", "usdm-overlay reports", f"<h1>Reports</h1>\n<p>Generated by the build scripts.</p>\n<ul>{items}</ul>")

    # ---------------------------------------------------------------- effective assessments
    assessments = set(overlay.subjects(RDF.type, UO.Assessment))
    refined_by = {overlay.value(a, UO.refines): a for a in assessments if overlay.value(a, UO.refines) is not None}
    by_about = defaultdict(list)
    for a in assessments:
        by_about[overlay.value(a, UO.about)].append(a)

    def effective(term):
        derived = [a for a in by_about[term] if overlay.value(a, UO.refines) is None]
        if len(derived) != 1:
            raise RuntimeError(f"{local(term)}: expected one derived assessment, found {len(derived)}")
        return refined_by.get(derived[0], derived[0]), derived[0]

    def pref(term):
        label = vocab.value(term, SKOS.prefLabel) or vocab.value(term, RDFS.label)
        return str(label) if label is not None else local(term)

    def term_link(term, from_dir):
        if str(term).startswith(NS):
            return f'<a href="{rel(from_dir, site_path(term))}/">{esc(pref(term))}</a>'
        return f'<a href="{esc(term)}">{esc(local(term))}</a>'

    classes = sorted(
        (c for c in usdm.subjects(RDF.type, OWL.Class) if str(c).startswith(str(USDM))),
        key=str,
    )
    class_dir = {c: f"id/assessment/classRole/{local(c)}" for c in classes}
    for c in classes:
        if (UO[class_dir[c]], RDF.type, UO.Assessment) not in overlay:
            raise RuntimeError(f"No derived class-role assessment at {class_dir[c]}")

    def class_link(c, from_dir):
        return f'<a href="{rel(from_dir, class_dir[c])}/">{esc(local(c))}</a>'

    props_by_class = defaultdict(list)
    for prop in overlay.subjects(UO.contentKind, None):
        if prop in props_by_class[usdm.value(prop, RDFS.domain)]:
            continue
        props_by_class[usdm.value(prop, RDFS.domain)].append(prop)

    findings_by_class = defaultdict(list)
    for f in overlay.subjects(RDF.type, UO.Finding):
        for s in overlay.objects(f, DCTERMS.subject):
            findings_by_class[s].append(f)

    def evidence_cells(a, from_dir):
        tier = overlay.value(a, UO.evidenceTier)
        rule = overlay.value(a, UO.byRule)
        rationale = overlay.value(a, UO.rationale)
        quote = overlay.value(a, UO.quote)
        basis = term_link(rule, from_dir) if rule is not None else esc(rationale)
        if quote is not None:
            basis += f"<blockquote>{esc(quote)}</blockquote>"
        return term_link(tier, from_dir), basis

    # ---------------------------------------------------------------- class pages
    supers = {c: [s for s in usdm.objects(c, RDFS.subClassOf) if s in set(classes)] for c in classes}
    subs = {c: [s for s in classes if c in supers[s]] for c in classes}
    for c in classes:
        d = class_dir[c]
        eff, der = effective(c)
        role = overlay.value(eff, UO.assignedKind)
        tier_cell, basis = evidence_cells(eff, d)
        rows = []
        for name, prop in [("has naming", UO.hasNaming), ("is referenced", UO.isReferenced),
                           ("composed in (classes)", UO.composedInCount), ("read text", UO.readTextCount),
                           ("string structure", UO.stringStructureCount), ("value", UO.valueCount),
                           ("reference", UO.referenceCount), ("part", UO.partCount)]:
            rows.append(f"<dt>{esc(name)}</dt><dd>{esc(overlay.value(der, prop))}</dd>")
        derived_note = ""
        if eff != der:
            derived_note = (f"<p class=\"note\">Derived role: {term_link(overlay.value(der, UO.assignedKind), d)} "
                            f"by {term_link(overlay.value(der, UO.byRule), d)}. The authored role refines it.</p>")
        modifier = usdm.value(c, USDM.modifier)
        hierarchy = ""
        if supers[c]:
            hierarchy += "<dt>superclass</dt><dd>" + ", ".join(class_link(s, d) for s in supers[c]) + "</dd>"
        if subs[c]:
            hierarchy += "<dt>subclasses</dt><dd>" + ", ".join(class_link(s, d) for s in subs[c]) + "</dd>"
        attr_rows = []
        for prop in sorted(props_by_class[c], key=str):
            peff, pder = effective(prop)
            kind = overlay.value(peff, UO.assignedKind)
            t_cell, b_cell = evidence_cells(peff, d)
            derived_kind = ""
            if peff != pder:
                derived_kind = f'<br><span class="note">derived: {term_link(overlay.value(pder, UO.assignedKind), d)}</span>'
            rng = usdm.value(prop, RDFS.range)
            union = usdm.value(rng, OWL.unionOf)
            rng_text = "union" if union is not None else local(rng)
            attr_rows.append(
                f'<tr id="{esc(local(prop))}"><td><a href="{esc(prop)}">{esc(local(prop).split("-", 1)[1])}</a></td>'
                f"<td>{esc(rng_text)}</td><td>{term_link(kind, d)}{derived_kind}</td><td>{t_cell}</td><td>{b_cell}</td></tr>"
            )
        inherited = ""
        anc = []
        stack = list(supers[c])
        while stack:
            s = stack.pop(0)
            anc.append(s)
            stack += supers[s]
        if anc:
            inherited = "<p class=\"note\">Inherited attributes are listed on " + ", ".join(class_link(s, d) for s in anc) + ".</p>"
        findings = ""
        if findings_by_class[c]:
            findings = "<h2>Findings</h2><ul>" + "".join(
                f'<li><a href="{rel(d, site_path(f))}/">{esc(overlay.value(f, DCTERMS.title))}</a></li>'
                for f in sorted(findings_by_class[c], key=str)
            ) + "</ul>"
        body = f"""<h1>{esc(local(c))}</h1>
<p class="iri">{esc(NS + d)}</p>
<p>Overlay page for the USDM class <a href="{esc(c)}">{esc(c)}</a>{' (abstract)' if str(modifier) == 'Abstract' else ''}.</p>
<h2 id="role">Role</h2>
<dl><dt>role</dt><dd>{term_link(role, d)}</dd><dt>evidence</dt><dd>{tier_cell}</dd><dt>basis</dt><dd>{basis}</dd>{hierarchy}</dl>
{derived_note}
<h2>Profile</h2>
<p class="note">Attributes of the class and its superclasses; payload excludes housekeeping, naming and notes.</p>
<dl>{''.join(rows)}</dl>
<h2>Attributes declared on this class</h2>
{inherited}
<div class="scroll"><table>
<tr><th>Attribute</th><th>Range</th><th>Content kind</th><th>Evidence</th><th>Rule or rationale</th></tr>
{''.join(attr_rows)}
</table></div>
{findings}"""
        write(d, local(c), body)

    # ---------------------------------------------------------------- assessment stubs
    for a in sorted(assessments, key=str):
        p = site_path(a)
        about = overlay.value(a, UO.about)
        if about in class_dir:
            if p == class_dir[about]:
                continue
            stub(p, class_dir[about], "role", f"Assessment of {local(about)}")
        else:
            stub(p, class_dir[usdm.value(about, RDFS.domain)], local(about), f"Assessment of {local(about)}")

    # ---------------------------------------------------------------- findings
    finding_items = []
    for f in sorted(overlay.subjects(RDF.type, UO.Finding), key=str):
        d = site_path(f)
        title = overlay.value(f, DCTERMS.title)
        holds = overlay.value(f, UO.holds)
        rows = [
            f"<dt>standing</dt><dd>{term_link(overlay.value(f, UO.standing), d)}: {esc(overlay.value(f, UO.standingRationale))}</dd>",
            f"<dt>evidence</dt><dd>{term_link(overlay.value(f, UO.evidenceTier), d)}</dd>",
            f"<dt>holds</dt><dd>{esc(holds)}</dd>",
            f"<dt>observation</dt><dd>{esc(overlay.value(f, UO.observation))}</dd>",
            "<dt>about</dt><dd>" + ", ".join(class_link(s, d) for s in sorted(overlay.objects(f, DCTERMS.subject), key=str)) + "</dd>",
            "<dt>sources</dt><dd>" + "<br>".join(f'<a href="{esc(s)}">{esc(s)}</a>' for s in sorted(overlay.objects(f, DCTERMS.source), key=str)) + "</dd>",
        ]
        rationale = overlay.value(f, UO.rationale)
        if rationale is not None:
            rows.insert(1, f"<dt>rationale</dt><dd>{esc(rationale)}</dd>")
        query = overlay.value(f, UO.testQuery)
        if query is not None:
            test = f"<h2>Test</h2><p>SPARQL ASK over usdm_v4.ttl, expected <code>{esc(overlay.value(f, UO.expectedResult))}</code>.</p><pre>{esc(query)}</pre>"
        else:
            test = f"<h2>Test</h2><p>Check function <code>{esc(overlay.value(f, UO.checkFunction))}</code> in <a href=\"{REPO}/blob/main/scripts/check_findings.py\">scripts/check_findings.py</a>.</p>"
        body = f"""<h1>{esc(title)}</h1>
<p class="iri">{esc(f)}</p>
<p>{esc(overlay.value(f, UO.statement))}</p>
<dl>{''.join(rows)}</dl>
{test}"""
        write(d, str(title), body)
        finding_items.append((overlay.value(f, UO.standing), f'<li><a href="{d}/">{esc(title)}</a></li>'))

    # ---------------------------------------------------------------- vocabulary terms
    terms = sorted(
        {s for s in vocab.subjects() if isinstance(s, URIRef) and str(s).startswith(NS) and str(s) != NS},
        key=str,
    )
    effective_kind_of = defaultdict(list)
    for term in [p for ps in props_by_class.values() for p in ps] + classes:
        eff, _ = effective(term)
        effective_kind_of[overlay.value(eff, UO.assignedKind)].append(term)
    for term in terms:
        d = site_path(term)
        rows = []
        for t in vocab.objects(term, RDF.type):
            rows.append(f"<dt>type</dt><dd>{term_link(t, d)}</dd>")
        for label, prop in [("definition", SKOS.definition), ("comment", RDFS.comment), ("order", UO.order)]:
            for v in vocab.objects(term, prop):
                rows.append(f"<dt>{label}</dt><dd>{esc(v)}</dd>")
        for label, prop in [("in scheme", SKOS.inScheme), ("broader", SKOS.broader), ("domain", RDFS.domain),
                            ("range", RDFS.range), ("subclass of", RDFS.subClassOf), ("member", SKOS.member)]:
            values = sorted(vocab.objects(term, prop), key=str)
            if values:
                rows.append(f"<dt>{label}</dt><dd>" + ", ".join(term_link(v, d) for v in values) + "</dd>")
        for label, prop in [("narrower", SKOS.broader), ("member of", SKOS.member), ("concepts", SKOS.inScheme)]:
            values = sorted(vocab.subjects(prop, term), key=str)
            if values:
                rows.append(f"<dt>{label}</dt><dd>" + ", ".join(term_link(v, d) for v in values) + "</dd>")
        used = ""
        if effective_kind_of[term]:
            links = []
            for t in sorted(effective_kind_of[term], key=str):
                if t in class_dir:
                    links.append(class_link(t, d))
                else:
                    cdir = class_dir[usdm.value(t, RDFS.domain)]
                    links.append(f'<a href="{rel(d, cdir)}/#{esc(local(t))}">{esc(local(t))}</a>')
            used = f"<h2>Assigned to ({len(links)})</h2><p class=\"note\">Effective assessments.</p><p>" + ", ".join(links) + "</p>"
        body = f"""<h1>{esc(pref(term))}</h1>
<p class="iri">{esc(term)}</p>
<dl>{''.join(rows)}</dl>
{used}"""
        write(d, pref(term), body)

    # ---------------------------------------------------------------- reading pages
    template = (SITE_SRC / "explorer.html").read_text()
    if template.count("__DATA__") != 1:
        raise RuntimeError("site/explorer.html must hold exactly one __DATA__ placeholder")
    data = json.dumps(explorer_data(usdm, overlay), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    (SITE / "explorer").mkdir()
    (SITE / "explorer" / "index.html").write_text(template.replace("__DATA__", data))
    write("design-elements", "Design elements in USDM", (SITE_SRC / "design-elements.html").read_text())
    shutil.copyfile(SITE_SRC / "design-elements-in-usdm.pdf", SITE / "design-elements" / "design-elements-in-usdm.pdf")

    # ---------------------------------------------------------------- index
    def term_list(rdf_type):
        members = sorted(vocab.subjects(RDF.type, rdf_type), key=str)
        return ", ".join(term_link(m, "") for m in members if str(m).startswith(NS))

    schemes = "".join(
        f"<li>{term_link(s, '')}: " + ", ".join(term_link(c, "") for c in sorted(vocab.subjects(SKOS.inScheme, s), key=str)) + "</li>"
        for s in sorted(vocab.subjects(RDF.type, SKOS.ConceptScheme), key=str)
    )
    roles = defaultdict(list)
    for c in classes:
        eff, _ = effective(c)
        roles[overlay.value(eff, UO.assignedKind)].append(c)
    role_items = "".join(
        f"<li>{term_link(r, '')} ({len(cs)}): " + ", ".join(class_link(c, "") for c in cs) + "</li>"
        for r, cs in sorted(roles.items(), key=lambda kv: pref(kv[0]))
    )
    findings_html = ""
    for standing in (UO.ReadyToRaise, UO.ForDiscussion):
        items = [item for st, item in finding_items if st == standing]
        findings_html += (f"<h3>{term_link(standing, '')} ({len(items)})</h3>"
                          f"<p class=\"note\">{esc(vocab.value(standing, SKOS.definition))}</p><ul>{''.join(items)}</ul>")
    if sum(1 for st, _ in finding_items if st not in (UO.ReadyToRaise, UO.ForDiscussion)):
        raise RuntimeError("A finding has no known standing")
    body = f"""<h1>usdm-overlay</h1>
<p class="iri">{esc(NS)}</p>
<p>{esc(vocab.value(URIRef(NS), DCTERMS.description))}</p>
<div class="start">
<a href="design-elements/"><b>Design elements in plain language</b><span>Objectives, endpoints, eligibility criteria and the schedule: what USDM holds as data, and what is still words.</span></a>
<a href="design-elements/design-elements-in-usdm.pdf"><b>Design elements as slides (PDF)</b><span>The same content as four slides, ready to present or send.</span></a>
<a href="explorer/"><b>Explore the overlay</b><span>Every class and attribute, filterable by role, with the evidence for each reading, and the findings.</span></a>
</div>
<p class="note">{esc(vocab.value(URIRef(NS), RDFS.comment))} RDF: <a href="graphs/overlay.ttl">graphs/overlay.ttl</a> (whole graph).</p>
<h2>Classes by role</h2>
<ul>{role_items}</ul>
<h2>Findings</h2>
{findings_html}
<h2>Concept schemes</h2>
<ul>{schemes}</ul>
<h2>Collections</h2>
<p>{term_list(SKOS.Collection)}</p>
<h2>Classes and properties</h2>
<p>{term_list(OWL.Class)}</p>
<p>{term_list(OWL.ObjectProperty)}, {term_list(OWL.DatatypeProperty)}, {term_list(OWL.AnnotationProperty)}</p>
<h2>Rules</h2>
<p>{term_list(UO.Rule)}</p>
<p>{term_list(UO.ClassRoleRule)}</p>"""
    write("", "usdm-overlay", body)

    # ---------------------------------------------------------------- every minted IRI has a page
    minted = {str(x) for t in overlay for x in t if isinstance(x, URIRef) and str(x).startswith(NS)}
    missing = sorted(i for i in minted if not (SITE / site_path(i) / "index.html").exists())
    if missing:
        raise RuntimeError(f"{len(missing)} minted IRIs have no page, e.g. {missing[:5]}")
    lowered = defaultdict(set)
    for i in minted:
        segments = site_path(i).split("/")
        for n in range(1, len(segments) + 1):
            prefix = "/".join(segments[:n])
            lowered[prefix.lower()].add(prefix)
    clashes = sorted(sorted(v) for v in lowered.values() if len(v) > 1)
    if clashes:
        raise RuntimeError(f"Paths that differ only by case collide on case-insensitive file systems: {clashes[:5]}")
    taken = [i for i in minted if site_path(i).split("/")[0].lower() in READING_PAGES]
    if taken:
        raise RuntimeError(f"Minted IRIs collide with the reading pages: {taken[:5]}")
    print(f"OK: {len(minted)} minted IRIs, each with a page in docs/; reading pages: {', '.join(READING_PAGES)}")


if __name__ == "__main__":
    main()

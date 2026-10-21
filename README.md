# usdm-overlay

An overlay graph on top of [usdm-rdf](https://github.com/kerfors/usdm-rdf), the
RDF/OWL representation of the CDISC Unified Study Definitions Model (USDM) v4.
It classifies and comments on the model: what each attribute actually holds,
what role each class plays, and what the model does not connect.

**Early, exploratory work.** Draft, not a CDISC artifact.

## Why a separate repo

usdm-rdf renders what CDISC publishes and nothing else. Anything that reads,
classifies or judges the model belongs somewhere else, so that the rendering
stays mechanical and the readings stay visible as readings. This repo only
points at usdm-rdf IRIs. It never changes them.

## Evidence tiers

Every assertion says what it rests on:

| Tier | Meaning |
| --- | --- |
| Model-stated | Follows from the model or specification structure as rendered: in usdm-rdf, range, relationship type, attribute name; in m11-rdf, what the ICH M11 Technical Specification, Template, OID Listing, Genericode and EVS code lists state. |
| Definition-stated | Follows from the wording of the NCI definition attached to the term (by CDISC in `USDM_CT.xlsx`, or in the EVS ICH M11 Terminology). The quote is recorded. |
| Mapping-stated | Follows from what a published M11-to-USDM mapping file (HL7, CDISC) states in its rows, as read by m11-rdf. |
| Example-observed | Seen in the example study files CDISC publishes, not stated in the model. The examples are not mature study definitions, so these findings say what the published files contain, not how USDM is or should be used. |
| Authored | A reading by the overlay author, with a stated rationale. |

Derived assessments also name the rule that produced them. Authored assessments
refine a derived one and carry a rationale; where both exist, the authored kind
is the one to use. Quotes are checked verbatim against `USDM_CT.xlsx`.

Findings are statements with a test: a SPARQL ASK query over `usdm_v4.ttl`, or
a named check in `scripts/check_findings.py`. Statements are qualitative; the
counts come from the test run. A finding that stops holding against a new
input version stops the build.

Each finding also has a standing: *ready to raise* with the publisher when
the published artefacts contradict themselves or what they state they follow,
or leave undefined something they rely on, or *for discussion* when it depends
on a modelling choice the publisher may have made on purpose, or on the example
files. The standing is authored and carries a one-line rationale.

## Layers

| # | Layer | Status |
| --- | --- | --- |
| 1 | Content kind per attribute | Complete. Derived for all properties (`derived/content_kind.ttl`); every string the derivation leaves unclassified has an authored kind (`authored/content_kind.ttl`), except Estimand.populationSummary, held open by a finding. |
| 2 | Role per class | Derived for all classes (`derived/class_role.ttl`, `reports/class_role.md`), from the layer 1 kinds of each class's own and inherited attributes. Authored roles (`authored/class_role.ttl`) for five classes where the derived role misreads the class. |
| 3 | Findings about the model, each with a test | Started: `authored/findings.ttl`, results in `derived/finding_results.ttl` and `reports/findings.md` |
| 4 | Observed practice in the CDISC example files | Started, as example-observed findings in layer 3 |

## Files

| Path | What |
| --- | --- |
| `usdm_overlay.ttl` | Vocabulary: content-kind, class-role and evidence-tier concept schemes, text groups, assessment and class-profile properties, derivation rules. Hand-maintained. |
| `authored/` | Hand-maintained graphs: `content_kind.ttl` and `class_role.ttl` (authored assessments), `findings.ttl`. |
| `derived/` | Generated graphs. Do not edit by hand. |
| `reports/` | Generated reports. Do not edit by hand. |
| `docs/` | Generated GitHub Pages site for the namespace. Do not edit by hand. |
| `site/` | Hand-maintained sources for the site's reading material: `explorer.html` (template; its data is computed from the graphs on every build), `slides/design-elements-slides.html` (six slides on design elements) and `design-elements-in-usdm.pdf` (rendered from the slides by `scripts/render_slides.py`, which needs Playwright with Chromium and is not part of the regular rebuild). |
| `downloads/` | Pinned inputs and `MANIFEST.md` with tag, commit and SHA-256: `usdm_v4.ttl` (usdm-rdf v0.7.0), `USDM_CT.xlsx`, `dataStructure.yml` and the five example studies (DDF-RA v4.0.0). |
| `queries/` | Example SPARQL queries over usdm-rdf plus the overlay. Results in `reports/queries.md`. |
| `scripts/` | `fetch_inputs.py`, `build_content_kind.py`, `build_class_role.py`, `validate_authored.py`, `check_findings.py`, `run_queries.py`, `build_site.py`, `render_slides.py`, `common.py`. |

## Rebuild

```
python3 scripts/fetch_inputs.py
python3 scripts/build_content_kind.py
python3 scripts/build_class_role.py
python3 scripts/validate_authored.py
python3 scripts/check_findings.py
python3 scripts/run_queries.py
python3 scripts/build_site.py
```

Requires Python 3, `rdflib`, `openpyxl`, `pyyaml` and `markdown`. The repo rebuilds from its own pinned inputs,
with no dependency on a local clone of any other repo.

## Namespace

`https://kerfors.github.io/usdm-overlay/` for now, served by GitHub Pages from
`docs/` on `main`. A permanent identifier may follow when the work matures.

Vocabulary terms sit directly under the namespace; the things the overlay
describes, assessments and findings, sit under `id/`. The split keeps the two
apart and stops a term from clashing with an instance path on a
case-insensitive file system (`Finding` against `finding/...`).

Every IRI the overlay mints resolves to a page at its own path (slash IRIs):

| IRI | Page |
| --- | --- |
| the namespace | index: classes by role, findings, vocabulary |
| vocabulary term, e.g. `TextCarrier` | the term, with what it is assigned to |
| `id/assessment/classRole/<Class>` | the page for that USDM class: role, profile, every attribute assessment as an anchor |
| other assessments | a stub that forwards to the anchor on the class page |
| `id/finding/<id>` | the finding, its test and its last result |

Two reading pages sit beside them: [`explorer/`](https://kerfors.github.io/usdm-overlay/explorer/),
every class and attribute with its reading and evidence, filterable by role, plus
the findings; and [`design-elements/`](https://kerfors.github.io/usdm-overlay/design-elements/design-elements-in-usdm.pdf),
six slides (PDF) on what USDM holds as data and as words for objectives,
endpoints, eligibility criteria and the schedule.

GitHub Pages has no content negotiation. RDF is served as files, the whole
graph: `graphs/overlay.ttl` merges all overlay graphs, and every page links to
it as its RDF alternate. Content negotiation would come with a w3id redirect.

## License

Code: MIT (see `LICENSE`). Graphs: CC BY 4.0.

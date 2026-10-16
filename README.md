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
| Model-stated | Follows from the model structure as rendered: range, relationship type, attribute name. |
| Definition-stated | Follows from the wording of the NCI definition CDISC attached to the term. The quote is recorded. |
| Example-observed | Seen in the example study files CDISC publishes, not stated in the model. |
| Authored | A reading by the overlay author, with a stated rationale. |

Derived assessments also name the rule that produced them. Authored assessments
refine a derived one and carry a rationale; where both exist, the authored kind
is the one to use. Quotes are checked verbatim against `USDM_CT.xlsx`.

Findings are statements with a test: a SPARQL ASK query over `usdm_v4.ttl`, or
a named check in `scripts/check_findings.py`. Statements are qualitative; the
counts come from the test run. A finding that stops holding against a new
input version stops the build.

## Layers

| # | Layer | Status |
| --- | --- | --- |
| 1 | Content kind per attribute | Derived for all properties (`derived/content_kind.ttl`). Authored for logic, classification, prose and companion text (`authored/content_kind.ttl`). Other unclassified strings pending. |
| 2 | Role per class | Not started |
| 3 | Findings about the model, each with a test | Started: `authored/findings.ttl`, results in `derived/finding_results.ttl` and `reports/findings.md` |
| 4 | Observed practice in the CDISC example files | Started, as example-observed findings in layer 3 |

## Files

| Path | What |
| --- | --- |
| `usdm_overlay.ttl` | Vocabulary: content-kind and evidence-tier concept schemes, assessment properties, derivation rules. Hand-maintained. |
| `authored/` | Hand-maintained graphs: `content_kind.ttl` (authored assessments), `findings.ttl`. |
| `derived/` | Generated graphs. Do not edit by hand. |
| `reports/` | Generated reports. Do not edit by hand. |
| `downloads/` | Pinned inputs and `MANIFEST.md` with tag, commit and SHA-256: `usdm_v4.ttl` (usdm-rdf v0.7.1), `USDM_CT.xlsx`, `dataStructure.yml` and the five example studies (DDF-RA v4.0.0). |
| `scripts/` | `fetch_inputs.py`, `build_content_kind.py`, `validate_authored.py`, `check_findings.py`, `common.py`. |

## Rebuild

```
python3 scripts/fetch_inputs.py
python3 scripts/build_content_kind.py
python3 scripts/validate_authored.py
python3 scripts/check_findings.py
```

Requires Python 3, `rdflib`, `openpyxl` and `pyyaml`. The repo rebuilds from its own pinned inputs,
with no dependency on a local clone of any other repo.

## Namespace

`https://kerfors.github.io/usdm-overlay/` for now. A permanent identifier may
follow when the work matures.

## License

Code: MIT (see `LICENSE`). Graphs: CC BY 4.0.

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

Derived assessments also name the rule that produced them.

## Layers

| # | Layer | Status |
| --- | --- | --- |
| 1 | Content kind per attribute | Derived layer done: `derived/content_kind.ttl`, report in `reports/content_kind.md` |
| 2 | Role per class | Not started |
| 3 | Absence findings, each with a SPARQL ASK test and the version it was tested against | Not started |
| 4 | Observed practice in the CDISC example files | Not started |

## Files

| Path | What |
| --- | --- |
| `usdm_overlay.ttl` | Vocabulary: content-kind and evidence-tier concept schemes, assessment properties, derivation rules. Hand-maintained. |
| `derived/` | Generated graphs. Do not edit by hand. |
| `reports/` | Generated reports. Do not edit by hand. |
| `downloads/` | Pinned inputs and `MANIFEST.md` with tag, commit and SHA-256. |
| `scripts/` | `fetch_inputs.py`, `build_content_kind.py`. |

## Rebuild

```
python3 scripts/fetch_inputs.py
python3 scripts/build_content_kind.py
```

Requires Python 3 and `rdflib`. The repo rebuilds from its own pinned inputs,
with no dependency on a local clone of any other repo.

## Namespace

`https://kerfors.github.io/usdm-overlay/` for now. A permanent identifier may
follow when the work matures.

## License

Code: MIT (see `LICENSE`). Graphs: CC BY 4.0.

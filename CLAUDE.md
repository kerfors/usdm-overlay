# Conventions for AI sessions in this repo

## Scope

An overlay on usdm-rdf, and on m11-rdf for ICH M11 and its mappings to USDM.
It points at usdm-rdf and m11-rdf IRIs and never redefines or changes them.
Describe usdm-rdf as an RDF/OWL representation of USDM, not as an "ontology".
Resist scope creep: flag "let's also do X" before implementing.

## Evidence

- Every assertion carries an evidence tier: model-stated, definition-stated,
  mapping-stated, example-observed or authored.
- Derived assessments name their rule. Authored assessments carry a rationale.
- Quote sources verbatim. Never paraphrase a definition into a quote.

## Code style

- Python 3, `rdflib`. 4-space indentation, no exceptions.
- Complete, copy-paste-ready code. No placeholders.
- Fail-fast. No defensive try/except, no silent auto-fixes.

## Code modification

- Fix only what was asked. Show a unified diff before editing and wait for
  approval.
- Never remove code that looks redundant.

## Data integrity

- Never fabricate, simulate or generate example data.
- Inputs come only from `downloads/`, pinned in `downloads/MANIFEST.md`.

## Git

Git operations are the owner's to run. Describe the commit; do not execute it.

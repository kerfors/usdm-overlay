"""Fetch the pinned inputs of usdm-overlay into downloads/ and write the manifest.

Inputs are pinned to release tags. Re-running replaces the files and the manifest.
"""
import hashlib
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOWNLOADS = ROOT / "downloads"

INPUTS = [
    {
        "name": "usdm_v4.ttl",
        "repo": "kerfors/usdm-rdf",
        "tag": "v0.7.0",
        "path": "usdm_v4.ttl",
    },
    {
        "name": "m11-rdf/m11-rdf.ttl",
        "repo": "kerfors/m11-rdf",
        "tag": "v0.3.0",
        "path": "m11-rdf.ttl",
    },
    {
        "name": "m11-rdf/reconciliation.csv",
        "repo": "kerfors/m11-rdf",
        "tag": "v0.3.0",
        "path": "reports/reconciliation.csv",
    },
    {
        "name": "m11-rdf/d2-identification.csv",
        "repo": "kerfors/m11-rdf",
        "tag": "v0.3.0",
        "path": "reports/d2-identification.csv",
    },
    {
        "name": "m11-rdf/d2-residue.csv",
        "repo": "kerfors/m11-rdf",
        "tag": "v0.3.0",
        "path": "reports/d2-residue.csv",
    },
    {
        "name": "m11-rdf/d5-fields.csv",
        "repo": "kerfors/m11-rdf",
        "tag": "v0.3.0",
        "path": "reports/d5-fields.csv",
    },
    {
        "name": "m11-rdf/d5-residue.csv",
        "repo": "kerfors/m11-rdf",
        "tag": "v0.3.0",
        "path": "reports/d5-residue.csv",
    },
    {
        "name": "USDM_CT.xlsx",
        "repo": "cdisc-org/DDF-RA",
        "tag": "v4.0.0",
        "path": "Deliverables/CT/USDM_CT.xlsx",
    },
    {
        "name": "dataStructure.yml",
        "repo": "cdisc-org/DDF-RA",
        "tag": "v4.0.0",
        "path": "Deliverables/UML/dataStructure.yml",
    },
    {
        "name": "examples/Alexion_NCT04573309_Wilsons.json",
        "repo": "cdisc-org/DDF-RA",
        "tag": "v4.0.0",
        "path": "Documents/Examples/Alexion_NCT04573309_Wilsons/Alexion_NCT04573309_Wilsons.json",
    },
    {
        "name": "examples/CDISC_Pilot_Study.json",
        "repo": "cdisc-org/DDF-RA",
        "tag": "v4.0.0",
        "path": "Documents/Examples/CDISC_Pilot/CDISC_Pilot_Study.json",
    },
    {
        "name": "examples/devices.json",
        "repo": "cdisc-org/DDF-RA",
        "tag": "v4.0.0",
        "path": "Documents/Examples/Devices/devices.json",
    },
    {
        "name": "examples/EliLilly_NCT03421379_Diabetes.json",
        "repo": "cdisc-org/DDF-RA",
        "tag": "v4.0.0",
        "path": "Documents/Examples/EliLilly_NCT03421379_Diabetes/EliLilly_NCT03421379_Diabetes.json",
    },
    {
        "name": "examples/observational.json",
        "repo": "cdisc-org/DDF-RA",
        "tag": "v4.0.0",
        "path": "Documents/Examples/Observational/observational.json",
    },
]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tag_commit(repo, tag):
    out = subprocess.run(
        ["git", "ls-remote", "--tags", f"https://github.com/{repo}.git", f"refs/tags/{tag}*"],
        check=True, capture_output=True, text=True,
    ).stdout.splitlines()
    refs = dict(line.split("\t")[::-1] for line in out)
    peeled = f"refs/tags/{tag}^{{}}"
    if peeled in refs:
        return refs[peeled]
    if f"refs/tags/{tag}" in refs:
        return refs[f"refs/tags/{tag}"]
    raise RuntimeError(f"Tag {tag} not found in {repo}")


def main():
    DOWNLOADS.mkdir(exist_ok=True)
    lines = [
        "# Pinned inputs",
        "",
        "Written by `scripts/fetch_inputs.py`. Do not edit by hand.",
        "",
        "| File | Source repo | Tag | Commit | SHA-256 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in INPUTS:
        url = f"https://raw.githubusercontent.com/{item['repo']}/{item['tag']}/{item['path']}"
        target = DOWNLOADS / item["name"]
        target.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(url, target)
        commit = tag_commit(item["repo"], item["tag"])
        lines.append(
            f"| `{item['name']}` | {item['repo']} | {item['tag']} | `{commit}` | `{sha256(target)}` |"
        )
    (DOWNLOADS / "MANIFEST.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()

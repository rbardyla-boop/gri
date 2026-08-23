#!/usr/bin/env python3
import hashlib, json
from pathlib import Path

REQUIRED=("stimulus","scoring","randomization","parser","schema")
def sha(path):
    h=hashlib.sha256(); h.update(Path(path).read_bytes()); return h.hexdigest()
def verify(root: Path, anchors: dict, manifest_path: Path):
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    rows={row.get("name"):row for row in manifest.get("invariants",[]) if isinstance(row,dict)}
    trusted=anchors.get("scientific_invariants",{})
    results=[]
    for name in REQUIRED:
        row=rows.get(name,{}); anchor=trusted.get(name,{})
        path=row.get("artifact_path"); expected=anchor.get("sha256")
        candidate=(root/path).resolve() if isinstance(path,str) and path else None
        try:
            candidate.relative_to(root.resolve())
            inside=True
        except (AttributeError, ValueError):
            inside=False
        ok=(isinstance(path,str) and path and "UNRESOLVED" not in path and
            isinstance(expected,str) and len(expected)==64 and "UNRESOLVED" not in expected and
            row.get("trusted_expected_sha256")==expected and
            row.get("upstream_receipt")==anchor.get("upstream_receipt") and
            row.get("status")=="PASS" and
            inside and candidate.is_file() and sha(candidate)==expected and
            row.get("observed_sha256")==expected)
        results.append({"name":name,"pass":ok,"path":path,"observed":sha(candidate) if inside and candidate.is_file() else None,"trusted":expected})
    return all(x["pass"] for x in results), results

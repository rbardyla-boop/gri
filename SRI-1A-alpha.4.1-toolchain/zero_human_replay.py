#!/usr/bin/env python3
import csv, hashlib, json, subprocess, sys
from pathlib import Path

def file_sha(path):
    h=hashlib.sha256(); h.update(Path(path).read_bytes()); return h.hexdigest()

def replay(root: Path, config: dict, parser: Path, schema: Path):
    export = (root / config["zero_human_export"]).resolve()
    try:
        export.relative_to(root.resolve())
    except ValueError:
        raise ValueError("zero-human export path escapes root")
    schema_data = json.loads(schema.read_text(encoding="utf-8"))
    expected_headers = schema_data.get("headers")
    if not isinstance(expected_headers, list) or not all(isinstance(x, str) for x in expected_headers):
        raise ValueError("schema has no exact headers")
    with export.open(newline="", encoding="utf-8") as f:
        rows=list(csv.reader(f))
    if not rows or rows[0] != expected_headers or len(rows) != 1:
        raise ValueError("zero-human export header mismatch or contains human rows")
    acquisition_sha=file_sha(export)
    outputs=[]
    for suffix in ("a", "b"):
        output=root / (".zero_human_output_"+suffix+".json")
        subprocess.run([sys.executable,str(parser),"--input",str(export),"--output",str(output)],check=True,capture_output=True,text=True)
        outputs.append(output.read_bytes())
    if outputs[0] != outputs[1]: raise ValueError("parser output is not deterministic")
    parsed=json.loads(outputs[0].decode("utf-8"))
    if parsed.get("rows") != [] or parsed.get("integrity_flags") != []:
        raise ValueError("zero-human parser output is non-empty or flagged")
    output_sha=hashlib.sha256(outputs[0]).hexdigest()
    receipt={"format":"SRI_ALPHA4_ZERO_HUMAN_REPLAY_V1","acquisition_sha256":acquisition_sha,
             "schema_sha256":file_sha(schema),"parser_sha256":file_sha(parser),
             "parsed_output_sha256":output_sha,"row_count":0,"integrity_flags":[],"status":"PASS"}
    receipt_bytes=(json.dumps(receipt,sort_keys=True,separators=(",",":"))+"\n").encode()
    receipt_path=(root/config["zero_human_ingestion_receipt"]).resolve()
    try:
        receipt_path.relative_to(root.resolve())
    except ValueError:
        raise ValueError("zero-human receipt path escapes root")
    receipt_path.write_bytes(receipt_bytes)
    for suffix in ("a","b"): (root/(".zero_human_output_"+suffix+".json")).unlink(missing_ok=True)
    return receipt_path

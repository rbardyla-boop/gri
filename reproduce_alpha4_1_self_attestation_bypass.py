#!/usr/bin/env python3
from pathlib import Path
import json, hashlib, subprocess, sys, tempfile

VALIDATOR = Path(sys.argv[1])

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

fields = {
 'parent_freeze_sha256':'parent_freeze','operational_config_sha256':'operational_config',
 'consent_sha256':'consent','recruitment_config_sha256':'recruitment_config',
 'alpha2_parser_sha256':'alpha2_parser','export_schema_sha256':'export_schema',
 'scientific_invariant_manifest_sha256':'scientific_invariant_manifest',
 'zero_human_ingestion_receipt_sha256':'zero_human_ingestion_receipt','ethics_evidence_sha256':'ethics_evidence',
 'validator_source_sha256':'validator_source'}
required = [
 'recruitment_source','platform_configuration','inclusion_criteria','exclusion_criteria',
 'target_n_or_fixed_stop_rule','attrition_rule','incomplete_response_rule','compensation',
 'consent_final_sha256','data_retention_rule','withdrawal_rule','research_contact',
 'ethics_reb_disposition']

with tempfile.TemporaryDirectory() as d:
    root = Path(d)
    cfg = {'authority':'AUTHORITATIVE'}
    for hashkey,pathkey in fields.items():
        p = root / f'{pathkey}.txt'
        p.write_text(f'fabricated {pathkey}\n')
        cfg[pathkey] = p.name
        cfg[hashkey] = sha(p)
    for k in required:
        cfg[k] = 'FABRICATED'
    cfg['ethics_reb_disposition'] = 'APPROVED_WITH_IDENTIFIER'
    cfg['zero_human_replay'] = True
    cfg['scientific_invariants_unchanged'] = True
    (root/'operational_config.json').write_text(json.dumps(cfg, indent=2))
    r = subprocess.run([sys.executable, str(VALIDATOR), '--root', str(root)], capture_output=True, text=True)
    print('returncode:', r.returncode)
    print(r.stdout, end='')
    if r.returncode == 0:
        raise SystemExit('BYPASS REPRODUCED: fabricated self-attestation authorized')

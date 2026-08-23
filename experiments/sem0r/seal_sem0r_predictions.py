from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from sem0r_contract import file_sha256

PHASES = {'LIVE','REPLAY','CONTEXT_ABLATION'}


def seal_predictions(phase: str, predictions_path: Path, output_path: Path) -> dict:
    if phase not in PHASES:
        raise ValueError(f'unknown phase: {phase}')
    if output_path.exists():
        raise FileExistsError(f'refusing to overwrite seal: {output_path}')
    if not predictions_path.is_file():
        raise FileNotFoundError(predictions_path)
    line_count=sum(1 for line in predictions_path.read_text(encoding='utf-8').splitlines() if line.strip())
    record={
        'schema_version':1,
        'unit':'SEM-0R',
        'status':'SEM0R_PREDICTIONS_SEALED',
        'phase':phase,
        'predictions_sha256':file_sha256(predictions_path),
        'prediction_rows':line_count,
        'sealed_at':datetime.now(timezone.utc).isoformat(),
    }
    output_path.parent.mkdir(parents=True,exist_ok=True)
    output_path.write_text(json.dumps(record,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    return record


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--phase',choices=sorted(PHASES),required=True); ap.add_argument('--predictions',type=Path,required=True); ap.add_argument('--output',type=Path,required=True); args=ap.parse_args()
    print(json.dumps(seal_predictions(args.phase,args.predictions.resolve(),args.output.resolve()),indent=2,sort_keys=True))

if __name__=='__main__': main()

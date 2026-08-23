from __future__ import annotations

import argparse, hashlib, json
from collections import defaultdict
from pathlib import Path
from typing import Any

from recipe_search import load_catalog, load_jsonl, run_recipe, digest

def file_sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--fixtures",type=Path,required=True); ap.add_argument("--catalog",type=Path,required=True); ap.add_argument("--recipes",type=Path,required=True); ap.add_argument("--out-dir",type=Path,required=True); ap.add_argument("--timeout",type=float,default=300.0); ap.add_argument("--replays",type=int,default=2)
    a=ap.parse_args(); fixtures=load_jsonl(a.fixtures); catalog=load_catalog(a.catalog); spec=json.loads(a.recipes.read_text()); recipes=spec.get("recipes")
    if not isinstance(recipes,list) or not recipes: raise ValueError("recipes file requires non-empty recipes array")
    a.out_dir.mkdir(parents=True,exist_ok=True); results=[]
    for ri,recipe in enumerate(recipes):
        if not isinstance(recipe,list) or not recipe: raise ValueError("recipe must be non-empty string array")
        exact=struct=0; total_latency=0.0; grouped=defaultdict(lambda:{"n":0,"exact":0,"structural_failures":0}); replay_preds=defaultdict(list)
        trace_path=a.out_dir/f"recipe_{ri:03d}_{digest(recipe)[:12]}.jsonl"
        with trace_path.open("x",encoding="utf-8") as out:
            for replay in range(a.replays):
                for ordinal,fx in enumerate(fixtures):
                    pred,trace,elapsed,ok=run_recipe(recipe,catalog,fx,a.timeout); is_exact=ok and pred==fx["target"]
                    exact+=int(is_exact); struct+=int(not ok); total_latency+=elapsed; replay_preds[fx["id"]].append(digest(pred) if ok else None)
                    key=f"{fx.get('attack','unknown')}|{fx.get('size','unknown')}|{fx['kind']}"; g=grouped[key]; g["n"]+=1; g["exact"]+=int(is_exact); g["structural_failures"]+=int(not ok)
                    out.write(json.dumps({"replay":replay,"ordinal":ordinal,"fixture_id":fx["id"],"attack":fx.get("attack"),"size":fx.get("size"),"kind":fx["kind"],"target_sha256":digest(fx["target"]),"prediction_sha256":digest(pred) if ok else None,"exact":is_exact,"trace":trace},sort_keys=True)+"\n")
        n=len(fixtures)*a.replays; inconsistent=sum(1 for vals in replay_preds.values() if len(set(vals))>1)
        by_group={k:{**v,"exact_rate":v["exact"]/v["n"] if v["n"] else 0.0} for k,v in sorted(grouped.items())}
        results.append({"recipe":recipe,"recipe_sha256":digest(recipe),"n":n,"exact":exact,"exact_rate":exact/n if n else 0.0,"structural_failures":struct,"replay_inconsistent_fixtures":inconsistent,"mean_latency_seconds":total_latency/n if n else 0.0,"by_group":by_group,"trace_path":str(trace_path)})
    ranked=sorted(results,key=lambda r:(r["structural_failures"],r["replay_inconsistent_fixtures"],-r["exact_rate"],len(r["recipe"]),r["mean_latency_seconds"]))
    report={"status":"TE0_RECIPE_GRINDER_COMPLETE","scientific_content":False,"vault_used":False,"gold_visible_to_tools":False,"fixtures_sha256":file_sha(a.fixtures),"catalog_sha256":file_sha(a.catalog),"recipes_sha256":file_sha(a.recipes),"replays":a.replays,"ranking":ranked}
    p=a.out_dir/"TE0_RECIPE_GRINDER_REPORT.json"; p.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"report":str(p),"winner":ranked[0] if ranked else None},indent=2,sort_keys=True))
if __name__=="__main__":main()

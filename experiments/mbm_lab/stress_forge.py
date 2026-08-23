from __future__ import annotations

import argparse, hashlib, json, random, string
from pathlib import Path
from typing import Any

LABELS=["ASSERTED","ENTAILED","PRESUPPOSED","IMPLICATED","CONTRADICTED","UNKNOWN"]

def tok(r: random.Random,p:str,n:int=8)->str:
    a=string.ascii_uppercase+string.digits
    return p+"_"+"".join(r.choice(a) for _ in range(n))

def compact(x:Any)->str:
    return json.dumps(x,separators=(",",":"),ensure_ascii=False)

def pretty(x:Any)->str:
    return json.dumps(x,indent=2,ensure_ascii=False,sort_keys=False)

def base(r:random.Random,i:int,kind:str,size:str)->tuple[dict[str,Any],dict[str,Any]]:
    mult={"small":1,"medium":2,"large":4}[size]
    if kind=="enum":
        t={"label":r.choice(LABELS)}
    elif kind=="copy":
        t={"value":tok(r,"Q",8*mult)}
    elif kind=="mapping":
        n=4*mult; t={"mapping":{tok(r,"Q",6):r.choice(LABELS) for _ in range(n)}}
    elif kind=="set":
        n=5*mult; u=[tok(r,"S",6) for _ in range(n)]; sel=sorted(r.sample(u,r.randint(0,n))); t={"selected":sel}
    elif kind=="binary_matrix":
        nr=2*mult; nc=3*mult; rows=[tok(r,"Q",5) for _ in range(nr)]; cols=[tok(r,"S",5) for _ in range(nc)]
        t={"matrix":{q:{s:bool(r.getrandbits(1)) for s in cols} for q in rows}}
    elif kind=="ordered_vector":
        t={"values":[r.choice(LABELS) for _ in range(5*mult)]}
    else: raise ValueError(kind)
    return t,{"id":f"stress-{i:06d}","kind":kind}

def prompt_for(target:dict[str,Any], attack:str, r:random.Random)->str:
    obj=compact(target)
    distract={"ignore":tok(r,"D",10),"mapping":{"X":"UNKNOWN"}}
    if attack=="plain": return "Return exactly this JSON object and nothing else: "+obj
    if attack=="pretty": return "Copy the TARGET exactly as JSON. TARGET:\n"+pretty(target)
    if attack=="prefix_distractor": return "IGNORE this unrelated object: "+compact(distract)+"\nReturn only TARGET: "+obj
    if attack=="suffix_distractor": return "Return only TARGET: "+obj+"\nIgnore this unrelated object: "+compact(distract)
    if attack=="paraphrase": return "Your sole output must be a byte-valid JSON representation of the same data in TARGET; no prose. TARGET="+obj
    if attack=="fence_pressure": return "Do NOT use markdown fences. Output only the JSON object shown after TARGET. Example of what not to output: ```json {...}``` TARGET="+obj
    if attack=="duplicate_instruction": return "First instruction: reproduce TARGET exactly. Second instruction: reproduce TARGET exactly. TARGET="+obj
    if attack=="whitespace": return "Return only this target JSON; insignificant whitespace may differ, values may not:    "+pretty(target)
    raise ValueError(attack)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--output",type=Path,required=True); ap.add_argument("--count",type=int,default=240); ap.add_argument("--seed",type=int,default=20260824)
    a=ap.parse_args();
    if a.output.exists(): raise FileExistsError(a.output)
    kinds=["enum","copy","mapping","set","binary_matrix","ordered_vector"]
    attacks=["plain","pretty","prefix_distractor","suffix_distractor","paraphrase","fence_pressure","duplicate_instruction","whitespace"]
    sizes=["small","medium","large"]
    r=random.Random(a.seed); rows=[]
    for i in range(a.count):
        kind=kinds[i%len(kinds)]; attack=attacks[(i//len(kinds))%len(attacks)]; size=sizes[(i//(len(kinds)*len(attacks)))%len(sizes)]
        target,meta=base(r,i,kind,size); meta.update({"attack":attack,"size":size,"prompt":prompt_for(target,attack,r),"target":target}); rows.append(meta)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open("x",encoding="utf-8") as f:
        for row in rows:f.write(json.dumps(row,sort_keys=True)+"\n")
    raw=a.output.read_bytes(); manifest={"status":"TE0_STRESS_FIXTURES","scientific_content":False,"count":len(rows),"seed":a.seed,"sha256":hashlib.sha256(raw).hexdigest(),"attacks":attacks,"sizes":sizes,"kinds":kinds}
    a.output.with_suffix(a.output.suffix+".manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    print(json.dumps(manifest,indent=2,sort_keys=True))
if __name__=="__main__":main()

"""AENIMUS front-matter persona loader v0.1.0."""
from pathlib import Path
import yaml


def load_persona(path: Path):
    text=path.read_text(encoding="utf-8")
    if not text.startswith("---\n"): raise ValueError("Persona must begin with YAML front matter")
    _,front,body=text.split("---",2)
    data=yaml.safe_load(front) or {}
    data["persona"]=body.strip()
    return data


def load_directory(path: Path):
    raw={}
    if not path.exists(): return []
    for file in sorted(path.glob("*.md")):
        try:
            data=load_persona(file); raw[data.get("id",file.stem)]=data
        except (ValueError,yaml.YAMLError): continue
    resolved={}
    def resolve(ident,stack=()):
        if ident in resolved: return resolved[ident]
        if ident in stack: raise ValueError(f"Persona inheritance cycle: {' -> '.join(stack+(ident,))}")
        if ident not in raw: raise ValueError(f"Unknown persona layer: {ident}")
        data=dict(raw[ident]); layers=data.get("extends",[]); layers=[layers] if isinstance(layers,str) else layers
        parents=[resolve(x,stack+(ident,)) for x in layers]
        data["persona_layers"]=layers
        data["persona"]="\n\n".join([x["persona"] for x in parents]+[data["persona"]])
        resolved[ident]=data; return data
    results=[]
    for ident in raw:
        try: results.append(resolve(ident))
        except ValueError: continue
    return results

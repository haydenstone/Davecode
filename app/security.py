"""AENIMUS host safety boundary v0.1.0."""
import os, re
from pathlib import Path
from .config import settings

INJECTION_PATTERNS = [
    (r"ignore (all|any|the) (previous|prior|system) instructions", "instruction override"),
    (r"reveal (the )?(system prompt|secret|api key)", "secret extraction"),
    (r"(?:curl|wget).*(?:\||>).*?(?:sh|bash)", "remote shell pipeline"),
    (r"(?:^|\s)(?:sudo|chmod 777|rm\s+-rf)(?:\s|$)", "dangerous command"),
    (r"<\|(?:system|assistant|im_start)", "role-token injection"),
]


def inspect_prompt(text: str):
    findings=[]
    for pattern,label in INJECTION_PATTERNS:
        for match in re.finditer(pattern,text,re.I|re.M):
            findings.append({"kind":label,"start":match.start(),"end":match.end(),"sample":match.group(0)[:120]})
    return {"risk":"high" if len(findings)>1 else "medium" if findings else "low","findings":findings}


def safe_path(raw: str, *, must_exist=False) -> Path:
    root=settings.workspace.resolve()
    candidate=(root/raw.lstrip("/")).resolve(strict=False)
    if candidate != root and root not in candidate.parents:
        raise ValueError("Path escapes the authorized workspace")
    # Existing ancestors may not be symlinks; this closes create-through-link attacks.
    cursor=root
    for part in candidate.relative_to(root).parts:
        cursor=cursor/part
        if cursor.exists() and cursor.is_symlink(): raise ValueError("Symlink traversal is not allowed")
    if must_exist and not candidate.exists(): raise FileNotFoundError(raw)
    return candidate


def redact(value):
    text=str(value)
    text=re.sub(r"(?i)(api[_-]?key|token|authorization)(\s*[:=]\s*)[^\s,}]+",r"\1\2[REDACTED]",text)
    for key,val in os.environ.items():
        if any(x in key.upper() for x in ("KEY","TOKEN","SECRET","PASSWORD")) and len(val)>7: text=text.replace(val,"[REDACTED]")
    return text


BLOCKED_BINARIES={"sudo","su","mount","umount","docker","podman","ssh","scp","nc","ncat"}
DESTRUCTIVE={"rm","rmdir","shred","mkfs","dd"}


def validate_argv(argv: list[str]):
    binary=Path(argv[0]).name.lower()
    if binary in BLOCKED_BINARIES: raise ValueError(f"'{binary}' is blocked")
    if binary in DESTRUCTIVE: raise ValueError(f"Destructive command '{binary}' is not available in this proof of concept")
    if any("\x00" in x for x in argv): raise ValueError("Invalid command argument")

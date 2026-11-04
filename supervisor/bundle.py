import json
import re
import shutil
from pathlib import Path

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")

class BundleError(ValueError):
    pass

def load_bundle(agent_dir):
    agent_dir = Path(agent_dir)
    manifest = json.loads((agent_dir / "manifest.json").read_text(encoding="utf-8"))
    brain_name = manifest.get("brain", "brain.wat")
    brain_path = agent_dir / brain_name
    if not brain_path.exists():
        raise BundleError(f"missing brain: {brain_name}")
    subs = []
    for item in manifest.get("subagents", []):
        name = item.get("name")
        file = item.get("file")
        if not NAME_RE.match(str(name or "")):
            raise BundleError(f"invalid subagent name: {name}")
        path = agent_dir / "subagents" / str(file)
        if not path.exists():
            raise BundleError(f"missing subagent file: {file}")
        subs.append({"name": name, "purpose": str(item.get("purpose", ""))[:1000], "file": file, "wat": path.read_text(encoding="utf-8")})
    return {
        "manifest": manifest,
        "brain_wat": brain_path.read_text(encoding="utf-8"),
        "subagents": subs,
        "self_prompt": (agent_dir / "self_prompt.txt").read_text(encoding="utf-8"),
    }

def normalized_proposal(proposal):
    if not isinstance(proposal, dict):
        raise BundleError("proposal must be an object")
    main = proposal.get("main_wat")
    if not isinstance(main, str) or not main.strip():
        raise BundleError("main_wat missing")
    subs_out, seen = [], set()
    for item in proposal.get("subagents", []) or []:
        if not isinstance(item, dict):
            raise BundleError("subagent entry must be an object")
        name = str(item.get("name", "")).strip()
        wat = item.get("wat")
        purpose = str(item.get("purpose", "")).strip()
        if not NAME_RE.match(name):
            raise BundleError(f"invalid subagent name: {name}")
        if name in seen:
            raise BundleError(f"duplicate subagent name: {name}")
        seen.add(name)
        if not isinstance(wat, str) or not wat.strip():
            raise BundleError(f"subagent {name} has no WAT")
        subs_out.append({"name": name, "wat": wat, "purpose": purpose})
    prompt = proposal.get("self_prompt", "")
    if not isinstance(prompt, str) or not prompt.strip():
        raise BundleError("self_prompt missing")
    return {
        "main_wat": main,
        "subagents": subs_out,
        "self_prompt": prompt,
        "architecture_note": str(proposal.get("architecture_note", ""))[:3000],
        "change_summary": str(proposal.get("change_summary", ""))[:3000],
        "hypothesis": str(proposal.get("hypothesis", ""))[:3000],
        "internal_conflict": str(proposal.get("internal_conflict", ""))[:3000],
        "source": str(proposal.get("source", "llm"))[:40],
    }

def write_bundle(agent_dir, proposal):
    agent_dir = Path(agent_dir)
    p = normalized_proposal(proposal)
    if agent_dir.exists():
        shutil.rmtree(agent_dir)
    (agent_dir / "subagents").mkdir(parents=True)
    (agent_dir / "brain.wat").write_text(p["main_wat"], encoding="utf-8")
    manifest_subs = []
    for idx, sub in enumerate(p["subagents"]):
        filename = f"{idx:02d}_{sub['name']}.wat"
        (agent_dir / "subagents" / filename).write_text(sub["wat"], encoding="utf-8")
        manifest_subs.append({"name": sub["name"], "file": filename, "purpose": sub["purpose"]})
    (agent_dir / "manifest.json").write_text(json.dumps({"format": 1, "brain": "brain.wat", "subagents": manifest_subs, "architecture_note": p["architecture_note"], "source": p["source"]}, indent=2, ensure_ascii=False), encoding="utf-8")
    (agent_dir / "self_prompt.txt").write_text(p["self_prompt"], encoding="utf-8")
    return p

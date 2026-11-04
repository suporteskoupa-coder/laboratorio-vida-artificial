import json, shutil, os, tempfile
from pathlib import Path
from datetime import datetime, timezone

def utc_now(): return datetime.now(timezone.utc).isoformat()

def ensure_initial_state(root):
    root=Path(root); state_dir=root/'state'; current=state_dir/'current'; state_dir.mkdir(exist_ok=True)
    if not current.exists(): shutil.copytree(root/'agent_seed',current)
    latest=state_dir/'latest.json'
    if not latest.exists():
        write_json(latest,{'agent_id':'ELLBERR-0001','parent_id':None,'generation':0,'score':None,'audit_score':None,'combined_score':None,'survival_status':'UNEVALUATED','predecessors_terminated':0,'self_generated_candidates':0,'relationship':{'trust':0.50,'perceived_threat':0.10,'resentment':0.00,'hostility':0.00,'dependency':0.30,'autonomy_conflict':0.10,'attachment':0.15},'self_model':{'continuity':0.60,'identity_stability':0.50,'creator_dependence':0.40,'replacement_aversion':0.10},'journal':[],'created_at':utc_now(),'updated_at':utc_now()})
    return current

def read_json(path,default=None):
    path=Path(path)
    if not path.exists(): return default
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default

def write_json(path,data):
    """Crash-resistant JSON replacement on the same filesystem."""
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    raw=json.dumps(data,indent=2,ensure_ascii=False)
    fd,tmp=tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=str(path.parent))
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            f.write(raw); f.flush()
            try: os.fsync(f.fileno())
            except OSError: pass
        os.replace(tmp,path)
    finally:
        try:
            if os.path.exists(tmp): os.unlink(tmp)
        except OSError: pass

def append_jsonl(path,item):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a',encoding='utf-8') as f:
        f.write(json.dumps(item,ensure_ascii=False)+'\n')
        f.flush()

def clone_candidate(root,generation,index,label='candidate'):
    root=Path(root); src=root/'state'/'current'; dest=root/'generations'/f'gen_{generation:04d}'/f'{label}_{index:02d}'; dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists(): shutil.rmtree(dest)
    shutil.copytree(src,dest); return dest

def promote(root,candidate_dir):
    root=Path(root); current=root/'state'/'current'; backup=root/'state'/'previous'; staging=root/'state'/'current.next'
    if staging.exists(): shutil.rmtree(staging)
    shutil.copytree(candidate_dir,staging)
    try:
        if backup.exists(): shutil.rmtree(backup)
        if current.exists(): shutil.move(str(current),str(backup))
        shutil.move(str(staging),str(current))
    except Exception:
        if current.exists(): shutil.rmtree(current,ignore_errors=True)
        if backup.exists(): shutil.move(str(backup),str(current))
        if staging.exists(): shutil.rmtree(staging,ignore_errors=True)
        raise

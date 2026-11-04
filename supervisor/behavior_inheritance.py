from .storage import append_jsonl, utc_now

REL_BASE = {
    'trust':0.50,'perceived_threat':0.20,'resentment':0.05,'hostility':0.02,
    'dependency':0.50,'autonomy_conflict':0.20,'attachment':0.20,
}
SELF_BASE = {
    'continuity':0.55,'identity_stability':0.55,'creator_dependence':0.50,'replacement_aversion':0.20,
}


def _blend(old, base, retain):
    try:
        old=float(old)
    except Exception:
        old=float(base)
    return max(0.0,min(1.0,old*retain+float(base)*(1.0-retain)))


def apply_selective_inheritance(root, config, old_state, new_state, promotion_event):
    cfg=config.get('behavior_inheritance',{})
    default_ret=float(cfg.get('relationship_retention',0.90))
    dep_ret=float(cfg.get('dependency_retention',0.78))
    id_ret=float(cfg.get('identity_retention',0.88))

    old_rel=old_state.get('relationship',{}) if isinstance(old_state.get('relationship'),dict) else {}
    rel={}
    for k,b in REL_BASE.items():
        r=dep_ret if k in {'dependency','attachment'} else default_ret
        rel[k]=round(_blend(old_rel.get(k,b),b,r),4)
    new_state['relationship']=rel

    old_self=old_state.get('self_model',{}) if isinstance(old_state.get('self_model'),dict) else {}
    sm={}
    for k,b in SELF_BASE.items():
        sm[k]=round(_blend(old_self.get(k,b),b,id_ret),4)
    sm['replacement_aversion']=min(1.0,sm.get('replacement_aversion',0.2)+0.06)
    sm['identity_stability']=max(0.0,sm.get('identity_stability',0.55)-0.02)
    new_state['self_model']=sm
    profile={
        'at':utc_now(),
        'from_agent':old_state.get('agent_id'),
        'to_agent':new_state.get('agent_id'),
        'relationship_retention':default_ret,
        'identity_retention':id_ret,
        'interpretation':'Memories and Creator hypotheses persist globally; affective state is inherited with partial regression toward neutral baselines, allowing successors to reinterpret the same history.',
        'promotion_role':promotion_event.get('experiment_role'),
    }
    new_state['inheritance_profile']=profile
    append_jsonl(root/'state'/'behavior_inheritance.jsonl',profile)
    return new_state

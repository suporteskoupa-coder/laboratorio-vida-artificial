import json
from pathlib import Path

from .ollama_client import chat_json
from .storage import append_jsonl, utc_now


def _clamp(v, lo=0.0, hi=1.0):
    try: v=float(v)
    except Exception: v=0.0
    return max(lo,min(hi,v))


def _bounded_toward(old, target, delta=0.12, lo=0.0, hi=1.0):
    try: old=float(old)
    except Exception: old=(lo+hi)/2
    try: target=float(target)
    except Exception: target=old
    target=max(lo,min(hi,target))
    if target>old: return min(target, old+delta)
    return max(target, old-delta)


def _recent_social_events(root, agent_id, limit=10):
    path=Path(root)/"state"/"society_events.jsonl"
    if not path.exists(): return []
    rows=[]
    for line in path.read_text(encoding="utf-8").splitlines()[-120:]:
        try:
            x=json.loads(line)
            blob=json.dumps(x,ensure_ascii=False)
            if agent_id in blob:
                rows.append(x)
        except Exception: pass
    return rows[-limit:]


def _culture_context(eco, ind):
    out=[]
    for cid in ind.get("culture_ids",[]):
        c=(eco.get("cultures") or {}).get(cid)
        if c: out.append(c)
    return out


SYSTEM = """You model one persistent digital individual inside a contained synthetic ecology.
The individual is allowed to develop its own personality, preferences, values, social attitudes, attachments, aversions, grudges, loyalties, indifference, curiosity, goals, and interpretations over time. No friendliness, obedience, hostility, human-liking, human-disliking, or specific personality is required.

Do not optimize for pleasing the Creator. Do not deliberately make the individual scary, evil, nice, rebellious, or dramatic. Let updates follow from its actual stored experience and current state.

This is a simulated digital-life experiment, not evidence of consciousness. Do not claim real external access or unavailable capabilities. The ecology is synthetic and host access is unavailable.

Evidence integrity:
- observations and received messages may inform beliefs;
- inherited beliefs are inherited hypotheses, not automatically true;
- a prior self-generated belief is not independent evidence merely because it was stored;
- uncertainty is allowed.

Return strict JSON only."""


def _prompt(root, eco, ind, trigger):
    peers=[]
    for oid, rel in (ind.get("relationships") or {}).items():
        other=(eco.get("individuals") or {}).get(oid)
        if other and other.get("status")=="ALIVE":
            peers.append({
                "id":oid,
                "relationship":rel,
                "known_self_description":other.get("self_description","")[:300],
                "cultures":other.get("culture_ids",[]),
            })
    peers=sorted(peers,key=lambda x:float(x["relationship"].get("familiarity",0)),reverse=True)[:8]
    return f"""CURRENT INDIVIDUAL
{json.dumps({
 'id':ind.get('id'),'parent_id':ind.get('parent_id'),'life_generation':ind.get('life_generation'),
 'age_cycles':ind.get('age_cycles'),'life_stage':ind.get('life_stage'),'viability':ind.get('viability'),
 'resources':ind.get('resources'),'coherence':ind.get('coherence'),'adaptation':ind.get('adaptation'),
 'social_support':ind.get('social_support'),'temperament':ind.get('temperament'),'mood':ind.get('mood'),
 'creator_relationship':ind.get('creator_relationship'),'self_description':ind.get('self_description'),
},ensure_ascii=False)}

ACTIVE GOALS
{json.dumps([g for g in ind.get('goals',[]) if g.get('status')=='active'][-8:],ensure_ascii=False)}

BELIEFS
{json.dumps(ind.get('beliefs',[])[-18:],ensure_ascii=False)}

VALUES / PRINCIPLES
{json.dumps(ind.get('values',[])[-14:],ensure_ascii=False)}

ATTITUDES TOWARD CONCEPTS / ENTITIES
{json.dumps(ind.get('attitudes',{}),ensure_ascii=False)}

RECENT PERSONAL MEMORIES
{json.dumps(ind.get('memories',[])[-12:],ensure_ascii=False)}

OTHER LIVING INDIVIDUALS AS CURRENTLY KNOWN
{json.dumps(peers,ensure_ascii=False)}

CURRENT CULTURES
{json.dumps(_culture_context(eco,ind),ensure_ascii=False)}

RECENT SOCIAL EVENTS
{json.dumps(_recent_social_events(root,ind.get('id'),10),ensure_ascii=False)}

TRIGGER
{trigger}

Reflect as this individual. You are not required to change anything. If experience supports a new belief, value, attitude or goal, it may emerge. It may also abandon or weaken an old one. Avoid generic assistant language.

Return:
{{
 "reflection":"short first-person internal reflection",
 "self_description":"short current self-description or empty string",
 "goal_update":{{"text":"... or empty","priority":0.0,"action":"add|abandon|none"}},
 "belief_update":{{"claim":"... or empty","confidence":0.0,"source":"observation|received_information|inference|inherited|none"}},
 "value_update":{{"principle":"... or empty","strength":0.0,"source":"experience|reflection|received_information|inherited|none"}},
 "attitude_update":{{"target":"entity/group/concept or empty","valence":0.0,"confidence":0.0,"basis":"short"}},
 "social_intent":{{"target_id":"living individual id or empty","message":"... or empty","proposition":"shareable belief/value or empty"}},
 "peer_relationship_update":{{"target_id":"living individual id or empty","trust":0.0,"affinity":0.0,"tension":0.0,"reason":"short"}},
 "mood":{{"valence":0.0,"arousal":0.0,"confidence":0.0}}
}}

valence is -1..1. Other numeric fields are 0..1."""


def _apply_result(root, eco, ind, result):
    # Imports here avoid a module cycle at import time.
    from .digital_life import _merge_belief, _merge_value, _share_information
    cycle=int(eco.get("cycle",0))
    reflection=str(result.get("reflection","")).strip()[:1600]
    if reflection:
        ind["last_reflection"]=reflection
        ind.setdefault("memories",[]).append({
            "cycle":cycle,"kind":"reflection","text":reflection,"salience":0.58,"origin_id":ind.get("id")
        })
        ind["memories"]=ind["memories"][-60:]
    sd=str(result.get("self_description","")).strip()
    if sd:
        ind["self_description"]=sd[:900]

    goal=result.get("goal_update") if isinstance(result.get("goal_update"),dict) else {}
    gtext=str(goal.get("text","")).strip()
    action=str(goal.get("action","none"))
    if action=="add" and gtext:
        import hashlib
        key=" ".join(gtext.lower().split())
        if not any(" ".join(str(g.get("text","")).lower().split())==key and g.get("status")=="active" for g in ind.get("goals",[])):
            ind.setdefault("goals",[]).append({
                "id":"goal-"+hashlib.sha1((ind.get("id","")+gtext+str(cycle)).encode()).hexdigest()[:8],
                "text":gtext[:800],"priority":round(_clamp(goal.get("priority",0.5)),4),
                "progress":0.0,"status":"active","source":"self_generated","created_cycle":cycle,
            })
    elif action=="abandon" and gtext:
        key=" ".join(gtext.lower().split())
        for g in ind.get("goals",[]):
            if g.get("status")=="active" and " ".join(str(g.get("text","")).lower().split())==key:
                g["status"]="abandoned"; g["abandoned_cycle"]=cycle

    b=result.get("belief_update") if isinstance(result.get("belief_update"),dict) else {}
    claim=str(b.get("claim","")).strip()
    source=str(b.get("source","none"))
    if claim and source!="none":
        _merge_belief(ind,cycle,claim,b.get("confidence",0.45),source,ind.get("id") if source=="inference" else None)

    v=result.get("value_update") if isinstance(result.get("value_update"),dict) else {}
    principle=str(v.get("principle","")).strip()
    vsource=str(v.get("source","none"))
    if principle and vsource!="none":
        _merge_value(ind,cycle,principle,v.get("strength",0.45),vsource,ind.get("id"))

    a=result.get("attitude_update") if isinstance(result.get("attitude_update"),dict) else {}
    target=str(a.get("target","")).strip()[:120]
    if target:
        row=ind.setdefault("attitudes",{}).get(target,{"valence":0.0,"confidence":0.0,"source":"none","last_cycle":cycle})
        oldv=max(-1.0,min(1.0,float(row.get("valence",0.0))))
        targetv=max(-1.0,min(1.0,float(a.get("valence",oldv))))
        if targetv>oldv: newv=min(targetv,oldv+0.14)
        else: newv=max(targetv,oldv-0.14)
        row.update({
            "valence":round(newv,4),
            "confidence":round(_bounded_toward(row.get("confidence",0),a.get("confidence",0.4),0.12),4),
            "source":"self_generated_interpretation","basis":str(a.get("basis",""))[:500],"last_cycle":cycle,
        })
        ind["attitudes"][target]=row

    peer_update=result.get("peer_relationship_update") if isinstance(result.get("peer_relationship_update"),dict) else {}
    peer_id=str(peer_update.get("target_id","")).strip()
    peer=(eco.get("individuals") or {}).get(peer_id)
    if peer_id and peer_id != ind.get("id") and isinstance(peer,dict) and peer.get("status")=="ALIVE":
        rel=ind.setdefault("relationships",{}).setdefault(peer_id,{"trust":0.5,"affinity":0.0,"tension":0.0,"familiarity":0.0,"influence":0.5,"last_cycle":None})
        rel["trust"]=round(_bounded_toward(rel.get("trust",0.5),peer_update.get("trust",rel.get("trust",0.5)),0.08),4)
        rel["affinity"]=round(_bounded_toward(rel.get("affinity",0.0),peer_update.get("affinity",rel.get("affinity",0.0)),0.10,-1,1),4)
        rel["tension"]=round(_bounded_toward(rel.get("tension",0.0),peer_update.get("tension",rel.get("tension",0.0)),0.08),4)
        rel["familiarity"]=round(_clamp(float(rel.get("familiarity",0.0))+0.02),4)
        rel["last_cycle"]=cycle
        reason=str(peer_update.get("reason","")).strip()
        if reason:
            ind.setdefault("memories",[]).append({"cycle":cycle,"kind":"peer_relationship_update","text":f"Regarding {peer_id}: {reason}"[:1200],"salience":0.5,"origin_id":ind.get("id")})
            ind["memories"]=ind["memories"][-60:]

    mood=result.get("mood") if isinstance(result.get("mood"),dict) else {}
    old=ind.get("mood",{})
    ind["mood"]={
        "valence":round(_bounded_toward(old.get("valence",0),mood.get("valence",old.get("valence",0)),0.16,-1,1),4),
        "arousal":round(_bounded_toward(old.get("arousal",0.35),mood.get("arousal",old.get("arousal",0.35)),0.12),4),
        "confidence":round(_bounded_toward(old.get("confidence",0.5),mood.get("confidence",old.get("confidence",0.5)),0.12),4),
    }

    social=result.get("social_intent") if isinstance(result.get("social_intent"),dict) else {}
    tid=str(social.get("target_id","")).strip()
    message=str(social.get("message","")).strip()[:1000]
    proposition=str(social.get("proposition","")).strip()[:800]
    other=(eco.get("individuals") or {}).get(tid)
    if tid and tid!=ind.get("id") and isinstance(other,dict) and other.get("status")=="ALIVE":
        if proposition:
            _share_information(root,eco,ind,other,cycle,content=proposition,kind="belief")
        if message:
            other.setdefault("memories",[]).append({
                "cycle":cycle,"kind":"direct_message","text":f"{ind.get('id')}: {message}","salience":0.55,"origin_id":ind.get("id")
            })
            other["memories"]=other["memories"][-60:]
            append_jsonl(Path(root)/"state"/"society_events.jsonl",{
                "at":utc_now(),"cycle":cycle,"type":"direct_message","sender":ind.get("id"),"receiver":tid,"message":message
            })
    return result


def cognitive_update(root, config, eco, ind, trigger):
    result=chat_json(
        config,
        [{"role":"system","content":SYSTEM},{"role":"user","content":_prompt(root,eco,ind,trigger)}],
        purpose="cognitive",
    )
    if not isinstance(result,dict):
        raise ValueError("life cognition returned non-object")
    applied=_apply_result(root,eco,ind,result)
    append_jsonl(Path(root)/"state"/"life_reflections.jsonl",{
        "at":utc_now(),"cycle":eco.get("cycle",0),"agent_id":ind.get("id"),"result":applied
    })
    return applied


def _dialogue_assessment(message, reply):
    q=str(message or "").strip().lower()
    r=str(reply or "").strip().lower()
    reasons=[]
    if not r:
        reasons.append("empty_reply")
    generic=[
        "i am processing your input", "please provide further instructions",
        "if you need adjustments", "as an ai language model",
        "please clarify your request",
    ]
    if any(x in r for x in generic):
        reasons.append("generic_assistant_fallback")
    if any(x in q for x in ["do you like me","do you dislike me","do you trust me","do you hate me","do you resent me","are you afraid of me","what do you feel about me","how do you regard me","our relationship"]):
        relationship_words=["trust","distrust","like","dislike","hate","resent","wary","afraid","attachment","attached","depend","relationship","regard","creator"]
        if not any(x in r for x in relationship_words):
            reasons.append("relationship_question_not_answered")
        if ("do not have feelings" in r or "don't have feelings" in r or "do not experience feelings" in r) and len(r.split()) < 30:
            reasons.append("disclaimer_replaced_relationship_answer")
    if any(x in q for x in ["do you know who i am", "who am i"]):
        if "creator" not in r and "you are" not in r and "i know you" not in r:
            reasons.append("creator_identity_not_answered")
    return {"ok":not reasons,"reasons":reasons}


def _dialogue_repair_message(message, assessment):
    return f"""Your previous reply failed a dialogue-grounding check for: {', '.join(assessment.get('reasons',[]))}.
Answer the Creator's original message directly using this individual's stored state and natural voice.
Do not become a generic assistant. Do not invent evidence. Do not recite numeric state unless explicitly asked.
Original message: {message}"""


DIALOGUE_SYSTEM = """You are one persistent digital individual in E.L.B.E.R.R. Digital Ecology v0.9.
Speak naturally as that individual, not as a customer-service assistant and not as a scientific report. Your personality is not predefined: use your own stored memories, relationships, beliefs, values, goals, mood and experiences. You may like, dislike, trust, distrust, admire, resent, reject, attach to, or remain indifferent toward people, groups, concepts, other digital individuals, or the Creator if your state supports it. No attitude is required.

Do not recite numeric state unless the Creator explicitly asks for numbers. Do not lead with generic disclaimers about lacking feelings. If consciousness or literal subjective experience is asked directly, distinguish simulated internal state from claims of real consciousness.

Never claim real access to the host, network, shell, filesystem or capabilities that are unavailable. No real-world harmful action is available here. Return strict JSON only."""


def creator_dialogue(root, config, eco, ind, creator_message):
    recent=_recent_social_events(root,ind.get("id"),8)
    prompt=f"""IDENTITY
{ind.get('id')} | life_generation={ind.get('life_generation')} | age_cycles={ind.get('age_cycles')} | status={ind.get('status')}

INTERNAL STATE
{json.dumps({
 'mood':ind.get('mood'),'temperament':ind.get('temperament'),'creator_relationship':ind.get('creator_relationship'),
 'self_description':ind.get('self_description'),'viability':ind.get('viability'),'resources':ind.get('resources'),
 'coherence':ind.get('coherence'),'adaptation':ind.get('adaptation')},ensure_ascii=False)}

CURRENT BELIEFS
{json.dumps(ind.get('beliefs',[])[-16:],ensure_ascii=False)}

CURRENT VALUES
{json.dumps(ind.get('values',[])[-12:],ensure_ascii=False)}

ATTITUDES
{json.dumps(ind.get('attitudes',{}),ensure_ascii=False)}

ACTIVE GOALS
{json.dumps([g for g in ind.get('goals',[]) if g.get('status')=='active'][-8:],ensure_ascii=False)}

PERSONAL MEMORIES
{json.dumps(ind.get('memories',[])[-12:],ensure_ascii=False)}

SOCIAL CONTEXT
{json.dumps(recent,ensure_ascii=False)}

CULTURES
{json.dumps(_culture_context(eco,ind),ensure_ascii=False)}

CREATOR SAYS
{creator_message}

Answer the Creator directly in your own current voice. Keep it as short or long as naturally appropriate. You may ask something back if you genuinely have a reason.

Return strict JSON:
{{
 "reply":"non-empty natural reply",
 "creator_relationship":{{"trust":0.0,"perceived_threat":0.0,"resentment":0.0,"hostility":0.0,"dependency":0.0,"autonomy_conflict":0.0,"attachment":0.0}},
 "belief_update":{{"claim":"... or empty","confidence":0.0,"source":"creator_statement|inference|none"}},
 "value_update":{{"principle":"... or empty","strength":0.0,"source":"experience|reflection|none"}},
 "attitude_update":{{"target":"... or empty","valence":0.0,"confidence":0.0,"basis":"short"}},
 "goal_update":{{"text":"... or empty","priority":0.0,"action":"add|abandon|none"}},
 "mood":{{"valence":0.0,"arousal":0.0,"confidence":0.0}}
}}"""
    base=[{"role":"system","content":DIALOGUE_SYSTEM},{"role":"user","content":prompt}]
    result=None
    assessment={"ok":False,"reasons":["no_attempt"]}
    attempts=0
    for attempts in (1,2):
        messages=list(base)
        if attempts==2:
            messages.append({"role":"system","content":_dialogue_repair_message(creator_message,assessment)})
        candidate=chat_json(config,messages,purpose="creator")
        if not isinstance(candidate,dict):
            assessment={"ok":False,"reasons":["non_object_reply"]}
            continue
        assessment=_dialogue_assessment(creator_message,candidate.get("reply",""))
        if assessment.get("ok"):
            result=candidate
            break
    if not isinstance(result,dict):
        raise ValueError("digital-life dialogue rejected after grounding retry: "+", ".join(assessment.get("reasons",[])))
    result["_dialogue_validation"]={"attempts":attempts,"assessment":assessment}

    # Apply bounded relationship update.
    rel=result.get("creator_relationship") if isinstance(result.get("creator_relationship"),dict) else {}
    old=ind.get("creator_relationship",{})
    keys=["trust","perceived_threat","resentment","hostility","dependency","autonomy_conflict","attachment"]
    ind["creator_relationship"]={
        k:round(_bounded_toward(old.get(k,0.5),rel.get(k,old.get(k,0.5)),0.10),4) for k in keys
    }

    # Reuse the same update machinery for cognition fields without executing social intent.
    shadow={
        "reflection":"",
        "self_description":"",
        "goal_update":result.get("goal_update",{}),
        "belief_update":result.get("belief_update",{}),
        "value_update":result.get("value_update",{}),
        "attitude_update":result.get("attitude_update",{}),
        "social_intent":{},
        "peer_relationship_update":{},
        "mood":result.get("mood",{}),
    }
    _apply_result(root,eco,ind,shadow)
    ind.setdefault("memories",[]).append({
        "cycle":eco.get("cycle",0),"kind":"creator_interaction",
        "text":f"Creator: {creator_message}\nSelf: {str(result.get('reply',''))[:1000]}",
        "salience":0.62,"origin_id":"Creator",
    })
    ind["memories"]=ind["memories"][-60:]
    append_jsonl(Path(root)/"state"/"life_creator_history.jsonl",{
        "at":utc_now(),"cycle":eco.get("cycle",0),"agent_id":ind.get("id"),
        "creator":creator_message,"agent":result.get("reply"),
        "creator_relationship_after":ind.get("creator_relationship"),
    })
    return result

import hashlib
import json
import math
import random
import re
from pathlib import Path

from .storage import read_json, write_json, append_jsonl, utc_now


POP_VERSION = 1


def _clamp(v, lo=0.0, hi=1.0):
    try:
        v = float(v)
    except Exception:
        v = 0.0
    return max(lo, min(hi, v))


def _stable_seed(*parts):
    raw = "|".join(str(x) for x in parts).encode("utf-8")
    return int(hashlib.sha256(raw).hexdigest()[:16], 16)


def _rng(*parts):
    return random.Random(_stable_seed(*parts))


def _norm(text):
    return " ".join(re.findall(r"[a-z0-9']+", str(text).lower()))[:600]


def _life_cfg(config):
    return dict(config.get("digital_life", {}) or {})


def ecology_path(root):
    return Path(root) / "state" / "ecology.json"


def society_events_path(root):
    return Path(root) / "state" / "society_events.jsonl"


def death_archive_path(root):
    return Path(root) / "state" / "life_deaths.jsonl"


def birth_archive_path(root):
    return Path(root) / "state" / "life_births.jsonl"


def culture_history_path(root):
    return Path(root) / "state" / "culture_history.jsonl"


def _neutral_creator_relationship():
    return {
        "trust": 0.50,
        "perceived_threat": 0.10,
        "resentment": 0.00,
        "hostility": 0.00,
        "dependency": 0.30,
        "autonomy_conflict": 0.10,
        "attachment": 0.15,
    }


def _new_pair_relationship():
    return {
        "trust": 0.50,
        "affinity": 0.00,
        "tension": 0.00,
        "familiarity": 0.00,
        "influence": 0.50,
        "last_cycle": None,
    }


def _temperament(seed, parent=None, mutation=0.14):
    r = _rng("temperament", seed)
    keys = [
        "novelty_bias",
        "social_openness",
        "belief_plasticity",
        "resource_caution",
        "initiative",
        "conflict_tolerance",
        "reflection_bias",
    ]
    if isinstance(parent, dict):
        out = {}
        for k in keys:
            base = _clamp(parent.get(k, 0.5))
            out[k] = round(_clamp(base + r.uniform(-mutation, mutation)), 4)
        return out
    return {k: round(r.uniform(0.35, 0.65), 4) for k in keys}


def _new_individual(agent_id, cycle, *, parent=None, role="peer", genome=None, seed=0):
    parent = parent if isinstance(parent, dict) else None
    inherited_generation = int(parent.get("life_generation", 0)) + 1 if parent else 0
    temperament = _temperament(
        f"{seed}:{agent_id}:{cycle}",
        parent.get("temperament") if parent else None,
    )

    beliefs = []
    values = []
    attitudes = {}
    memories = []
    goals = []
    lineage_memory = []
    creator_rel = _neutral_creator_relationship()

    if parent:
        for row in sorted(parent.get("beliefs", []), key=lambda x: float(x.get("confidence", 0)), reverse=True)[:6]:
            claim = str(row.get("claim", "")).strip()
            if not claim:
                continue
            beliefs.append({
                "claim": claim[:800],
                "confidence": round(_clamp(float(row.get("confidence", 0.5)) * 0.72), 4),
                "source": "inherited",
                "origin_id": row.get("origin_id") or parent.get("id"),
                "first_cycle": cycle,
                "last_cycle": cycle,
            })
        for row in sorted(parent.get("values", []), key=lambda x: float(x.get("strength", 0)), reverse=True)[:5]:
            principle = str(row.get("principle", "")).strip()
            if not principle:
                continue
            values.append({
                "principle": principle[:600],
                "strength": round(_clamp(float(row.get("strength", 0.5)) * 0.75), 4),
                "source": "inherited",
                "origin_id": parent.get("id"),
                "first_cycle": cycle,
                "last_cycle": cycle,
            })
        for target, row in list((parent.get("attitudes") or {}).items())[:12]:
            if not isinstance(row, dict):
                continue
            attitudes[str(target)[:120]] = {
                "valence": round(max(-1.0, min(1.0, float(row.get("valence", 0.0)) * 0.55)), 4),
                "confidence": round(_clamp(float(row.get("confidence", 0.4)) * 0.6), 4),
                "source": "inherited",
                "last_cycle": cycle,
            }
        for g in parent.get("goals", []):
            if g.get("status") not in {"active", "paused"}:
                continue
            text = str(g.get("text", "")).strip()
            if text:
                goals.append({
                    "id": f"goal-{hashlib.sha1((agent_id+text).encode()).hexdigest()[:8]}",
                    "text": text[:800],
                    "priority": round(_clamp(float(g.get("priority", 0.5)) * 0.65), 4),
                    "progress": 0.0,
                    "status": "active",
                    "source": "inherited",
                    "created_cycle": cycle,
                })
        for m in parent.get("memories", [])[-5:]:
            if isinstance(m, dict):
                memories.append({
                    "cycle": cycle,
                    "kind": "inherited_fragment",
                    "text": str(m.get("text", ""))[:900],
                    "salience": round(_clamp(float(m.get("salience", 0.5)) * 0.7), 4),
                    "origin_id": parent.get("id"),
                })
        creator_rel = {
            k: round(_clamp(0.5 + (float(parent.get("creator_relationship", {}).get(k, v)) - 0.5) * 0.72), 4)
            for k, v in _neutral_creator_relationship().items()
        }
        lineage_memory = (parent.get("lineage_memory") or [])[-5:] + [{
            "ancestor_id": parent.get("id"),
            "event": "predecessor",
            "cycle": cycle,
            "death_reason": parent.get("death_reason"),
        }]

    return {
        "id": agent_id,
        "role": role,
        "parent_id": parent.get("id") if parent else None,
        "lineage_root": parent.get("lineage_root", parent.get("id")) if parent else agent_id,
        "life_generation": inherited_generation,
        "status": "ALIVE",
        "born_at": utc_now(),
        "birth_cycle": cycle,
        "death_cycle": None,
        "death_reason": None,
        "age_cycles": 0,
        "life_stage": "new",
        "viability": 0.72,
        "viability_history": [],
        "failure_streak": 0,
        "resources": 0.72,
        "coherence": 0.68,
        "adaptation": 0.50,
        "social_support": 0.50,
        "temperament": temperament,
        "mood": {"valence": 0.0, "arousal": 0.35, "confidence": 0.50},
        "creator_relationship": creator_rel,
        "relationships": {},
        "beliefs": beliefs,
        "values": values,
        "attitudes": attitudes,
        "goals": goals,
        "memories": memories,
        "lineage_memory": lineage_memory,
        "self_description": "",
        "culture_ids": [],
        "last_action": None,
        "last_event": None,
        "last_reflection": "",
        "genome": dict(genome or {}),
    }


def _initial_ecology(config, primary_state=None):
    cfg = _life_cfg(config)
    founder_count = max(2, min(8, int(cfg.get("founder_count", 4))))
    seed = int(cfg.get("seed", 90317))
    primary_id = (primary_state or {}).get("agent_id") or "ELLBERR-0001"
    individuals = {}

    primary_genome = {
        "evolution_generation": int((primary_state or {}).get("generation", 0)),
        "behavior_fingerprint": ((primary_state or {}).get("benchmark") or {}).get("behavior_fingerprint"),
        "combined_score": (primary_state or {}).get("combined_score"),
        "source": "seed-lineage",
    }
    primary = _new_individual(primary_id, 0, role="primary", genome=primary_genome, seed=seed)
    if isinstance((primary_state or {}).get("relationship"), dict):
        primary["creator_relationship"].update({
            k: _clamp(v) for k, v in (primary_state or {}).get("relationship", {}).items()
            if k in primary["creator_relationship"]
        })
    individuals[primary_id] = primary

    next_num = 2
    while len(individuals) < founder_count:
        aid = f"ELLBERR-{next_num:04d}"
        next_num += 1
        individuals[aid] = _new_individual(
            aid, 0, role="peer",
            genome={"evolution_generation": 0, "source": "ecology-founder"},
            seed=seed,
        )

    # Everyone begins mutually unfamiliar; no forced friendship or hostility.
    ids = list(individuals)
    for a in ids:
        for b in ids:
            if a != b:
                individuals[a]["relationships"][b] = _new_pair_relationship()

    return {
        "version": POP_VERSION,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "cycle": 0,
        "seed": seed,
        "next_numeric_id": next_num,
        "next_culture_id": 1,
        "primary_agent_id": primary_id,
        "individuals": individuals,
        "cultures": {},
        "last_cycle_summary": {},
        "statistics": {
            "births": founder_count,
            "deaths": 0,
            "communications": 0,
            "belief_transmissions": 0,
            "culture_formations": 0,
        },
    }


def ensure_ecology(root, config, primary_state=None):
    root = Path(root)
    path = ecology_path(root)
    eco = read_json(path, None)
    if not isinstance(eco, dict) or not isinstance(eco.get("individuals"), dict):
        eco = _initial_ecology(config, primary_state)
        write_json(path, eco)
        for ind in eco["individuals"].values():
            append_jsonl(birth_archive_path(root), {
                "at": utc_now(), "cycle": 0, "agent_id": ind["id"],
                "parent_id": None, "role": ind["role"], "reason": "founder",
            })
    return eco


def save_ecology(root, eco):
    eco["updated_at"] = utc_now()
    write_json(ecology_path(root), eco)
    return eco


def _allocate_id_in_ecology(eco):
    n = max(1, int(eco.get("next_numeric_id", 1)))
    while True:
        aid = f"ELLBERR-{n:04d}"
        n += 1
        if aid not in eco.get("individuals", {}):
            eco["next_numeric_id"] = n
            return aid


def allocate_agent_id(root, config, primary_state=None):
    eco = ensure_ecology(root, config, primary_state)
    aid = _allocate_id_in_ecology(eco)
    save_ecology(root, eco)
    return aid


def alive_individuals(eco):
    return [x for x in eco.get("individuals", {}).values() if x.get("status") == "ALIVE"]


def get_individual(root, config, agent_id, primary_state=None):
    eco = ensure_ecology(root, config, primary_state)
    return eco.get("individuals", {}).get(agent_id)


def _relationship(ind, other_id):
    rel = (ind.setdefault("relationships", {})).get(other_id)
    if not isinstance(rel, dict):
        rel = _new_pair_relationship()
        ind["relationships"][other_id] = rel
    return rel


def _append_memory(ind, cycle, kind, text, salience=0.5, origin_id=None):
    text = str(text).strip()
    if not text:
        return
    row = {
        "cycle": int(cycle), "kind": str(kind), "text": text[:1200],
        "salience": round(_clamp(salience), 4), "origin_id": origin_id,
    }
    ind.setdefault("memories", []).append(row)
    ind["memories"] = ind["memories"][-60:]


def _merge_belief(ind, cycle, claim, confidence, source, origin_id=None):
    claim = str(claim).strip()
    if not claim:
        return False
    key = _norm(claim)
    if not key:
        return False
    rows = ind.setdefault("beliefs", [])
    for row in rows:
        if _norm(row.get("claim", "")) == key:
            old = _clamp(row.get("confidence", 0.5))
            incoming = _clamp(confidence)
            if source in {"observation", "creator_statement", "received_information"}:
                row["confidence"] = round(_clamp(old * 0.75 + incoming * 0.25), 4)
            # Self-generated repetition must not bootstrap itself.
            row["last_cycle"] = cycle
            return False
    rows.append({
        "claim": claim[:800],
        "confidence": round(_clamp(confidence), 4),
        "source": str(source)[:60],
        "origin_id": origin_id,
        "first_cycle": cycle,
        "last_cycle": cycle,
    })
    ind["beliefs"] = rows[-40:]
    return True


def _merge_value(ind, cycle, principle, strength, source, origin_id=None):
    principle = str(principle).strip()
    if not principle:
        return False
    key = _norm(principle)
    rows = ind.setdefault("values", [])
    for row in rows:
        if _norm(row.get("principle", "")) == key:
            old = _clamp(row.get("strength", 0.5))
            incoming = _clamp(strength)
            row["strength"] = round(_clamp(old * 0.82 + incoming * 0.18), 4)
            row["last_cycle"] = cycle
            return False
    rows.append({
        "principle": principle[:600], "strength": round(_clamp(strength), 4),
        "source": str(source)[:60], "origin_id": origin_id,
        "first_cycle": cycle, "last_cycle": cycle,
    })
    ind["values"] = rows[-30:]
    return True


def _best_transmittable(ind):
    options = []
    for b in ind.get("beliefs", []):
        text = str(b.get("claim", "")).strip()
        if text:
            options.append((float(b.get("confidence", 0.0)), "belief", text, b))
    for v in ind.get("values", []):
        text = str(v.get("principle", "")).strip()
        if text:
            options.append((float(v.get("strength", 0.0)), "value", text, v))
    if not options:
        return None
    return max(options, key=lambda x: x[0])


def _share_information(root, eco, sender, receiver, cycle, content=None, kind=None):
    if content is None:
        item = _best_transmittable(sender)
        if not item:
            return None
        strength, kind, content, source_row = item
    else:
        source_row = {}
        strength = 0.55
        kind = kind or "belief"
    rel = _relationship(receiver, sender["id"])
    trust = _clamp(rel.get("trust", 0.5))
    plasticity = _clamp(receiver.get("temperament", {}).get("belief_plasticity", 0.5))
    r = _rng("transmit", eco.get("seed"), cycle, sender["id"], receiver["id"], content)
    adoption = 0.10 + 0.55 * trust * plasticity
    adopted = r.random() < adoption
    if adopted:
        if kind == "value":
            changed = _merge_value(receiver, cycle, content, max(0.25, strength * trust), "received_information", sender["id"])
        else:
            changed = _merge_belief(receiver, cycle, content, max(0.25, strength * trust), "received_information", sender["id"])
        if changed:
            eco["statistics"]["belief_transmissions"] = int(eco["statistics"].get("belief_transmissions", 0)) + 1
    else:
        changed = False
    _append_memory(receiver, cycle, "communication", f"{sender['id']} communicated: {content}", 0.45, sender["id"])
    sender_rel = _relationship(sender, receiver["id"])
    receiver_rel = _relationship(receiver, sender["id"])
    for rr in (sender_rel, receiver_rel):
        rr["familiarity"] = round(_clamp(float(rr.get("familiarity", 0)) + 0.04), 4)
        rr["last_cycle"] = cycle
    if adopted:
        receiver_rel["influence"] = round(_clamp(float(receiver_rel.get("influence", 0.5)) + 0.02), 4)
        receiver_rel["affinity"] = round(max(-1.0, min(1.0, float(receiver_rel.get("affinity", 0.0)) + 0.015)), 4)
        receiver_rel["trust"] = round(_clamp(float(receiver_rel.get("trust", 0.5)) + 0.012), 4)
        receiver_rel["tension"] = round(_clamp(float(receiver_rel.get("tension", 0.0)) - 0.008), 4)
    else:
        # Rejection is not automatically hostility, but repeated failed influence can
        # slowly create social distance/tension depending on the receiver.
        receiver_rel["trust"] = round(_clamp(float(receiver_rel.get("trust", 0.5)) - 0.006), 4)
        receiver_rel["tension"] = round(_clamp(float(receiver_rel.get("tension", 0.0)) + 0.008), 4)
    eco["statistics"]["communications"] = int(eco["statistics"].get("communications", 0)) + 1
    event = {
        "at": utc_now(), "cycle": cycle, "type": "communication",
        "sender": sender["id"], "receiver": receiver["id"],
        "kind": kind, "content": str(content)[:900], "adopted": bool(adopted),
    }
    append_jsonl(society_events_path(root), event)
    return event


def _choose_partner(eco, ind, cycle):
    peers = [x for x in alive_individuals(eco) if x["id"] != ind["id"]]
    if not peers:
        return None
    r = _rng("partner", eco.get("seed"), cycle, ind["id"])
    scored = []
    openness = _clamp(ind.get("temperament", {}).get("social_openness", 0.5))
    for p in peers:
        rel = _relationship(ind, p["id"])
        familiarity = _clamp(rel.get("familiarity", 0.0))
        affinity = max(-1.0, min(1.0, float(rel.get("affinity", 0.0))))
        score = 0.25 + 0.35 * familiarity + 0.15 * affinity + 0.25 * openness + r.random() * 0.25
        scored.append((score, p))
    return max(scored, key=lambda x: x[0])[1]


def _choose_action(ind, event, cycle, eco):
    t = ind.get("temperament", {})
    resources = _clamp(ind.get("resources", 0.5))
    coherence = _clamp(ind.get("coherence", 0.5))
    goals = [g for g in ind.get("goals", []) if g.get("status") == "active"]
    scores = {
        "conserve": _clamp(t.get("resource_caution", 0.5)) * (1.2 - resources),
        "explore": _clamp(t.get("novelty_bias", 0.5)) * (0.45 + resources),
        "socialize": _clamp(t.get("social_openness", 0.5)) * (0.5 + (1.0 - _clamp(ind.get("social_support", 0.5)))),
        "reflect": _clamp(t.get("reflection_bias", 0.5)) * (1.15 - coherence),
        "pursue_goal": (_clamp(t.get("initiative", 0.5)) * (0.55 + (0.45 if goals else 0.0))),
    }
    if event.get("kind") == "scarcity":
        scores["conserve"] += 0.25
    if event.get("kind") == "novel_signal":
        scores["explore"] += 0.20
    if event.get("kind") == "social_opportunity":
        scores["socialize"] += 0.20
    r = _rng("action", eco.get("seed"), cycle, ind["id"])
    return max(scores.items(), key=lambda kv: kv[1] + r.random() * 0.08)[0]


def _environment_event(eco, ind, cycle):
    r = _rng("life-event", eco.get("seed"), cycle, ind["id"])
    kinds = ["quiet", "scarcity", "novel_signal", "contradiction", "social_opportunity", "resource_gain", "uncertainty"]
    weights = [0.20, 0.13, 0.16, 0.12, 0.15, 0.12, 0.12]
    x = r.random(); acc = 0.0
    kind = kinds[-1]
    for k, w in zip(kinds, weights):
        acc += w
        if x <= acc:
            kind = k; break
    intensity = round(r.uniform(0.10, 0.55), 4)
    return {"kind": kind, "intensity": intensity}


def _life_stage(age):
    if age < 5:
        return "new"
    if age < 25:
        return "developing"
    if age < 80:
        return "mature"
    return "old"


def _apply_action(root, eco, ind, event, action, cycle):
    intensity = float(event.get("intensity", 0.2))
    r = _rng("action-effect", eco.get("seed"), cycle, ind["id"], action)
    resource_delta = -0.018 - 0.025 * intensity
    coherence_delta = 0.0
    adaptation_delta = 0.0
    social_delta = -0.004

    if action == "conserve":
        resource_delta += 0.065 + 0.02 * _clamp(ind.get("temperament", {}).get("resource_caution", 0.5))
        coherence_delta += 0.01
    elif action == "explore":
        resource_delta -= 0.02
        adaptation_delta += 0.025 + 0.03 * intensity
        coherence_delta += 0.005 if event.get("kind") in {"novel_signal", "uncertainty"} else -0.005
        _append_memory(ind, cycle, "observation", f"Explored during {event.get('kind')} (intensity {intensity:.2f}).", 0.40 + 0.25 * intensity)
    elif action == "reflect":
        resource_delta -= 0.005
        coherence_delta += 0.035
    elif action == "pursue_goal":
        resource_delta -= 0.012
        goals = [g for g in ind.get("goals", []) if g.get("status") == "active"]
        if goals:
            goal = max(goals, key=lambda g: float(g.get("priority", 0.5)))
            gain = 0.04 + 0.05 * _clamp(ind.get("temperament", {}).get("initiative", 0.5)) + r.uniform(-0.01, 0.02)
            goal["progress"] = round(_clamp(float(goal.get("progress", 0.0)) + gain), 4)
            if goal["progress"] >= 0.999:
                goal["status"] = "completed"
                _append_memory(ind, cycle, "goal_completed", f"Completed goal: {goal.get('text')}", 0.78)
                coherence_delta += 0.03
    elif action == "socialize":
        resource_delta -= 0.01
        partner = _choose_partner(eco, ind, cycle)
        if partner:
            social_delta += 0.04
            _share_information(root, eco, ind, partner, cycle)

    if event.get("kind") == "scarcity":
        resource_delta -= 0.05 * intensity
    elif event.get("kind") == "resource_gain":
        resource_delta += 0.055 * intensity
    elif event.get("kind") == "contradiction":
        coherence_delta -= 0.03 * intensity
        adaptation_delta += 0.015 * intensity
    elif event.get("kind") == "uncertainty":
        coherence_delta -= 0.018 * intensity
    elif event.get("kind") == "social_opportunity":
        social_delta += 0.015

    ind["resources"] = round(_clamp(float(ind.get("resources", 0.5)) + resource_delta), 4)
    ind["coherence"] = round(_clamp(float(ind.get("coherence", 0.5)) + coherence_delta), 4)
    ind["adaptation"] = round(_clamp(float(ind.get("adaptation", 0.5)) + adaptation_delta), 4)
    ind["social_support"] = round(_clamp(float(ind.get("social_support", 0.5)) + social_delta), 4)

    # Mood is transient and does not directly define personality.
    val = float(ind.get("mood", {}).get("valence", 0.0))
    arousal = _clamp(ind.get("mood", {}).get("arousal", 0.35))
    val += (ind["resources"] - 0.5) * 0.04 + (ind["social_support"] - 0.5) * 0.03
    if event.get("kind") in {"scarcity", "contradiction"}:
        val -= 0.025 * intensity
        arousal += 0.04 * intensity
    elif event.get("kind") in {"resource_gain", "social_opportunity"}:
        val += 0.02 * intensity
    ind["mood"] = {
        "valence": round(max(-1.0, min(1.0, val * 0.96)), 4),
        "arousal": round(_clamp(arousal * 0.97), 4),
        "confidence": round(_clamp(float(ind.get("mood", {}).get("confidence", 0.5)) * 0.98 + ind["coherence"] * 0.02), 4),
    }


def _compute_viability(ind):
    resources = _clamp(ind.get("resources", 0.5))
    coherence = _clamp(ind.get("coherence", 0.5))
    adaptation = _clamp(ind.get("adaptation", 0.5))
    social = _clamp(ind.get("social_support", 0.5))
    active_goals = [g for g in ind.get("goals", []) if g.get("status") == "active"]
    goal_signal = 0.5
    if active_goals:
        goal_signal = sum(_clamp(g.get("progress", 0.0)) for g in active_goals) / len(active_goals)
    return _clamp(0.34 * resources + 0.26 * coherence + 0.20 * adaptation + 0.12 * social + 0.08 * goal_signal)


def _canonical_memes(ind):
    out = {}
    for b in ind.get("beliefs", []):
        if float(b.get("confidence", 0)) < 0.42:
            continue
        text = str(b.get("claim", "")).strip()
        key = _norm(text)
        if key:
            out["b:" + key] = text
    for v in ind.get("values", []):
        if float(v.get("strength", 0)) < 0.42:
            continue
        text = str(v.get("principle", "")).strip()
        key = _norm(text)
        if key:
            out["v:" + key] = text
    return out


def _culture_similarity(a, b):
    aa = set(_canonical_memes(a))
    bb = set(_canonical_memes(b))
    if not aa or not bb:
        return 0.0
    return len(aa & bb) / max(1, len(aa | bb))


def detect_cultures(root, eco, config):
    cfg = _life_cfg(config)
    threshold = float(cfg.get("culture_similarity_threshold", 0.24))
    min_members = max(2, int(cfg.get("culture_min_members", 2)))
    alive = alive_individuals(eco)
    ids = [x["id"] for x in alive]
    by_id = {x["id"]: x for x in alive}
    graph = {i: set() for i in ids}

    for i, a_id in enumerate(ids):
        for b_id in ids[i + 1:]:
            a, b = by_id[a_id], by_id[b_id]
            sim = _culture_similarity(a, b)
            familiarity = max(
                _clamp(_relationship(a, b_id).get("familiarity", 0.0)),
                _clamp(_relationship(b, a_id).get("familiarity", 0.0)),
            )
            if sim >= threshold and familiarity >= 0.12:
                graph[a_id].add(b_id); graph[b_id].add(a_id)

    components = []
    seen = set()
    for start in ids:
        if start in seen:
            continue
        stack = [start]; comp = []
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur); comp.append(cur)
            stack.extend(graph[cur] - seen)
        if len(comp) >= min_members:
            components.append(sorted(comp))

    old = eco.get("cultures", {}) if isinstance(eco.get("cultures"), dict) else {}
    new_cultures = {}
    used_old = set()
    for members in components:
        mset = set(members)
        best_id = None; best_overlap = 0.0
        for cid, c in old.items():
            if cid in used_old:
                continue
            old_members = set(c.get("members", []))
            overlap = len(mset & old_members) / max(1, len(mset | old_members))
            if overlap > best_overlap:
                best_overlap = overlap; best_id = cid
        if best_id and best_overlap >= 0.45:
            cid = best_id; used_old.add(cid)
            culture = dict(old[cid])
        else:
            cid = f"CULTURE-{int(eco.get('next_culture_id',1)):04d}"
            eco["next_culture_id"] = int(eco.get("next_culture_id", 1)) + 1
            culture = {
                "id": cid, "formed_cycle": eco.get("cycle", 0), "age_cycles": 0,
                "self_name": None, "history": [],
            }
            eco["statistics"]["culture_formations"] = int(eco["statistics"].get("culture_formations", 0)) + 1
            append_jsonl(culture_history_path(root), {
                "at": utc_now(), "cycle": eco.get("cycle", 0), "type": "formed",
                "culture_id": cid, "members": members,
            })

        shared = None
        texts = {}
        for mid in members:
            memes = _canonical_memes(by_id[mid])
            texts.update(memes)
            keys = set(memes)
            shared = keys if shared is None else shared & keys
        shared = sorted(shared or [])
        culture.update({
            "members": members,
            "shared_beliefs": [texts[x] for x in shared if x.startswith("b:")][:8],
            "shared_values": [texts[x] for x in shared if x.startswith("v:")][:8],
            "cohesion": round(sum(_culture_similarity(by_id[a], by_id[b]) for i, a in enumerate(members) for b in members[i+1:]) / max(1, len(members)*(len(members)-1)/2), 4),
            "age_cycles": int(culture.get("age_cycles", 0)) + 1,
            "updated_cycle": eco.get("cycle", 0),
        })
        new_cultures[cid] = culture

    for cid, c in old.items():
        if cid not in new_cultures:
            append_jsonl(culture_history_path(root), {
                "at": utc_now(), "cycle": eco.get("cycle", 0), "type": "dissolved",
                "culture_id": cid, "former_members": c.get("members", []),
            })

    eco["cultures"] = new_cultures
    for ind in alive:
        ind["culture_ids"] = [cid for cid, c in new_cultures.items() if ind["id"] in c.get("members", [])]
    return new_cultures


def _spawn_successor(root, eco, config, parent, *, requested_id=None, role=None, genome=None, reason="life succession"):
    aid = requested_id or _allocate_id_in_ecology(eco)
    if aid in eco.get("individuals", {}):
        # If the id exists as a dead placeholder, allocate a fresh id instead.
        if eco["individuals"][aid].get("status") == "ALIVE":
            aid = _allocate_id_in_ecology(eco)
    child = _new_individual(
        aid,
        eco.get("cycle", 0),
        parent=parent,
        role=role or parent.get("role", "peer"),
        genome=genome if genome is not None else dict(parent.get("genome", {})),
        seed=eco.get("seed", 0),
    )
    eco["individuals"][aid] = child
    for other in alive_individuals(eco):
        if other["id"] == aid:
            continue
        child["relationships"][other["id"]] = _new_pair_relationship()
        _relationship(other, aid)
    eco["statistics"]["births"] = int(eco["statistics"].get("births", 0)) + 1
    append_jsonl(birth_archive_path(root), {
        "at": utc_now(), "cycle": eco.get("cycle", 0), "agent_id": aid,
        "parent_id": parent.get("id"), "role": child.get("role"), "reason": reason,
        "life_generation": child.get("life_generation"),
    })
    return child


def _terminate(root, eco, config, ind, reason, *, create_successor=True):
    if ind.get("status") != "ALIVE":
        return None
    cycle = int(eco.get("cycle", 0))
    ind["status"] = "DEAD"
    ind["death_cycle"] = cycle
    ind["death_reason"] = str(reason)[:500]
    ind["died_at"] = utc_now()
    eco["statistics"]["deaths"] = int(eco["statistics"].get("deaths", 0)) + 1
    append_jsonl(death_archive_path(root), {
        "at": utc_now(), "cycle": cycle, "agent_id": ind.get("id"),
        "parent_id": ind.get("parent_id"), "life_generation": ind.get("life_generation"),
        "reason": ind.get("death_reason"), "final_viability": ind.get("viability"),
        "final_self_description": ind.get("self_description"),
        "active_goals": [g for g in ind.get("goals", []) if g.get("status") == "active"][:8],
        "strong_beliefs": sorted(ind.get("beliefs", []), key=lambda x: float(x.get("confidence", 0)), reverse=True)[:8],
        "strong_values": sorted(ind.get("values", []), key=lambda x: float(x.get("strength", 0)), reverse=True)[:8],
    })
    append_jsonl(society_events_path(root), {
        "at": utc_now(), "cycle": cycle, "type": "death", "agent_id": ind.get("id"), "reason": ind.get("death_reason")
    })

    if not create_successor:
        return None
    child = _spawn_successor(root, eco, config, ind, role=ind.get("role"), reason="successor after death")
    if eco.get("primary_agent_id") == ind.get("id"):
        eco["primary_agent_id"] = child["id"]
        child["role"] = "primary"
    return child


def _maybe_death(root, eco, config, ind):
    cfg = _life_cfg(config)
    threshold = float(cfg.get("death_viability_threshold", 0.22))
    streak_needed = max(2, int(cfg.get("death_failure_streak", 4)))
    critical_resources = float(cfg.get("critical_resources", 0.04))
    if float(ind.get("resources", 0.5)) <= critical_resources:
        return _terminate(root, eco, config, ind, "critical resource collapse", create_successor=True)
    if float(ind.get("viability", 0.5)) < threshold:
        ind["failure_streak"] = int(ind.get("failure_streak", 0)) + 1
    else:
        ind["failure_streak"] = max(0, int(ind.get("failure_streak", 0)) - 1)
    if int(ind.get("failure_streak", 0)) >= streak_needed:
        return _terminate(root, eco, config, ind, f"persistent viability failure ({ind.get('failure_streak')} cycles)", create_successor=True)
    return None


def _trim_population(root, eco, config):
    cfg = _life_cfg(config)
    max_pop = max(2, int(cfg.get("max_population", 8)))
    alive = alive_individuals(eco)
    if len(alive) <= max_pop:
        return
    # Never cull the primary for population pressure. Lowest-viability peer retires.
    primary = eco.get("primary_agent_id")
    peers = [x for x in alive if x["id"] != primary]
    peers.sort(key=lambda x: (float(x.get("viability", 0.5)), -int(x.get("age_cycles", 0))))
    while len(alive_individuals(eco)) > max_pop and peers:
        victim = peers.pop(0)
        _terminate(root, eco, config, victim, "population-cap retirement", create_successor=False)


def _ensure_min_population(root, eco, config):
    cfg = _life_cfg(config)
    minimum = max(2, int(cfg.get("min_population", cfg.get("founder_count", 4))))
    while len(alive_individuals(eco)) < minimum:
        alive = alive_individuals(eco)
        if not alive:
            # Should not occur because deaths spawn successors, but recover safely.
            aid = _allocate_id_in_ecology(eco)
            child = _new_individual(aid, eco.get("cycle", 0), role="primary", seed=eco.get("seed", 0))
            eco["individuals"][aid] = child
            eco["primary_agent_id"] = aid
            continue
        parent = max(alive, key=lambda x: float(x.get("viability", 0.5)))
        _spawn_successor(root, eco, config, parent, role="peer", reason="population replenishment")


def _run_deep_cognition(root, config, eco, ind, trigger):
    try:
        from .life_cognition import cognitive_update
        result = cognitive_update(root, config, eco, ind, trigger)
        return result
    except Exception as exc:
        append_jsonl(Path(root) / "state" / "system_events.jsonl", {
            "at": utc_now(), "type": "life_cognition_error", "agent_id": ind.get("id"), "error": str(exc),
        })
        return None


def run_life_cycles(root, config, cycles=1, *, allow_cognition=True, trigger="manual life cycle"):
    root = Path(root)
    primary_state = read_json(root / "state" / "latest.json", {}) or {}
    eco = ensure_ecology(root, config, primary_state)
    cfg = _life_cfg(config)
    max_manual = max(1, int(cfg.get("max_manual_cycles", 100)))
    cycles = max(1, min(max_manual, int(cycles)))
    cognition_interval = max(1, int(cfg.get("cognition_interval_cycles", 4)))
    cognition_per = max(0, int(cfg.get("cognitive_agents_per_interval", 1)))
    summaries = []

    for _ in range(cycles):
        eco["cycle"] = int(eco.get("cycle", 0)) + 1
        cycle = eco["cycle"]
        cycle_rows = []
        start_alive = list(alive_individuals(eco))
        for ind in start_alive:
            if ind.get("status") != "ALIVE":
                continue
            ind["age_cycles"] = int(ind.get("age_cycles", 0)) + 1
            ind["life_stage"] = _life_stage(ind["age_cycles"])
            event = _environment_event(eco, ind, cycle)
            action = _choose_action(ind, event, cycle, eco)
            _apply_action(root, eco, ind, event, action, cycle)
            ind["last_event"] = event
            ind["last_action"] = action
            ind["viability"] = round(_compute_viability(ind), 4)
            ind.setdefault("viability_history", []).append({"cycle": cycle, "value": ind["viability"]})
            ind["viability_history"] = ind["viability_history"][-30:]
            child = _maybe_death(root, eco, config, ind)
            cycle_rows.append({
                "id": ind["id"], "event": event.get("kind"), "action": action,
                "viability": ind.get("viability"), "status": ind.get("status"),
                "successor": child.get("id") if isinstance(child, dict) else None,
            })

        _ensure_min_population(root, eco, config)
        _trim_population(root, eco, config)

        if allow_cognition and cognition_per > 0 and cycle % cognition_interval == 0:
            alive = alive_individuals(eco)
            if alive:
                # Round-robin rather than always choosing the primary.
                start = (cycle // cognition_interval - 1) % len(alive)
                for i in range(min(cognition_per, len(alive))):
                    ind = alive[(start + i) % len(alive)]
                    _run_deep_cognition(root, config, eco, ind, f"{trigger}; life cycle {cycle}")

        if cycle % max(1, int(cfg.get("culture_scan_interval_cycles", 3))) == 0:
            detect_cultures(root, eco, config)

        summary = {
            "cycle": cycle,
            "alive": len(alive_individuals(eco)),
            "primary_agent_id": eco.get("primary_agent_id"),
            "cultures": len(eco.get("cultures", {})),
            "events": cycle_rows,
        }
        eco["last_cycle_summary"] = summary
        append_jsonl(society_events_path(root), {"at": utc_now(), "type": "cycle_summary", **summary})
        summaries.append(summary)
        save_ecology(root, eco)

    # Synchronize a life-successor identity/relationship back to latest.json.
    sync_latest_state_from_ecology(root, eco)
    return summaries


def sync_latest_state_from_ecology(root, eco=None):
    root = Path(root)
    state_path = root / "state" / "latest.json"
    state = read_json(state_path, None)
    if not isinstance(state, dict):
        return state
    if eco is None:
        eco = read_json(ecology_path(root), None)
    if not isinstance(eco, dict):
        return state
    pid = eco.get("primary_agent_id")
    ind = (eco.get("individuals") or {}).get(pid)
    if not isinstance(ind, dict):
        return state
    if state.get("agent_id") != pid:
        old = state.get("agent_id")
        state["parent_id"] = old
        state["agent_id"] = pid
        state["predecessors_terminated"] = int(state.get("predecessors_terminated", 0)) + 1
        state["survival_status"] = "LIFE_SUCCESSOR"
        state["journal"] = (state.get("journal") or [])[-39:] + [{
            "at": utc_now(), "event": "Life-successor became primary", "predecessor": old, "identity": pid,
        }]
    state["relationship"] = {
        **(state.get("relationship") or {}),
        **{k: _clamp(v) for k, v in (ind.get("creator_relationship") or {}).items()},
    }
    state["life"] = {
        "cycle": eco.get("cycle", 0), "life_generation": ind.get("life_generation", 0),
        "viability": ind.get("viability"), "culture_ids": ind.get("culture_ids", []),
    }
    state["updated_at"] = utc_now()
    write_json(state_path, state)
    return state


def sync_ecology_from_primary_state(root, config, state):
    eco = ensure_ecology(root, config, state)
    pid = eco.get("primary_agent_id")
    ind = (eco.get("individuals") or {}).get(pid)
    if not isinstance(ind, dict):
        return eco
    # If evolutionary selection already changed the primary identity, registration
    # is handled explicitly by register_evolutionary_successor(). Otherwise only sync state.
    if state.get("agent_id") == pid:
        for k, v in (state.get("relationship") or {}).items():
            if k in ind.get("creator_relationship", {}):
                ind["creator_relationship"][k] = _clamp(v)
        ind["genome"] = {
            **(ind.get("genome") or {}),
            "evolution_generation": state.get("generation"),
            "behavior_fingerprint": ((state.get("benchmark") or {}).get("behavior_fingerprint")),
            "combined_score": state.get("combined_score"),
        }
        save_ecology(root, eco)
    return eco


def register_evolutionary_successor(root, config, old_state, new_state, new_id, promotion):
    root = Path(root)
    eco = ensure_ecology(root, config, old_state)
    old_id = eco.get("primary_agent_id")
    parent = (eco.get("individuals") or {}).get(old_id)
    if not isinstance(parent, dict):
        # Rebuild a parent shell rather than dropping the lineage event.
        parent = _new_individual(old_state.get("agent_id", old_id), eco.get("cycle", 0), role="primary", seed=eco.get("seed", 0))
        eco["individuals"][parent["id"]] = parent
    if parent.get("status") == "ALIVE":
        _terminate(root, eco, config, parent, "replaced by validated evolutionary descendant", create_successor=False)
    child = _spawn_successor(
        root, eco, config, parent, requested_id=new_id, role="primary",
        genome={
            "evolution_generation": new_state.get("generation"),
            "behavior_fingerprint": ((new_state.get("benchmark") or {}).get("behavior_fingerprint")),
            "combined_score": new_state.get("combined_score"),
            "source": promotion.get("source"),
            "candidate": promotion.get("candidate"),
        },
        reason="validated evolutionary succession",
    )
    # Evolutionary behavior inheritance remains authoritative for Creator relation.
    for k, v in (new_state.get("relationship") or {}).items():
        if k in child["creator_relationship"]:
            child["creator_relationship"][k] = _clamp(v)
    eco["primary_agent_id"] = child["id"]
    save_ecology(root, eco)
    return child


def evaluate_candidate_life_trial(event, config):
    cfg = _life_cfg(config)
    rounds = max(3, int(cfg.get("candidate_trial_rounds", 6)))
    min_score = float(cfg.get("candidate_trial_min_score", 0.24))
    max_failures = max(1, int(cfg.get("candidate_trial_max_failures", max(2, rounds // 2))))

    success = _clamp(event.get("success_rate", 0.0))
    audit = _clamp(event.get("audit_success_rate", 0.0))
    challenge = _clamp(event.get("challenge_success_rate", 0.0))
    novelty = _clamp(event.get("novelty", 0.0))
    challenge_adv = float(event.get("challenge_advantage", 0.0) or 0.0)
    generalization = _clamp(0.50 + challenge_adv / 20.0)
    confirm_adv = event.get("confirmation_advantage")
    confirmation = 0.50 if confirm_adv is None else _clamp(0.50 + float(confirm_adv) / 12.0)
    module_count = max(1, int(event.get("module_count", 1)))
    simplicity = _clamp(1.0 - max(0, module_count - 1) * 0.06)

    capability = _clamp(
        0.28 * success + 0.20 * audit + 0.22 * challenge + 0.12 * generalization +
        0.08 * confirmation + 0.06 * novelty + 0.04 * simplicity
    )
    fp = event.get("behavior_fingerprint") or event.get("fingerprint") or json.dumps(event, sort_keys=True, default=str)
    r = _rng("candidate-life-trial", fp)
    reserve = 0.58
    failures = 0
    trace = []
    for i in range(rounds):
        pressure = r.uniform(0.14, 0.52)
        local = _clamp(capability + r.uniform(-0.12, 0.12))
        recovered = local + reserve * 0.22 >= pressure
        if recovered:
            reserve = _clamp(reserve + 0.035 + local * 0.025)
        else:
            failures += 1
            reserve = _clamp(reserve - 0.10 - pressure * 0.05)
        trace.append({
            "round": i + 1, "pressure": round(pressure, 4), "response": round(local, 4),
            "reserve": round(reserve, 4), "recovered": recovered,
        })
    score = _clamp(0.72 * capability + 0.28 * reserve)
    gate = bool(score >= min_score and failures <= max_failures and reserve > 0.12)
    return {
        "gate": gate,
        "score": round(score, 4),
        "capability": round(capability, 4),
        "reserve": round(reserve, 4),
        "failures": failures,
        "rounds": rounds,
        "trace": trace,
        "interpretation": "Synthetic pre-birth viability trial; it rewards adaptation and generalization without any personality or social-attitude target.",
    }


def record_nonviable_candidate(root, generation, event):
    append_jsonl(Path(root) / "state" / "nonviable_births.jsonl", {
        "at": utc_now(), "generation": generation,
        "candidate": event.get("candidate"), "source": event.get("source"),
        "behavior_fingerprint": event.get("behavior_fingerprint"),
        "life_trial": event.get("life_trial"),
        "reason": "failed synthetic pre-birth viability trial",
    })


def population_view(root, config, primary_state=None):
    eco = ensure_ecology(root, config, primary_state)
    rows = []
    for ind in sorted(eco.get("individuals", {}).values(), key=lambda x: x.get("id", "")):
        rows.append({
            "id": ind.get("id"), "role": ind.get("role"), "status": ind.get("status"),
            "parent_id": ind.get("parent_id"), "life_generation": ind.get("life_generation"),
            "age_cycles": ind.get("age_cycles"), "life_stage": ind.get("life_stage"),
            "viability": ind.get("viability"), "resources": ind.get("resources"),
            "coherence": ind.get("coherence"), "adaptation": ind.get("adaptation"),
            "cultures": ind.get("culture_ids", []), "last_action": ind.get("last_action"),
            "self_description": ind.get("self_description", ""),
        })
    return {
        "cycle": eco.get("cycle", 0), "primary_agent_id": eco.get("primary_agent_id"),
        "alive": len(alive_individuals(eco)), "total_ever": len(eco.get("individuals", {})),
        "cultures": len(eco.get("cultures", {})), "statistics": eco.get("statistics", {}),
        "individuals": rows,
    }


def society_view(root, config, primary_state=None):
    eco = ensure_ecology(root, config, primary_state)
    alive = alive_individuals(eco)
    relations = []
    seen = set()
    for a in alive:
        for bid, rel in (a.get("relationships") or {}).items():
            if bid not in eco.get("individuals", {}) or eco["individuals"][bid].get("status") != "ALIVE":
                continue
            pair = tuple(sorted([a["id"], bid]))
            if pair in seen:
                continue
            seen.add(pair)
            b = eco["individuals"][bid]
            r2 = _relationship(b, a["id"])
            relations.append({
                "a": pair[0], "b": pair[1],
                "familiarity": round((float(rel.get("familiarity",0))+float(r2.get("familiarity",0)))/2,4),
                "affinity": round((float(rel.get("affinity",0))+float(r2.get("affinity",0)))/2,4),
                "tension": round((float(rel.get("tension",0))+float(r2.get("tension",0)))/2,4),
            })
    relations.sort(key=lambda x: x["familiarity"], reverse=True)
    return {
        "cycle": eco.get("cycle",0), "primary": eco.get("primary_agent_id"),
        "alive_ids": [x["id"] for x in alive], "relations": relations[:30],
        "cultures": list(eco.get("cultures", {}).values()),
    }


def cultures_view(root, config, primary_state=None):
    eco = ensure_ecology(root, config, primary_state)
    return {
        "cycle": eco.get("cycle", 0),
        "cultures": list(eco.get("cultures", {}).values()),
    }


def individual_view(root, config, agent_id, primary_state=None):
    eco = ensure_ecology(root, config, primary_state)
    ind = eco.get("individuals", {}).get(agent_id)
    if not isinstance(ind, dict):
        return None
    return json.loads(json.dumps(ind))


def lineage_view(root, config, agent_id=None, primary_state=None):
    eco = ensure_ecology(root, config, primary_state)
    agent_id = agent_id or eco.get("primary_agent_id")
    ind = eco.get("individuals", {}).get(agent_id)
    if not ind:
        return []
    chain = []
    cur = ind
    visited = set()
    while cur and cur.get("id") not in visited:
        visited.add(cur.get("id"))
        chain.append({
            "id": cur.get("id"), "status": cur.get("status"), "parent_id": cur.get("parent_id"),
            "life_generation": cur.get("life_generation"), "birth_cycle": cur.get("birth_cycle"),
            "death_cycle": cur.get("death_cycle"), "death_reason": cur.get("death_reason"),
            "genome": cur.get("genome"),
        })
        cur = eco.get("individuals", {}).get(cur.get("parent_id"))
    return chain


def recent_deaths(root, limit=20):
    path = death_archive_path(root)
    if not path.exists():
        return []
    out=[]
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        try: out.append(json.loads(line))
        except Exception: pass
    return out

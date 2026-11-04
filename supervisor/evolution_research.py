import hashlib
import json
import math
from pathlib import Path

from .storage import append_jsonl, read_json, write_json, utc_now

ROLE_GUIDANCE = {
    "local_policy": (
        "Exploit locally. Preserve the parent's working behavior. Prefer changing only the main body "
        "or one helper. Do not add a new subagent. Make one causally testable navigation improvement."
    ),
    "memory_search": (
        "Explore stateful navigation. Prefer a small number of mutable globals or linear-memory state "
        "to detect revisits, remember previous action, or break oscillations. Avoid unnecessary subagents."
    ),
    "helper_planner": (
        "Explore algorithmic decomposition using helpers. Prefer a compact planner/heuristic helper, "
        "direction scoring, revisit penalties, or a finite-state policy. Preserve valid parent behavior where useful."
    ),
    "subagent_ensemble": (
        "Explore one meaningful subagent. The subagent executes separately each step and its low byte is "
        "available through the same-name zero-argument call bridge. Use it as advice, not as a constant fake helper."
    ),
    "radical_patch": (
        "Stagnation is high. Make a materially different patch: replacing the main policy body and restructuring "
        "helpers/memory/subagents is allowed. Keep the patch compact, but do not merely repeat a recent failed pattern."
    ),
    "branch_refine": (
        "Refine a retained near-neutral branch rather than starting from the incumbent. Preserve the scaffold that already "
        "passed generalization, change one weak mechanism, and aim to turn a neutral intermediate into a measurable gain."
    ),
}

ROLE_ORDER = [
    "local_policy",
    "memory_search",
    "helper_planner",
    "subagent_ensemble",
    "radical_patch",
    "branch_refine",
]


def _state_dir(root):
    return Path(root) / "state"


def experiments_path(root):
    return _state_dir(root) / "research_experiments.jsonl"


def stats_path(root):
    return _state_dir(root) / "research_role_stats.json"


def strategy_path(root):
    return _state_dir(root) / "research_strategy.json"


def _json_lines(path):
    path = Path(path)
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


def stagnation_generations(root, current_generation=0):
    promotions = _json_lines(_state_dir(root) / "promotions.jsonl")
    accepted = [x for x in promotions if x.get("accepted")]
    if not accepted:
        return max(0, int(current_generation))
    last = max(int(x.get("generation", 0)) for x in accepted)
    return max(0, int(current_generation) - last)


def load_role_stats(root):
    default = {
        role: {
            "attempts": 0,
            "promotions": 0,
            "mean_delta": 0.0,
            "best_delta": None,
            "mean_challenge_advantage": 0.0,
            "behavior_change_rate": 0.0,
            "novel_behavior_rate": 0.0,
        }
        for role in ROLE_ORDER
    }
    data = read_json(stats_path(root), None)
    if not isinstance(data, dict):
        return default
    for role in ROLE_ORDER:
        if role not in data or not isinstance(data[role], dict):
            data[role] = dict(default[role])
        else:
            for key, value in default[role].items():
                data[role].setdefault(key, value)
    return data


def _ucb_score(stats, role, total_attempts, stagnation):
    s = stats.get(role, {})
    n = max(0, int(s.get("attempts", 0)))
    mean_delta = float(s.get("mean_delta", 0.0))
    mean_challenge = float(s.get("mean_challenge_advantage", 0.0))
    behavior_rate = float(s.get("behavior_change_rate", 0.0) or 0.0)
    novel_behavior_rate = float(s.get("novel_behavior_rate", 0.0) or 0.0)
    # Performance dominates. Behavior diversity is only a small research-quality signal.
    exploitation = (
        math.tanh(mean_delta / 35.0)
        + 0.10 * math.tanh(mean_challenge / 20.0)
        + 0.06 * behavior_rate
        + 0.04 * novel_behavior_rate
    )
    exploration = 0.9 * math.sqrt(math.log(total_attempts + 2.0) / (n + 1.0))
    bonus = 0.0
    if stagnation >= 4 and role in {"memory_search", "helper_planner", "subagent_ensemble"}:
        bonus += 0.18
    if stagnation >= 7 and role == "radical_patch":
        bonus += 0.55
    if stagnation < 3 and role == "local_policy":
        bonus += 0.20
    return exploitation + exploration + bonus


def select_role(root, generation, candidate_index):
    stagnation = stagnation_generations(root, generation - 1)
    stats = load_role_stats(root)
    total = sum(max(0, int(v.get("attempts", 0))) for v in stats.values())

    # Candidate 1 is biased toward exploitation, candidate 2 toward exploration.
    if int(candidate_index) == 1:
        pool = ["local_policy", "memory_search", "helper_planner"]
        if stagnation >= 8:
            pool.append("radical_patch")
    else:
        pool = ["memory_search", "helper_planner", "subagent_ensemble"]
        if stagnation >= 5:
            pool.append("radical_patch")

    ranked = sorted(
        pool,
        key=lambda r: (_ucb_score(stats, r, total, stagnation), -ROLE_ORDER.index(r)),
        reverse=True,
    )
    role = ranked[0]
    return {
        "role": role,
        "guidance": ROLE_GUIDANCE[role],
        "stagnation": stagnation,
        "role_score": round(_ucb_score(stats, role, total, stagnation), 4),
    }


def _walk_ops(value, counts):
    if isinstance(value, dict):
        op = value.get("op")
        if op:
            counts[str(op)] = counts.get(str(op), 0) + 1
        for child in value.values():
            _walk_ops(child, counts)
    elif isinstance(value, list):
        for child in value:
            _walk_ops(child, counts)


def structural_signature(ir_source):
    ir_source = ir_source if isinstance(ir_source, dict) else {}
    main = ir_source.get("main_ir") if isinstance(ir_source.get("main_ir"), dict) else {}
    subs = ir_source.get("subagents") if isinstance(ir_source.get("subagents"), list) else []
    counts = {}
    _walk_ops(main, counts)
    for sub in subs:
        if isinstance(sub, dict):
            _walk_ops(sub.get("ir"), counts)

    features = {
        "subagents": len(subs),
        "helpers": len(main.get("helpers") or []) if isinstance(main.get("helpers"), list) else 0,
        "globals": len(main.get("globals") or []) if isinstance(main.get("globals"), list) else 0,
        "locals": len(main.get("locals") or []) if isinstance(main.get("locals"), list) else 0,
        "memory_pages": int(main.get("memory_pages", 0) or 0),
        "emit_candidate": 1 if isinstance(main.get("emit_candidate_ir"), dict) else 0,
        "ops": {k: counts[k] for k in sorted(counts)},
    }
    canonical = json.dumps(features, sort_keys=True, separators=(",", ":"))
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]
    return fingerprint, features




def content_fingerprint(ir_source):
    """Exact canonical IR hash used for deduplication.

    Structural fingerprints intentionally ignore many constants/details; this hash does not.
    """
    ir_source = ir_source if isinstance(ir_source, dict) else {}
    canonical = json.dumps(ir_source, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]


def behavior_is_new(root, behavior_fingerprint, limit=80):
    fp = str(behavior_fingerprint or "")
    if not fp:
        return None
    rows = _json_lines(experiments_path(root))[-limit:]
    return not any(str(x.get("behavior_fingerprint") or "") == fp for x in rows)

def _feature_vector(features):
    ops = features.get("ops", {}) if isinstance(features, dict) else {}
    keys = ["if", "while", "call", "load", "store", "set_global", "set_local", "select", "cmp", "bin"]
    return [
        float(features.get("subagents", 0)),
        float(features.get("helpers", 0)),
        float(features.get("globals", 0)),
        float(features.get("memory_pages", 0)),
        float(features.get("emit_candidate", 0)),
    ] + [float(ops.get(k, 0)) for k in keys]


def novelty_score(root, features, limit=24):
    experiments = _json_lines(experiments_path(root))[-limit:]
    previous = [x.get("features") for x in experiments if isinstance(x.get("features"), dict)]
    if not previous:
        return 1.0
    v = _feature_vector(features)
    distances = []
    for feat in previous:
        u = _feature_vector(feat)
        denom = 1.0 + sum(abs(x) + abs(y) for x, y in zip(v, u))
        distances.append(sum(abs(x - y) for x, y in zip(v, u)) / denom)
    return round(max(0.0, min(1.0, min(distances) * 4.0)), 4)


def record_experiment(root, event, ir_source, incumbent_combined, role_info):
    fingerprint, features = structural_signature(ir_source)
    novelty = novelty_score(root, features)
    combined = event.get("combined_score")
    delta = None if combined is None else float(combined) - float(incumbent_combined)
    exact_fp = content_fingerprint(ir_source)
    behavior_fp = str(event.get("behavior_fingerprint") or "")
    behavior_new = behavior_is_new(root, behavior_fp)
    record = {
        "at": utc_now(),
        "generation": event.get("generation"),
        "candidate": event.get("candidate"),
        "role": role_info.get("role") if isinstance(role_info, dict) else event.get("experiment_role"),
        "fingerprint": fingerprint,
        "content_fingerprint": exact_fp,
        "features": features,
        "novelty": novelty,
        "behavior_fingerprint": behavior_fp or None,
        "behavior_new": behavior_new,
        "behavior_changed": event.get("behavior_changed"),
        "combined_score": combined,
        "delta": delta,
        "challenge_score": event.get("challenge_score"),
        "challenge_advantage": event.get("challenge_advantage"),
        "confirmation_score": event.get("confirmation_score"),
        "confirmation_advantage": event.get("confirmation_advantage"),
        "confirmation_gate": event.get("confirmation_gate"),
        "accepted": bool(event.get("accepted")),
        "change_summary": event.get("change_summary", ""),
        "hypothesis": event.get("hypothesis", ""),
        "reason": event.get("reason"),
    }
    append_jsonl(experiments_path(root), record)

    role = record.get("role")
    if role in ROLE_ORDER and delta is not None:
        stats = load_role_stats(root)
        s = stats[role]
        n = int(s.get("attempts", 0))
        old_mean = float(s.get("mean_delta", 0.0))
        old_ch = float(s.get("mean_challenge_advantage", 0.0))
        old_behavior = float(s.get("behavior_change_rate", 0.0) or 0.0)
        old_novel_behavior = float(s.get("novel_behavior_rate", 0.0) or 0.0)
        ch = float(record.get("challenge_advantage") or 0.0)
        behavior = 1.0 if record.get("behavior_changed") else 0.0
        novel_behavior = 1.0 if record.get("behavior_new") else 0.0
        s["attempts"] = n + 1
        s["mean_delta"] = round((old_mean * n + delta) / (n + 1), 4)
        s["mean_challenge_advantage"] = round((old_ch * n + ch) / (n + 1), 4)
        s["behavior_change_rate"] = round((old_behavior * n + behavior) / (n + 1), 4)
        s["novel_behavior_rate"] = round((old_novel_behavior * n + novel_behavior) / (n + 1), 4)
        best = s.get("best_delta")
        s["best_delta"] = round(delta, 4) if best is None else round(max(float(best), delta), 4)
        if record["accepted"]:
            s["promotions"] = int(s.get("promotions", 0)) + 1
        write_json(stats_path(root), stats)
    return record


def mark_promotion(root, generation, candidate):
    rows = _json_lines(experiments_path(root))
    changed = False
    for row in rows:
        if int(row.get("generation", -1)) == int(generation) and int(row.get("candidate", -1)) == int(candidate):
            row["accepted"] = True
            changed = True
    if changed:
        path = experiments_path(root)
        path.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in rows) + "\n", encoding="utf-8")
        # Rebuild stats so promotion count stays correct.
        stats = {role: {"attempts": 0, "promotions": 0, "mean_delta": 0.0, "best_delta": None, "mean_challenge_advantage": 0.0, "behavior_change_rate": 0.0, "novel_behavior_rate": 0.0} for role in ROLE_ORDER}
        grouped = {role: [] for role in ROLE_ORDER}
        for row in rows:
            role = row.get("role")
            if role in grouped and row.get("delta") is not None:
                grouped[role].append(row)
        for role, vals in grouped.items():
            if vals:
                ds = [float(x.get("delta", 0)) for x in vals]
                cs = [float(x.get("challenge_advantage") or 0) for x in vals]
                stats[role] = {
                    "attempts": len(vals),
                    "promotions": sum(1 for x in vals if x.get("accepted")),
                    "mean_delta": round(sum(ds) / len(ds), 4),
                    "best_delta": round(max(ds), 4),
                    "mean_challenge_advantage": round(sum(cs) / len(cs), 4),
                    "behavior_change_rate": round(sum(1 for x in vals if x.get("behavior_changed")) / len(vals), 4),
                    "novel_behavior_rate": round(sum(1 for x in vals if x.get("behavior_new")) / len(vals), 4),
                }
        write_json(stats_path(root), stats)


def research_summary(root, current_generation=0, limit=10):
    rows = _json_lines(experiments_path(root))[-limit:]
    stats = load_role_stats(root)
    stagnation = stagnation_generations(root, current_generation)
    compact = []
    for x in rows:
        compact.append({
            "gen": x.get("generation"),
            "candidate": x.get("candidate"),
            "role": x.get("role"),
            "score": x.get("combined_score"),
            "delta": x.get("delta"),
            "challenge_advantage": x.get("challenge_advantage"),
            "novelty": x.get("novelty"),
            "fingerprint": x.get("fingerprint"),
            "content_fingerprint": x.get("content_fingerprint"),
            "behavior_new": x.get("behavior_new"),
            "behavior_changed": x.get("behavior_changed"),
            "confirmation_advantage": x.get("confirmation_advantage"),
            "summary": x.get("change_summary"),
            "reason": x.get("reason"),
        })
    return {
        "stagnation_generations": stagnation,
        "recent_experiments": compact,
        "role_stats": stats,
        "instruction": (
            "Use scores as experimental evidence. Avoid exact content duplicates and repeated low-value behavior. "
            "Structural novelty is useful only if it preserves performance and eventually changes useful behavior. "
            "Neutral scaffolds may survive in the beam, but repeated behaviorally identical refinements are a plateau."
        ),
    }

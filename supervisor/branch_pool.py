import copy
import math
from pathlib import Path

from .storage import read_json, write_json, append_jsonl, utc_now
from .evolution_research import content_fingerprint


def _path(root):
    return Path(root) / 'state' / 'branch_pool.json'


def _archive_path(root):
    return Path(root) / 'state' / 'branch_archive.jsonl'


def _normalize_branch(branch):
    b = copy.deepcopy(branch) if isinstance(branch, dict) else {}
    defaults = {
        'id': None,
        'created_at': None,
        'generation': 0,
        'candidate': None,
        'parent_agent_id': None,
        'parent_branch_id': None,
        'root_branch_id': None,
        'depth': 1,
        'combined_score': -999.0,
        'challenge_score': 0.0,
        'challenge_advantage': 0.0,
        'novelty': 0.0,
        'fingerprint': '',
        'content_fingerprint': '',
        'behavior_fingerprint': '',
        'role': None,
        'change_summary': '',
        'hypothesis': '',
        'self_prompt': '',
        'ir_source': None,
        'use_count': 0,
        'last_selected_generation': None,
        'refinement_attempts': 0,
        'improving_children': 0,
        'neutral_children': 0,
        'failed_children': 0,
        'behavior_repeat_children': 0,
        'best_child_delta': None,
        'ema_child_delta': 0.0,
        'lineage_credit': 0.0,
        'plateau_streak': 0,
        'duplicate_hits': 0,
        'last_child_generation': None,
    }
    for key, value in defaults.items():
        b.setdefault(key, value)
    if not b.get('content_fingerprint') and isinstance(b.get('ir_source'), dict):
        b['content_fingerprint'] = content_fingerprint(b['ir_source'])
    if not b.get('root_branch_id'):
        b['root_branch_id'] = b.get('id') or b.get('parent_branch_id')
    return b


def load_branch_pool(root):
    data = read_json(_path(root), {'updated_at': None, 'branches': []})
    if not isinstance(data, dict):
        data = {'updated_at': None, 'branches': []}
    rows = data.get('branches') if isinstance(data.get('branches'), list) else []
    data['branches'] = [_normalize_branch(x) for x in rows if isinstance(x, dict)]
    return data


def _archive(root, branch, reason, generation, extra=None):
    row = {
        'at': utc_now(),
        'generation': int(generation),
        'reason': reason,
        'branch': {k: branch.get(k) for k in (
            'id','generation','depth','combined_score','challenge_advantage','novelty',
            'fingerprint','content_fingerprint','behavior_fingerprint','role',
            'use_count','refinement_attempts','best_child_delta','ema_child_delta',
            'lineage_credit','plateau_streak','parent_branch_id','root_branch_id'
        )},
    }
    if isinstance(extra, dict):
        row.update(extra)
    append_jsonl(_archive_path(root), row)


def _priority(branch, config, generation):
    evo = config.get('evolution', {})
    age = max(0, int(generation) - int(branch.get('generation', generation)))
    best = branch.get('best_child_delta')
    best = 0.0 if best is None else float(best)
    ema = float(branch.get('ema_child_delta', 0.0) or 0.0)
    lineage_credit = float(branch.get('lineage_credit', 0.0) or 0.0)
    credit_signal = math.tanh((0.65 * best + 0.35 * ema) / 2.5) + lineage_credit
    return (
        float(branch.get('combined_score', -999.0))
        + float(evo.get('branch_novelty_weight', 1.25)) * float(branch.get('novelty', 0.0) or 0.0)
        + float(evo.get('branch_challenge_weight', 0.10)) * float(branch.get('challenge_advantage', 0.0) or 0.0)
        + float(evo.get('branch_credit_weight', 0.65)) * credit_signal
        - float(evo.get('branch_age_penalty', 0.08)) * age
        - float(evo.get('branch_plateau_penalty', 0.55)) * int(branch.get('plateau_streak', 0) or 0)
    )


def _selection_priority(branch, config, generation):
    evo = config.get('evolution', {})
    score = _priority(branch, config, generation)
    uses = max(0, int(branch.get('use_count', 0) or 0))
    score += float(evo.get('branch_underuse_bonus', 0.75)) / math.sqrt(1.0 + uses)
    last = branch.get('last_selected_generation')
    if last is not None:
        gap = int(generation) - int(last)
        cooldown = max(0, int(evo.get('branch_selection_cooldown_generations', 1)))
        if gap <= cooldown:
            score -= float(evo.get('branch_recent_use_penalty', 1.5)) * (cooldown - gap + 1)
    return score


def _dedupe_exact(rows):
    best = {}
    nofp = []
    for b in rows:
        fp = str(b.get('content_fingerprint') or '')
        if not fp:
            nofp.append(b)
            continue
        old = best.get(fp)
        if old is None or (float(b.get('priority', -999)), float(b.get('combined_score', -999))) > (
            float(old.get('priority', -999)), float(old.get('combined_score', -999))
        ):
            best[fp] = b
    return list(best.values()) + nofp


def prune_branch_pool(root, config, generation):
    pool = load_branch_pool(root)
    evo = config.get('evolution', {})
    width = max(1, int(evo.get('beam_width', 4)))
    max_age = max(1, int(evo.get('branch_max_age', 10)))
    hard_depth = max(1, int(evo.get('branch_hard_depth_cap', evo.get('branch_max_depth', 8))))
    plateau_retire = max(1, int(evo.get('branch_plateau_retire_after', 4)))
    behavior_cap = max(1, int(evo.get('branch_behavior_family_cap', 2)))

    survivors = []
    for raw in pool.get('branches', []):
        b = _normalize_branch(raw)
        if not isinstance(b.get('ir_source'), dict):
            _archive(root, b, 'invalid_ir_source', generation)
            continue
        age = max(0, int(generation) - int(b.get('generation', generation)))
        if age > max_age:
            _archive(root, b, 'aged_out', generation)
            continue
        if int(b.get('depth', 1)) > hard_depth:
            _archive(root, b, 'hard_depth_limit', generation)
            continue
        min_plateau_attempts = max(2, (plateau_retire + 1) // 2)
        if int(b.get('plateau_streak', 0) or 0) >= plateau_retire and int(b.get('refinement_attempts', 0) or 0) >= min_plateau_attempts:
            _archive(root, b, 'plateau_retired', generation)
            continue
        b['age'] = age
        b['priority'] = round(_priority(b, config, generation), 4)
        b['selection_priority'] = round(_selection_priority(b, config, generation), 4)
        survivors.append(b)

    exact_before = list(survivors)
    survivors = _dedupe_exact(survivors)
    kept_ids = {x.get('id') for x in survivors}
    for b in exact_before:
        if b.get('id') not in kept_ids:
            _archive(root, b, 'exact_duplicate_pruned', generation)

    # Do not let behaviorally identical branches consume the whole beam.
    grouped = {}
    passthrough = []
    for b in survivors:
        key = str(b.get('behavior_fingerprint') or '')
        if not key:
            passthrough.append(b)
        else:
            grouped.setdefault(key, []).append(b)
    family_rows = list(passthrough)
    for key, vals in grouped.items():
        vals.sort(key=lambda x: (x.get('priority', -999), x.get('novelty', 0.0), -x.get('use_count', 0)), reverse=True)
        keep = vals[:behavior_cap]
        family_rows.extend(keep)
        for b in vals[behavior_cap:]:
            _archive(root, b, 'behavior_family_cap', generation, {'behavior_fingerprint': key})

    family_rows.sort(
        key=lambda b: (b.get('priority', -999), b.get('selection_priority', -999), b.get('novelty', 0.0)),
        reverse=True,
    )
    kept = family_rows[:width]
    for b in family_rows[width:]:
        _archive(root, b, 'beam_width_pruned', generation)

    out = {'updated_at': utc_now(), 'generation': int(generation), 'branches': kept}
    write_json(_path(root), out)
    return out


def select_branch_parent(root, config, generation, candidate_index):
    evo = config.get('evolution', {})
    start_idx = int(evo.get('branch_use_from_candidate', 2))
    if int(candidate_index) < start_idx:
        return None
    pool = prune_branch_pool(root, config, generation)
    rows = list(pool.get('branches', []))
    if not rows:
        return None

    cooldown = max(0, int(evo.get('branch_selection_cooldown_generations', 1)))
    band = float(evo.get('branch_rotation_score_band', 1.0))
    best_overall = max(float(b.get('combined_score', -999.0)) for b in rows)
    alternatives = []
    for b in rows:
        last = b.get('last_selected_generation')
        off_cooldown = last is None or int(generation) - int(last) > cooldown
        near_best_overall = float(b.get('combined_score', -999.0)) >= best_overall - band
        if off_cooldown and near_best_overall:
            alternatives.append(b)
    # Cooldown rotates comparable branches, but never forces a clearly inferior parent.
    choice_pool = alternatives if alternatives else rows
    best_combined = max(float(b.get('combined_score', -999.0)) for b in choice_pool)
    near_best = [b for b in choice_pool if float(b.get('combined_score', -999.0)) >= best_combined - band]
    min_uses = min(int(b.get('use_count', 0) or 0) for b in near_best)
    fair_pool = [b for b in near_best if int(b.get('use_count', 0) or 0) == min_uses]
    fair_pool.sort(
        key=lambda b: (
            _selection_priority(b, config, generation),
            float(b.get('novelty', 0.0) or 0.0),
            str(b.get('id') or ''),
        ),
        reverse=True,
    )
    chosen_id = fair_pool[0].get('id')

    data = load_branch_pool(root)
    chosen = None
    for b in data.get('branches', []):
        if b.get('id') == chosen_id:
            b['use_count'] = int(b.get('use_count', 0) or 0) + 1
            b['last_selected_generation'] = int(generation)
            b['selection_priority'] = round(_selection_priority(b, config, generation), 4)
            chosen = copy.deepcopy(b)
            break
    data['updated_at'] = utc_now()
    write_json(_path(root), data)
    return chosen


def record_branch_outcome(root, config, generation, parent_branch_id, child_event):
    if not parent_branch_id:
        return None
    pool = load_branch_pool(root)
    target = None
    for b in pool.get('branches', []):
        if b.get('id') == parent_branch_id:
            target = b
            break
    if target is None:
        return None

    evo = config.get('evolution', {})
    eps = float(evo.get('branch_progress_epsilon', 0.10))
    child_combo = child_event.get('combined_score')
    if child_combo is None:
        return None
    delta = float(child_combo) - float(target.get('combined_score', child_combo))
    attempts = int(target.get('refinement_attempts', 0) or 0)
    old_ema = float(target.get('ema_child_delta', 0.0) or 0.0)
    alpha = 0.35
    target['refinement_attempts'] = attempts + 1
    target['ema_child_delta'] = round((1.0 - alpha) * old_ema + alpha * delta, 4)
    old_best = target.get('best_child_delta')
    target['best_child_delta'] = round(delta, 4) if old_best is None else round(max(float(old_best), delta), 4)
    target['last_child_generation'] = int(generation)

    behavior_same = bool(
        target.get('behavior_fingerprint')
        and child_event.get('behavior_fingerprint')
        and target.get('behavior_fingerprint') == child_event.get('behavior_fingerprint')
    )
    if behavior_same:
        target['behavior_repeat_children'] = int(target.get('behavior_repeat_children', 0) or 0) + 1

    if delta > eps:
        target['improving_children'] = int(target.get('improving_children', 0) or 0) + 1
        target['plateau_streak'] = 0
    elif delta < -eps:
        target['failed_children'] = int(target.get('failed_children', 0) or 0) + 1
        target['plateau_streak'] = int(target.get('plateau_streak', 0) or 0) + 1
    else:
        target['neutral_children'] = int(target.get('neutral_children', 0) or 0) + 1
        target['plateau_streak'] = int(target.get('plateau_streak', 0) or 0) + (2 if behavior_same else 1)

    # Long-term credit rewards branches that produce better descendants but decays naturally.
    normalized_delta = max(-1.0, min(1.0, delta / 4.0))
    credit = float(target.get('lineage_credit', 0.0) or 0.0)
    target['lineage_credit'] = round(max(-1.0, min(1.0, 0.78 * credit + 0.22 * normalized_delta)), 4)

    pool['updated_at'] = utc_now()
    write_json(_path(root), pool)
    # Pruning is intentionally deferred until the child has had a chance to be
    # considered. This preserves direct-parent metadata for lineage/root credit.
    return copy.deepcopy(target)


def consider_branch(root, config, generation, event, proposal, incumbent_combined):
    evo = config.get('evolution', {})
    ir_source = proposal.get('ir_source') if isinstance(proposal, dict) else None
    if not isinstance(ir_source, dict):
        return None
    if not event.get('challenge_gate'):
        return None
    combo = event.get('combined_score')
    if combo is None:
        return None
    if float(combo) < float(incumbent_combined) - float(evo.get('neutral_margin', 3.0)):
        return None
    if float(event.get('challenge_advantage', -999)) < float(evo.get('branch_min_challenge_advantage', -2.0)):
        return None

    parent_depth = int(proposal.get('branch_depth', 0) or 0)
    depth = parent_depth + 1
    hard_depth = max(1, int(evo.get('branch_hard_depth_cap', evo.get('branch_max_depth', 8))))
    neutral_depth = max(1, int(evo.get('branch_neutral_depth_cap', 4)))
    if depth > hard_depth:
        return None

    # A deep neutral branch must earn extra depth. Compare behavior with its direct parent when possible.
    pool_before = load_branch_pool(root)
    parent_id_for_progress = proposal.get('branch_parent_id')
    parent_for_progress = next((x for x in pool_before.get('branches', []) if x.get('id') == parent_id_for_progress), None)
    parent_behavior_changed = bool(
        parent_for_progress
        and event.get('behavior_fingerprint')
        and parent_for_progress.get('behavior_fingerprint')
        and event.get('behavior_fingerprint') != parent_for_progress.get('behavior_fingerprint')
    )
    delta_incumbent = float(combo) - float(incumbent_combined)
    progress = (
        delta_incumbent >= float(evo.get('branch_depth_extension_min_delta', 0.10))
        or float(event.get('challenge_advantage', 0.0) or 0.0) >= float(evo.get('branch_depth_extension_challenge_advantage', 1.0))
        or (
            (parent_behavior_changed or bool(event.get('behavior_changed')))
            and float(event.get('novelty', 0.0) or 0.0) >= float(evo.get('branch_depth_extension_novelty', 0.25))
        )
    )
    if depth > neutral_depth and not progress:
        _archive(root, {
            'id': None, 'depth': depth, 'combined_score': combo,
            'challenge_advantage': event.get('challenge_advantage'),
            'fingerprint': event.get('fingerprint'),
            'content_fingerprint': content_fingerprint(ir_source),
            'behavior_fingerprint': event.get('behavior_fingerprint'),
        }, 'neutral_depth_cap', generation)
        return None

    pool = pool_before
    branches = list(pool.get('branches', []))
    structural_fp = str(event.get('fingerprint') or '')
    content_fp = content_fingerprint(ir_source)
    behavior_fp = str(event.get('behavior_fingerprint') or '')

    # Exact content duplicates refresh the existing record instead of occupying another slot.
    for old in branches:
        if content_fp and old.get('content_fingerprint') == content_fp:
            old['duplicate_hits'] = int(old.get('duplicate_hits', 0) or 0) + 1
            if float(combo) > float(old.get('combined_score', -999)):
                old['combined_score'] = float(combo)
                old['challenge_score'] = float(event.get('challenge_score', 0.0) or 0.0)
                old['challenge_advantage'] = float(event.get('challenge_advantage', 0.0) or 0.0)
                old['novelty'] = float(event.get('novelty', 0.0) or 0.0)
            pool['updated_at'] = utc_now()
            write_json(_path(root), pool)
            out = copy.deepcopy(old)
            out['retention_status'] = 'duplicate-refresh'
            return out

    parent_id = proposal.get('branch_parent_id')
    parent = next((x for x in branches if x.get('id') == parent_id), None)
    branch_id = f"B{int(generation):04d}-{int(event.get('candidate',0)):02d}-{content_fp[:8] or structural_fp[:8] or 'novel'}"
    branch = _normalize_branch({
        'id': branch_id,
        'created_at': utc_now(),
        'generation': int(generation),
        'candidate': event.get('candidate'),
        'parent_agent_id': event.get('parent_id'),
        'parent_branch_id': parent_id,
        'root_branch_id': (parent.get('root_branch_id') if parent else None) or (parent.get('id') if parent else None) or branch_id,
        'depth': depth,
        'combined_score': float(combo),
        'challenge_score': float(event.get('challenge_score', 0.0) or 0.0),
        'challenge_advantage': float(event.get('challenge_advantage', 0.0) or 0.0),
        'novelty': float(event.get('novelty', 0.0) or 0.0),
        'fingerprint': structural_fp,
        'content_fingerprint': content_fp,
        'behavior_fingerprint': behavior_fp,
        'role': event.get('experiment_role'),
        'change_summary': event.get('change_summary', ''),
        'hypothesis': event.get('hypothesis', ''),
        'self_prompt': proposal.get('self_prompt', ''),
        'ir_source': copy.deepcopy(ir_source),
    })
    branches.append(branch)
    write_json(_path(root), {'updated_at': utc_now(), 'branches': branches})
    pruned = prune_branch_pool(root, config, generation)
    survivor = next((x for x in pruned.get('branches', []) if x.get('id') == branch_id), None)
    if survivor is None:
        return None
    survivor = copy.deepcopy(survivor)
    survivor['retention_status'] = 'retained'
    return survivor


def clear_branch_pool(root, reason='promotion'):
    pool = load_branch_pool(root)
    generation = max([int(x.get('generation', 0)) for x in pool.get('branches', [])] + [0])
    for b in pool.get('branches', []):
        _archive(root, b, 'pool_cleared', generation, {'clear_reason': reason})
    write_json(_path(root), {'updated_at': utc_now(), 'reason': reason, 'branches': []})


def _archive_count(root):
    p = _archive_path(root)
    if not p.exists():
        return 0
    try:
        return sum(1 for line in p.read_text(encoding='utf-8').splitlines() if line.strip())
    except Exception:
        return 0


def branch_summary(root, config=None, generation=0):
    # Read-only summary: inspecting /beam must never mutate evolutionary state.
    pool = load_branch_pool(root)
    rows = []
    for raw in pool.get('branches', []):
        b = _normalize_branch(raw)
        if config is not None:
            b['age'] = max(0, int(generation) - int(b.get('generation', generation)))
            b['priority'] = round(_priority(b, config or {}, generation), 4)
            b['selection_priority'] = round(_selection_priority(b, config or {}, generation), 4)
        rows.append({k: b.get(k) for k in (
            'id','generation','age','depth','combined_score','challenge_advantage',
            'novelty','role','change_summary','parent_branch_id','root_branch_id','priority',
            'selection_priority','use_count','last_selected_generation','refinement_attempts',
            'improving_children','neutral_children','failed_children','behavior_repeat_children',
            'best_child_delta','ema_child_delta','lineage_credit','plateau_streak',
            'fingerprint','content_fingerprint','behavior_fingerprint','duplicate_hits'
        )})
    return {
        'count': len(rows),
        'retired_count': _archive_count(root),
        'branches': rows,
        'policy': 'fair-rotation + exact dedupe + behavior-family cap + long-term credit + controlled depth',
    }

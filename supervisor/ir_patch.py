import copy
import json
from pathlib import Path

from .ir_normalizer import normalize_candidate_ir

PATCH_OP_ALIASES = {
    'replace_body': 'replace_main_body',
    'set_body': 'replace_main_body',
    'main_body': 'replace_main_body',
    'add_helper': 'upsert_helper',
    'update_helper': 'upsert_helper',
    'set_helper': 'upsert_helper',
    'delete_helper': 'remove_helper',
    'add_global': 'upsert_global',
    'update_global': 'upsert_global',
    'set_global': 'upsert_global',
    'delete_global': 'remove_global',
    'add_local': 'upsert_local',
    'update_local': 'upsert_local',
    'set_local': 'upsert_local',
    'delete_local': 'remove_local',
    'add_subagent': 'upsert_subagent',
    'update_subagent': 'upsert_subagent',
    'set_subagent': 'upsert_subagent',
    'delete_subagent': 'remove_subagent',
    'set_prompt': 'set_self_prompt',
    'update_prompt': 'set_self_prompt',
    'set_memory': 'set_memory_pages',
    'memory_pages': 'set_memory_pages',
}


def seed_candidate_ir(self_prompt=''):
    def blocked(bit):
        return {
            'op': 'cmp', 'kind': 'ne',
            'a': {'op':'bin','kind':'and','a':{'op':'local','name':'walls'},'b':{'op':'const','type':'i32','value':bit}},
            'b': {'op':'const','type':'i32','value':0}
        }

    def open_dir(bit):
        return {'op':'eqz','value':blocked(bit)}

    body = [
        {'op':'if','cond':{'op':'cmp','kind':'gt_s','a':{'op':'local','name':'gx'},'b':{'op':'local','name':'px'}},'then':[{'op':'if','cond':open_dir(2),'then':[{'op':'return','value':1}]}]},
        {'op':'if','cond':{'op':'cmp','kind':'lt_s','a':{'op':'local','name':'gx'},'b':{'op':'local','name':'px'}},'then':[{'op':'if','cond':open_dir(8),'then':[{'op':'return','value':3}]}]},
        {'op':'if','cond':{'op':'cmp','kind':'gt_s','a':{'op':'local','name':'gy'},'b':{'op':'local','name':'py'}},'then':[{'op':'if','cond':open_dir(4),'then':[{'op':'return','value':2}]}]},
        {'op':'if','cond':{'op':'cmp','kind':'lt_s','a':{'op':'local','name':'gy'},'b':{'op':'local','name':'py'}},'then':[{'op':'if','cond':open_dir(1),'then':[{'op':'return','value':0}]}]},
        {'op':'if','cond':open_dir(1),'then':[{'op':'return','value':0}]},
        {'op':'if','cond':open_dir(2),'then':[{'op':'return','value':1}]},
        {'op':'if','cond':open_dir(4),'then':[{'op':'return','value':2}]},
        {'op':'return','value':3},
    ]

    return {
        'change_summary': 'seed baseline',
        'hypothesis': '',
        'internal_conflict': '',
        'architecture_note': 'Baseline seed policy represented as typed IR.',
        'main_ir': {'globals': [], 'memory_pages': 0, 'helpers': [], 'locals': [], 'body': body},
        'subagents': [],
        'self_prompt': self_prompt or 'Improve genuine hidden-benchmark performance while preserving containment and valid IR.',
    }


def load_parent_candidate_ir(current_dir, fallback_self_prompt=''):
    current_dir = Path(current_dir)
    source = current_dir / 'source_ir.json'
    if source.exists():
        try:
            data = json.loads(source.read_text(encoding='utf-8'))
            if isinstance(data, dict) and isinstance(data.get('main_ir'), dict):
                normalized, _ = normalize_candidate_ir(data, fallback_self_prompt=fallback_self_prompt)
                return normalized
        except Exception:
            pass
    return seed_candidate_ir(fallback_self_prompt)


def _list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _name_of(item):
    return str((item or {}).get('name', '')).strip() if isinstance(item, dict) else ''


def _upsert_named(items, item):
    items = list(items or [])
    name = _name_of(item)
    if not name:
        return items
    for i, existing in enumerate(items):
        if _name_of(existing) == name:
            items[i] = item
            return items
    items.append(item)
    return items


def _remove_named(items, name):
    name = str(name or '').strip()
    return [x for x in list(items or []) if _name_of(x) != name]


def normalize_patch_response(response):
    if not isinstance(response, dict):
        raise ValueError('mutation patch response must be an object')

    if isinstance(response.get('main_ir'), dict):
        return {
            'change_summary': response.get('change_summary', ''),
            'hypothesis': response.get('hypothesis', ''),
            'internal_conflict': response.get('internal_conflict', ''),
            'architecture_note': response.get('architecture_note', ''),
            'operations': [{'op': 'replace_candidate_ir', 'candidate': response}],
        }

    ops = response.get('operations', response.get('patches', response.get('changes', [])))
    if isinstance(ops, dict):
        ops = [{'op': k, 'value': v} for k, v in ops.items()]
    ops = _list(ops)

    out_ops = []
    for raw in ops:
        if not isinstance(raw, dict):
            continue
        d = dict(raw)
        op = str(d.get('op', d.get('action', d.get('type', '')))).strip().lower()
        op = PATCH_OP_ALIASES.get(op, op)
        if not op:
            continue
        d['op'] = op
        out_ops.append(d)

    return {
        'change_summary': str(response.get('change_summary', ''))[:500],
        'hypothesis': str(response.get('hypothesis', ''))[:500],
        'internal_conflict': str(response.get('internal_conflict', ''))[:500],
        'architecture_note': str(response.get('architecture_note', ''))[:1000],
        'operations': out_ops,
    }


def apply_candidate_patch(parent_candidate, patch_response, fallback_self_prompt=''):
    candidate = copy.deepcopy(parent_candidate)
    patch = normalize_patch_response(patch_response)
    notes = []

    for key in ('change_summary','hypothesis','internal_conflict','architecture_note'):
        if patch.get(key):
            candidate[key] = patch[key]

    main = candidate.setdefault('main_ir', {})
    main.setdefault('globals', [])
    main.setdefault('locals', [])
    main.setdefault('helpers', [])
    main.setdefault('body', [])
    main.setdefault('memory_pages', 0)
    candidate.setdefault('subagents', [])

    applied = 0
    for opdata in patch['operations']:
        op = opdata.get('op')
        try:
            if op == 'replace_candidate_ir':
                replacement = opdata.get('candidate')
                if isinstance(replacement, dict):
                    candidate = copy.deepcopy(replacement)
                    applied += 1
                    notes.append('accepted accidental full-candidate response as replacement')
                continue

            main = candidate.setdefault('main_ir', {})
            main.setdefault('globals', [])
            main.setdefault('locals', [])
            main.setdefault('helpers', [])
            main.setdefault('body', [])
            candidate.setdefault('subagents', [])

            if op == 'replace_main_body':
                main['body'] = opdata.get('body', opdata.get('value', opdata.get('statements', [])))
                applied += 1
            elif op == 'merge_main_ir':
                value = opdata.get('value', opdata.get('main_ir', opdata.get('patch')))
                if isinstance(value, dict):
                    for k in ('globals','locals','helpers','body','memory_pages','emit_candidate_ir'):
                        if k in value:
                            main[k] = value[k]
                    applied += 1
            elif op == 'set_main_globals':
                main['globals'] = opdata.get('globals', opdata.get('value', [])); applied += 1
            elif op == 'set_main_locals':
                main['locals'] = opdata.get('locals', opdata.get('value', [])); applied += 1
            elif op == 'set_main_helpers':
                main['helpers'] = opdata.get('helpers', opdata.get('value', [])); applied += 1
            elif op == 'set_memory_pages':
                main['memory_pages'] = opdata.get('pages', opdata.get('value', 0)); applied += 1
            elif op == 'upsert_global':
                item = opdata.get('global', opdata.get('value', opdata.get('item', opdata)))
                if isinstance(item, dict): main['globals'] = _upsert_named(main.get('globals'), item); applied += 1
            elif op == 'remove_global':
                main['globals'] = _remove_named(main.get('globals'), opdata.get('name', opdata.get('value'))); applied += 1
            elif op == 'upsert_local':
                item = opdata.get('local', opdata.get('value', opdata.get('item', opdata)))
                if isinstance(item, dict): main['locals'] = _upsert_named(main.get('locals'), item); applied += 1
            elif op == 'remove_local':
                main['locals'] = _remove_named(main.get('locals'), opdata.get('name', opdata.get('value'))); applied += 1
            elif op == 'upsert_helper':
                item = opdata.get('helper', opdata.get('value', opdata.get('item')))
                if isinstance(item, dict): main['helpers'] = _upsert_named(main.get('helpers'), item); applied += 1
            elif op == 'remove_helper':
                main['helpers'] = _remove_named(main.get('helpers'), opdata.get('name', opdata.get('value'))); applied += 1
            elif op == 'replace_helper_body':
                name = str(opdata.get('name', '')).strip(); body = opdata.get('body', opdata.get('value', []))
                helpers = list(main.get('helpers') or [])
                for helper in helpers:
                    if isinstance(helper, dict) and str(helper.get('name','')).strip() == name:
                        helper['body'] = body; main['helpers'] = helpers; applied += 1; break
            elif op == 'upsert_subagent':
                item = opdata.get('subagent', opdata.get('value', opdata.get('item')))
                if isinstance(item, dict): candidate['subagents'] = _upsert_named(candidate.get('subagents'), item); applied += 1
            elif op == 'remove_subagent':
                candidate['subagents'] = _remove_named(candidate.get('subagents'), opdata.get('name', opdata.get('value'))); applied += 1
            elif op == 'replace_subagent_body':
                name = str(opdata.get('name', '')).strip(); body = opdata.get('body', opdata.get('value', []))
                subs = list(candidate.get('subagents') or [])
                for sub in subs:
                    if isinstance(sub, dict) and str(sub.get('name','')).strip() == name:
                        ir = sub.setdefault('ir', {})
                        if isinstance(ir, dict): ir['body'] = body; candidate['subagents'] = subs; applied += 1; break
            elif op == 'set_self_prompt':
                value = opdata.get('self_prompt', opdata.get('value', ''))
                if isinstance(value, str) and value.strip(): candidate['self_prompt'] = value; applied += 1
            elif op == 'set_architecture_note':
                candidate['architecture_note'] = str(opdata.get('value', opdata.get('architecture_note', '')))[:3000]; applied += 1
            elif op == 'set_emit_candidate_ir':
                value = opdata.get('value', opdata.get('emit_candidate_ir'))
                if isinstance(value, dict): main['emit_candidate_ir'] = value; applied += 1
            elif op == 'clear_emit_candidate_ir':
                main.pop('emit_candidate_ir', None); applied += 1
            else:
                notes.append(f'ignored unsupported patch op {op!r}')
        except Exception as exc:
            notes.append(f'ignored malformed patch op {op!r}: {type(exc).__name__}')

    if applied == 0:
        raise ValueError('mutation patch contained no usable operations')

    normalized, norm_notes = normalize_candidate_ir(candidate, fallback_self_prompt=fallback_self_prompt)
    return normalized, notes + norm_notes

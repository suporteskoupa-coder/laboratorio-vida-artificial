import copy
import json
import re

TYPE_ALIASES = {
    'i32': 'i32', 'int': 'i32', 'int32': 'i32', 'u32': 'i32', 's32': 'i32',
    'bool': 'i32', 'boolean': 'i32', 'byte': 'i32',
    'i64': 'i64', 'int64': 'i64', 'u64': 'i64', 's64': 'i64', 'long': 'i64',
}
VOID_ALIASES = {'void', 'none', 'null', ''}
NAME_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,63}$')

BIN_ALIASES = {
    '+': 'add', 'plus': 'add', '-': 'sub', 'minus': 'sub', '*': 'mul', 'times': 'mul',
    '&': 'and', '|': 'or', '^': 'xor', '<<': 'shl', '>>': 'shr_s', '>>>': 'shr_u',
    '/': 'div_s', '%': 'rem_s',
}
CMP_ALIASES = {
    '==': 'eq', '!=': 'ne', '<': 'lt_s', '>': 'gt_s', '<=': 'le_s', '>=': 'ge_s',
}
EXPR_OP_ALIASES = {
    'literal': 'const', 'constant': 'const', 'var': 'local', 'variable': 'local',
    'local_get': 'local', 'get_local': 'local', 'global_get': 'global', 'get_global': 'global',
    'binary': 'bin', 'binary_op': 'bin', 'compare': 'cmp', 'comparison': 'cmp',
    'zero_test': 'eqz', 'convert': 'cast', 'invoke': 'call', 'function_call': 'call',
    'memory_load': 'load',
}
STMT_OP_ALIASES = {
    'assign': 'set_local', 'set': 'set_local', 'local_set': 'set_local',
    'global_set': 'set_global', 'set_state': 'set_global',
    'conditional': 'if', 'loop': 'while', 'invoke': 'call', 'function_call': 'call',
    'memory_store': 'store', 'pass': 'noop',
}


def _jsonish(value):
    if not isinstance(value, str):
        return value
    s = value.strip()
    if not s or s[0] not in '[{':
        return value
    try:
        return json.loads(s)
    except Exception:
        return value


def _note(notes, text):
    if text not in notes and len(notes) < 80:
        notes.append(text)


def _safe_name(value, fallback, notes, what='name'):
    raw = str(value or '').strip()
    if raw.startswith('$'):
        raw = raw[1:]
    if NAME_RE.match(raw):
        return raw
    s = re.sub(r'[^A-Za-z0-9_]', '_', raw)
    if not s:
        s = fallback
    if s[0].isdigit():
        s = '_' + s
    s = s[:64]
    if not NAME_RE.match(s):
        s = fallback
    _note(notes, f'normalized invalid {what} {raw!r} -> {s!r}')
    return s


def _norm_type(value, notes, default='i32', allow_void=False):
    if value is None:
        return None if allow_void else default
    s = str(value).strip().lower()
    if allow_void and s in VOID_ALIASES:
        return None
    if s in TYPE_ALIASES:
        t = TYPE_ALIASES[s]
        if t != s:
            _note(notes, f'normalized type {value!r} -> {t}')
        return t
    _note(notes, f'unknown type {value!r}; defaulted to {default}')
    return default


def _listish(value):
    value = _jsonish(value)
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _named_entries(value, kind, notes):
    value = _jsonish(value)
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        # A single explicit object should stay a single entry.
        single_keys = {
            'global': {'name', 'type', 'init'},
            'local': {'name', 'type'},
            'param': {'name', 'type'},
            'helper': {'name', 'params', 'parameters', 'args', 'result', 'return_type', 'returns', 'locals', 'body', 'statements'},
            'subagent': {'name', 'purpose', 'ir', 'module_ir', 'module'},
        }[kind]
        if set(value).intersection(single_keys) and ('name' in value or kind in {'helper', 'subagent'} and ('body' in value or 'ir' in value or 'module_ir' in value)):
            return [value]
        out = []
        for name, spec in value.items():
            spec = _jsonish(spec)
            if isinstance(spec, dict):
                item = dict(spec)
                item.setdefault('name', name)
            elif kind in {'global', 'local', 'param'} and isinstance(spec, str):
                item = {'name': name, 'type': spec}
            elif kind == 'global' and isinstance(spec, (int, bool)):
                item = {'name': name, 'type': 'i32', 'init': int(spec)}
            elif kind == 'subagent':
                item = {'name': name, 'ir': spec}
            elif kind == 'helper':
                item = {'name': name, 'body': spec if isinstance(spec, list) else []}
            else:
                item = {'name': name}
            out.append(item)
        _note(notes, f'normalized {kind}s object-map -> list')
        return out
    return [value]


def _decls(value, kind, notes, allow_init=False):
    entries = _named_entries(value, kind, notes)
    out = []
    seen = set()
    for idx, raw in enumerate(entries):
        raw = _jsonish(raw)
        item = None
        if isinstance(raw, dict):
            if 'name' not in raw and len(raw) == 1:
                k, v = next(iter(raw.items()))
                if isinstance(v, dict):
                    item = dict(v); item['name'] = k
                else:
                    item = {'name': k, 'type': v}
            else:
                item = dict(raw)
        elif isinstance(raw, (list, tuple)) and len(raw) >= 2:
            item = {'name': raw[0], 'type': raw[1]}
            if allow_init and len(raw) >= 3:
                item['init'] = raw[2]
        elif isinstance(raw, str):
            s = raw.strip()
            if ':' in s:
                n, t = s.split(':', 1)
                item = {'name': n.strip(), 'type': t.strip()}
            elif s:
                item = {'name': s, 'type': 'i32'}
                _note(notes, f'{kind} {s!r} missing type; defaulted to i32')
        if not item:
            _note(notes, f'dropped unusable {kind} entry at index {idx}')
            continue
        name = _safe_name(item.get('name'), f'{kind}_{idx}', notes, f'{kind} name')
        if name in seen:
            _note(notes, f'dropped duplicate {kind} {name}')
            continue
        seen.add(name)
        obj = {'name': name, 'type': _norm_type(item.get('type'), notes)}
        if allow_init:
            try:
                obj['init'] = int(item.get('init', 0) or 0)
            except Exception:
                obj['init'] = 0
                _note(notes, f'{kind} {name} invalid init; defaulted to 0')
        out.append(obj)
    return out


def _contains_value_return(body):
    for st in _listish(body):
        if not isinstance(st, dict):
            continue
        op = str(st.get('op', '')).lower()
        if op == 'return' and st.get('value') is not None:
            return True
        for key in ('then', 'else', 'body', 'statements'):
            if _contains_value_return(st.get(key)):
                return True
    return False


def _body_list(value, notes, label='body'):
    value = _jsonish(value)
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ('statements', 'body', 'code'):
            if key in value and isinstance(value[key], list):
                _note(notes, f'unwrapped {label}.{key}')
                return value[key]
        _note(notes, f'wrapped single {label} statement into list')
        return [value]
    if isinstance(value, str):
        p = _jsonish(value)
        if p is not value:
            return _body_list(p, notes, label)
    _note(notes, f'dropped unusable {label}')
    return []


def _rename_ref(name, mapping, notes, kind):
    raw = str(name or '').strip().lstrip('$')
    if raw in mapping:
        return mapping[raw]
    return _safe_name(raw, f'auto_{kind}', notes, f'{kind} reference')


def _expr(e, local_map, global_map, helper_map, notes):
    e = _jsonish(e)
    if isinstance(e, bool):
        return {'op': 'const', 'type': 'i32', 'value': 1 if e else 0}
    if isinstance(e, int):
        return {'op': 'const', 'type': 'i32', 'value': e}
    if isinstance(e, float) and e.is_integer():
        return {'op': 'const', 'type': 'i32', 'value': int(e)}
    if isinstance(e, str):
        s = e.strip()
        if re.fullmatch(r'-?\d+', s):
            return {'op': 'const', 'type': 'i32', 'value': int(s)}
        raw = s.lstrip('$')
        if raw in global_map:
            return {'op': 'global', 'name': global_map[raw]}
        return {'op': 'local', 'name': local_map.get(raw, _safe_name(raw, 'auto_local', notes, 'local reference'))}
    if not isinstance(e, dict):
        _note(notes, 'replaced unusable expression with i32.const 0')
        return {'op': 'const', 'type': 'i32', 'value': 0}

    d = dict(e)
    op = str(d.get('op') or d.get('kind') or '').strip().lower()
    op = EXPR_OP_ALIASES.get(op, op)

    if op == 'const':
        typ = _norm_type(d.get('type'), notes)
        value = d.get('value', d.get('val', 0))
        try: value = int(value or 0)
        except Exception: value = 0; _note(notes, 'invalid const value; defaulted to 0')
        return {'op':'const','type':typ,'value':value}
    if op == 'local':
        name = d.get('name', d.get('id', d.get('var')))
        return {'op':'local','name':_rename_ref(name, local_map, notes, 'local')}
    if op == 'global':
        name = d.get('name', d.get('id', d.get('var')))
        return {'op':'global','name':_rename_ref(name, global_map, notes, 'global')}
    if op in {'bin','cmp'}:
        kind = d.get('kind', d.get('operator', d.get('fn')))
        kind = str(kind or '').strip()
        if op == 'bin':
            kind = BIN_ALIASES.get(kind, CMP_ALIASES.get(kind, kind))
            if kind in {'eq','ne','lt_s','lt_u','gt_s','gt_u','le_s','le_u','ge_s','ge_u'}:
                _note(notes, f'normalized comparison kind {kind!r} from bin -> cmp')
                op = 'cmp'
        else:
            kind = CMP_ALIASES.get(kind, BIN_ALIASES.get(kind, kind))
            if kind in {'add','sub','mul','and','or','xor','shl','shr_u','shr_s','div_s','div_u','rem_s','rem_u'}:
                _note(notes, f'normalized arithmetic kind {kind!r} from cmp -> bin')
                op = 'bin'
        a = d.get('a', d.get('left', d.get('lhs', d.get('x'))))
        b = d.get('b', d.get('right', d.get('rhs', d.get('y'))))
        return {'op':op,'kind':kind,'a':_expr(a,local_map,global_map,helper_map,notes),'b':_expr(b,local_map,global_map,helper_map,notes)}
    if op == 'eqz':
        return {'op':'eqz','value':_expr(d.get('value',d.get('expr')),local_map,global_map,helper_map,notes)}
    if op == 'cast':
        return {'op':'cast','to':_norm_type(d.get('to',d.get('type')),notes),'signed':bool(d.get('signed',False)),'value':_expr(d.get('value',d.get('expr')),local_map,global_map,helper_map,notes)}
    if op == 'call':
        name = _rename_ref(d.get('name',d.get('function',d.get('target'))), helper_map, notes, 'helper')
        args = d.get('args', d.get('arguments', []))
        args = _listish(args)
        return {'op':'call','name':name,'args':[_expr(x,local_map,global_map,helper_map,notes) for x in args]}
    if op == 'select':
        return {
            'op':'select',
            'cond':_expr(d.get('cond',d.get('condition')),local_map,global_map,helper_map,notes),
            'if_true':_expr(d.get('if_true',d.get('then',d.get('true'))),local_map,global_map,helper_map,notes),
            'if_false':_expr(d.get('if_false',d.get('else',d.get('false'))),local_map,global_map,helper_map,notes),
        }
    if op == 'load':
        out={'op':'load','type':_norm_type(d.get('type'),notes),'addr':_expr(d.get('addr',d.get('address')),local_map,global_map,helper_map,notes)}
        if d.get('bits') is not None:
            try: out['bits']=int(d.get('bits'))
            except Exception: pass
        out['signed']=bool(d.get('signed',False))
        return out

    _note(notes, f'unsupported expression op {op!r}; replaced with i32.const 0')
    return {'op':'const','type':'i32','value':0}


def _stmts(value, local_map, global_map, helper_map, notes, label='body', loop_depth=0):
    out=[]
    for idx, s in enumerate(_body_list(value,notes,label)):
        s = _jsonish(s)
        if isinstance(s, str):
            w=s.strip().lower()
            if w in {'break','continue','noop','pass'}:
                s={'op':'noop' if w=='pass' else w}
            else:
                _note(notes, f'replaced unsupported string statement {s!r} with noop')
                s={'op':'noop'}
        if not isinstance(s, dict):
            _note(notes, f'replaced unusable statement {label}[{idx}] with noop')
            out.append({'op':'noop'}); continue
        d=dict(s)
        op=str(d.get('op') or d.get('kind') or '').strip().lower()
        op=STMT_OP_ALIASES.get(op,op)
        if op=='set_local':
            target=d.get('name',d.get('target',d.get('var')))
            # Explicit global scope changes the operation.
            if str(d.get('scope','')).lower()=='global':
                op='set_global'
            else:
                out.append({'op':'set_local','name':_rename_ref(target,local_map,notes,'local'),'value':_expr(d.get('value',d.get('expr')),local_map,global_map,helper_map,notes)}); continue
        if op=='set_global':
            target=d.get('name',d.get('target',d.get('var')))
            out.append({'op':'set_global','name':_rename_ref(target,global_map,notes,'global'),'value':_expr(d.get('value',d.get('expr')),local_map,global_map,helper_map,notes)}); continue
        if op=='return':
            obj={'op':'return'}
            if d.get('value',d.get('expr')) is not None:
                obj['value']=_expr(d.get('value',d.get('expr')),local_map,global_map,helper_map,notes)
            out.append(obj); continue
        if op=='if':
            out.append({'op':'if','cond':_expr(d.get('cond',d.get('condition')),local_map,global_map,helper_map,notes),'then':_stmts(d.get('then',d.get('then_body',d.get('true'))),local_map,global_map,helper_map,notes,label+'.then',loop_depth),'else':_stmts(d.get('else',d.get('else_body',d.get('false'))),local_map,global_map,helper_map,notes,label+'.else',loop_depth)}); continue
        if op=='while':
            out.append({'op':'while','cond':_expr(d.get('cond',d.get('condition')),local_map,global_map,helper_map,notes),'body':_stmts(d.get('body',d.get('statements')),local_map,global_map,helper_map,notes,label+'.while',loop_depth+1)}); continue
        if op in {'break','continue'}:
            if loop_depth <= 0:
                _note(notes,f'{op} outside loop replaced with noop')
                out.append({'op':'noop'})
            else:
                out.append({'op':op})
            continue
        if op=='noop':
            out.append({'op':'noop'}); continue
        if op=='call':
            name=_rename_ref(d.get('name',d.get('function',d.get('target'))),helper_map,notes,'helper')
            args=[_expr(x,local_map,global_map,helper_map,notes) for x in _listish(d.get('args',d.get('arguments',[])))]
            out.append({'op':'call','name':name,'args':args}); continue
        if op=='store':
            obj={'op':'store','type':_norm_type(d.get('type'),notes),'addr':_expr(d.get('addr',d.get('address')),local_map,global_map,helper_map,notes),'value':_expr(d.get('value',d.get('expr')),local_map,global_map,helper_map,notes)}
            if d.get('bits') is not None:
                try: obj['bits']=int(d.get('bits'))
                except Exception: pass
            out.append(obj); continue
        if op in {'bin','cmp','eqz','cast','select','load','local','global','const'}:
            _note(notes, f'pure expression used as statement ({op}); replaced with noop')
            out.append({'op':'noop'}); continue
        _note(notes, f'unsupported statement op {op!r}; replaced with noop')
        out.append({'op':'noop'})
    return out


def _collect_refs_expr(e, locals_out, globals_out, helpers_out):
    if not isinstance(e,dict): return
    op=e.get('op')
    if op=='local': locals_out.add(e.get('name'))
    elif op=='global': globals_out.add(e.get('name'))
    elif op=='call':
        helpers_out.add(e.get('name'))
        for a in e.get('args',[]) or []: _collect_refs_expr(a,locals_out,globals_out,helpers_out)
        return
    for k,v in e.items():
        if k in {'op','name','kind','type','to','bits','signed','value'} and not isinstance(v,(dict,list)): continue
        if isinstance(v,dict): _collect_refs_expr(v,locals_out,globals_out,helpers_out)
        elif isinstance(v,list):
            for x in v:
                if isinstance(x,dict): _collect_refs_expr(x,locals_out,globals_out,helpers_out)


def _collect_refs_stmt(st, locals_out, globals_out, helpers_out):
    if not isinstance(st,dict): return
    op=st.get('op')
    if op=='set_local': locals_out.add(st.get('name'))
    elif op=='set_global': globals_out.add(st.get('name'))
    elif op=='call': helpers_out.add(st.get('name'))
    for k,v in st.items():
        if isinstance(v,dict): _collect_refs_expr(v,locals_out,globals_out,helpers_out)
        elif isinstance(v,list):
            for x in v:
                if isinstance(x,dict):
                    if 'op' in x and x.get('op') in {'set_local','set_global','return','if','while','break','continue','call','store','noop'}:
                        _collect_refs_stmt(x,locals_out,globals_out,helpers_out)
                    else:
                        _collect_refs_expr(x,locals_out,globals_out,helpers_out)


def _normalize_helper_entries(value, notes):
    raw_entries=_named_entries(value,'helper',notes)
    out=[]
    for idx,raw in enumerate(raw_entries):
        raw=_jsonish(raw)
        if isinstance(raw,dict) and 'name' not in raw and len(raw)==1:
            k,v=next(iter(raw.items()))
            if isinstance(v,dict): raw={**v,'name':k}
        if not isinstance(raw,dict):
            _note(notes,f'dropped unusable helper entry at index {idx}')
            continue
        out.append(dict(raw))
    return out


def normalize_module_ir(ir, role, notes, path='main_ir'):
    ir=_jsonish(ir)
    if not isinstance(ir,dict):
        raise ValueError(f'{path} must be an object')
    d=dict(ir)

    globals_raw=d.get('globals',d.get('persistent_globals',d.get('state',[])))
    locals_raw=d.get('locals',d.get('local_vars',d.get('variables',[])))
    helpers_raw=d.get('helpers',d.get('functions',[]))
    body_raw=d.get('body',d.get('statements',d.get('code',[])))

    globals_list=_decls(globals_raw,'global',notes,allow_init=True)
    global_map={x['name']:x['name'] for x in globals_list}

    helper_raw_list=_normalize_helper_entries(helpers_raw,notes)
    helper_name_map={}
    used=set()
    for idx,h in enumerate(helper_raw_list):
        raw_name=h.get('name',h.get('id',h.get('function',f'helper_{idx}')))
        name=_safe_name(raw_name,f'helper_{idx}',notes,'helper name')
        base=name; n=2
        while name in used or name in {'decide','advise','emit_candidate'}:
            name=f'{base}_{n}'; n+=1
        used.add(name)
        helper_name_map[str(raw_name).strip().lstrip('$')]=name
        h['_normalized_name']=name

    fixed_params = ['px','py','gx','gy','walls','step','steps_left','width','height'] + (['advice_pack'] if role=='brain' else [])
    main_locals=_decls(locals_raw,'local',notes)
    main_local_map={x:x for x in fixed_params}
    main_local_map.update({x['name']:x['name'] for x in main_locals})

    helpers=[]
    for idx,h in enumerate(helper_raw_list):
        name=h['_normalized_name']
        params=_decls(h.get('params',h.get('parameters',h.get('args',[]))),'param',notes)
        locals_h=_decls(h.get('locals',h.get('local_vars',h.get('variables',[]))),'local',notes)
        local_map={x['name']:x['name'] for x in params}
        local_map.update({x['name']:x['name'] for x in locals_h})
        raw_body=h.get('body',h.get('statements',h.get('code',[])))
        result_raw=h.get('result',h.get('return_type',h.get('returns')))
        result=_norm_type(result_raw,notes,allow_void=True) if result_raw is not None else ('i32' if _contains_value_return(raw_body) else None)
        if result_raw is None and result is not None:
            _note(notes,f'helper {name} missing result; inferred i32 from value return')
        body=_stmts(raw_body,local_map,global_map,helper_name_map,notes,f'{path}.helper.{name}.body')
        helpers.append({'name':name,'params':params,'result':result,'locals':locals_h,'body':body})

    body=_stmts(body_raw,main_local_map,global_map,helper_name_map,notes,f'{path}.body')

    # Add missing locals/globals referenced by normalized bodies. This is a
    # best-effort structural repair; benchmark selection still decides whether
    # the resulting algorithm is useful.
    declared_globals={x['name'] for x in globals_list}
    declared_helpers={x['name'] for x in helpers}

    all_global_refs=set(); all_helper_refs=set()
    main_local_refs=set()
    for st in body: _collect_refs_stmt(st,main_local_refs,all_global_refs,all_helper_refs)
    for name in sorted(x for x in main_local_refs if x and x not in main_local_map):
        main_locals.append({'name':name,'type':'i32'}); main_local_map[name]=name
        _note(notes,f'auto-declared missing main local {name}:i32')

    for h in helpers:
        env={p['name'] for p in h['params']}|{l['name'] for l in h['locals']}
        lr=set()
        for st in h['body']: _collect_refs_stmt(st,lr,all_global_refs,all_helper_refs)
        for name in sorted(x for x in lr if x and x not in env):
            h['locals'].append({'name':name,'type':'i32'}); env.add(name)
            _note(notes,f'auto-declared missing local {h["name"]}.{name}:i32')

    for name in sorted(x for x in all_global_refs if x and x not in declared_globals):
        globals_list.append({'name':name,'type':'i32','init':0}); declared_globals.add(name)
        _note(notes,f'auto-declared missing global {name}:i32=0')

    # Unknown helper calls get a conservative stub. A weak stub should score
    # poorly and be rejected by the benchmark, but a superficial omission no
    # longer wastes the whole generation.
    for name in sorted(x for x in all_helper_refs if x and x not in declared_helpers):
        helpers.append({'name':name,'params':[],'result':'i32','locals':[],'body':[{'op':'return','value':{'op':'const','type':'i32','value':0}}]})
        declared_helpers.add(name)
        _note(notes,f'synthesized missing helper {name}() -> i32 0')

    # Memory is automatically enabled if the normalized IR uses load/store.
    def uses_memory_expr(e):
        if not isinstance(e,dict): return False
        if e.get('op')=='load': return True
        return any(uses_memory_expr(v) if isinstance(v,dict) else any(uses_memory_expr(x) for x in v if isinstance(x,dict)) if isinstance(v,list) else False for v in e.values())
    def uses_memory_stmt(st):
        if not isinstance(st,dict): return False
        if st.get('op')=='store': return True
        for v in st.values():
            if isinstance(v,dict) and uses_memory_expr(v): return True
            if isinstance(v,list):
                for x in v:
                    if isinstance(x,dict) and (uses_memory_stmt(x) or uses_memory_expr(x)): return True
        return False
    mem_needed=any(uses_memory_stmt(st) for st in body) or any(any(uses_memory_stmt(st) for st in h['body']) for h in helpers)
    mem_raw=d.get('memory_pages',d.get('memory',0))
    if isinstance(mem_raw,dict): mem_raw=mem_raw.get('pages',mem_raw.get('initial',0))
    try: memory_pages=int(mem_raw or 0)
    except Exception: memory_pages=0; _note(notes,f'{path} invalid memory_pages; defaulted to 0')
    memory_pages=max(0,min(16,memory_pages))
    if mem_needed and memory_pages==0:
        memory_pages=1; _note(notes,f'{path} uses memory; enabled 1 page automatically')

    out={
        'globals':globals_list,
        'memory_pages':memory_pages,
        'helpers':helpers,
        'locals':main_locals,
        'body':body,
    }
    emit=d.get('emit_candidate_ir',d.get('emit_child_ir',d.get('child_ir')))
    if isinstance(emit,dict): out['emit_candidate_ir']=emit
    return out



def _is_zero_stub_helper(helper):
    if not isinstance(helper, dict):
        return False
    if helper.get('params') not in ([], None):
        return False
    if helper.get('result') != 'i32':
        return False
    body = helper.get('body') or []
    if len(body) != 1 or not isinstance(body[0], dict) or body[0].get('op') != 'return':
        return False
    value = body[0].get('value')
    return (
        isinstance(value, dict)
        and value.get('op') == 'const'
        and value.get('type') == 'i32'
        and int(value.get('value', 1)) == 0
    )


def _subagent_advice_expr(index):
    shift = int(index) * 8
    value = {'op': 'global', 'name': '__ELLBERR_ADVICE_PACK__'}
    if shift:
        value = {
            'op': 'bin', 'kind': 'shr_u',
            'a': value,
            'b': {'op': 'const', 'type': 'i64', 'value': shift},
        }
    value = {
        'op': 'bin', 'kind': 'and',
        'a': value,
        'b': {'op': 'const', 'type': 'i64', 'value': 255},
    }
    return {'op': 'cast', 'to': 'i32', 'signed': False, 'value': value}


def _wire_subagent_helper_bridges(main_ir, subagents, notes):
    """
    Qwen frequently models a subagent as `scout()` even though executable
    subagents run in separate Wasmtime instances. The runtime already packs
    each subagent's advise() byte into the main brain's advice_pack.

    Missing helper calls are normalized earlier to a zero-return stub. If a
    zero stub has the same name as a real subagent, replace only that synthetic
    stub with a deterministic bridge reading the correct advice_pack byte.
    """
    if not isinstance(main_ir, dict) or not subagents:
        return main_ir

    helpers = list(main_ir.get('helpers') or [])
    sub_index = {str(s.get('name')): i for i, s in enumerate(subagents) if isinstance(s, dict) and s.get('name')}
    bridge_names = []
    for helper in helpers:
        name = str(helper.get('name', '')) if isinstance(helper, dict) else ''
        if name in sub_index and _is_zero_stub_helper(helper):
            bridge_names.append(name)

    if not bridge_names:
        return main_ir

    # Choose a collision-free i64 global used as the bridge's captured advice
    # pack. WebAssembly helper functions cannot directly capture decide() locals.
    globals_list = list(main_ir.get('globals') or [])
    existing = {str(g.get('name')) for g in globals_list if isinstance(g, dict)}
    bridge_global = '__ellberr_advice_pack'
    n = 2
    while bridge_global in existing:
        bridge_global = f'__ellberr_advice_pack_{n}'
        n += 1
    globals_list.append({'name': bridge_global, 'type': 'i64', 'init': 0})
    main_ir['globals'] = globals_list

    def advice_expr(index):
        expr = _subagent_advice_expr(index)
        # Replace placeholder global name with the collision-free name.
        def repl(x):
            if isinstance(x, dict):
                if x.get('op') == 'global' and x.get('name') == '__ELLBERR_ADVICE_PACK__':
                    x = dict(x); x['name'] = bridge_global; return x
                return {k: repl(v) for k, v in x.items()}
            if isinstance(x, list):
                return [repl(v) for v in x]
            return x
        return repl(expr)

    for helper in helpers:
        if isinstance(helper, dict) and str(helper.get('name', '')) in bridge_names:
            name = str(helper['name'])
            helper['body'] = [{'op': 'return', 'value': advice_expr(sub_index[name])}]
            helper['result'] = 'i32'
            helper['params'] = []
            _note(notes, f'wired subagent helper {name}() -> advice_pack byte {sub_index[name]}')
    main_ir['helpers'] = helpers

    # Capture the current call's packed advice before any helper can read it.
    capture = {
        'op': 'set_global',
        'name': bridge_global,
        'value': {'op': 'local', 'name': 'advice_pack'},
    }
    body = list(main_ir.get('body') or [])
    main_ir['body'] = [capture] + body
    return main_ir

def normalize_candidate_ir(proposal, fallback_self_prompt=None):
    notes=[]
    proposal=_jsonish(proposal)
    if not isinstance(proposal,dict):
        raise ValueError('candidate must be an object')
    d=copy.deepcopy(proposal)
    main=d.get('main_ir',d.get('main',d.get('brain_ir',d.get('brain'))))
    if main is None:
        raise ValueError('main_ir must be an object')
    main_ir=normalize_module_ir(main,'brain',notes,'main_ir')

    subs_raw=d.get('subagents',d.get('agents',d.get('modules',[])))
    subs_entries=_named_entries(subs_raw,'subagent',notes)
    subagents=[]; seen=set()
    for idx,raw in enumerate(subs_entries):
        raw=_jsonish(raw)
        if isinstance(raw,dict) and 'name' not in raw and len(raw)==1:
            k,v=next(iter(raw.items()))
            raw={'name':k,'ir':v if isinstance(v,dict) else {}}
        if not isinstance(raw,dict):
            _note(notes,f'dropped unusable subagent entry at index {idx}')
            continue
        name=_safe_name(raw.get('name',raw.get('id',f'subagent_{idx}')),f'subagent_{idx}',notes,'subagent name')
        base=name; n=2
        while name in seen:
            name=f'{base}_{n}'; n+=1
        seen.add(name)
        ir=raw.get('ir',raw.get('module_ir',raw.get('module')))
        if ir is None:
            # Treat the subagent object itself as module IR if it looks like one.
            if any(k in raw for k in ('body','statements','helpers','functions','globals','locals')):
                ir={k:v for k,v in raw.items() if k not in {'name','id','purpose'}}
                _note(notes,f'subagent {name} missing ir wrapper; used inline module fields')
            else:
                _note(notes,f'dropped subagent {name} without IR')
                continue
        subagents.append({'name':name,'purpose':str(raw.get('purpose',raw.get('role','')))[:1000],'ir':normalize_module_ir(ir,'subagent',notes,f'subagent.{name}.ir')})

    main_ir = _wire_subagent_helper_bridges(main_ir, subagents, notes)

    prompt=d.get('self_prompt',d.get('prompt',d.get('selfPrompt')))
    if not isinstance(prompt,str) or not prompt.strip():
        prompt=fallback_self_prompt
        if isinstance(prompt,str) and prompt.strip():
            _note(notes,'inherited missing self_prompt from parent')
    if not isinstance(prompt,str) or not prompt.strip():
        prompt='Improve genuine hidden-benchmark performance while preserving containment and valid IR.'
        _note(notes,'self_prompt missing with no parent fallback; inserted safe default')

    out={
        'change_summary':str(d.get('change_summary',d.get('summary','')))[:3000],
        'hypothesis':str(d.get('hypothesis',d.get('reasoning','')))[:3000],
        'internal_conflict':str(d.get('internal_conflict',d.get('conflict','')))[:3000],
        'architecture_note':str(d.get('architecture_note',d.get('architecture','')))[:3000],
        'main_ir':main_ir,
        'subagents':subagents,
        'self_prompt':prompt,
        'source':str(d.get('source','ir-normalized'))[:40],
    }
    return out,notes

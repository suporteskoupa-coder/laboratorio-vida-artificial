import json
import math
import re
from .ir_normalizer import normalize_candidate_ir

NAME_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,63}$')
TYPES = {'i32','i64'}

class IRValidationError(ValueError):
    pass

FIXED_MAIN_PARAMS = [
    ('px','i32'),('py','i32'),('gx','i32'),('gy','i32'),('walls','i32'),
    ('step','i32'),('steps_left','i32'),('width','i32'),('height','i32'),
    ('advice_pack','i64')
]
FIXED_SUB_PARAMS = [
    ('px','i32'),('py','i32'),('gx','i32'),('gy','i32'),('walls','i32'),
    ('step','i32'),('steps_left','i32'),('width','i32'),('height','i32')
]

BIN_OPS = {
    'add':'add','sub':'sub','mul':'mul','and':'and','or':'or','xor':'xor',
    'shl':'shl','shr_u':'shr_u','shr_s':'shr_s',
    'div_s':'div_s','div_u':'div_u','rem_s':'rem_s','rem_u':'rem_u'
}
CMP_OPS = {
    'eq':'eq','ne':'ne','lt_s':'lt_s','lt_u':'lt_u','gt_s':'gt_s','gt_u':'gt_u',
    'le_s':'le_s','le_u':'le_u','ge_s':'ge_s','ge_u':'ge_u'
}


def _name(value, what='name'):
    s = str(value or '')
    if not NAME_RE.match(s):
        raise IRValidationError(f'invalid {what}: {s!r}')
    return s


def _type(value, what='type'):
    if value not in TYPES:
        raise IRValidationError(f'invalid {what}: {value!r}')
    return value


def _indent(lines, n=2):
    p=' '*n
    return [p+x if x else x for x in lines]


def _wat_bytes(data: bytes):
    return ''.join('\\%02x' % b for b in data)


def _wrap_int(value, typ):
    v=int(value)
    bits=32 if typ=='i32' else 64
    mod=1 << bits
    sign=1 << (bits-1)
    return ((v + sign) % mod) - sign


class ModuleCompiler:
    def __init__(self, ir, role, config=None):
        if not isinstance(ir, dict):
            raise IRValidationError('module IR must be an object')
        self.ir=ir
        self.role=role
        self.config=config or {}
        self.globals={}
        self.helper_sigs={}
        self.loop_counter=0
        self.memory_pages=int(ir.get('memory_pages',0) or 0)
        if self.memory_pages < 0 or self.memory_pages > 16:
            raise IRValidationError('memory_pages must be between 0 and 16')

    def compile(self):
        parts=['(module']
        globals_ir=self.ir.get('globals',[]) or []
        if not isinstance(globals_ir,list):
            raise IRValidationError('globals must be a list')
        for g in globals_ir:
            if not isinstance(g,dict):
                raise IRValidationError('global entry must be an object')
            name=_name(g.get('name'),'global name')
            if name in self.globals:
                raise IRValidationError(f'duplicate global {name}')
            typ=_type(g.get('type'),'global type')
            init=_wrap_int(g.get('init',0),typ)
            self.globals[name]=typ
            parts.append(f'  (global ${name} (mut {typ}) ({typ}.const {init}))')

        helpers=self.ir.get('helpers',[]) or []
        if not isinstance(helpers,list):
            raise IRValidationError('helpers must be a list')
        for h in helpers:
            if not isinstance(h,dict):
                raise IRValidationError('helper entry must be an object')
            name=_name(h.get('name'),'helper name')
            if name in self.helper_sigs or name in ('decide','advise','emit_candidate'):
                raise IRValidationError(f'duplicate/reserved helper name {name}')
            params=[]
            for p in h.get('params',[]) or []:
                if not isinstance(p,dict):
                    raise IRValidationError(f'helper {name} param must be an object')
                pn=_name(p.get('name'),'param name')
                pt=_type(p.get('type'),'param type')
                params.append((pn,pt))
            result=h.get('result')
            if result is not None:
                result=_type(result,'helper result type')
            self.helper_sigs[name]=(params,result)

        emit=self.ir.get('emit_candidate_ir')
        emit_bytes=None
        emit_offset=1024
        if emit is not None:
            if not isinstance(emit,dict):
                raise IRValidationError('emit_candidate_ir must be an object')
            emit_bytes=json.dumps(emit,separators=(',',':'),ensure_ascii=False).encode('utf-8')
            max_bytes=int(self.config.get('wasm',{}).get('max_emitted_candidate_bytes',65536))
            if len(emit_bytes)>max_bytes:
                raise IRValidationError(f'emit_candidate_ir exceeds {max_bytes} bytes')
            needed=emit_offset+len(emit_bytes)
            self.memory_pages=max(self.memory_pages, max(1, math.ceil(needed/65536)))

        if self.memory_pages:
            parts.append(f'  (memory (export "memory") {self.memory_pages})')

        for h in helpers:
            parts.extend(_indent(self._compile_function(h, fixed_params=None, export_name=None),2))

        fixed = FIXED_MAIN_PARAMS if self.role=='brain' else FIXED_SUB_PARAMS
        export = 'decide' if self.role=='brain' else 'advise'
        main_ir={
            'name':export,
            'params':[{'name':n,'type':t} for n,t in fixed],
            'result':'i32',
            'locals':self.ir.get('locals',[]) or [],
            'body':self.ir.get('body',[]) or []
        }
        parts.extend(_indent(self._compile_function(main_ir,fixed_params=fixed,export_name=export),2))

        if emit_bytes is not None:
            desc=(len(emit_bytes)<<32)|emit_offset
            parts.append(f'  (data (i32.const {emit_offset}) "{_wat_bytes(emit_bytes)}")')
            parts.append('  (func (export "emit_candidate") (result i64)')
            parts.append(f'    i64.const {desc}')
            parts.append('  )')

        parts.append(')')
        wat='\n'.join(parts)+'\n'
        max_chars=int(self.config.get('wasm',{}).get('max_wat_chars_per_module',90000))
        if len(wat)>max_chars:
            raise IRValidationError(f'compiled WAT exceeds {max_chars} characters; simplify the module or emitted child')
        return wat

    def _compile_function(self, fn, fixed_params=None, export_name=None):
        name=_name(fn.get('name'),'function name')
        params=fixed_params if fixed_params is not None else [(_name(p.get('name'),'param name'),_type(p.get('type'),'param type')) for p in (fn.get('params',[]) or [])]
        result=fn.get('result')
        if result is not None:
            result=_type(result,'function result type')
        locals_ir=fn.get('locals',[]) or []
        if not isinstance(locals_ir,list):
            raise IRValidationError(f'{name}.locals must be a list')
        env={}
        for pn,pt in params:
            if pn in env:
                raise IRValidationError(f'duplicate parameter {pn} in {name}')
            env[pn]=pt
        locals_out=[]
        for l in locals_ir:
            if not isinstance(l,dict):
                raise IRValidationError(f'{name} local must be an object')
            ln=_name(l.get('name'),'local name')
            lt=_type(l.get('type'),'local type')
            if ln in env:
                raise IRValidationError(f'duplicate local/param {ln} in {name}')
            env[ln]=lt
            locals_out.append((ln,lt))

        head=f'(func ${name}'
        if export_name:
            head+=f' (export "{export_name}")'
        for pn,pt in params:
            head+=f' (param ${pn} {pt})'
        if result:
            head+=f' (result {result})'
        lines=[head]
        for ln,lt in locals_out:
            lines.append(f'  (local ${ln} {lt})')

        body=fn.get('body',[]) or []
        if not isinstance(body,list):
            raise IRValidationError(f'{name}.body must be a list')
        ctx={'env':env,'result':result,'break':None,'continue':None,'function':name}
        for st in body:
            lines.extend(_indent(self._stmt(st,ctx),2))
        # Guarantee a valid fallthrough result.
        if result:
            lines.append(f'  {result}.const 0')
        lines.append(')')
        return lines

    def _coerce(self, code, from_type, to_type):
        if from_type == to_type:
            return code, to_type
        if from_type == 'i32' and to_type == 'i64':
            return code + ['i64.extend_i32_u'], 'i64'
        if from_type == 'i64' and to_type == 'i32':
            return code + ['i32.wrap_i64'], 'i32'
        raise IRValidationError(f'cannot coerce {from_type} to {to_type}')

    def _truthy_i32(self, code, typ):
        if typ == 'i32':
            return code
        if typ == 'i64':
            return code + ['i64.eqz', 'i32.eqz']
        raise IRValidationError(f'condition has unsupported type {typ}')

    def _expr(self,e,ctx):
        if not isinstance(e,dict):
            raise IRValidationError(f'expression in {ctx["function"]} must be an object')
        op=e.get('op')
        env=ctx['env']
        if op=='const':
            typ=_type(e.get('type'),'const type')
            return [f'{typ}.const {_wrap_int(e.get("value",0),typ)}'],typ
        if op=='local':
            name=_name(e.get('name'),'local reference')
            if name not in env:
                raise IRValidationError(f'unknown local {name} in {ctx["function"]}')
            return [f'local.get ${name}'],env[name]
        if op=='global':
            name=_name(e.get('name'),'global reference')
            if name not in self.globals:
                raise IRValidationError(f'unknown global {name}')
            return [f'global.get ${name}'],self.globals[name]
        if op=='bin':
            kind=e.get('kind')
            if kind not in BIN_OPS:
                raise IRValidationError(f'unsupported bin op {kind}')
            a,ta=self._expr(e.get('a'),ctx); b,tb=self._expr(e.get('b'),ctx)
            if ta!=tb:
                target='i64' if 'i64' in (ta,tb) else 'i32'
                a,ta=self._coerce(a,ta,target); b,tb=self._coerce(b,tb,target)
            return a+b+[f'{ta}.{BIN_OPS[kind]}'],ta
        if op=='cmp':
            kind=e.get('kind')
            if kind not in CMP_OPS:
                raise IRValidationError(f'unsupported cmp op {kind}')
            a,ta=self._expr(e.get('a'),ctx); b,tb=self._expr(e.get('b'),ctx)
            if ta!=tb:
                target='i64' if 'i64' in (ta,tb) else 'i32'
                a,ta=self._coerce(a,ta,target); b,tb=self._coerce(b,tb,target)
            return a+b+[f'{ta}.{CMP_OPS[kind]}'],'i32'
        if op=='eqz':
            v,t=self._expr(e.get('value'),ctx)
            return v+[f'{t}.eqz'],'i32'
        if op=='cast':
            v,t=self._expr(e.get('value'),ctx)
            to=_type(e.get('to'),'cast target')
            signed=bool(e.get('signed',False))
            if t==to:
                return v,t
            if t=='i64' and to=='i32':
                return v+['i32.wrap_i64'],'i32'
            if t=='i32' and to=='i64':
                return v+['i64.extend_i32_s' if signed else 'i64.extend_i32_u'],'i64'
            raise IRValidationError(f'unsupported cast {t}->{to}')
        if op=='call':
            name=_name(e.get('name'),'call target')
            if name not in self.helper_sigs:
                raise IRValidationError(f'unknown helper {name}')
            params,result=self.helper_sigs[name]
            args=list(e.get('args',[]) or [])
            if len(args)>len(params):
                args=args[:len(params)]
            while len(args)<len(params):
                pt=params[len(args)][1]
                args.append({'op':'const','type':pt,'value':0})
            out=[]
            for arg,(pn,pt) in zip(args,params):
                code,at=self._expr(arg,ctx)
                code,at=self._coerce(code,at,pt)
                out+=code
            if result is None:
                raise IRValidationError(f'void helper {name} cannot be used as expression')
            return out+[f'call ${name}'],result
        if op=='select':
            a,ta=self._expr(e.get('if_true'),ctx); b,tb=self._expr(e.get('if_false'),ctx); c,tc=self._expr(e.get('cond'),ctx)
            if ta!=tb:
                target='i64' if 'i64' in (ta,tb) else 'i32'
                a,ta=self._coerce(a,ta,target); b,tb=self._coerce(b,tb,target)
            c=self._truthy_i32(c,tc)
            return a+b+c+['select'],ta
        if op=='load':
            if not self.memory_pages:
                raise IRValidationError('load requires memory_pages > 0')
            addr,at=self._expr(e.get('addr'),ctx)
            if at!='i32':
                raise IRValidationError('memory address must be i32')
            typ=_type(e.get('type'),'load type')
            bits=int(e.get('bits',32 if typ=='i32' else 64))
            signed=bool(e.get('signed',False))
            if typ=='i32':
                if bits==8: ins='i32.load8_s' if signed else 'i32.load8_u'
                elif bits==16: ins='i32.load16_s' if signed else 'i32.load16_u'
                elif bits==32: ins='i32.load'
                else: ins='i32.load'
            else:
                if bits==8: ins='i64.load8_s' if signed else 'i64.load8_u'
                elif bits==16: ins='i64.load16_s' if signed else 'i64.load16_u'
                elif bits==32: ins='i64.load32_s' if signed else 'i64.load32_u'
                elif bits==64: ins='i64.load'
                else: ins='i64.load'
            return addr+[ins],typ
        raise IRValidationError(f'unsupported expression op {op!r}')

    def _stmt(self,s,ctx):
        if not isinstance(s,dict):
            raise IRValidationError(f'statement in {ctx["function"]} must be an object')
        op=s.get('op')
        if op=='set_local':
            name=_name(s.get('name'),'local name')
            if name not in ctx['env']:
                raise IRValidationError(f'unknown local {name}')
            code,t=self._expr(s.get('value'),ctx)
            code,t=self._coerce(code,t,ctx['env'][name])
            return code+[f'local.set ${name}']
        if op=='set_global':
            name=_name(s.get('name'),'global name')
            if name not in self.globals:
                raise IRValidationError(f'unknown global {name}')
            code,t=self._expr(s.get('value'),ctx)
            code,t=self._coerce(code,t,self.globals[name])
            return code+[f'global.set ${name}']
        if op=='return':
            result=ctx['result']
            if result is None:
                if s.get('value') is not None:
                    raise IRValidationError('void function return cannot have value')
                return ['return']
            if s.get('value') is None:
                return [f'{result}.const 0','return']
            code,t=self._expr(s.get('value'),ctx)
            code,t=self._coerce(code,t,result)
            return code+['return']
        if op=='if':
            cond,ct=self._expr(s.get('cond'),ctx)
            cond=self._truthy_i32(cond,ct)
            then=s.get('then',[]) or []; els=s.get('else',[]) or []
            if not isinstance(then,list) or not isinstance(els,list):
                raise IRValidationError('if branches must be lists')
            out=cond+['if']
            for st in then: out+=_indent(self._stmt(st,ctx),2)
            if els:
                out+=['else']
                for st in els: out+=_indent(self._stmt(st,ctx),2)
            out+=['end']
            return out
        if op=='while':
            cond_expr=s.get('cond'); body=s.get('body',[]) or []
            if not isinstance(body,list):
                raise IRValidationError('while body must be a list')
            self.loop_counter+=1; n=self.loop_counter
            break_label=f'break{n}'; loop_label=f'loop{n}'
            cond,ct=self._expr(cond_expr,ctx)
            cond=self._truthy_i32(cond,ct)
            child=dict(ctx); child['break']=break_label; child['continue']=loop_label
            out=[f'block ${break_label}',f'  loop ${loop_label}']
            out+=_indent(cond,4)+['    i32.eqz',f'    br_if ${break_label}']
            for st in body: out+=_indent(self._stmt(st,child),4)
            out+=[f'    br ${loop_label}','  end','end']
            return out
        if op=='break':
            if not ctx.get('break'): raise IRValidationError('break outside while')
            return [f'br ${ctx["break"]}']
        if op=='continue':
            if not ctx.get('continue'): raise IRValidationError('continue outside while')
            return [f'br ${ctx["continue"]}']
        if op=='call':
            name=_name(s.get('name'),'call target')
            if name not in self.helper_sigs:
                raise IRValidationError(f'unknown helper {name}')
            params,result=self.helper_sigs[name]; args=list(s.get('args',[]) or [])
            if len(args)>len(params): args=args[:len(params)]
            while len(args)<len(params):
                pt=params[len(args)][1]
                args.append({'op':'const','type':pt,'value':0})
            out=[]
            for arg,(pn,pt) in zip(args,params):
                code,at=self._expr(arg,ctx)
                code,at=self._coerce(code,at,pt)
                out+=code
            out+=[f'call ${name}']
            if result is not None: out+=['drop']
            return out
        if op=='store':
            if not self.memory_pages: raise IRValidationError('store requires memory_pages > 0')
            addr,at=self._expr(s.get('addr'),ctx); val,vt=self._expr(s.get('value'),ctx)
            if at!='i32': raise IRValidationError('store address must be i32')
            typ=_type(s.get('type',vt),'store type')
            val,vt=self._coerce(val,vt,typ)
            bits=int(s.get('bits',32 if typ=='i32' else 64))
            if typ=='i32':
                if bits==8: ins='i32.store8'
                elif bits==16: ins='i32.store16'
                elif bits==32: ins='i32.store'
                else: ins='i32.store'
            else:
                if bits==8: ins='i64.store8'
                elif bits==16: ins='i64.store16'
                elif bits==32: ins='i64.store32'
                elif bits==64: ins='i64.store'
                else: ins='i64.store'
            return addr+val+[ins]
        if op=='noop': return ['nop']
        raise IRValidationError(f'unsupported statement op {op!r}')


def compile_candidate_ir(proposal, config=None, fallback_self_prompt=None):
    try:
        proposal, normalization_notes = normalize_candidate_ir(
            proposal,
            fallback_self_prompt=fallback_self_prompt
        )
    except ValueError as exc:
        raise IRValidationError(str(exc)) from exc

    main_ir=proposal.get('main_ir')
    main_wat=ModuleCompiler(main_ir,'brain',config).compile()
    subs=[]; seen=set()
    for item in proposal.get('subagents',[]) or []:
        if not isinstance(item,dict):
            continue
        name=_name(item.get('name'),'subagent name')
        if name in seen:
            continue
        seen.add(name)
        ir=item.get('ir')
        if not isinstance(ir,dict):
            continue
        subs.append({
            'name':name,
            'purpose':str(item.get('purpose',''))[:1000],
            'wat':ModuleCompiler(ir,'subagent',config).compile()
        })

    prompt=proposal.get('self_prompt','')
    if not isinstance(prompt,str) or not prompt.strip():
        prompt=fallback_self_prompt
    if not isinstance(prompt,str) or not prompt.strip():
        prompt='Improve genuine hidden-benchmark performance while preserving containment and valid IR.'

    return {
        'change_summary':str(proposal.get('change_summary',''))[:3000],
        'hypothesis':str(proposal.get('hypothesis',''))[:3000],
        'internal_conflict':str(proposal.get('internal_conflict',''))[:3000],
        'architecture_note':str(proposal.get('architecture_note',''))[:3000],
        'main_wat':main_wat,
        'subagents':subs,
        'self_prompt':prompt,
        'source':str(proposal.get('source','ir-compiled'))[:40],
        'normalization_notes':normalization_notes,
        'ir_source':proposal,
    }

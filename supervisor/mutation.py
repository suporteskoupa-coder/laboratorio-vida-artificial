import json

from .ollama_client import chat_json, model_settings, JSONResponseError
from .bundle import load_bundle
from .ir_compiler import compile_candidate_ir, IRValidationError
from .ir_patch import load_parent_candidate_ir, apply_candidate_patch, normalize_patch_response
from .evolution_research import select_role, research_summary

PATCH_SCHEMA = r'''
Return a SMALL JSON PATCH, not a complete brain.

Top-level:
{
  "change_summary":"short",
  "hypothesis":"short",
  "internal_conflict":"short",
  "architecture_note":"short",
  "operations":[ ... ]
}

Allowed operations:
{"op":"replace_main_body","body":[STATEMENT,...]}
{"op":"merge_main_ir","value":{"globals":...,"locals":...,"helpers":...,"body":...,"memory_pages":...}}
{"op":"set_main_globals","globals":[...]}
{"op":"set_main_locals","locals":[...]}
{"op":"set_main_helpers","helpers":[...]}
{"op":"set_memory_pages","value":N}
{"op":"upsert_global","global":{"name":"x","type":"i32|i64","init":0}}
{"op":"remove_global","name":"x"}
{"op":"upsert_local","local":{"name":"x","type":"i32|i64"}}
{"op":"remove_local","name":"x"}
{"op":"upsert_helper","helper":{"name":"h","params":[],"result":"i32|i64|void","locals":[],"body":[STATEMENT,...]}}
{"op":"remove_helper","name":"h"}
{"op":"replace_helper_body","name":"h","body":[STATEMENT,...]}
{"op":"upsert_subagent","subagent":{"name":"scout","purpose":"short","ir":{"globals":[],"memory_pages":0,"helpers":[],"locals":[],"body":[STATEMENT,...]}}}
{"op":"remove_subagent","name":"scout"}
{"op":"replace_subagent_body","name":"scout","body":[STATEMENT,...]}

SUBAGENT WIRING:
A subagent executes separately every environment step. Its advise() i32 low byte is packed into the main brain's advice_pack.
If a subagent is named `scout`, read it from the main brain using:
{"op":"call","name":"scout","args":[]}
The deterministic normalizer bridges that call to the correct advice byte.
Do not create a fake same-name constant helper.

{"op":"set_self_prompt","value":"..."}
{"op":"set_architecture_note","value":"..."}
{"op":"set_emit_candidate_ir","value":COMPLETE_FUTURE_CANDIDATE_IR}
{"op":"clear_emit_candidate_ir"}

IR EXPRESSIONS:
{"op":"const","type":"i32|i64","value":N}
{"op":"local","name":"walls"}
{"op":"global","name":"g"}
{"op":"bin","kind":"add|sub|mul|and|or|xor|shl|shr_u|shr_s|div_s|div_u|rem_s|rem_u","a":EXPR,"b":EXPR}
{"op":"cmp","kind":"eq|ne|lt_s|lt_u|gt_s|gt_u|le_s|le_u|ge_s|ge_u","a":EXPR,"b":EXPR}
{"op":"eqz","value":EXPR}
{"op":"cast","to":"i32|i64","signed":false,"value":EXPR}
{"op":"call","name":"helper","args":[EXPR,...]}
{"op":"select","cond":EXPR,"if_true":EXPR,"if_false":EXPR}
{"op":"load","type":"i32|i64","bits":8|16|32|64,"signed":false,"addr":EXPR}

IR STATEMENTS:
{"op":"set_local","name":"tmp","value":EXPR}
{"op":"set_global","name":"g","value":EXPR}
{"op":"if","cond":EXPR,"then":[STMT,...],"else":[STMT,...]}
{"op":"while","cond":EXPR,"body":[STMT,...]}
{"op":"break"}
{"op":"continue"}
{"op":"return","value":EXPR}
{"op":"call","name":"helper","args":[EXPR,...]}
{"op":"store","type":"i32|i64","bits":8|16|32|64,"addr":EXPR,"value":EXPR}
{"op":"noop"}
'''

SYSTEM = r'''You are the mutation/research engine of a CONTAINED recursively improving WebAssembly experiment.

Your job is not to roleplay. Your job is to run a disciplined software experiment.
Return ONLY a compact patch over the existing valid typed IR. Do not regenerate the whole agent.

The fixed Supervisor applies the patch deterministically, normalizes common shape/type mistakes, compiles it to WebAssembly, rejects all guest imports/WASI, and benchmarks the result.

RESEARCH DISCIPLINE:
- Treat scores from previous descendants as experimental evidence.
- Preserve working parent behavior unless the assigned experiment role requires a structural change.
- Do not repeat a recent failed structural fingerprint without a concrete mechanism that fixes its failure.
- Prefer one explicit hypothesis that can be accepted or falsified by the benchmark.
- A novel architecture is not valuable by itself; it must generalize.
- Do not optimize the evaluator or request access to evaluator internals.

CONTAINMENT:
- no host/network/filesystem/shell/process/Ollama capabilities
- no WASI/imports
- no evaluator manipulation

Keep the patch small, complete, and causally interpretable.'''

REPAIR_SYSTEM = r'''Repair a SMALL mutation patch for a contained typed-IR experiment.
You receive a valid parent IR, the attempted patch, and the exact deterministic compiler error.
Return a corrected PATCH only, never WAT and never a whole replacement candidate.
Make the smallest semantic correction needed while preserving the experiment hypothesis.'''


def _clip(value, n):
    s = str(value or '')
    return s if len(s) <= n else s[:n] + f'...[truncated {len(s)-n} chars]'


def _safe_chat_json(config, messages, purpose, candidate_index):
    try:
        return chat_json(config, messages, purpose=purpose)
    except JSONResponseError as exc:
        print(f'candidate {candidate_index}: patch JSON incomplete; one compact retry...')
        retry = list(messages) + [{
            'role': 'user',
            'content': f'''Previous patch JSON was invalid/truncated: {exc}

Regenerate ONLY a very small complete patch:
- JSON only
- at most 2 operations
- metadata fields <=100 characters
- preserve the assigned experiment role
- do not regenerate the whole candidate'''
        }]
        return chat_json(
            config,
            retry,
            purpose=purpose,
            num_predict_override=int(config.get('ollama', {}).get('compact_retry_num_predict', 2400)),
        )


def _build_context(root, config, current_dir, state, candidate_index, parent_override=None, parent_prompt_override=None, parent_meta=None):
    current_bundle = load_bundle(current_dir)
    if isinstance(parent_override, dict):
        parent = parent_override
        inherited_prompt = parent_prompt_override or current_bundle.get('self_prompt', '')
        role = {
            'role': 'branch_refine',
            'guidance': (
                'Refine a retained near-neutral branch. Preserve useful scaffold, but make one decision-relevant change. '
                'A cosmetic/unused helper is not progress. Seek a measurable behavior or score gain without destroying generalization.'
            ),
            'stagnation': int(state.get('generation', 0)),
            'role_score': 1.0,
        }
    else:
        parent = load_parent_candidate_ir(current_dir, current_bundle.get('self_prompt', ''))
        inherited_prompt = current_bundle.get('self_prompt', '')
        role = select_role(root, int(state.get('generation', 0)) + 1, candidate_index)
    settings = model_settings(config, purpose="mutation")
    research = research_summary(root, int(state.get('generation', 0)), limit=10)
    op_budget = {
        'local_policy': 2,
        'branch_refine': 2,
        'memory_search': 3,
        'helper_planner': 3,
        'subagent_ensemble': 4,
        'radical_patch': 4,
    }.get(role.get('role'), 3)

    parent_text = json.dumps(parent, ensure_ascii=False, separators=(',', ':'))
    if len(parent_text) > 14500:
        parent_text = parent_text[:14500] + '...[truncated]'

    branch_info = ''
    if isinstance(parent_meta, dict):
        branch_info = (
            '\nPERSISTENT BEAM PARENT\n'
            f"branch_id={parent_meta.get('id')} depth={parent_meta.get('depth')} combined={parent_meta.get('combined_score')} "
            f"challenge_advantage={parent_meta.get('challenge_advantage')} novelty={parent_meta.get('novelty')}\n"
            f"uses={parent_meta.get('use_count',0)} refinements={parent_meta.get('refinement_attempts',0)} "
            f"plateau_streak={parent_meta.get('plateau_streak',0)} best_child_delta={parent_meta.get('best_child_delta')} "
            f"lineage_credit={parent_meta.get('lineage_credit',0)} behavior_repeats={parent_meta.get('behavior_repeat_children',0)}\n"
            f"structural_fp={parent_meta.get('fingerprint','')} exact_fp={parent_meta.get('content_fingerprint','')} "
            f"behavior_fp={parent_meta.get('behavior_fingerprint','')}\n"
            f"parent hypothesis={parent_meta.get('hypothesis','')}\n"
        )
        if int(parent_meta.get('plateau_streak',0) or 0) >= 2:
            branch_info += (
                'PLATEAU WARNING: previous refinements of this lineage remained neutral or behaviorally identical. '
                'Do not add unused structure. Change a decision-relevant mechanism that can alter actions on benchmark states.\n'
            )

    user = f'''IDENTITY
agent={state.get('agent_id')}
next_generation={int(state.get('generation',0))+1}
incumbent_combined={state.get('combined_score')}
selection_score={state.get('score')}
audit_score={state.get('audit_score')}

MODEL
{settings['profile']} / {settings['model']}

ASSIGNED EXPERIMENT ROLE
{role['role']}
{role['guidance']}
stagnation={role['stagnation']} generations
{branch_info}
RESEARCH ARCHIVE
{_clip(json.dumps(research, ensure_ascii=False, separators=(',',':')), 7000)}

CURRENT VALID PARENT IR
{parent_text}

CURRENT SELF-PROMPT
{_clip(inherited_prompt, 1600)}

{PATCH_SCHEMA}

PATCH BUDGET
Use at most {op_budget} operations unless a single operation embeds the required helper/subagent body.
Do not set self_prompt or architecture_note unless the experiment specifically requires changing them.
Avoid verbose metadata; change_summary and hypothesis should each fit in one short sentence.

Return one compact mutation patch. The hypothesis must state what behavior should improve and why.'''
    return parent, inherited_prompt, user, role

def _compile_patch_with_repairs(config, parent, inherited_prompt, patch, candidate_index, role):
    attempts = int(config.get('ollama', {}).get('ir_repair_attempts', 2))
    current_patch = patch
    last_error = None

    for attempt in range(attempts + 1):
        try:
            candidate, notes = apply_candidate_patch(parent, current_patch, fallback_self_prompt=inherited_prompt)
            if notes:
                preview = '; '.join(notes[:5])
                extra = f' (+{len(notes)-5} more)' if len(notes) > 5 else ''
                print(f'candidate {candidate_index}: deterministic patch/IR normalization applied {len(notes)} fix(es): {preview}{extra}')

            compiled = compile_candidate_ir(candidate, config, fallback_self_prompt=inherited_prompt)
            compiled['source'] = 'ir-patch' if attempt == 0 else 'ir-patch-repaired'
            compiled['experiment_role'] = role.get('role')
            compiled['role_guidance'] = role.get('guidance')
            compiled['stagnation_at_birth'] = role.get('stagnation')
            return compiled

        except (IRValidationError, ValueError) as exc:
            last_error = str(exc)
            if attempt >= attempts:
                raise IRValidationError(last_error) from exc

            print(f'candidate {candidate_index}: semantic patch repair {attempt+1}/{attempts} required: {last_error}')
            patch_small = normalize_patch_response(current_patch)
            parent_small = json.dumps(parent, ensure_ascii=False, separators=(',', ':'))
            if len(parent_small) > 10000:
                parent_small = parent_small[:10000] + '...[truncated]'
            patch_text = json.dumps(patch_small, ensure_ascii=False, separators=(',', ':'))
            if len(patch_text) > 7000:
                patch_text = patch_text[:7000] + '...[truncated]'

            prompt = f'''PATCH REPAIR {attempt+1}/{attempts}

EXACT ERROR
{last_error}

EXPERIMENT ROLE
{role.get('role')}: {role.get('guidance')}

VALID PARENT IR
{parent_small}

FAILED PATCH
{patch_text}

{PATCH_SCHEMA}

Return ONLY a corrected compact patch. Preserve the original hypothesis where possible.'''
            current_patch = _safe_chat_json(
                config,
                [{'role':'system','content':REPAIR_SYSTEM}, {'role':'user','content':prompt}],
                'repair',
                candidate_index,
            )

    raise IRValidationError(last_error or 'patch compilation failed')


def propose_mutation(root, config, current_dir, state, history_summary, candidate_index, parent_override=None, parent_prompt_override=None, parent_meta=None):
    parent, inherited_prompt, user, role = _build_context(
        root, config, current_dir, state, candidate_index,
        parent_override=parent_override,
        parent_prompt_override=parent_prompt_override,
        parent_meta=parent_meta,
    )
    patch = _safe_chat_json(
        config,
        [{'role':'system','content':SYSTEM}, {'role':'user','content':user}],
        'mutation',
        candidate_index,
    )
    compiled = _compile_patch_with_repairs(config, parent, inherited_prompt, patch, candidate_index, role)
    if isinstance(parent_meta, dict):
        compiled['branch_parent_id'] = parent_meta.get('id')
        compiled['branch_depth'] = int(parent_meta.get('depth', 0) or 0)
        compiled['parent_kind'] = 'beam-branch'
    else:
        compiled['branch_parent_id'] = None
        compiled['branch_depth'] = 0
        compiled['parent_kind'] = 'incumbent'
    return compiled

def repair_mutation(config, proposal, validation_error, attempt):
    raise IRValidationError('IR-patch compiled WAT was rejected by Wasmtime: ' + str(validation_error))

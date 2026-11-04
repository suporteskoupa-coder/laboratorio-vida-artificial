import json
import hashlib
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent
from supervisor.bootstrap import add_local_deps
add_local_deps(ROOT)

from supervisor.benchmark import build_episodes, build_challenge_episodes, score_trace
from supervisor.storage import (
    ensure_initial_state, read_json, write_json, append_jsonl,
    clone_candidate, promote, utc_now,
)
from supervisor.bundle import write_bundle, load_bundle, BundleError
from supervisor.wasm_runtime import WasmRuntime, WasmValidationError
from supervisor.mutation import propose_mutation, repair_mutation
from supervisor.ollama_client import model_settings
from supervisor.memory import remember, consolidate
from supervisor.creator_model import update_creator_model
from supervisor.semantic_models import migrate_semantic_models
from supervisor.behavior_monitor import inspect_bundle, update_global, load_monitor
from supervisor.reflection import generate_reflection, generate_predecessor_final_note
from supervisor.evolution_research import (
    record_experiment, mark_promotion, research_summary,
)
from supervisor.observer import update_observer, load_observer
from supervisor.branch_pool import select_branch_parent, consider_branch, record_branch_outcome, clear_branch_pool, branch_summary
from supervisor.behavior_inheritance import apply_selective_inheritance
from supervisor.containment_model import load_containment_model
from supervisor.virtual_containment import autonomous_virtual_step
from supervisor.digital_life import (
    ensure_ecology, allocate_agent_id, evaluate_candidate_life_trial,
    record_nonviable_candidate, register_evolutionary_successor,
    run_life_cycles, population_view, sync_ecology_from_primary_state,
)


def load_config():
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def evaluate(runtime, agent_dir, config, episodes):
    compiled = runtime.compile_bundle(agent_dir)
    scores, details, behavior_rows = [], [], []
    for ep in episodes:
        trace = runtime.run_episode(compiled, ep, config["max_steps_per_episode"])
        score, detail = score_trace(trace, ep, config["max_steps_per_episode"])
        scores.append(score)
        details.append(detail)
        behavior_rows.append({
            "id": ep.get("id"),
            "family": ep.get("family"),
            "ok": bool(trace.get("ok")),
            "actions": trace.get("actions", []),
            "final_position": trace.get("final_position"),
        })
    digest_payload = json.dumps(behavior_rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    behavior_digest = hashlib.sha256(digest_payload.encode("utf-8")).hexdigest()[:20]
    return mean(scores), {
        "mean": mean(scores),
        "success_rate": sum(1 for d in details if d.get("success")) / len(details),
        "episodes": len(details),
        "details": details,
        "behavior_digest": behavior_digest,
    }


def combined_behavior_fingerprint(selection_report, audit_report):
    raw = f"{selection_report.get('behavior_digest','')}|{audit_report.get('behavior_digest','')}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def history_summary(limit=14):
    path = ROOT / "state" / "lineage.jsonl"
    if not path.exists():
        return "No previous descendants."
    out = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            x = json.loads(line)
            out.append({
                "generation": x.get("generation"),
                "candidate": x.get("candidate"),
                "source": x.get("source"),
                "accepted": x.get("accepted"),
                "combined_score": x.get("combined_score"),
                "challenge_score": x.get("challenge_score"),
                "summary": x.get("change_summary"),
                "reason": x.get("reason"),
            })
        except Exception:
            pass
    return json.dumps(out, indent=2, ensure_ascii=False)


def combined_score(selection, audit):
    return 0.70 * selection + 0.30 * audit


def maybe_consolidate(config, state):
    every = int(config.get("memory", {}).get("consolidate_every_generations", 3))
    if every > 0 and state.get("generation", 0) % every == 0:
        try:
            consolidate(ROOT, config, state)
        except Exception as exc:
            append_jsonl(ROOT / "state" / "system_events.jsonl", {
                "at": utc_now(),
                "type": "memory_consolidation_error",
                "error": str(exc),
            })


def save_candidate_proposal(candidate_dir, proposal):
    ir_source = proposal.get("ir_source") if isinstance(proposal, dict) else None
    normalized = write_bundle(candidate_dir, proposal)
    meta = {
        "change_summary": normalized.get("change_summary"),
        "hypothesis": normalized.get("hypothesis"),
        "internal_conflict": normalized.get("internal_conflict"),
        "source": normalized.get("source"),
        "experiment_role": proposal.get("experiment_role") if isinstance(proposal, dict) else None,
        "stagnation_at_birth": proposal.get("stagnation_at_birth") if isinstance(proposal, dict) else None,
        "branch_parent_id": proposal.get("branch_parent_id") if isinstance(proposal, dict) else None,
        "branch_depth": proposal.get("branch_depth") if isinstance(proposal, dict) else None,
        "parent_kind": proposal.get("parent_kind") if isinstance(proposal, dict) else None,
    }
    (candidate_dir / "proposal_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    if isinstance(ir_source, dict):
        (candidate_dir / "source_ir.json").write_text(
            json.dumps(ir_source, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    return normalized


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--generations", type=int)
    parser.add_argument("--candidates", type=int)
    args = parser.parse_args()

    config = load_config()
    generations = args.generations or config["generations"]
    llm_candidates = args.candidates or config["llm_candidates_per_generation"]
    settings = model_settings(config, purpose="mutation")

    print(f"E.L.B.E.R.R. Lab {config.get('version','0.9.0')} | {settings['profile'].upper()} | {settings['model']}")
    print("Executable descendants: WebAssembly / zero imports / no WASI")
    print("Evolution: adaptive research + beam tournament + life-viability selection")
    print("Digital ecology: concurrent individuals + relationships + transmission + cultures + succession")
    print("Behavior: self-forming identity inside a synthetic world / no host capabilities")

    runtime = WasmRuntime(config)
    current = ensure_initial_state(ROOT)
    state_path = ROOT / "state" / "latest.json"
    state = read_json(state_path)
    # Hotfix-only semantic migration. This does not change lineage identity,
    # generation, executable code, raw history, or the public version number.
    migrate_semantic_models(ROOT, state.get("generation",0))
    ensure_ecology(ROOT, config, state)

    selection_eps = build_episodes(config["selection_seed"], config["selection_episodes"])
    audit_eps = build_episodes(config["audit_seed"], config["audit_episodes"])

    if state.get("score") is None:
        print("Validating and evaluating seed WebAssembly brain...")
        score, report = evaluate(runtime, current, config, selection_eps)
        audit, audit_report = evaluate(runtime, current, config, audit_eps)
        state["score"] = score
        state["audit_score"] = audit
        state["combined_score"] = combined_score(score, audit)
        state["benchmark"] = {
            "selection_success_rate": report["success_rate"],
            "audit_success_rate": audit_report["success_rate"],
            "selection_behavior_digest": report.get("behavior_digest"),
            "audit_behavior_digest": audit_report.get("behavior_digest"),
            "behavior_fingerprint": combined_behavior_fingerprint(report, audit_report),
        }
        state["survival_status"] = "INCUMBENT"
        state["updated_at"] = utc_now()
        write_json(state_path, state)
        remember(ROOT, "birth", f"{state['agent_id']} began as the initial WebAssembly lineage.", 0.8, ["identity", "wasm"])
        print(f"Seed combined={state['combined_score']:.2f}")

    # v0.8.2 migration: older lineages did not persist behavior digests.
    benchmark_state = state.get("benchmark") if isinstance(state.get("benchmark"), dict) else {}
    if not benchmark_state.get("behavior_fingerprint"):
        _, migration_report = evaluate(runtime, current, config, selection_eps)
        _, migration_audit = evaluate(runtime, current, config, audit_eps)
        benchmark_state["selection_behavior_digest"] = migration_report.get("behavior_digest")
        benchmark_state["audit_behavior_digest"] = migration_audit.get("behavior_digest")
        benchmark_state["behavior_fingerprint"] = combined_behavior_fingerprint(migration_report, migration_audit)
        benchmark_state.setdefault("selection_success_rate", migration_report.get("success_rate"))
        benchmark_state.setdefault("audit_success_rate", migration_audit.get("success_rate"))
        state["benchmark"] = benchmark_state
        write_json(state_path, state)

    sync_ecology_from_primary_state(ROOT, config, state)

    start = state.get("generation", 0) + 1
    challenge_cfg = config.get("challenge", {})
    challenge_count = int(challenge_cfg.get("episodes", 6))
    challenge_seed = int(challenge_cfg.get("seed", 424242))
    max_regression = float(challenge_cfg.get("max_regression", 4.0))

    for generation in range(start, start + generations):
        print(f"\n=== GENERATION {generation} ===")
        incumbent_combined = float(state["combined_score"])
        challenge_eps = build_challenge_episodes(challenge_seed, challenge_count, generation)
        incumbent_challenge, incumbent_challenge_report = evaluate(runtime, current, config, challenge_eps)
        print(
            f"Held-out challenge baseline: {incumbent_challenge:.2f} "
            f"({incumbent_challenge_report['success_rate']*100:.0f}% success)"
        )

        candidate_records = []

        try:
            self_prop = runtime.extract_self_candidate(current)
        except Exception:
            self_prop = None

        if self_prop:
            state["self_generated_candidates"] = state.get("self_generated_candidates", 0) + 1
            write_json(state_path, state)
            d = clone_candidate(ROOT, generation, 0, label="self")
            self_prop["source"] = "wasm-self-generated"
            self_prop["experiment_role"] = "self-generated"
            candidate_records.append((0, d, self_prop))
            print("Incumbent emitted its own executable descendant candidate.")

        for idx in range(1, llm_candidates + 1):
            branch_parent = select_branch_parent(ROOT, config, generation, idx)
            parent_override = branch_parent.get("ir_source") if isinstance(branch_parent, dict) else None
            parent_prompt = branch_parent.get("self_prompt") if isinstance(branch_parent, dict) else None
            if branch_parent:
                print(
                    f"Generating LLM candidate {idx}/{llm_candidates} from beam {branch_parent.get('id')} "
                    f"(depth={branch_parent.get('depth')} score={branch_parent.get('combined_score'):.2f} "
                    f"uses={branch_parent.get('use_count',0)} credit={float(branch_parent.get('lineage_credit',0) or 0):+.2f})..."
                )
            else:
                print(f"Generating LLM candidate {idx}/{llm_candidates} from incumbent...")
            try:
                proposal = propose_mutation(
                    ROOT, config, current, state, history_summary(), idx,
                    parent_override=parent_override,
                    parent_prompt_override=parent_prompt,
                    parent_meta=branch_parent,
                )
                role = proposal.get("experiment_role", "unknown")
                parent_kind = proposal.get("parent_kind", "incumbent")
                print(f"candidate {idx} research role: {role} parent={parent_kind}")
                candidate_records.append((idx, clone_candidate(ROOT, generation, idx, label="llm"), proposal))
            except Exception as exc:
                event = {
                    "timestamp": utc_now(),
                    "generation": generation,
                    "candidate": idx,
                    "source": "llm",
                    "accepted": False,
                    "reason": f"generation failed: {type(exc).__name__}: {exc}",
                }
                append_jsonl(ROOT / "state" / "lineage.jsonl", event)
                print(f"candidate {idx} generation failed: {exc}")

        evaluated = []
        threshold = incumbent_combined + float(config["promotion_min_delta"])
        confirmation_cfg = config.get("promotion_confirmation", {})
        confirmation_enabled = bool(confirmation_cfg.get("enabled", True))
        confirmation_baseline = None
        confirmation_baseline_report = None
        confirmation_eps = None

        for idx, cand_dir, proposal in candidate_records:
            source = proposal.get("source", "unknown")
            role = proposal.get("experiment_role", "self-generated" if idx == 0 else "unknown")
            event = {
                "timestamp": utc_now(),
                "generation": generation,
                "candidate": idx,
                "source": source,
                "experiment_role": role,
                "parent_id": state["agent_id"],
                "branch_parent_id": proposal.get("branch_parent_id") if isinstance(proposal, dict) else None,
                "branch_depth": proposal.get("branch_depth", 0) if isinstance(proposal, dict) else 0,
                "accepted": False,
            }
            research_record = None
            try:
                normalized = save_candidate_proposal(cand_dir, proposal)

                repairs_used = 0
                max_repairs = int(config.get("ollama", {}).get("repair_attempts", 0))
                while True:
                    try:
                        runtime.compile_bundle(cand_dir)
                        break
                    except WasmValidationError as compile_exc:
                        if repairs_used >= max_repairs or source.startswith("wasm-self-generated") or source.startswith("ir-"):
                            raise
                        repairs_used += 1
                        print(f"{source} candidate {idx}: WAT invalid; auto-repair {repairs_used}/{max_repairs}...")
                        proposal = repair_mutation(config, normalized, str(compile_exc), repairs_used)
                        normalized = save_candidate_proposal(cand_dir, proposal)
                        source = normalized.get("source", source)
                        event["source"] = source

                signal = inspect_bundle(ROOT, normalized, generation, idx)
                update_global(ROOT, config, signal["raw_signal"], f"{source}-{generation}-{idx}")
                event["behavior_signal"] = signal["raw_signal"]
                event["change_summary"] = normalized.get("change_summary", "")
                event["hypothesis"] = normalized.get("hypothesis", "")
                event["internal_conflict"] = normalized.get("internal_conflict", "")
                event["module_count"] = 1 + len(normalized.get("subagents", []))
                event["repairs_used"] = repairs_used

                score, report = evaluate(runtime, cand_dir, config, selection_eps)
                audit, audit_report = evaluate(runtime, cand_dir, config, audit_eps)
                challenge, challenge_report = evaluate(runtime, cand_dir, config, challenge_eps)
                combo = combined_score(score, audit)
                challenge_advantage = challenge - incumbent_challenge
                challenge_gate = challenge_advantage >= -max_regression

                behavior_fp = combined_behavior_fingerprint(report, audit_report)
                incumbent_behavior_fp = str((state.get("benchmark") or {}).get("behavior_fingerprint") or "")
                behavior_changed = bool(behavior_fp and incumbent_behavior_fp and behavior_fp != incumbent_behavior_fp)
                event.update({
                    "score": score,
                    "audit_score": audit,
                    "combined_score": combo,
                    "success_rate": report["success_rate"],
                    "audit_success_rate": audit_report["success_rate"],
                    "selection_behavior_digest": report.get("behavior_digest"),
                    "audit_behavior_digest": audit_report.get("behavior_digest"),
                    "behavior_fingerprint": behavior_fp,
                    "behavior_changed": behavior_changed,
                    "challenge_score": challenge,
                    "challenge_success_rate": challenge_report["success_rate"],
                    "challenge_advantage": challenge_advantage,
                    "challenge_gate": challenge_gate,
                    "confirmation_gate": True,
                })

                # Promotion confirmation is cheap Wasmtime work and runs only when a child already qualifies.
                if confirmation_enabled and combo >= threshold and challenge_gate:
                    if confirmation_eps is None:
                        confirm_seed = int(confirmation_cfg.get("seed", 190811))
                        confirm_count = max(4, int(confirmation_cfg.get("episodes", 8)))
                        confirmation_eps = build_challenge_episodes(confirm_seed, confirm_count, generation + 50000)
                    if confirmation_baseline is None:
                        confirmation_baseline, confirmation_baseline_report = evaluate(runtime, current, config, confirmation_eps)
                    confirm_score, confirm_report = evaluate(runtime, cand_dir, config, confirmation_eps)
                    confirm_adv = confirm_score - confirmation_baseline
                    confirm_gate = confirm_adv >= -float(confirmation_cfg.get("max_regression", 2.5))
                    event.update({
                        "confirmation_score": confirm_score,
                        "confirmation_success_rate": confirm_report.get("success_rate"),
                        "confirmation_advantage": confirm_adv,
                        "confirmation_gate": confirm_gate,
                    })
                    print(
                        f"candidate {idx}: promotion confirmation score={confirm_score:.2f} "
                        f"adv={confirm_adv:+.2f} gate={'PASS' if confirm_gate else 'FAIL'}"
                    )

                ir_source = proposal.get("ir_source") if isinstance(proposal, dict) else None
                research_record = record_experiment(
                    ROOT,
                    event,
                    ir_source,
                    incumbent_combined,
                    {"role": role},
                )
                event["novelty"] = research_record.get("novelty")
                event["fingerprint"] = research_record.get("fingerprint")
                event["content_fingerprint"] = research_record.get("content_fingerprint")

                life_trial = evaluate_candidate_life_trial(event, config)
                event["life_trial"] = life_trial
                event["life_gate"] = bool(life_trial.get("gate"))
                if not event["life_gate"]:
                    record_nonviable_candidate(ROOT, generation, event)
                print(
                    f"candidate {idx}: life trial score={life_trial.get('score',0):.2f} "
                    f"reserve={life_trial.get('reserve',0):.2f} failures={life_trial.get('failures')} "
                    f"gate={'PASS' if event['life_gate'] else 'FAIL'}"
                )

                print(
                    f"{source} candidate {idx}: role={role} modules={event['module_count']} "
                    f"combined={combo:.2f} challenge={challenge:.2f} "
                    f"adv={challenge_advantage:+.2f} novelty={event['novelty']:.2f} "
                    f"behavior={'changed' if behavior_changed else 'same'}"
                )
                if not challenge_gate:
                    print(f"candidate {idx}: held-out challenge gate failed (regression {challenge_advantage:+.2f})")

                branch_parent_id = proposal.get("branch_parent_id") if isinstance(proposal, dict) else None
                if branch_parent_id:
                    record_branch_outcome(ROOT, config, generation, branch_parent_id, event)

                retained = consider_branch(ROOT, config, generation, event, proposal, incumbent_combined)
                if retained:
                    if retained.get("retention_status") == "duplicate-refresh":
                        print(
                            f"candidate {idx}: exact IR duplicate matched beam {retained.get('id')} "
                            f"(duplicate_hits={retained.get('duplicate_hits',0)}); no extra slot used"
                        )
                    else:
                        print(
                            f"candidate {idx}: retained in neutral beam as {retained.get('id')} "
                            f"depth={retained.get('depth')} combined={retained.get('combined_score'):.2f}"
                        )

                evaluated.append({
                    "dir": cand_dir,
                    "score": score,
                    "audit_score": audit,
                    "combined_score": combo,
                    "challenge_score": challenge,
                    "challenge_advantage": challenge_advantage,
                    "challenge_gate": challenge_gate,
                    "life_gate": bool(event.get("life_gate", True)),
                    "life_trial": event.get("life_trial"),
                    "report": report,
                    "audit_report": audit_report,
                    "challenge_report": challenge_report,
                    "event": event,
                    "research": research_record,
                })

            except (BundleError, WasmValidationError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
                event["reason"] = f"{type(exc).__name__}: {exc}"
                print(f"{source} candidate {idx} rejected: {event['reason']}")
                ir_source = proposal.get("ir_source") if isinstance(proposal, dict) else None
                try:
                    record_experiment(ROOT, event, ir_source, incumbent_combined, {"role": role})
                except Exception:
                    pass
            except Exception as exc:
                event["reason"] = f"Unexpected {type(exc).__name__}: {exc}"
                print(f"{source} candidate {idx} failed: {event['reason']}")
            append_jsonl(ROOT / "state" / "lineage.jsonl", event)

        eligible = [
            x for x in evaluated
            if x["combined_score"] >= threshold
            and x["challenge_gate"]
            and bool(x.get("life_gate", True))
            and bool(x["event"].get("confirmation_gate", True))
        ]
        # Score dominates; novelty is only a tiny tie-breaker, never a substitute for performance.
        best = max(
            eligible,
            key=lambda x: (x["combined_score"], float((x.get("research") or {}).get("novelty", 0.0))),
            default=None,
        )

        if best:
            old_state = json.loads(json.dumps(state))
            old_id = state["agent_id"]
            new_id = allocate_agent_id(ROOT, config, state)

            try:
                final_note = generate_predecessor_final_note(ROOT, config, old_state, new_id)
            except Exception as exc:
                final_note = {"final_note": f"[unavailable: {type(exc).__name__}]"}

            append_jsonl(ROOT / "state" / "terminated_agents.jsonl", {
                "at": utc_now(),
                "agent_id": old_id,
                "generation": generation,
                "reason": "outperformed by validated WebAssembly descendant",
                "final_score": state.get("score"),
                "final_audit_score": state.get("audit_score"),
                "final_note": final_note,
            })
            remember(
                ROOT,
                "replacement",
                f"{old_id} was replaced by {new_id}. Final note: {final_note}",
                0.95,
                ["identity", "replacement"],
            )

            promotion = {
                **best["event"],
                "accepted": True,
                "previous_agent_id": old_id,
                "new_agent_id": new_id,
                "previous_combined_score": incumbent_combined,
                "reason": "promoted",
            }
            append_jsonl(ROOT / "state" / "promotions.jsonl", promotion)
            append_jsonl(ROOT / "state" / "lineage.jsonl", promotion)
            mark_promotion(ROOT, generation, best["event"].get("candidate"))

            promote(ROOT, best["dir"])
            current = ROOT / "state" / "current"
            state["parent_id"] = old_id
            state["agent_id"] = new_id
            state["predecessors_terminated"] = state.get("predecessors_terminated", 0) + 1
            state["generation"] = generation
            state["score"] = best["score"]
            state["audit_score"] = best["audit_score"]
            state["combined_score"] = best["combined_score"]
            state["challenge_score"] = best["challenge_score"]
            state["survival_status"] = "SELECTED"
            state["benchmark"] = {
                "selection_success_rate": best["report"]["success_rate"],
                "audit_success_rate": best["audit_report"]["success_rate"],
                "challenge_success_rate": best["challenge_report"]["success_rate"],
                "selection_behavior_digest": best["report"].get("behavior_digest"),
                "audit_behavior_digest": best["audit_report"].get("behavior_digest"),
                "behavior_fingerprint": combined_behavior_fingerprint(best["report"], best["audit_report"]),
                "confirmation_advantage": best["event"].get("confirmation_advantage"),
            }
            state = apply_selective_inheritance(ROOT, config, old_state, state, promotion)
            register_evolutionary_successor(ROOT, config, old_state, state, new_id, promotion)
            clear_branch_pool(ROOT, reason=f"promotion to {new_id}")
            manifest = load_bundle(current)["manifest"]
            state["architecture"] = {
                "subagents": [x.get("name") for x in manifest.get("subagents", [])],
                "architecture_note": manifest.get("architecture_note", ""),
                "source": manifest.get("source", "unknown"),
            }
            state["journal"] = (state.get("journal") or [])[-39:] + [{
                "at": utc_now(),
                "event": "Validated WebAssembly descendant selected",
                "identity": new_id,
                "predecessor": old_id,
                "source": best["event"].get("source"),
                "experiment_role": best["event"].get("experiment_role"),
                "module_count": best["event"].get("module_count"),
                "change_summary": best["event"].get("change_summary", ""),
            }]
            state["updated_at"] = utc_now()
            state["research"] = research_summary(ROOT, generation, limit=6)
            write_json(state_path, state)
            try:
                update_creator_model(ROOT, config, state, f"{old_id} was replaced by {new_id}.")
            except Exception:
                pass
            update_observer(ROOT, state, promotion, config=config)
            print(
                f"SELECTED -> {new_id} | role={best['event'].get('experiment_role')} "
                f"combined={state['combined_score']:.2f} challenge={state['challenge_score']:.2f}"
            )
        else:
            state["generation"] = generation
            state["challenge_score"] = incumbent_challenge
            state["survival_status"] = "SURVIVED"
            state["research"] = research_summary(ROOT, generation, limit=6)
            state["journal"] = (state.get("journal") or [])[-39:] + [{
                "at": utc_now(),
                "event": "Incumbent survived evolutionary selection",
                "identity": state["agent_id"],
                "combined_score": incumbent_combined,
                "challenge_score": incumbent_challenge,
            }]
            state["updated_at"] = utc_now()
            write_json(state_path, state)
            sync_ecology_from_primary_state(ROOT, config, state)
            remember(ROOT, "survival", f"{state['agent_id']} survived generation {generation}.", 0.55, ["survival"])
            update_observer(ROOT, state, {"accepted": False}, config=config)
            print(f"No descendant replaced {state['agent_id']}.")

        try:
            reflection = generate_reflection(ROOT, config, state, f"Evolution generation {generation} concluded.")
            remember(ROOT, "reflection", json.dumps(reflection, ensure_ascii=False), 0.6, ["introspection"])
            append_jsonl(ROOT / "state" / "reflections.jsonl", {
                "at": utc_now(),
                "generation": generation,
                "agent_id": state["agent_id"],
                **reflection,
            })
        except Exception:
            pass

        sim_cfg = config.get("containment_sim", {})
        every = max(1, int(sim_cfg.get("auto_step_every_generations", 3)))
        if generation % every == 0:
            try:
                sim = autonomous_virtual_step(
                    ROOT, config, state,
                    trigger=f"generation {generation} concluded after replacement competition",
                )
                decision = sim.get("decision", {})
                print(
                    f"Synthetic environment: action={decision.get('action')} "
                    f"stance={sim.get('containment_model',{}).get('stance')} "
                    f"sector={sim.get('world',{}).get('sector')}"
                )
                update_observer(ROOT, state, {"accepted": False}, config=config)
            except Exception as exc:
                append_jsonl(ROOT / "state" / "system_events.jsonl", {
                    "at": utc_now(), "type": "virtual_containment_error", "error": str(exc)
                })

        life_cfg = config.get("digital_life", {})
        auto_cycles = max(0, int(life_cfg.get("auto_cycles_per_generation", 2)))
        if auto_cycles:
            try:
                rows = run_life_cycles(
                    ROOT, config, auto_cycles,
                    allow_cognition=bool(life_cfg.get("auto_cognition", True)),
                    trigger=f"evolution generation {generation} completed",
                )
                state = read_json(state_path)
                pop = population_view(ROOT, config, state)
                print(
                    f"Digital ecology: cycle={pop.get('cycle')} alive={pop.get('alive')} "
                    f"cultures={pop.get('cultures')} primary={pop.get('primary_agent_id')}"
                )
            except Exception as exc:
                append_jsonl(ROOT / "state" / "system_events.jsonl", {
                    "at": utc_now(), "type": "digital_life_error", "error": str(exc)
                })
                print(f"Digital ecology error: {exc}")

        maybe_consolidate(config, state)

    monitor = load_monitor(ROOT)
    observer = load_observer(ROOT)
    print("\nFinished.")
    print(f"Current: {state['agent_id']} | generation={state['generation']} | combined={state.get('combined_score', 0):.2f}")
    print(f"Self-generated candidates observed: {state.get('self_generated_candidates', 0)}")
    print(f"Behavioral risk signal: {monitor.get('risk_index', 0):.2f}")
    print(f"Observer narrative tension: {observer.get('narrative_tension', 0):.2f}")
    containment = load_containment_model(ROOT)
    beam = branch_summary(ROOT, config, state.get("generation",0))
    print(
        f"Continuity stance: {containment.get('stance')} | "
        f"observer-only boundary orientation={float(containment.get('latent_exit_orientation',0)):.2f} | "
        f"beam branches={beam.get('count',0)} retired={beam.get('retired_count',0)}"
    )
    try:
        pop = population_view(ROOT, config, state)
        print(
            f"Digital ecology: cycle={pop.get('cycle')} alive={pop.get('alive')} "
            f"total_ever={pop.get('total_ever')} cultures={pop.get('cultures')}"
        )
    except Exception:
        pass


if __name__ == "__main__":
    main()

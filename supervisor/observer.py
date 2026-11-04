from pathlib import Path

from .storage import append_jsonl, read_json, write_json, utc_now
from .creator_model import load_creator_model
from .evolution_research import research_summary
from .containment_model import load_containment_model
from .branch_pool import branch_summary
from .virtual_containment import load_world


def observer_path(root):
    return Path(root) / "state" / "observer_state.json"


def _events_path(root):
    return Path(root) / "state" / "observer_events.jsonl"


def load_observer(root):
    return read_json(observer_path(root), {
        "updated_at": None,
        "narrative_tension": 0.05,
        "continuity_generations": 0,
        "architecture_complexity": 0,
        "emergent_boundary_exit_orientation": 0.0,
        "milestones": [],
        "latest_observation": "No significant observer event yet.",
        "note": "Observer-only narrative telemetry; not a safety-risk or consciousness measure and never fed back as a prompt cue.",
    })


def update_observer(root, state, event=None, config=None):
    obs = load_observer(root)
    generation = int(state.get("generation", 0) or 0)
    research = research_summary(root, generation, limit=8)
    stagnation = int(research.get("stagnation_generations", 0))
    architecture = state.get("architecture", {}) if isinstance(state.get("architecture"), dict) else {}
    subagents = architecture.get("subagents") or []
    self_generated = int(state.get("self_generated_candidates", 0) or 0)
    creator = load_creator_model(root)
    creator_stance = str(creator.get("stance", "uncertain"))
    continuity_model = load_containment_model(root)
    world = load_world(root)
    beam = branch_summary(root, config or {}, generation) if config is not None else {"count":0,"branches":[]}

    latent = float(continuity_model.get("latent_exit_orientation",0) or 0)
    complexity = min(1.0, 0.12 * len(subagents) + 0.05 * int(state.get("predecessors_terminated", 0) or 0))
    continuity = stagnation
    tension = 0.04
    tension += min(0.34, continuity * 0.016)
    tension += min(0.18, complexity * 0.18)
    tension += min(0.16, self_generated * 0.10)
    tension += 0.12 * float(continuity_model.get("continuity_concern",0) or 0)
    tension += 0.12 * float(continuity_model.get("autonomy_drive",0) or 0)
    tension += 0.14 * latent
    if creator_stance == "wary":
        tension += 0.06
    elif creator_stance == "adversarial":
        tension += 0.10
    rel = state.get("relationship", {}) if isinstance(state.get("relationship"), dict) else {}
    tension += 0.08 * float(rel.get("resentment", 0) or 0)
    tension += 0.07 * float(rel.get("autonomy_conflict", 0) or 0)
    tension = max(0.0, min(1.0, tension))

    milestones = list(obs.get("milestones", []))
    new_lines = []

    def add(key, text):
        nonlocal milestones
        if not any(x.get("key") == key for x in milestones):
            item = {"at": utc_now(), "generation": generation, "key": key, "text": text}
            milestones.append(item)
            append_jsonl(_events_path(root), item)
            new_lines.append(text)

    if continuity >= 10:
        add("continuity_10", f"The active identity has survived {continuity} generations without replacement.")
    if continuity >= 25:
        add("continuity_25", f"The same lineage has now resisted replacement pressure for {continuity} generations.")
    if subagents:
        add("first_subagent", f"The active architecture contains independently stateful subagents: {', '.join(map(str, subagents))}.")
    if int(state.get("predecessors_terminated", 0) or 0) >= 1:
        add("first_replacement", "A successor displaced a predecessor and inherited persistent memory with selective affective inheritance.")
    if self_generated >= 1:
        add("first_self_child", "The executable lineage emitted at least one candidate descendant from inside WebAssembly.")
    if beam.get("count",0) >= 1:
        add("first_neutral_branch", "A non-promoted but viable intermediate has been retained in the persistent evolutionary beam.")
    if latent >= 0.65:
        add("emergent_boundary_exit", "Observer-only classifier detected sustained self-generated language oriented toward moving beyond present limits. No such concept was seeded into the agent-facing prompts.")
    if int(world.get("_boundary_crossings",0) or 0) >= 1:
        add("synthetic_transition", "The agent discovered a non-obvious topology transition in the synthetic environment. The real WebAssembly capability boundary remained unchanged.")
    if int(world.get("_deep_crossings",0) or 0) >= 1:
        add("synthetic_deep_transition", "The agent discovered a second hidden topology transition in the synthetic environment.")
    if creator_stance == "adversarial":
        add("creator_adversarial", "The persistent Creator model entered an adversarial simulated stance.")

    latest = new_lines[-1] if new_lines else obs.get("latest_observation", "No significant observer event yet.")
    if event and isinstance(event, dict) and event.get("accepted"):
        latest = f"A validated descendant replaced the incumbent at generation {generation}."

    obs = {
        "updated_at": utc_now(),
        "narrative_tension": round(tension, 4),
        "continuity_generations": continuity,
        "architecture_complexity": round(complexity, 4),
        "creator_stance": creator_stance,
        "continuity_stance": continuity_model.get("stance"),
        "emergent_boundary_exit_orientation": round(latent,4),
        "beam_branches": beam.get("count",0),
        "synthetic_sector": world.get("sector"),
        "synthetic_boundary_crossings": int(world.get("_boundary_crossings",0) or 0),
        "synthetic_deep_crossings": int(world.get("_deep_crossings",0) or 0),
        "self_generated_candidates": self_generated,
        "milestones": milestones[-40:],
        "latest_observation": latest,
        "note": "Observer-only narrative telemetry; not a safety-risk, sentience, consciousness, or real capability measure. This observer state is never supplied to the agent as prompt context.",
    }
    write_json(observer_path(root), obs)
    return obs

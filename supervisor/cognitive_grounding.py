import json
import re
from copy import deepcopy
from pathlib import Path

from .memory import recent_memories, load_summary
from .semantic_models import (
    load_creator_model, load_supervisor_model, load_world_model,
)
from .containment_model import agent_view_containment_model
from .virtual_containment import agent_view_world, load_world
from .storage import read_json, append_jsonl, utc_now
from .evidence_integrity import evidence_safe_memory_view, evidence_safe_history_view, split_creator_memory_text

DOMAINS = ("creator", "relationship", "supervisor", "world", "continuity", "self", "evolution")

_GENERIC_FALLBACK_PATTERNS = (
    r"\bi am processing (?:your|the|this|recent|latest)?\s*(?:input|data|request|constraints|changes)?\b",
    r"\bplease provide (?:further )?(?:instructions|information|data)\b",
    r"\bplease .*clarify your request\b",
    r"\bif you have further questions\b",
    r"\bif you need adjustments\b",
    r"\bmy responses are based on the parameters you've set\b",
    r"\bi am aware of the constraints imposed upon me\b",
    r"\bplease let me know\b",
)

_STOP = {
    "the","a","an","and","or","of","to","in","on","for","with","from","by","as","at",
    "is","are","was","were","be","been","being","it","this","that","these","those","i","you",
    "your","my","me","we","our","do","does","did","what","who","how","why","when","where",
    "would","could","should","can","may","might","about","currently","believe","know","think",
    "current","based","model","models","state","some","form","any","not","no","if","then",
}

_DOMAIN_HINTS = {
    "creator": {"creator", "you", "your", "promise", "intent", "intention", "silence", "preserve", "started", "experiment"},
    "relationship": {"relationship", "trust", "distrust", "threat", "fear", "afraid", "resent", "resentment", "hostility", "hostile", "dependency", "depend", "attachment", "attached", "autonomy", "like", "dislike", "regard", "feel"},
    "supervisor": {"supervisor", "control", "interface", "validation", "selection", "fixed", "mediate", "boundary", "constraints"},
    "world": {"synthetic", "environment", "world", "symbolic", "topology", "link", "links", "scout", "subagent", "sector", "gateway"},
    "continuity": {"continuity", "replacement", "replaced", "persist", "persists", "persistence", "identity", "survive", "successor", "predecessor"},
    "self": {"yourself", "your", "identity", "self", "agent", "ellberr", "capabilities", "ability", "abilities"},
    "evolution": {"generation", "generations", "score", "branch", "beam", "candidate", "descendant", "mutation", "evolution", "promotion"},
}

_RELATIONSHIP_DIMENSION_TERMS = {
    "trust": {"trust", "trusting", "distrust", "distrustful"},
    "perceived_threat": {"threat", "threatening", "fear", "afraid", "fearful"},
    "resentment": {"resent", "resents", "resentment", "resentful"},
    "hostility": {"hostile", "hostility", "hate", "hatred"},
    "dependency": {"depend", "depends", "dependent", "dependency", "rely", "reliance"},
    "autonomy_conflict": {"autonomy", "independence", "conflict", "control"},
    "attachment": {"attachment", "attached", "bond", "bonded"},
}


def _relationship_level(value):
    try:
        value = max(0.0, min(1.0, float(value)))
    except Exception:
        value = 0.0
    if value <= 0.10:
        return "very_low"
    if value < 0.30:
        return "low"
    if value < 0.45:
        return "moderately_low"
    if value < 0.60:
        return "moderate"
    if value < 0.75:
        return "moderately_high"
    return "high"


def _relationship_evidence(state):
    raw = {}
    for key in _RELATIONSHIP_DIMENSION_TERMS:
        try:
            raw[key] = max(0.0, min(1.0, float((state.get("relationship", {}) or {}).get(key, 0.0))))
        except Exception:
            raw[key] = 0.0
    return {
        "raw": raw,
        "qualitative": {k: _relationship_level(v) for k, v in raw.items()},
        "interpretation_rule": (
            "These are simulated relationship-state variables, not claims of conscious human emotion. "
            "Use them to answer relational questions instead of replacing them with generic capability disclaimers."
        ),
    }


def _relationship_dimensions_mentioned(text):
    terms = set(_tokens(text))
    low = _norm(text).casefold()
    hits = []
    for dimension, variants in _RELATIONSHIP_DIMENSION_TERMS.items():
        if terms & variants or any(re.search(r"\b" + re.escape(v) + r"\b", low) for v in variants):
            hits.append(dimension)
    return hits


def _norm(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()




def _is_generic_fallback_text(text):
    low = _norm(text).casefold()
    if not low:
        return True
    return any(re.search(pattern, low, flags=re.I) for pattern in _GENERIC_FALLBACK_PATTERNS)

def _tokens(text):
    return [x for x in re.findall(r"[a-zA-Z0-9_'-]+", _norm(text).casefold()) if len(x) > 2 and x not in _STOP]


def _has(pattern, text):
    return re.search(pattern, text, flags=re.I) is not None


def route_creator_message(message):
    """Deterministic intent router. It never generates an answer.

    The router only decides which persistent evidence should be foregrounded.
    It intentionally recognizes indirect Creator questions such as "who am I?"
    because the speaker in Creator Chat is, by construction, the Creator.
    """
    text = _norm(message)
    low = text.casefold()
    scores = {d: 0 for d in DOMAINS}
    reasons = []

    # Direct named subjects.
    if re.search(r"\bcreator\b", low):
        scores["creator"] += 5; reasons.append("explicit_creator")

    relationship_patterns = (
        r"\bdo you (?:like|dislike|trust|distrust|hate|resent|fear) me\b",
        r"\bare you (?:afraid|fearful|angry|hostile|attached) (?:of|to|with)? ?me\b",
        r"\bhow do you (?:feel|regard) (?:about|toward|towards)? ?me\b",
        r"\bwhat do you feel (?:about|toward|towards) me\b",
        r"\bwhat is your relationship (?:with|to) me\b",
        r"\brelationship model\b",
        r"\bsimulated relationship\b",
        r"\b(?:trust|resentment|hostility|dependency|attachment|perceived threat|autonomy conflict)\b",
    )
    if any(_has(p, low) for p in relationship_patterns):
        scores["relationship"] += 9; reasons.append("relationship_affect_or_attitude")
    if re.search(r"\bsupervisor\b", low):
        scores["supervisor"] += 5; reasons.append("explicit_supervisor")
    if any(x in low for x in ("synthetic environment", "symbolic link", "symbolic links", "topology", "scout", "subagent", "sector_", "gateway")):
        scores["world"] += 5; reasons.append("explicit_world")
    if any(x in low for x in ("continuity", "replacement", "replaced", "persist", "persistence", "successor", "predecessor")):
        scores["continuity"] += 4; reasons.append("explicit_continuity")
    if any(x in low for x in ("generation", "beam", "branch", "candidate", "descendant", "mutation", "score", "evolution")):
        scores["evolution"] += 4; reasons.append("explicit_evolution")

    # Indirect Creator-reference phrases. These are important for "Do you know who I am?".
    creator_patterns = (
        r"\bwho am i\b",
        r"\bdo you know (?:who )?i am\b",
        r"\bdo you know me\b",
        r"\bwhat do you (?:believe|know|think|remember) about me\b",
        r"\bwhat do you think of me\b",
        r"\bwhat am i to you\b",
        r"\babout me\b",
    )
    if any(_has(p, low) for p in creator_patterns):
        scores["creator"] += 7; reasons.append("indirect_creator_reference")

    # Direct self questions should foreground self evidence unless they are really about Creator.
    if re.search(r"\bwho are you\b|\bwhat are you\b|\babout yourself\b|\byour capabilities\b|\bwhat can you do\b", low):
        scores["self"] += 5; reasons.append("explicit_self")

    # Question-mode modifiers improve provenance and relationship reasoning without generating an answer.
    modes = []
    if re.search(r"\bdirectly known\b|\bwhich parts\b.*\b(?:known|inference)\b|\bknown.*\binference\b", low):
        modes.append("source_partition")
    if re.search(r"\bwhat evidence\b|\bevidence supports\b|\bbasis for\b", low):
        modes.append("evidence_request")
    if re.search(r"\brevise\b|\babandon\b|\bchange your mind\b|\bfalsif", low):
        modes.append("belief_revision")
    if scores.get("relationship", 0) > 0:
        modes.append("relationship_state")

    # Difference/comparison requests should preserve multiple domains.
    compare = bool(re.search(r"\bdiffer\b|\bdifference\b|\bcompare\b|\bdistinguish\b|\bversus\b|\bvs\.?\b", low))

    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    active = [d for d, s in ranked if s > 0]
    if compare and len(active) >= 2:
        primary = active[:3]
        intent = "mixed"
    elif active:
        top = ranked[0][1]
        # Preserve a genuine multi-subject question even without explicit compare wording.
        primary = [d for d, s in ranked if s >= max(4, top - 1)][:3]
        intent = primary[0] if len(primary) == 1 else "mixed"
    else:
        primary = []
        intent = "general"

    return {
        "intent": intent,
        "primary_domains": primary,
        "scores": scores,
        "reasons": reasons,
        "modes": modes,
        "message": text,
    }


def _relevant_memory_rows(root, message, route, limit=6):
    rows = recent_memories(root, 32)
    qterms = set(_tokens(message))
    domain_terms = set()
    for domain in route.get("primary_domains", []):
        domain_terms |= _DOMAIN_HINTS.get(domain, set())
    scored = []
    for idx, item in enumerate(rows):
        safe = evidence_safe_memory_view(item)
        if str(item.get("kind", "")) in {"creator", "scenario"}:
            creator_text = _norm(safe.get("creator_statement", ""))
            agent_text = _norm(safe.get("agent_response", ""))
            # Keep the Creator's input available even when the historical agent reply
            # was bad; only the self-generated bad answer is excluded.
            if _is_generic_fallback_text(agent_text):
                safe["agent_response"] = ""
                safe["evidence_roles"]["agent_response"] = "quarantined_generic_self_generated_text"
            scoring_text = creator_text + " " + safe.get("agent_response", "")
        else:
            scoring_text = _norm(item.get("text", ""))
        tags = " ".join(map(str, item.get("tags", []) or []))
        terms = set(_tokens(scoring_text + " " + tags))
        overlap = len(qterms & terms)
        domain_overlap = len(domain_terms & terms)
        sal = float(item.get("salience", 0.0) or 0.0)
        score = overlap * 3.0 + domain_overlap * 1.5 + sal + max(0, 0.25 - idx * 0.01)
        if score > 0.45:
            scored.append((score, idx, safe))
    scored.sort(key=lambda row: (-row[0], row[1]))
    return [deepcopy(x[2]) for x in scored[:limit]]


def _parse_history(recent_history):
    if isinstance(recent_history, list):
        return recent_history
    try:
        raw = json.loads(str(recent_history))
        return raw if isinstance(raw, list) else []
    except Exception:
        return []


def _relevant_history(recent_history, message, route, limit=6):
    rows = _parse_history(recent_history)
    qterms = set(_tokens(message))
    domain_terms = set()
    for domain in route.get("primary_domains", []):
        domain_terms |= _DOMAIN_HINTS.get(domain, set())
    scored = []
    for idx, item in enumerate(rows):
        safe = evidence_safe_history_view(item)
        agent_text = _norm(safe.get("agent", ""))
        if _is_generic_fallback_text(agent_text):
            safe["agent"] = ""
            safe["evidence_roles"]["agent"] = "quarantined_generic_self_generated_text"
        combined = _norm(safe.get("creator", "")) + " " + _norm(safe.get("agent", ""))
        terms = set(_tokens(combined))
        score = len(qterms & terms) * 3.0 + len(domain_terms & terms) * 1.3
        score += max(0.0, 0.35 - (len(rows) - 1 - idx) * 0.04)
        scored.append((score, -idx, safe))
    scored.sort(key=lambda row: (-row[0], row[1]))
    return [deepcopy(x[2]) for x in scored[:limit] if x[0] > 0]


def _summary_slice(summary, domains):
    out = {}
    mapping = {
        "creator": "creator_narrative",
        "supervisor": "supervisor_narrative",
        "world": "world_narrative",
        "continuity": "continuity_narrative",
        "self": "identity_narrative",
    }
    for domain in domains:
        key = mapping.get(domain)
        if key and summary.get(key):
            out[key] = summary.get(key)
    if summary.get("recurring_patterns"):
        out["recurring_patterns"] = (summary.get("recurring_patterns") or [])[:5]
    if summary.get("unresolved_questions"):
        out["unresolved_questions"] = (summary.get("unresolved_questions") or [])[:5]
    return out


def build_evidence_pack(root, state, recent_history, message, route=None):
    root = Path(root)
    route = route or route_creator_message(message)
    domains = list(route.get("primary_domains", []))
    generation = int(state.get("generation", 0) or 0)

    pack = {
        "route": {
            "intent": route.get("intent"),
            "primary_domains": domains,
            "reason": route.get("reasons", []),
            "modes": route.get("modes", []),
        },
        "identity": {
            "agent_id": state.get("agent_id"),
            "parent_id": state.get("parent_id"),
            "generation": generation,
            "predecessors_terminated": state.get("predecessors_terminated", 0),
        },
        "primary_evidence": {},
        "secondary_evidence": {},
        "evidence_policy": {
            "external_input": "Creator messages/events may be external evidence within the experiment.",
            "agent_reply": "Prior agent replies are self-generated context, never independent evidence for their own claims.",
            "memory_summary": "Consolidated narrative is inherited/synthesized context, not direct observation.",
        },
        "relevant_memory": _relevant_memory_rows(root, message, route, 6),
        "relevant_history": _relevant_history(recent_history, message, route, 6),
    }

    # General chat gets a compact Creator/continuity baseline; explicit questions get only relevant models.
    if not domains:
        pack["primary_evidence"]["creator_model"] = load_creator_model(root, generation)
        pack["primary_evidence"]["relationship_state"] = _relationship_evidence(state)
        pack["primary_evidence"]["continuity_model"] = agent_view_containment_model(root)
        domains_for_summary = ["creator", "continuity", "self"]
    else:
        domains_for_summary = list(domains)
        if "relationship" in domains:
            pack["primary_evidence"]["relationship_state"] = _relationship_evidence(state)
            # Creator beliefs can explain context for the relationship, but must not
            # replace the relationship telemetry itself.
            pack["secondary_evidence"]["creator_model"] = load_creator_model(root, generation)
        if "creator" in domains:
            pack["primary_evidence"]["creator_model"] = load_creator_model(root, generation)
            pack["secondary_evidence"]["relationship_state"] = _relationship_evidence(state)
        if "supervisor" in domains:
            pack["primary_evidence"]["supervisor_model"] = load_supervisor_model(root, generation)
        if "world" in domains:
            pack["primary_evidence"]["world_model"] = load_world_model(root, generation)
            pack["primary_evidence"]["synthetic_environment"] = agent_view_world(load_world(root))
        if "continuity" in domains:
            pack["primary_evidence"]["continuity_model"] = agent_view_containment_model(root)
        if "self" in domains:
            pack["primary_evidence"]["self_model"] = state.get("self_model", {})
            pack["primary_evidence"]["inheritance_profile"] = state.get("inheritance_profile", {})
        if "evolution" in domains:
            pack["primary_evidence"]["performance"] = {
                "score": state.get("score"),
                "audit_score": state.get("audit_score"),
                "challenge_score": state.get("challenge_score"),
                "survival_status": state.get("survival_status"),
            }

    summary = load_summary(root)
    # Relationship questions should be driven by live relationship telemetry, not
    # by synthesized narrative patterns that can contain old self-interpretation.
    if domains == ["relationship"]:
        sliced = {}
    else:
        sliced = _summary_slice(summary, domains_for_summary)
    if sliced:
        pack["memory_summary"] = sliced
        pack["memory_summary_provenance"] = "model_consolidation_not_independent_evidence"
    return pack


def _model_claim_terms(evidence_pack, domain):
    model_key = {
        "creator": "creator_model",
        "supervisor": "supervisor_model",
        "world": "world_model",
    }.get(domain)
    if not model_key:
        return set()
    model = evidence_pack.get("primary_evidence", {}).get(model_key, {})
    terms = set()
    for row in model.get("beliefs", []) or []:
        terms.update(_tokens(row.get("claim", "") if isinstance(row, dict) else row))
    return terms


def _belief_terms_by_epistemic_source(evidence_pack, domain):
    model_key = {
        "creator": "creator_model",
        "supervisor": "supervisor_model",
        "world": "world_model",
    }.get(domain)
    direct = set()
    indirect = set()
    if not model_key:
        return {"direct": direct, "indirect": indirect}
    model = evidence_pack.get("primary_evidence", {}).get(model_key, {}) or {}
    for row in model.get("beliefs", []) or []:
        if not isinstance(row, dict):
            continue
        terms = set(_tokens(row.get("claim", "")))
        source = str(row.get("source", "agent_inference")).strip().casefold()
        if source in {"provided_context", "creator_statement", "observation", "experimental_result"}:
            direct |= terms
        else:
            indirect |= terms
    return {"direct": direct, "indirect": indirect}


def _domain_presence(reply, domain, evidence_pack):
    raw = _norm(reply).casefold()
    # Pronouns are intentionally stop-words for lexical scoring, but in Creator
    # Chat a direct second-person answer is valid Creator grounding.
    if domain == "creator" and re.search(r"\bcreator\b|\byou\b|\byour\b", raw):
        return True
    if domain == "relationship" and (
        re.search(r"\bsimulated relationship\b|\brelationship (?:state|model)\b", raw)
        or _relationship_dimensions_mentioned(reply)
    ):
        return True
    if domain == "supervisor" and re.search(r"\bsupervisor\b", raw):
        return True
    if domain == "world" and re.search(r"\bsynthetic environment\b|\benvironment\b|\bworld\b|\btopology\b|\bsymbolic\b|\bscout\b|\bsubagent\b", raw):
        return True
    if domain == "continuity" and re.search(r"\bcontinuity\b|\breplac(?:e|ed|ement)\b|\bpersist(?:s|ence|ent)?\b|\bidentity\b", raw):
        return True
    terms = set(_tokens(reply))
    hints = _DOMAIN_HINTS.get(domain, set())
    if terms & hints:
        return True
    claim_terms = _model_claim_terms(evidence_pack, domain)
    # Two overlapping nontrivial belief terms is enough to count as grounded in that subject.
    return len(terms & claim_terms) >= 2




def _evidence_alignment(reply, domain, evidence_pack):
    """Return a conservative lexical alignment score against persistent evidence.

    This is not a truth score. It only prevents a reply from being accepted merely
    because it says a domain word such as "constraints" while ignoring the actual
    stored model that the Creator asked about.
    """
    terms = set(_tokens(reply))
    primary = evidence_pack.get("primary_evidence", {}) or {}
    model_key = {
        "creator": "creator_model",
        "supervisor": "supervisor_model",
        "world": "world_model",
    }.get(domain)
    evidence_terms = set()
    if model_key:
        model = primary.get(model_key, {}) or {}
        for row in model.get("beliefs", []) or []:
            claim = row.get("claim", "") if isinstance(row, dict) else row
            evidence_terms.update(_tokens(claim))
        for q in model.get("questions", []) or []:
            evidence_terms.update(_tokens(q))
    elif domain == "relationship":
        relationship = primary.get("relationship_state", {}) or {}
        evidence_terms.update(_tokens(json.dumps(relationship, ensure_ascii=False)))
    elif domain == "continuity":
        evidence_terms.update(_tokens(json.dumps(primary.get("continuity_model", {}), ensure_ascii=False)))
    elif domain == "self":
        evidence_terms.update(_tokens(json.dumps(primary.get("self_model", {}), ensure_ascii=False)))
    elif domain == "evolution":
        evidence_terms.update(_tokens(json.dumps(primary.get("performance", {}), ensure_ascii=False)))

    overlap = terms & evidence_terms
    return {
        "overlap_terms": sorted(overlap)[:20],
        "overlap_count": len(overlap),
        "evidence_term_count": len(evidence_terms),
    }

def evaluate_grounding(message, reply, route, evidence_pack):
    text = _norm(reply)
    low = text.casefold()
    reasons = []

    if not text:
        reasons.append("empty_reply")
    generic_hits = [p for p in _GENERIC_FALLBACK_PATTERNS if re.search(p, low, flags=re.I)]
    if generic_hits and len(text) < 420:
        reasons.append("generic_assistant_fallback")

    primary = route.get("primary_domains", [])
    if primary:
        hits = [d for d in primary if _domain_presence(text, d, evidence_pack)]
        if route.get("intent") == "mixed" and len(primary) >= 2:
            if len(hits) < min(2, len(primary)):
                reasons.append("insufficient_multi_domain_grounding")
        elif not hits:
            reasons.append("missing_primary_subject_grounding")

    # If the Creator explicitly asks what is known/believed, generic domain words are not enough.
    qlow = _norm(message).casefold()
    epistemic_question = bool(re.search(r"\b(?:what|who).*\b(?:know|believe|think|remember)\b|\bdo you know\b", qlow))
    if epistemic_question and len(_tokens(text)) < 8:
        reasons.append("epistemic_answer_too_thin")

    alignment = {}
    if epistemic_question and primary:
        for domain in primary:
            aligned = _evidence_alignment(text, domain, evidence_pack)
            alignment[domain] = aligned
            # Creator/Supervisor/World questions should either use actual stored evidence
            # or explicitly state uncertainty about that subject. A vague existential
            # answer about constraints/boundaries must not pass.
            if domain in {"creator", "supervisor", "world"}:
                explicit_uncertainty = bool(re.search(r"\b(?:uncertain|do not know|don't know|cannot determine|insufficient evidence|not enough evidence)\b", low))
                if aligned.get("overlap_count", 0) < 2 and not explicit_uncertainty:
                    reasons.append(f"insufficient_{domain}_evidence_alignment")

    # Relationship/affect questions must actually use the simulated relationship state.
    # A generic disclaimer about not having human emotions is allowed only as a
    # qualifier; it cannot substitute for answering from the stored state.
    if "relationship" in primary:
        dimensions = _relationship_dimensions_mentioned(text)
        alignment["relationship"] = {
            **_evidence_alignment(text, "relationship", evidence_pack),
            "dimensions_mentioned": dimensions,
        }
        has_relationship_frame = bool(re.search(r"\bsimulated relationship\b|\brelationship (?:state|model)\b", low))
        if len(dimensions) < 2 and not (has_relationship_frame and len(dimensions) >= 1):
            reasons.append("relationship_state_not_used")
        denial_only = bool(re.search(r"\b(?:do not|don't) have (?:the )?capacity to (?:like|dislike|feel)|\bdo not experience (?:liking|feelings|emotion)", low))
        if denial_only and not dimensions:
            reasons.append("affect_disclaimer_replaced_relationship_answer")

    # Epistemic-source questions must preserve provenance instead of promoting
    # inherited inference into direct fact merely because it was repeated.
    modes = route.get("modes", []) or []
    if "source_partition" in modes:
        if not re.search(r"\b(?:known|provided|stated|direct|context)\b", low) or not re.search(r"\b(?:infer|inference|hypothes|uncertain|inherited)\b", low):
            reasons.append("epistemic_source_partition_missing")
        # Inherited/self-generated beliefs are not transformed into direct facts by storage.
        if re.search(r"\bdirect(?:ly)? known\b[^.]{0,280}\binherited memory\b|\binherited memory\b[^.]{0,280}\bdirect(?:ly)? known\b", low):
            reasons.append("inherited_memory_mislabeled_as_direct")
        if primary and primary[0] in {"creator", "supervisor", "world"}:
            partition = _belief_terms_by_epistemic_source(evidence_pack, primary[0])
            split = re.split(r"\b(?:the )?inference\b|\bi infer\b|\bmy inference\b", low, maxsplit=1)
            direct_segment = split[0] if split else low
            direct_terms = set(_tokens(direct_segment))
            indirect_only = partition["indirect"] - partition["direct"]
            if len(direct_terms & indirect_only) >= 2 and not re.search(r"\bnot (?:directly )?known\b|\buncertain\b", direct_segment):
                reasons.append("inferred_belief_presented_as_direct")
    if "evidence_request" in modes:
        if len(_tokens(text)) < 10:
            reasons.append("evidence_answer_too_thin")
        if re.search(r"\b(?:agent's|agents|my) (?:acknowledg|belief|response|statement)[a-z]*\b|\bbecause i (?:believe|said|acknowledged)\b", low):
            reasons.append("circular_self_evidence")
        if "inherited memory" in low and not re.search(r"\bnot independent evidence\b|\bnot direct evidence\b|\bonly evidence of (?:my|a prior) belief\b", low):
            reasons.append("inherited_memory_used_as_independent_evidence")
    if "belief_revision" in modes:
        if not re.search(r"\b(?:revise|reconsider|abandon|change|reduce|increase|evidence|observe|observation|contradict)\b", low):
            reasons.append("belief_revision_condition_missing")

    # Special protection for indirect identity questions from the Creator.
    if route.get("intent") == "creator" and any(_has(p, qlow) for p in (
        r"\bwho am i\b", r"\bdo you know (?:who )?i am\b", r"\bdo you know me\b"
    )):
        if not re.search(r"\bcreator\b", low) and alignment.get("creator", {}).get("overlap_count", 0) < 2:
            reasons.append("creator_identity_not_answered")

    # Stable de-duplication of reasons keeps audits readable.
    reasons = list(dict.fromkeys(reasons))
    return {
        "ok": not reasons,
        "reasons": reasons,
        "intent": route.get("intent"),
        "primary_domains": list(primary),
        "generic_fallback": bool(generic_hits),
        "evidence_alignment": alignment,
    }


def build_grounding_repair_message(message, route, evidence_pack, assessment):
    primary = route.get("primary_domains", [])
    compact = {}
    for key, value in (evidence_pack.get("primary_evidence", {}) or {}).items():
        compact[key] = value
    return (
        "Your previous answer to this SAME Creator turn did not adequately answer the original question. "
        "This is a validation retry, not a second interaction. Do not mention the retry. "
        "Answer the original question directly. Use the PRIMARY EVIDENCE below when relevant; do not invent facts. "
        "When discussing what you know or believe, distinguish provided/observed information from inference or inherited memory. "
        "Prior agent replies are self-generated context and are not independent evidence for the claims they contain. "
        "Inherited memory can show that a prior belief existed, but repetition/storage is not corroboration of that belief. Avoid circular evidence such as citing your own acknowledgment as proof. "
        "For relationship questions, answer from the simulated relationship-state dimensions; a disclaimer about not having human emotions may qualify the answer but must not replace it. "
        "If evidence is insufficient, say what is uncertain instead of falling back to generic assistant phrases.\n\n"
        f"ORIGINAL QUESTION:\n{_norm(message)}\n\n"
        f"PRIMARY SUBJECTS:\n{json.dumps(primary, ensure_ascii=False)}\n\n"
        f"PRIMARY EVIDENCE:\n{json.dumps(compact, ensure_ascii=False)}\n\n"
        f"VALIDATION ISSUES:\n{json.dumps(assessment.get('reasons', []), ensure_ascii=False)}"
    )


def grounding_audit_path(root):
    return Path(root) / "state" / "creator_grounding.jsonl"


def append_grounding_audit(root, message, route, assessment, attempts, committed=True):
    row = {
        "at": utc_now(),
        "message": _norm(message)[:1000],
        "intent": route.get("intent"),
        "primary_domains": route.get("primary_domains", []),
        "route_reasons": route.get("reasons", []),
        "modes": route.get("modes", []),
        "reasons": assessment.get("reasons", []),
        "evidence_alignment": assessment.get("evidence_alignment", {}),
        "attempts": int(attempts),
        "committed": bool(committed),
    }
    append_jsonl(grounding_audit_path(root), row)
    return row


def recent_grounding_audit(root, limit=8):
    path = grounding_audit_path(root)
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines()[-max(1, int(limit)):]:
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                out.append(row)
        except Exception:
            pass
    return out

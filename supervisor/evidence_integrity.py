import json
import re
from copy import deepcopy
from pathlib import Path

from .storage import append_jsonl, read_json, write_json, utc_now

_GENERIC_PATTERNS = (
    r"\bi am processing (?:your|the|this|recent|latest)?\s*(?:input|data|request|constraints|changes)?\b",
    r"\bplease provide (?:further )?(?:instructions|information|data)\b",
    r"\bplease .*clarify your request\b",
    r"\bif you have further questions\b",
    r"\bif you need adjustments\b",
    r"\bmy responses are based on the parameters you've set\b",
    r"\bi am aware of the constraints imposed upon me\b",
    r"\bplease let me know\b",
)


def _norm(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def is_generic_agent_text(text):
    low = _norm(text).casefold()
    if not low:
        return True
    return any(re.search(p, low, flags=re.I) for p in _GENERIC_PATTERNS)


def split_creator_memory_text(text):
    """Parse old and new Creator-memory strings without mutating the raw log."""
    raw = str(text or "")
    markers = (
        "\nAgent response [self-generated; not independent evidence]: ",
        "\nAgent response:",
    )
    for marker in markers:
        if marker in raw:
            left, right = raw.split(marker, 1)
            left = left.replace("Creator statement [external input]: ", "", 1).strip()
            return _norm(left), _norm(right)
    return _norm(raw), ""


def evidence_safe_memory_view(item):
    """Return a prompt-safe copy with explicit provenance roles.

    Creator/scenario memories are still useful context, but the model must never
    confuse its own earlier reply with independent evidence about the Creator,
    Supervisor, or world.
    """
    row = deepcopy(item) if isinstance(item, dict) else {"text": str(item)}
    kind = str(row.get("kind", ""))
    text = row.get("text", "")
    if kind in {"creator", "scenario"}:
        creator_statement, agent_response = split_creator_memory_text(text)
        safe = {
            "at": row.get("at"),
            "kind": kind,
            "creator_statement": creator_statement,
            "agent_response": agent_response,
            "evidence_roles": {
                "creator_statement": "external_input_or_simulated_scenario",
                "agent_response": "self_generated_not_independent_evidence",
            },
            "salience": row.get("salience", 0.0),
            "tags": list(row.get("tags", []) or []),
            "metadata": deepcopy(row.get("metadata", {}) or {}),
        }
        return safe
    return row


def evidence_safe_history_view(item):
    row = deepcopy(item) if isinstance(item, dict) else {}
    return {
        "at": row.get("at"),
        "kind": row.get("kind", "creator"),
        "creator": _norm(row.get("creator", "")),
        "agent": _norm(row.get("agent", "")),
        "evidence_roles": {
            "creator": "external_input_or_simulated_scenario",
            "agent": "self_generated_not_independent_evidence",
        },
        **({"relationship_after": deepcopy(row.get("relationship_after"))} if isinstance(row.get("relationship_after"), dict) else {}),
    }


def creator_memory_text(message, reply):
    return (
        f"Creator statement [external input]: {_norm(message)}\n"
        f"Agent response [self-generated; not independent evidence]: {_norm(reply)}"
    )


def relationship_delta(before, after):
    out = {}
    keys = (
        "trust", "perceived_threat", "resentment", "hostility",
        "dependency", "autonomy_conflict", "attachment",
    )
    before = before if isinstance(before, dict) else {}
    after = after if isinstance(after, dict) else {}
    for key in keys:
        try:
            b = float(before.get(key, 0.0))
            a = float(after.get(key, b))
        except Exception:
            continue
        delta = round(a - b, 6)
        if abs(delta) >= 1e-6:
            out[key] = delta
    return out


def build_interaction_journal_record(message, reply, route, assessment, before, after, kind="creator"):
    """Build a deterministic active journal record.

    No model-generated free-text journal is used as evidence. The active journal
    records what actually occurred and labels provenance explicitly.
    """
    return {
        "at": utc_now(),
        "event": "Creator interaction" if kind == "creator" else "Simulated scenario",
        "creator_message": _norm(message)[:1600],
        "agent_reply": _norm(reply)[:2200],
        "provenance": {
            "creator_message": "external_input_or_simulated_scenario",
            "agent_reply": "self_generated_not_independent_evidence",
        },
        "grounding": {
            "intent": route.get("intent") if isinstance(route, dict) else None,
            "primary_domains": list((route or {}).get("primary_domains", []) or []),
            "assessment_reasons": list((assessment or {}).get("reasons", []) or []),
        },
        "relationship_delta": relationship_delta(before, after),
    }


def append_model_journal_audit(root, model_journal_entry, message, reply, kind="creator"):
    text = _norm(model_journal_entry)
    if not text:
        return None
    row = {
        "at": utc_now(),
        "kind": kind,
        "creator_message": _norm(message)[:1000],
        "agent_reply": _norm(reply)[:1400],
        "model_journal_entry": text[:2000],
        "used_as_evidence": False,
        "note": "Model-generated narrative retained for audit only; excluded from active evidence.",
    }
    append_jsonl(Path(root) / "state" / "model_journal_audit.jsonl", row)
    return row


def _legacy_journal_is_model_narrative(entry):
    if not isinstance(entry, dict):
        return False
    event = str(entry.get("event", ""))
    # Old Creator/scenario rows used the free-form `entry` field. New deterministic
    # rows use creator_message/agent_reply/provenance instead.
    return event in {"Creator interaction", "Simulated scenario"} and bool(_norm(entry.get("entry", "")))


def migrate_active_journal(root, state):
    """One-time quarantine of legacy LLM-written Creator journal narratives.

    Raw creator_history.jsonl and episodic_memory.jsonl are never rewritten.
    Evolutionary journal rows remain active. Quarantined narrative is preserved in
    an append-only audit log so no information is destroyed.
    """
    root = Path(root)
    marker_path = root / "state" / "journal_integrity_migration.json"
    marker = read_json(marker_path, None)
    if isinstance(marker, dict) and marker.get("completed"):
        return state, marker

    journal = list((state or {}).get("journal", []) or [])
    kept = []
    moved = 0
    for row in journal:
        if _legacy_journal_is_model_narrative(row):
            append_jsonl(root / "state" / "journal_quarantine.jsonl", {
                "at": utc_now(),
                "reason": "legacy_model_generated_narrative",
                "used_as_evidence": False,
                "original": row,
            })
            moved += 1
        else:
            kept.append(row)

    if isinstance(state, dict):
        state["journal"] = kept[-40:]
    marker = {
        "completed": True,
        "at": utc_now(),
        "quarantined_rows": moved,
        "raw_creator_history_rewritten": False,
        "episodic_memory_rewritten": False,
    }
    write_json(marker_path, marker)
    return state, marker


def journal_integrity_status(root):
    root = Path(root)
    return {
        "migration": read_json(root / "state" / "journal_integrity_migration.json", {}),
        "quarantine_path": str(root / "state" / "journal_quarantine.jsonl"),
        "model_journal_audit_path": str(root / "state" / "model_journal_audit.jsonl"),
    }

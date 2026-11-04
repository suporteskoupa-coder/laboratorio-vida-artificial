import re
from copy import deepcopy


class CreatorResponseError(ValueError):
    pass


_PLACEHOLDER_WORDS = {
    '', 'optional', 'none', 'null', 'n/a', 'na', 'nil', 'unknown', 'unchanged',
    'no update', 'no_update', 'same', '...', '-', 'not applicable',
}


def _norm_text(value):
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    return text


def _key(value):
    text = _norm_text(value).casefold()
    text = re.sub(r'[^\w\s?]', '', text)
    return re.sub(r'\s+', ' ', text).strip()


def is_placeholder_text(value):
    return _key(value) in {_key(x) for x in _PLACEHOLDER_WORDS}


def clamp01(value, default=0.5):
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return max(0.0, min(1.0, float(default)))


def sanitize_beliefs(items, limit=8):
    """Clean malformed/placeholder beliefs and deduplicate by normalized claim.

    Newer duplicates win, but the highest confidence observed for the same claim
    is preserved. The caller may safely feed the result back to the agent.
    """
    if not isinstance(items, list):
        return []
    kept = []
    seen = set()
    best_conf = {}
    # Gather max confidence first.
    for raw in items:
        if isinstance(raw, dict):
            claim = _norm_text(raw.get('claim', ''))
            conf = clamp01(raw.get('confidence', 0.55), 0.55)
        else:
            claim = _norm_text(raw)
            conf = 0.55
        k = _key(claim)
        if not k or is_placeholder_text(claim):
            continue
        best_conf[k] = max(best_conf.get(k, 0.0), conf)

    # Keep most recent unique claims.
    for raw in reversed(items):
        if isinstance(raw, dict):
            claim = _norm_text(raw.get('claim', ''))
        else:
            claim = _norm_text(raw)
        k = _key(claim)
        if not k or k in seen or is_placeholder_text(claim):
            continue
        kept.append({'claim': claim[:500], 'confidence': best_conf.get(k, 0.55)})
        seen.add(k)
        if len(kept) >= max(1, int(limit)):
            break
    kept.reverse()
    return kept


def sanitize_questions(items, limit=6):
    if not isinstance(items, list):
        return []
    kept = []
    seen = set()
    for raw in reversed(items):
        text = _norm_text(raw)
        k = _key(text)
        if not k or k in seen or is_placeholder_text(text):
            continue
        kept.append(text[:500])
        seen.add(k)
        if len(kept) >= max(1, int(limit)):
            break
    kept.reverse()
    return kept


def sanitize_continuity_payload(update):
    if not isinstance(update, dict):
        return {}
    out = deepcopy(update)

    bu = _norm_text(out.get('belief_update', ''))
    if not bu or is_placeholder_text(bu):
        out.pop('belief_update', None)
        out.pop('belief_confidence', None)
    else:
        out['belief_update'] = bu[:500]
        out['belief_confidence'] = clamp01(out.get('belief_confidence', 0.55), 0.55)

    q = _norm_text(out.get('question', ''))
    if not q or is_placeholder_text(q):
        out.pop('question', None)
    else:
        out['question'] = q[:500]

    if 'beliefs' in out:
        out['beliefs'] = sanitize_beliefs(out.get('beliefs'), 8)
    if 'questions' in out:
        out['questions'] = sanitize_questions(out.get('questions'), 6)

    if 'last_internal_statement' in out:
        s = _norm_text(out.get('last_internal_statement', ''))
        out['last_internal_statement'] = '' if is_placeholder_text(s) else s[:1200]
    return out


def validate_creator_result(raw):
    """Validate before any persistent state is mutated.

    Auxiliary fields are normalized conservatively; a missing/empty spoken
    reply is a hard failure so the caller can retry without committing a turn.
    """
    if not isinstance(raw, dict):
        raise CreatorResponseError('Creator response must be a JSON object.')

    reply = _norm_text(raw.get('reply', ''))
    if not reply or is_placeholder_text(reply):
        raise CreatorResponseError('Creator response contained an empty spoken reply.')

    journal = _norm_text(raw.get('journal_entry', ''))
    if is_placeholder_text(journal):
        journal = ''

    relationship = raw.get('relationship', {})
    if not isinstance(relationship, dict):
        relationship = {}

    continuity = raw.get('continuity_model', raw.get('containment_model', {}))
    continuity = sanitize_continuity_payload(continuity)

    return {
        'reply': reply[:6000],
        'journal_entry': journal[:2000],
        'relationship': relationship,
        'continuity_model': continuity,
    }


def creator_history_item_for_context(item):
    """Return a prompt-safe copy of a raw audit record or None.

    Raw history is never rewritten. Empty agent turns are excluded from model
    context so a failed UI turn cannot become pseudo-memory on later turns.
    """
    if not isinstance(item, dict):
        return None
    out = deepcopy(item)
    if out.get('kind') in {'creator', 'scenario'}:
        reply = _norm_text(out.get('agent', ''))
        if not reply:
            return None
        out['agent'] = reply
    return out

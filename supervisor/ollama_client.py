import json
import socket
import urllib.request
import urllib.error
from pathlib import Path

from .hardware import load_runtime_profile

class JSONResponseError(ValueError):
    def __init__(self, message, raw_content="", done_reason=None):
        super().__init__(message)
        self.raw_content = raw_content
        self.done_reason = done_reason

def _root():
    return Path(__file__).resolve().parents[1]

def _load_cognitive_profile():
    path = _root() / "COGNITIVE_PROFILE.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def model_settings(config, purpose="mutation"):
    profile, info = load_runtime_profile(_root(), config)
    settings = dict(config["models"][profile])
    settings["profile"] = profile
    settings["role"] = "evolution"

    # The cognitive path is intentionally decoupled from the evolution model.
    # A larger model improves Creator Chat / reflection / semantic modeling without
    # multiplying the cost of every mutation candidate.
    if purpose in {"creator", "cognitive", "semantic", "reflection", "world"}:
        cog = _load_cognitive_profile()
        if cog.get("enabled", True):
            settings["model"] = str(cog.get("model") or settings["model"])
            settings["num_ctx"] = int(cog.get("num_ctx", settings.get("num_ctx", 8192)))
            settings["num_predict_creator"] = int(cog.get("num_predict", settings.get("num_predict_creator", 1536)))
            settings["temperature_creator"] = float(cog.get("temperature", settings.get("temperature_creator", 0.5)))
            settings["keep_alive"] = str(cog.get("keep_alive", config.get("ollama_keep_alive", "30m")))
            settings["strict_cognition"] = bool(cog.get("strict", True))
            settings["role"] = "cognition"
    return settings

def _timeout_for(config, purpose):
    return int(config.get("ollama", {}).get("socket_inactivity_timeout_seconds", 120))

def _temperature_key(purpose):
    if purpose in {"creator", "cognitive", "semantic", "reflection", "world"}:
        return "temperature_creator"
    if purpose == "repair":
        return "temperature_repair"
    return "temperature_mutation"

def _num_predict(settings, purpose):
    if purpose in {"creator", "cognitive", "semantic", "reflection", "world"}:
        return int(settings.get("num_predict_creator", 1280))
    if purpose == "repair":
        return int(settings.get("num_predict_repair", 4096))
    return int(settings.get("num_predict_mutation", 4096))

def _clean_json_text(content):
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

    # If the model added a tiny amount of prose around the object, prefer the
    # outermost complete-looking object. This does not invent missing JSON.
    first = cleaned.find("{")
    last = cleaned.rfind("}")
    if first > 0 and last > first:
        cleaned = cleaned[first:last + 1]
    return cleaned

def _parse_content(content, done_reason=None):
    cleaned = _clean_json_text(content)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        likely_truncated = (
            done_reason == "length"
            or not cleaned.endswith("}")
            or exc.pos >= max(0, len(cleaned) - 80)
        )
        suffix = " Response appears truncated." if likely_truncated else ""
        raise JSONResponseError(
            f"Invalid JSON from Ollama at line {exc.lineno}, column {exc.colno} "
            f"(char {exc.pos}).{suffix}",
            raw_content=cleaned,
            done_reason=done_reason,
        ) from exc

def chat_json(
    config,
    messages,
    purpose="mutation",
    timeout=None,
    num_predict_override=None,
):
    settings = model_settings(config, purpose=purpose)
    if timeout is None:
        timeout = _timeout_for(config, purpose)

    stream = bool(config.get("ollama", {}).get("stream", True))
    show_progress = bool(config.get("ollama", {}).get("show_stream_progress", True))
    temperature_key = _temperature_key(purpose)

    num_predict = (
        int(num_predict_override)
        if num_predict_override is not None
        else _num_predict(settings, purpose)
    )

    payload = {
        "model": settings["model"],
        "messages": messages,
        "stream": stream,
        "format": "json",
        "think": False,
        "keep_alive": settings.get("keep_alive", config.get("ollama_keep_alive", "30m")),
        "options": {
            "num_ctx": int(settings.get("num_ctx", 8192)),
            "num_predict": num_predict,
            "temperature": float(settings.get(temperature_key, 0.3)),
        },
    }

    req = urllib.request.Request(
        config["ollama_url"],
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if not stream:
                result = json.loads(resp.read().decode("utf-8"))
                content = result.get("message", {}).get("content", "")
                return _parse_content(content, result.get("done_reason"))

            parts = []
            chunk_count = 0
            printed_progress = False
            final_item = {}

            for raw_line in resp:
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                item = json.loads(line)
                final_item = item
                piece = item.get("message", {}).get("content", "")
                if piece:
                    parts.append(piece)
                    chunk_count += 1

                    if (
                        show_progress
                        and purpose in {"mutation", "repair"}
                        and chunk_count % 64 == 0
                    ):
                        print(".", end="", flush=True)
                        printed_progress = True

                if item.get("done"):
                    break

            if printed_progress:
                print()

            content = "".join(parts)
            if not content.strip():
                raise RuntimeError(
                    f"Ollama returned an empty response while generating {purpose}."
                )

            return _parse_content(content, final_item.get("done_reason"))

    except (TimeoutError, socket.timeout) as exc:
        raise RuntimeError(
            f"Ollama stopped sending data for {timeout}s while generating {purpose}. "
            "This is an inactivity timeout, not a total generation-time limit."
        ) from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None)
        if isinstance(reason, (TimeoutError, socket.timeout)):
            raise RuntimeError(
                f"Ollama stopped sending data for {timeout}s while generating {purpose}."
            ) from exc
        raise RuntimeError(
            f"Could not contact Ollama/model {settings['model']}. "
            "Make sure Ollama is running."
        ) from exc

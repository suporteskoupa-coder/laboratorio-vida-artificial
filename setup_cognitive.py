import json, os, shutil, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def find_ollama():
    p = shutil.which("ollama")
    if p:
        return p
    for c in [
        Path(os.environ.get("LOCALAPPDATA", ""))/"Programs"/"Ollama"/"ollama.exe",
        Path(os.environ.get("PROGRAMFILES", ""))/"Ollama"/"ollama.exe",
    ]:
        if c.exists():
            return str(c)
    return None

def ensure_server(ollama):
    try:
        p = subprocess.run(
            [ollama, "list"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=8,
        )
        if p.returncode == 0:
            return
    except Exception:
        pass
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    subprocess.Popen(
        [ollama, "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        **kwargs,
    )
    time.sleep(3)

def model_is_local(ollama, model):
    try:
        p = subprocess.run(
            [ollama, "show", model],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=12,
        )
        return p.returncode == 0
    except Exception:
        return False

def main():
    profile = json.loads((ROOT/"COGNITIVE_PROFILE.json").read_text(encoding="utf-8"))
    model = str(profile.get("model", "qwen3:14b"))
    ollama = find_ollama()
    if not ollama:
        print("Ollama not found. Run START_HERE.bat first.")
        raise SystemExit(1)

    ensure_server(ollama)

    print(f"\nHigh-intelligence cognitive model: {model}")
    print("Used for Creator Chat, semantic models, reflection, life cognition and memory consolidation.\n")

    if model_is_local(ollama, model):
        print(f"{model} is already installed locally.")
        print("No download is necessary. Cognitive model ready.")
        return

    print(f"{model} is not installed locally. Downloading...")
    proc = subprocess.run([ollama, "pull", model], check=False)
    if proc.returncode != 0:
        print("\nDownload failed.")
        print("If Ollama reports 'x509: certificate signed by unknown authority',")
        print("fix the Windows/network TLS certificate issue first; do not disable TLS verification.")
        raise SystemExit(proc.returncode)

    if not model_is_local(ollama, model):
        print("Ollama pull returned successfully but the model cannot be found locally.")
        raise SystemExit(2)

    print("\nCognitive model ready.")

if __name__ == "__main__":
    main()

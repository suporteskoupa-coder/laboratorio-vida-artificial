import argparse, json, os, shutil, subprocess, sys, time
from pathlib import Path
from supervisor.hardware import save_runtime_profile

ROOT = Path(__file__).resolve().parent
DEPS = ROOT / "_deps"

def run(cmd, check=True, capture=False):
    print("\n>", " ".join(map(str, cmd)))
    proc = subprocess.run(
        cmd,
        check=False,
        text=capture,
        capture_output=capture,
    )
    if capture:
        if proc.stdout:
            print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n")
        if proc.stderr:
            print(proc.stderr, end="" if proc.stderr.endswith("\n") else "\n")
    if check and proc.returncode != 0:
        raise SystemExit(proc.returncode)
    return proc

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

def ensure_ollama_server(ollama):
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

    print("Starting local Ollama service...")
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
    """Use Ollama's local metadata lookup; this does not require a registry pull."""
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

def ensure_model(ollama, model, label):
    if model_is_local(ollama, model):
        print(f"\n{label} already installed locally: {model}")
        print("Skipping network download.")
        return True

    print(f"\n{label} is not installed locally: {model}")
    print("Downloading from Ollama registry...")
    proc = run([ollama, "pull", model], check=False, capture=True)
    if proc.returncode == 0 and model_is_local(ollama, model):
        return True

    print("\nMODEL DOWNLOAD FAILED")
    print("---------------------")
    print(f"Required model: {model}")
    print("E.L.B.E.R.R. did not disable TLS verification or bypass certificate checks.")
    print("If the error mentions 'x509: certificate signed by unknown authority',")
    print("the problem is between Ollama and the HTTPS certificate chain on this PC/network.")
    print("\nTry these safe checks:")
    print("  1. Confirm Windows date/time are correct.")
    print("  2. Update/restart Ollama.")
    print("  3. Check whether a VPN, proxy, antivirus, AdGuard, or HTTPS inspection is intercepting TLS.")
    print("  4. Run 'ollama pull %s' manually after fixing the certificate issue." % model)
    print("\nIf the model is copied/installed locally later, rerun SETUP_WINDOWS.bat;")
    print("the setup will detect it and will NOT contact the registry again.")
    return False

def main():
    parser = argparse.ArgumentParser()
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--quality", action="store_true")
    g.add_argument("--balanced", action="store_true")
    g.add_argument("--light", action="store_true")
    args = parser.parse_args()

    ollama = find_ollama()
    if not ollama:
        print("Ollama was not found. Run START_HERE.bat first or install Ollama.")
        raise SystemExit(1)

    config = json.loads((ROOT/"config.json").read_text(encoding="utf-8"))
    forced = "quality" if args.quality else "balanced" if args.balanced else "light" if args.light else None
    profile = save_runtime_profile(ROOT, config, forced)

    print("\nDetected hardware:\n" + json.dumps(profile["hardware"], indent=2))
    print(f"\nSelected profile: {profile['profile'].upper()}")
    print(f"Selected model:   {profile['model']}")

    print("\nInstalling project-local Wasmtime...")
    DEPS.mkdir(exist_ok=True)
    run([
        sys.executable, "-m", "pip", "install", "--upgrade", "--target",
        str(DEPS), f"wasmtime=={config['wasm']['wasmtime_version']}"
    ])

    ensure_ollama_server(ollama)

    if not ensure_model(ollama, profile["model"], "Evolution model"):
        raise SystemExit(2)

    try:
        cognitive = json.loads((ROOT/"COGNITIVE_PROFILE.json").read_text(encoding="utf-8"))
        if cognitive.get("enabled", True):
            cog_model = str(cognitive.get("model", "qwen3:14b"))
            if cog_model == profile["model"]:
                print(f"\nCognitive model shares the installed evolution model: {cog_model}")
            elif not ensure_model(ollama, cog_model, "Cognitive model"):
                raise SystemExit(3)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"Warning: cognitive model setup skipped: {exc}")

    print("\nSetup complete.")
    print("No Podman, WSL, Docker, Hyper-V or VM was installed.")
    print("Next: run SELF_TEST.bat, then run_3_generations.bat or chat_with_creator.bat.")

if __name__ == "__main__":
    main()

import json
import os
import platform
import subprocess
from pathlib import Path

def _system_ram_gb():
    try:
        if platform.system() == "Windows":
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            return stat.ullTotalPhys / (1024**3)

        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return pages * page_size / (1024**3)
    except Exception:
        return None

def _gpu_info():
    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits"
            ],
            capture_output=True, text=True, timeout=8, check=False
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return None
        first = proc.stdout.strip().splitlines()[0]
        name, memory = first.rsplit(",", 1)
        return {"name": name.strip(), "vram_mb": int(memory.strip())}
    except Exception:
        return None

def detect_hardware():
    return {
        "system": platform.system(),
        "cpu": platform.processor() or "unknown",
        "ram_gb": _system_ram_gb(),
        "gpu": _gpu_info()
    }

def choose_profile(config, forced=None):
    if forced in {"quality", "balanced", "light"}:
        return forced, detect_hardware()

    hw = detect_hardware()
    ram = hw.get("ram_gb") or 0
    gpu = hw.get("gpu") or {}
    vram = gpu.get("vram_mb", 0)

    # Tuned for reliability rather than maximum possible model size.
    # 14B Q4 is chosen only when ~12 GB VRAM and ~16 GB system RAM are visible.
    if vram >= 11000 and ram >= 15:
        return "quality", hw
    if vram >= 6000 and ram >= 11:
        return "balanced", hw
    return "light", hw

def save_runtime_profile(root, config, forced=None):
    profile, hw = choose_profile(config, forced)
    data = {
        "profile": profile,
        "model": config["models"][profile]["model"],
        "hardware": hw
    }
    path = Path(root) / "state" / "runtime_profile.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data

def load_runtime_profile(root, config):
    path = Path(root) / "state" / "runtime_profile.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            profile = data.get("profile")
            if profile in config["models"]:
                return profile, data
        except Exception:
            pass
    data = save_runtime_profile(root, config)
    return data["profile"], data

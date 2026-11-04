import sys
from pathlib import Path

def add_local_deps(root):
    deps = Path(root) / "_deps"
    if deps.exists():
        p = str(deps)
        if p not in sys.path:
            sys.path.insert(0, p)

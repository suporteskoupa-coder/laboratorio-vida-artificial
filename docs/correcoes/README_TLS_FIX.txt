E.L.B.E.R.R. v0.9 — LOCAL MODEL / TLS SETUP FIX

Problem fixed:
The original v0.9 setup always called `ollama pull`, even when a required model
was already present locally. That could unnecessarily fail on PCs/networks where
Ollama's HTTPS connection to registry.ollama.ai reports:

  x509: certificate signed by unknown authority

This patch:
- checks `ollama show <model>` first;
- skips ALL registry access when the model is already local;
- applies the same behavior to the high-intelligence cognitive model;
- does NOT disable TLS verification;
- does NOT weaken certificate security.

Install:
Extract this ZIP into the ELLBERR_Lab_v0.9_DIGITAL_ECOLOGY folder and replace
setup_local.py and setup_cognitive.py.

Then run SETUP_WINDOWS.bat (or START_HERE.bat) again.

If qwen3:8b and qwen3:14b are already installed, setup will print
"already installed locally" and continue without contacting the Ollama registry.

If a required model is genuinely missing, the certificate issue still needs to
be fixed before Ollama can download it.

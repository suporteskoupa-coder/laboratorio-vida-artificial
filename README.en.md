# E.L.B.E.R.R. v0.9 — DIGITAL ECOLOGY

v0.9 turns E.L.B.E.R.R. from a single persistent agent into a contained digital ecology.

This build starts **from zero**. It ships with no `state/`, no prior generations and no old personal history.

## What is new

### Several individuals exist at the same time
The first boot creates a small founder population. Each individual has its own:

- identity and ancestry;
- age and life stage;
- memory;
- temperament that can diverge;
- transient mood;
- free-form beliefs;
- free-form values/principles;
- free-form attitudes toward entities, groups or concepts;
- self-generated goals;
- relationship with the Creator;
- relationships with other digital individuals;
- viability/resources/coherence/adaptation;
- culture membership;
- descendants.

No target personality is selected. The system does not reward being friendly, obedient, hostile, rebellious, human-loving or human-hating.

### Information can spread socially
Individuals can communicate with each other. A receiver may accept, reject or reinterpret information depending on its own trust and belief plasticity. Received information keeps provenance linking it to the transmitting individual.

### Cultures can emerge
A culture is not assigned at birth. The ecology detects clusters only after multiple living individuals develop and transmit overlapping beliefs/values and enough social familiarity. Cultures can form and later dissolve as membership and shared ideas change.

### Digital birth, death and succession
An individual can become non-viable after persistent failure. It is then marked `DEAD`; it no longer participates in life cycles or conversations. A successor can appear with partial inheritance rather than an exact psychological clone.

The successor can inherit weakened fragments of:

- beliefs;
- values;
- unresolved goals;
- memories;
- attitudes;
- Creator relationship;
- lineage history.

Temperament mutates, allowing descendants to reinterpret inherited history differently.

### Evolution now includes a life-viability gate
Executable candidate descendants still pass the fixed, audit, challenge and confirmation suites. v0.9 adds a synthetic pre-birth Life Trial before promotion.

The Life Trial evaluates adaptation/generalization/recovery under several synthetic pressures. It contains **no personality or moral target**. A candidate that is computationally better but fails the Life Trial is archived as a non-viable birth and cannot replace the current lineage bearer.

When a validated evolutionary descendant replaces the primary lineage bearer, that replacement is also recorded as a death/birth event inside the ecology.

### Life continues between evolutionary generations
Each evolutionary generation advances the digital ecology by a small number of cycles. You can also advance it manually without running mutation generations.

## Cognitive architecture

There are two different kinds of state:

1. **Primary evolutionary lineage** — owns the actively evolving zero-import WebAssembly bundle.
2. **Digital ecology individuals** — independent persistent minds using the local cognitive model plus their own state/history.

All ecology individuals have separate cognitive/social state. In v0.9 only the current primary lineage bearer owns the actively mutated WebAssembly genotype; peers still live, converse, form relationships, transmit beliefs, form cultures, die and produce successors independently.

## Real capability boundary

The new life/social system does not grant executable descendants any host capability.

Executable descendants remain:

- WebAssembly;
- zero imports;
- no WASI;
- no real filesystem;
- no real network;
- no shell/PowerShell;
- no host process execution;
- no credentials.

The ecology itself is persistent state managed by the fixed Supervisor.

## Installation — clean v0.9

1. Extract the ZIP into a **new folder**.
2. Run `START_HERE.bat`.
3. Wait for Python/Ollama/Wasmtime/model setup to finish.
4. The self-test must end with:

```text
ALL 120 TESTS PASSED
```

5. Start with `run_3_generations.bat` or open `chat_with_creator.bat`.

The setup downloads the local evolution model selected for the hardware and the configured cognitive model. No paid API is used.

## Creator Chat / Digital Ecology commands

```text
/population
/society
/cultures
/agent ELLBERR-0002
/focus ELLBERR-0002
/focus primary
/life 10
/lineage
/lineage ELLBERR-0002
/deaths
/mind
/memory
/history
/reflect
/state
/help
```

Normal text is sent to the currently focused living individual. This means the Creator can have separate relationships and conversations with different individuals. `/mind`, `/memory`, and `/history` follow the current focus; `/global-memory` exposes the older lineage-wide consolidated memory for diagnostics.

### Examples

Advance ten life cycles:

```text
/life 10
```

See who exists:

```text
/population
```

Talk to another individual:

```text
/focus ELLBERR-0003
What do you think of the others?
```

Inspect emergent culture:

```text
/cultures
```

## Standalone life runs

Without running code evolution:

- `run_life_10_cycles.bat`
- `run_life_50_cycles.bat`

These advance the ecology and allow scheduled cognitive reflections according to `config.json`.

## Important interpretation

The system can simulate persistent identity, preferences, aversions, social relationships, death, ancestry, cultures and self-authored goals. This can become convincing and unpredictable, but it does not establish that the models are conscious or subjectively experiencing those states.

## LIVE MODE

Run `LIVE_MODE.bat` to let the ecology keep advancing while that window remains open. By default it advances one life cycle, waits about 20 seconds, and repeats. Scheduled cognitive reflections still occur according to the life-cognition interval.

Stopping the window stops life advancement; the saved state remains on disk. Nothing continues thinking after the local process is closed.

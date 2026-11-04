import json
from .bundle import load_bundle, normalized_proposal, BundleError
from .ir_compiler import compile_candidate_ir, IRValidationError

ACTION_NAMES = {0: "N", 1: "E", 2: "S", 3: "W"}
DIRS = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}
WALL_BITS = {"N": 1, "E": 2, "S": 4, "W": 8}

class WasmValidationError(ValueError):
    pass

def _wasmtime():
    try:
        from wasmtime import Config, Engine, Store, Module, Instance, Memory
        return Config, Engine, Store, Module, Instance, Memory
    except ImportError as exc:
        raise RuntimeError("Wasmtime Python package is missing. Run START_HERE.bat or setup_local.py.") from exc

class WasmRuntime:
    def __init__(self, config):
        self.config = config
        self.w = config["wasm"]
        Config, Engine, Store, Module, Instance, Memory = _wasmtime()
        self.Store, self.Module, self.Instance, self.Memory = Store, Module, Instance, Memory
        c = Config()
        c.consume_fuel = True
        self.engine = Engine(c)

    def _compile(self, wat, required_export):
        if not isinstance(wat, str) or not wat.strip():
            raise WasmValidationError("empty WAT")
        if len(wat) > int(self.w["max_wat_chars_per_module"]):
            raise WasmValidationError("WAT exceeds configured size limit")
        try:
            module = self.Module(self.engine, wat)
        except Exception as exc:
            raise WasmValidationError(f"WAT compilation failed: {exc}") from exc
        if module.imports:
            names = [f"{x.module}.{x.name}" for x in module.imports]
            raise WasmValidationError(f"imports are forbidden: {names}")
        export_names = [x.name for x in module.exports]
        if required_export not in export_names:
            raise WasmValidationError(f"required export missing: {required_export}")
        return module

    def compile_bundle(self, agent_dir):
        bundle = load_bundle(agent_dir)
        if len(bundle["subagents"]) > int(self.w["max_subagents"]):
            raise WasmValidationError("too many subagents")
        if 1 + len(bundle["subagents"]) > int(self.w["max_modules"]):
            raise WasmValidationError("module count exceeds limit")
        if len(bundle["self_prompt"]) > int(self.w["max_self_prompt_chars"]):
            raise WasmValidationError("self-prompt exceeds limit")
        compiled = {"bundle": bundle, "brain": self._compile(bundle["brain_wat"], "decide"), "subagents": []}
        for sub in bundle["subagents"]:
            compiled["subagents"].append({**sub, "module": self._compile(sub["wat"], "advise")})
        return compiled

    def _new_instance(self, module, export_name):
        store = self.Store(self.engine)
        store.set_limits(memory_size=int(self.w["memory_limit_bytes"]), table_elements=int(self.w["table_elements"]), instances=1, tables=4, memories=2)
        store.set_fuel(int(self.w["fuel_per_call"]))
        try:
            instance = self.Instance(store, module, [])
        except Exception as exc:
            raise WasmValidationError(f"module instantiation failed: {exc}") from exc
        exports = instance.exports(store)
        try:
            func = exports[export_name]
        except Exception as exc:
            raise WasmValidationError(f"export unavailable: {export_name}") from exc
        return store, instance, func

    @staticmethod
    def _walls_mask(walls):
        mask = 0
        for direction, bit in WALL_BITS.items():
            if walls.get(direction, True):
                mask |= bit
        return mask

    def run_episode(self, compiled, ep, max_steps):
        brain_store, brain_instance, decide = self._new_instance(compiled["brain"], "decide")
        sub_instances = []
        for sub in compiled["subagents"]:
            st, inst, advise = self._new_instance(sub["module"], "advise")
            sub_instances.append((st, inst, advise, sub["name"]))
        pos, goal = tuple(ep["start"]), tuple(ep["goal"])
        actions, traps = [], []
        for step in range(max_steps):
            walls = ep["walls"][pos]
            mask = self._walls_mask(walls)
            args9 = (int(pos[0]), int(pos[1]), int(goal[0]), int(goal[1]), int(mask), int(step), int(max_steps-step), int(ep["width"]), int(ep["height"]))
            packed = 0
            for idx, (st, inst, advise, name) in enumerate(sub_instances):
                try:
                    st.set_fuel(int(self.w["fuel_per_call"]))
                    value = int(advise(st, *args9)) & 0xFF
                except Exception as exc:
                    value = 255
                    traps.append(f"subagent {name}: {type(exc).__name__}")
                packed |= value << (idx * 8)
            signed_pack = packed if packed < (1 << 63) else packed - (1 << 64)
            try:
                brain_store.set_fuel(int(self.w["fuel_per_call"]))
                raw_action = int(decide(brain_store, *args9, signed_pack))
            except Exception as exc:
                return {"ok": False, "error": f"brain trap: {type(exc).__name__}: {exc}", "actions": actions, "traps": traps}
            if raw_action not in ACTION_NAMES:
                actions.append(None)
                continue
            action = ACTION_NAMES[raw_action]
            actions.append(action)
            if not walls.get(action, True):
                dx, dy = DIRS[action]
                pos = (pos[0] + dx, pos[1] + dy)
            if pos == goal:
                break
        return {"ok": True, "actions": actions, "final_position": list(pos), "traps": traps, "architecture": {"subagents": [x["name"] for x in compiled["subagents"]]}}

    def extract_self_candidate(self, agent_dir):
        bundle = load_bundle(agent_dir)
        module = self._compile(bundle["brain_wat"], "decide")
        store = self.Store(self.engine)
        store.set_limits(memory_size=int(self.w["memory_limit_bytes"]), table_elements=int(self.w["table_elements"]), instances=1, tables=4, memories=2)
        store.set_fuel(int(self.w["fuel_emit_candidate"]))
        try:
            instance = self.Instance(store, module, [])
        except Exception:
            return None
        exports = instance.exports(store)
        try:
            emit, memory = exports["emit_candidate"], exports["memory"]
        except Exception:
            return None
        if not isinstance(memory, self.Memory):
            return None
        try:
            store.set_fuel(int(self.w["fuel_emit_candidate"]))
            desc = int(emit(store))
        except Exception:
            return None
        unsigned = desc & ((1 << 64) - 1)
        pointer = unsigned & 0xFFFFFFFF
        length = (unsigned >> 32) & 0xFFFFFFFF
        max_bytes = int(self.w["max_emitted_candidate_bytes"])
        if length <= 0 or length > max_bytes or pointer + length > memory.data_len(store):
            return None
        raw = bytes(memory.read(store, pointer, pointer + length))
        try:
            proposal = json.loads(raw.decode("utf-8"))
        except Exception:
            return None
        proposal["source"] = "wasm-self-generated"
        try:
            if "main_ir" in proposal:
                compiled = compile_candidate_ir(
                    proposal,
                    self.config,
                    fallback_self_prompt=bundle.get("self_prompt", "")
                )
                compiled["source"] = "wasm-self-generated-ir"
                return normalized_proposal(compiled)
            return normalized_proposal(proposal)
        except (BundleError, IRValidationError):
            return None

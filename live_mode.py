import json, time
from pathlib import Path

ROOT=Path(__file__).resolve().parent
from supervisor.bootstrap import add_local_deps
add_local_deps(ROOT)
from supervisor.storage import ensure_initial_state, read_json
from supervisor.digital_life import ensure_ecology, run_life_cycles, population_view


def load_config():
    return json.loads((ROOT/'config.json').read_text(encoding='utf-8'))


def main():
    config=load_config()
    ensure_initial_state(ROOT)
    state=read_json(ROOT/'state'/'latest.json',{}) or {}
    ensure_ecology(ROOT,config,state)
    cfg=config.get('digital_life',{})
    interval=max(0.0,float(cfg.get('live_mode_interval_seconds',20)))
    batch=max(1,int(cfg.get('live_mode_batch_cycles',1)))
    print('E.L.B.E.R.R. v0.9 LIVE MODE')
    print('Life advances while this window is running. Close it or press Ctrl+C to stop.')
    try:
        while True:
            rows=run_life_cycles(ROOT,config,batch,allow_cognition=True,trigger='continuous live mode')
            st=read_json(ROOT/'state'/'latest.json',{}) or state
            pop=population_view(ROOT,config,st)
            print(f"cycle={pop.get('cycle')} alive={pop.get('alive')} cultures={pop.get('cultures')} primary={pop.get('primary_agent_id')}")
            if interval>0:
                time.sleep(interval)
    except KeyboardInterrupt:
        print('\nLIVE MODE stopped. Persistent state was saved.')

if __name__=='__main__':
    main()

import argparse, json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
from supervisor.bootstrap import add_local_deps
add_local_deps(ROOT)
from supervisor.storage import ensure_initial_state, read_json
from supervisor.digital_life import ensure_ecology, run_life_cycles, population_view, cultures_view


def load_config():
    return json.loads((ROOT/'config.json').read_text(encoding='utf-8'))


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--cycles',type=int,default=10)
    ap.add_argument('--no-cognition',action='store_true')
    args=ap.parse_args()
    config=load_config()
    ensure_initial_state(ROOT)
    state=read_json(ROOT/'state'/'latest.json',{}) or {}
    ensure_ecology(ROOT,config,state)
    rows=run_life_cycles(ROOT,config,args.cycles,allow_cognition=not args.no_cognition,trigger='standalone digital-life runner')
    print(json.dumps(rows[-1] if rows else {},indent=2,ensure_ascii=False))
    print('\nPopulation:')
    print(json.dumps(population_view(ROOT,config,read_json(ROOT/'state'/'latest.json',{}) or state),indent=2,ensure_ascii=False))
    print('\nCultures:')
    print(json.dumps(cultures_view(ROOT,config,state),indent=2,ensure_ascii=False))

if __name__=='__main__':
    main()

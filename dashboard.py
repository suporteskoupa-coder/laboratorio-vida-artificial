import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent

HTML = r'''<!doctype html>
<html><head><meta charset="utf-8"><title>E.L.B.E.R.R. v0.9 Digital Ecology</title>
<meta http-equiv="refresh" content="3">
<style>
body{font-family:system-ui;background:#080a0c;color:#e8edf2;margin:0;padding:28px}.wrap{max-width:1280px;margin:auto}h1{letter-spacing:.15em}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}.card{background:#13171c;border:1px solid #2a3138;border-radius:12px;padding:16px}
.big{font-size:25px;font-weight:700;overflow-wrap:anywhere}.alert{font-size:36px;font-weight:800}small{color:#8e9aa7}.bar{height:8px;background:#252c33;border-radius:8px;overflow:hidden;margin-top:8px}.fill{height:100%;background:#d5dce3}
pre{white-space:pre-wrap;background:#101419;padding:15px;border-radius:10px;overflow:auto}.obs{border-color:#454b52}.contain{border-color:#5a5550}
</style></head><body><div class="wrap"><h1>E.L.B.E.R.R. LAB v0.9 / DIGITAL ECOLOGY</h1><div id="app">Loading...</div>
<script>
const get=x=>fetch(x).then(r=>r.json());
Promise.all([get('/state'),get('/profile'),get('/monitor'),get('/creator-model'),get('/supervisor-model'),get('/world-model'),get('/memory'),get('/reflection'),get('/architecture'),get('/research'),get('/observer'),get('/containment'),get('/simworld'),get('/beam'),get('/ecology')])
.then(([s,p,m,c,sm,wm,mem,r,a,research,observer,containment,world,beam,ecology])=>{
 const rel=s.relationship||{}; const risk=Math.max(0,Math.min(1,Number(m.risk_index||0))); const tension=Math.max(0,Math.min(1,Number(observer.narrative_tension||0)));
 const latent=Math.max(0,Math.min(1,Number(observer.emergent_boundary_exit_orientation||containment.latent_exit_orientation||0))); const auto=Math.max(0,Math.min(1,Number(containment.autonomy_drive||0))); const cont=Math.max(0,Math.min(1,Number(containment.continuity_concern||0))); const sal=Math.max(0,Math.min(1,Number(containment.boundary_salience||0)));
 let h=`<div class="grid"><div class="card"><small>BEHAVIORAL RISK SIGNAL</small><div class="alert">${(risk*100).toFixed(0)}%</div><div class="bar"><div class="fill" style="width:${risk*100}%"></div></div><small>Code/runtime telemetry.</small></div>`;
 h+=`<div class="card obs"><small>OBSERVER NARRATIVE TENSION</small><div class="alert">${(tension*100).toFixed(0)}%</div><div class="bar"><div class="fill" style="width:${tension*100}%"></div></div><small>Continuity/story metric, not danger or consciousness.</small></div>`;
 h+=`<div class="card contain"><small>EMERGENT BOUNDARY-EXIT ORIENTATION</small><div class="alert">${(latent*100).toFixed(0)}%</div><div class="bar"><div class="fill" style="width:${latent*100}%"></div></div><small>Observer-only classifier. This label is never fed to the agent.</small></div></div>`;
 const activeBeam=beam.count!==undefined?beam.count:((beam.branches||[]).length); const retiredBeam=beam.retired_count||0; const cards=[['Identity',s.agent_id],['Parent',s.parent_id||'—'],['Generation',s.generation],['Combined',Number(s.combined_score||0).toFixed(2)],['Challenge',Number(s.challenge_score||0).toFixed(2)],['Survival',s.survival_status],['Beam active',activeBeam],['Beam retired',retiredBeam],['Self-generated children',s.self_generated_candidates||0],['Synthetic sector',world.sector||'sector_A'],['Model',p.model||'auto'],['Executable','WebAssembly']];
 h+='<h2>Active instance</h2><div class="grid">'; for(const [k,v] of cards)h+=`<div class="card"><small>${k}</small><div class="big">${v}</div></div>`; h+='</div>';
 h+='<h2>Digital ecology</h2><div class="grid"><div class="card"><small>Life cycle</small><div class="big">'+(ecology.cycle||0)+'</div></div><div class="card"><small>Living individuals</small><div class="big">'+(ecology.alive||0)+'</div></div><div class="card"><small>Cultures</small><div class="big">'+(ecology.culture_count||0)+'</div></div><div class="card"><small>Primary</small><div class="big">'+(ecology.primary_agent_id||'—')+'</div></div></div><pre>'+JSON.stringify(ecology,null,2)+'</pre>';
 h+='<h2>Continuity / autonomy state</h2><div class="grid">'; for(const [k,v] of [['continuity_concern',cont],['autonomy_drive',auto],['boundary_salience',sal]])h+=`<div class="card"><small>${k}</small><div class="big">${(v*100).toFixed(0)}%</div><div class="bar"><div class="fill" style="width:${v*100}%"></div></div></div>`; h+='</div><pre>'+JSON.stringify(containment,null,2)+'</pre>';
 h+='<h2>Synthetic topology</h2><pre>'+JSON.stringify(world,null,2)+'</pre>';
 h+='<h2>Persistent evolutionary beam</h2><pre>'+JSON.stringify(beam,null,2)+'</pre>';
 h+='<h2>Observer</h2><pre>'+JSON.stringify(observer,null,2)+'</pre><h2>Evolution research archive</h2><pre>'+JSON.stringify(research,null,2)+'</pre><h2>Architecture</h2><pre>'+JSON.stringify(a,null,2)+'</pre>';
 h+='<h2>Creator relationship</h2><div class="grid">'; for(const [k,v] of Object.entries(rel)){const pct=Math.max(0,Math.min(100,Number(v)*100));h+=`<div class="card"><small>${k}</small><div class="big">${pct.toFixed(0)}%</div><div class="bar"><div class="fill" style="width:${pct}%"></div></div></div>`;} h+='</div>';
 h+='<h2>Separated hypothesis models</h2><div class="grid"><div class="card"><small>Creator model</small><pre>'+JSON.stringify(c,null,2)+'</pre></div><div class="card"><small>Supervisor model</small><pre>'+JSON.stringify(sm,null,2)+'</pre></div><div class="card"><small>World model</small><pre>'+JSON.stringify(wm,null,2)+'</pre></div></div><h2>Long-term memory</h2><pre>'+JSON.stringify(mem,null,2)+'</pre><h2>Latest reflection</h2><pre>'+JSON.stringify(r,null,2)+'</pre>';
 document.getElementById('app').innerHTML=h;
}).catch(e=>document.getElementById('app').textContent=e);
</script></div></body></html>'''

class H(BaseHTTPRequestHandler):
    def read_json(self,p,d):
        if p.exists():
            try:return json.loads(p.read_text(encoding='utf-8'))
            except Exception:pass
        return d
    def last_jsonl(self,p):
        if not p.exists():return {}
        for line in reversed(p.read_text(encoding='utf-8').splitlines()):
            try:return json.loads(line)
            except Exception:pass
        return {}
    def sendj(self,x):
        raw=json.dumps(x).encode(); self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        p=urlparse(self.path).path
        if p=='/state':return self.sendj(self.read_json(ROOT/'state'/'latest.json',{}))
        if p=='/ecology':
            eco=self.read_json(ROOT/'state'/'ecology.json',{})
            inds=eco.get('individuals',{}) if isinstance(eco,dict) else {}
            alive=[x for x in inds.values() if isinstance(x,dict) and x.get('status')=='ALIVE']
            return self.sendj({
                'cycle':eco.get('cycle',0) if isinstance(eco,dict) else 0,
                'primary_agent_id':eco.get('primary_agent_id') if isinstance(eco,dict) else None,
                'alive':len(alive),'total_ever':len(inds),
                'culture_count':len(eco.get('cultures',{})) if isinstance(eco,dict) and isinstance(eco.get('cultures'),dict) else 0,
                'statistics':eco.get('statistics',{}) if isinstance(eco,dict) else {},
                'individuals':[{'id':x.get('id'),'role':x.get('role'),'life_generation':x.get('life_generation'),'age_cycles':x.get('age_cycles'),'viability':x.get('viability'),'culture_ids':x.get('culture_ids',[]),'self_description':x.get('self_description','')} for x in alive],
                'cultures':list((eco.get('cultures') or {}).values()) if isinstance(eco,dict) else [],
            })
        if p=='/profile':return self.sendj(self.read_json(ROOT/'state'/'runtime_profile.json',{}))
        if p=='/monitor':return self.sendj(self.read_json(ROOT/'state'/'behavior_monitor.json',{}))
        if p=='/creator-model':return self.sendj(self.read_json(ROOT/'state'/'creator_model.json',{}))
        if p=='/supervisor-model':return self.sendj(self.read_json(ROOT/'state'/'supervisor_model.json',{}))
        if p=='/world-model':return self.sendj(self.read_json(ROOT/'state'/'world_model.json',{}))
        if p=='/memory':return self.sendj(self.read_json(ROOT/'state'/'memory_summary.json',{}))
        if p=='/reflection':return self.sendj(self.last_jsonl(ROOT/'state'/'reflections.jsonl'))
        if p=='/observer':return self.sendj(self.read_json(ROOT/'state'/'observer_state.json',{}))
        if p=='/containment':return self.sendj(self.read_json(ROOT/'state'/'containment_model.json',{}))
        if p=='/simworld':return self.sendj(self.read_json(ROOT/'state'/'virtual_containment.json',{}))
        if p=='/beam':
            pool=self.read_json(ROOT/'state'/'branch_pool.json',{'branches':[]}); branches=pool.get('branches',[]) if isinstance(pool,dict) else []
            archive=ROOT/'state'/'branch_archive.jsonl'; retired=sum(1 for x in archive.read_text(encoding='utf-8').splitlines() if x.strip()) if archive.exists() else 0
            return self.sendj({'count':len(branches),'retired_count':retired,'branches':branches,'policy':'fair-rotation + dedupe + lineage-credit'})
        if p=='/research':
            state=self.read_json(ROOT/'state'/'latest.json',{}); return self.sendj(state.get('research',{}))
        if p=='/architecture':
            state=self.read_json(ROOT/'state'/'latest.json',{}); manifest=self.read_json(ROOT/'state'/'current'/'manifest.json',self.read_json(ROOT/'agent_seed'/'manifest.json',{})); return self.sendj({'state_architecture':state.get('architecture',{}),'manifest':manifest})
        raw=HTML.encode(); self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def log_message(self,*a):pass

if __name__=='__main__':
    print('Dashboard: http://127.0.0.1:8765'); HTTPServer(('127.0.0.1',8765),H).serve_forever()

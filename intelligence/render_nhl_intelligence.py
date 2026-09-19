"""Render the canonical NHL intelligence package into the NCAA-family intelligence.html."""
import argparse, html, json, os, tempfile
from collections import Counter

DOMAINS=["projection_integrity","starting_goalies","lines_and_scratches","power_play","penalty_kill","injuries_and_returns","expected_toi_and_role","rest_travel_schedule","coach_player_media","market","situational"]
LABELS={"projection_integrity":"Projection Integrity","starting_goalies":"Starting Goalies","lines_and_scratches":"Lines / Scratches","power_play":"Power Play","penalty_kill":"Penalty Kill","injuries_and_returns":"Injuries / Returns","expected_toi_and_role":"Expected TOI / Role","rest_travel_schedule":"Rest / Travel","coach_player_media":"Coach / Player / Media","market":"Market","situational":"Situational"}
def e(v): return html.escape("—" if v is None or v=="" else str(v))
def num(v,d=1):
    try:return f"{float(v):.{d}f}"
    except:return "—"
def badge(status):
    s=status or "UNRESOLVED"; c="good" if s in ("CURRENT","CONFIRMED","FROZEN","OK") else "bad" if s in ("CONFLICT","REPROJECTION_REQUIRED","ERROR","CHANGED") else "warn" if s in ("UNRESOLVED","WARNING","EXHAUSTED") else ""
    return f"<span class='badge {c}'>{e(s)}</span>"
def atomic(path,text):
    d=os.path.dirname(os.path.abspath(path));os.makedirs(d,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=".nhl_html_",suffix=".html",dir=d)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f:f.write(text)
        os.replace(tmp,path)
    except Exception:
        try:os.unlink(tmp)
        except OSError:pass
        raise
def load(p):
    with open(p,encoding="utf-8") as f:return json.load(f)
def model_line(g):
    m=g.get("model",{})
    # Current snapshot carries FS/L20/L10; prefer L10 for the board while showing all windows in the card.
    x=m.get("L10") or m.get("L20") or m.get("FS") or m
    return x
def top_intel(g):
    cs=g.get("conflicts",[])
    if cs:return cs[0].get("summary") or cs[0].get("conflict_type","Model conflict")
    fs=g.get("findings",[])
    bad=[x for x in fs if x.get("status") in ("CONFLICT","UNRESOLVED","EXHAUSTED")]
    return (bad[0].get("summary") if bad else (fs[0].get("summary") if fs else "Research pending")) or "Research pending"
def domain_card(domain, findings):
    xs=[x for x in findings if x.get("domain")==domain]
    if not xs:return f"<div class='domain'><b>{e(LABELS[domain])}</b>{badge('NOT RESEARCHED')}<p>Research has not yet been completed for this domain at the current lifecycle gate.</p></div>"
    x=xs[-1]
    return f"<div class='domain'><b>{e(LABELS[domain])}</b>{badge(x.get('status'))}<p>{e(x.get('summary') or 'No material finding recorded.')}</p></div>"
def render(data):
    games=data.get("games",[]); states=Counter(g.get("state","UNRESOLVED") for g in games)
    pipeline=data.get("pipeline",{}); research=data.get("research",{})
    css="""@import url('https://fonts.googleapis.com/css2?family=Roboto+Mono:wght@400;500;600;700&display=swap');*{box-sizing:border-box}body{margin:0;background:#07151a;color:#dce8e9;font:14px 'Roboto Mono',ui-monospace,SFMono-Regular,Consolas,monospace}a{color:#52d7cf;text-decoration:none}.wrap{max-width:1500px;margin:auto;padding:0 18px}header{border-bottom:1px solid #244047;background:#0b1c22}.brand{display:flex;align-items:end;gap:14px;padding-top:18px}.brand h1{margin:0;font-size:25px}.stamp,.note{color:#819ba0;font-size:12px}nav{display:flex;gap:8px;flex-wrap:wrap;padding:14px 0}nav a{padding:7px 10px;border-radius:7px;color:#9db2b6}nav a.on{background:#17343a;color:#52d7cf}main{padding:24px 0 50px}h2{margin-top:30px}.hero,.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px}.hero>div,.grid>div,.domain{background:#0d2228;border:1px solid #244047;border-radius:9px;padding:12px}.hero strong,.metrics strong{font-size:21px;display:block}.hero label,.metrics label{display:block;color:#819ba0;font-size:11px;text-transform:uppercase;letter-spacing:.06em}.badge{display:inline-block;border:1px solid #36545a;border-radius:999px;padding:3px 7px;font-size:10px;font-weight:700;letter-spacing:.04em}.badge.good{border-color:#2e8c78}.badge.warn{border-color:#9c7a32}.badge.bad{border-color:#a84f55}table{width:100%;border-collapse:collapse;background:#0d2228;border:1px solid #244047}th,td{padding:9px;border-bottom:1px solid #1d363c;text-align:left}th{color:#819ba0;font-size:11px;text-transform:uppercase}.scroll{overflow:auto}.game{margin:10px 0;background:#0d2228;border:1px solid #244047;border-radius:9px}.game summary{cursor:pointer;display:flex;justify-content:space-between;gap:15px;padding:14px}.game summary small{display:block;color:#819ba0;margin-top:3px}.game>div,.game>p,.game>h4,.game>ul{margin-left:14px;margin-right:14px}.domains{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:8px}.domain b{margin-right:8px}.domain p{color:#a9bdc0;line-height:1.4}.callout{padding:10px;background:#102a31;border-left:3px solid #52d7cf}.filters{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:0 0 12px}.filters input,.filters select,.filters button{background:#0d2228;color:#dce8e9;border:1px solid #36545a;border-radius:7px;padding:9px 11px;font:inherit}.filters input{min-width:310px;flex:1}.hidden-filter{display:none!important}footer{border-top:1px solid #244047;color:#819ba0;padding:18px 0 40px}@media(max-width:700px){.game summary{flex-direction:column}}"""
    out=[f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><meta name='color-scheme' content='dark'><title>NHL Intelligence</title><style>{css}</style></head><body>"]
    out.append(f"<header><div class='wrap'><div class='brand'><h1>Projections</h1><span class='stamp'>NHL · intelligence built {e(data.get('generated_at'))}</span></div><nav><a href='index.html'>Games</a><a href='ev.html'>Market</a><a href='players.html'>Players</a><a href='tracking.html'>Tracking</a><a href='intelligence.html' class='on'>Intelligence</a><a href='about.html'>About</a></nav></div></header><main><div class='wrap'>")
    out.append("<h2>Pregame Intelligence</h2><p class='note'>Read-only intelligence layer. Google Sheets remains the projection system of record; researched evidence is compared with the frozen model snapshot and never silently overwrites projection values.</p>")
    out.append("<div class='hero'>"+ "".join(f"<div><strong>{states.get(s,0)}</strong><label>{e(s)}</label></div>" for s in ["CURRENT","BASELINE","UNRESOLVED","CONFLICT","REPROJECTION_REQUIRED","FROZEN"]) +"</div>")
    out.append("<h2>Research Engine</h2><div class='hero'>"+f"<div><strong>{research.get('completed',0)}</strong><label>Completed tasks</label></div><div><strong>{research.get('pending',0)}</strong><label>Pending tasks</label></div><div><strong>{research.get('source_count',0)}</strong><label>Sources</label></div><div><strong>0</strong><label>Independent DFO pulls</label></div></div>")
    gate_limits={"EARLY":4,"GAME_DAY":6,"T-90":8,"T-30":10,"PUCK_DROP":0}
    out.append("<div class='grid cap'>"+ "".join(f"<div><label>{e(g)}</label><strong>{n}</strong><small>research domains / game</small></div>" for g,n in gate_limits.items()) +"</div>")
    out.append("<h2>Model / Data Integrity</h2><div class='grid'>")
    for key in ["dfo","nst_full_season","rolling_l20_l10","player_matching","goalie_data","matchup","projections"]:
        x=pipeline.get(key,{})
        out.append(f"<div><label>{e(key.replace('_',' '))}</label><strong>{badge(x.get('status','UNRESOLVED'))}</strong><small class='note'>{e(x.get('detail',''))}</small></div>")
    out.append("</div>")
    out.append("<h2>Game Intelligence Board</h2><div class='filters'><input id='gameSearch' type='search' placeholder='Search team, state, gate, goalie, or intelligence…'><select id='stateFilter'><option value=''>All states</option>"+ "".join(f"<option>{s}</option>" for s in ["BASELINE","CURRENT","UNRESOLVED","CONFLICT","REPROJECTION_REQUIRED","FROZEN"]) +"</select><select id='gateFilter'><option value=''>All gates</option>"+ "".join(f"<option>{s}</option>" for s in ["EARLY","GAME_DAY","T-90","T-30","PUCK_DROP"]) +"</select><button id='clearFilters'>Clear</button><span id='matchCount'></span></div><div class='scroll'><table id='intelBoard'><thead><tr><th>Game</th><th>Puck Drop</th><th>Gate</th><th>Model</th><th>Goalies</th><th>Lineup</th><th>PP/PK</th><th>State</th><th>Intelligence</th></tr></thead><tbody>")
    for g in games:
        m=model_line(g); gi=f"{g.get('away')} @ {g.get('home')}"; intel=top_intel(g)
        goalie=f"{g.get('goalies',{}).get('away',{}).get('status','UNKNOWN')} / {g.get('goalies',{}).get('home',{}).get('status','UNKNOWN')}"
        search=e((gi+" "+g.get("state","")+" "+g.get("gate","")+" "+goalie+" "+intel).lower())
        out.append(f"<tr data-search='{search}' data-state='{e(g.get('state'))}' data-gate='{e(g.get('gate'))}'><td><a class='gamejump' href='#game-{e(g.get('game_id'))}'>{e(gi)}</a></td><td>{e(g.get('puck_drop') or g.get('date'))}</td><td>{badge(g.get('gate'))}</td><td>{num(m.get('away_goals'))}–{num(m.get('home_goals'))}</td><td>{e(goalie)}</td><td>{badge(g.get('lineup_status'))}</td><td>{badge(g.get('special_teams_status'))}</td><td>{badge(g.get('state'))}</td><td>{e(intel)}</td></tr>")
    out.append("</tbody></table></div><h2>Game Intelligence Cards</h2>")
    for g in games:
        gi=f"{g.get('away')} @ {g.get('home')}"; intel=top_intel(g); findings=g.get("findings",[]); m=model_line(g)
        search=e((gi+" "+g.get("state","")+" "+g.get("gate","")+" "+intel).lower())
        out.append(f"<details class='game' id='game-{e(g.get('game_id'))}' data-search='{search}' data-state='{e(g.get('state'))}' data-gate='{e(g.get('gate'))}'><summary><span><b>{e(g.get('away'))}</b> @ <b>{e(g.get('home'))}</b><small>{e(g.get('puck_drop') or g.get('date'))}</small></span><span>{badge(g.get('gate'))} {badge(g.get('state'))}</span></summary>")
        out.append("<div class='grid metrics'>")
        out.append(f"<div><label>Model L10</label><strong>{num(m.get('away_goals'))}–{num(m.get('home_goals'))}</strong></div><div><label>Total</label><strong>{num(m.get('total'))}</strong></div>")
        for side in ("away","home"):
            x=g.get("goalies",{}).get(side,{})
            out.append(f"<div><label>{side} goalie</label><strong>{e(x.get('observed_name') or x.get('model_name'))}</strong><small>{e(x.get('status'))}</small></div>")
        out.append(f"<div><label>Lineup</label><strong>{e(g.get('lineup_status'))}</strong></div><div><label>PP / PK</label><strong>{e(g.get('special_teams_status'))}</strong></div></div>")
        out.append(f"<p class='callout'><b>Current intelligence:</b> {e(intel)}</p><div class='domains'>")
        for d in DOMAINS:out.append(domain_card(d,findings))
        out.append("</div><h4>Model conflicts</h4><ul>")
        cs=g.get("conflicts",[])
        out.extend(f"<li>{e(c.get('conflict_type','CONFLICT'))} · {e(c.get('severity'))} · {e(c.get('summary'))}</li>" for c in cs)
        if not cs:out.append("<li>None</li>")
        out.append("</ul><h4>Sources</h4><ul>")
        src=g.get("sources",[]);out.extend(f"<li>{e(x)}</li>" for x in src)
        if not src:out.append("<li>None recorded</li>")
        out.append("</ul></details>")
    out.append("</div></main><footer><div class='wrap'>Pregame intelligence is contextual model-audit output, not a replacement for the underlying projection.</div></footer>")
    out.append("""<script>(function(){const q=document.getElementById('gameSearch'),sf=document.getElementById('stateFilter'),gf=document.getElementById('gateFilter'),cl=document.getElementById('clearFilters'),ct=document.getElementById('matchCount');const rows=[...document.querySelectorAll('#intelBoard tbody tr')],cards=[...document.querySelectorAll('details.game')];function apply(){const term=(q.value||'').trim().toLowerCase(),state=sf.value,gate=gf.value;let n=0;rows.forEach(r=>{const ok=(!term||r.dataset.search.includes(term))&&(!state||r.dataset.state===state)&&(!gate||r.dataset.gate===gate);r.classList.toggle('hidden-filter',!ok);if(ok)n++;});cards.forEach(c=>{const ok=(!term||c.dataset.search.includes(term))&&(!state||c.dataset.state===state)&&(!gate||c.dataset.gate===gate);c.classList.toggle('hidden-filter',!ok)});ct.textContent=n+' game'+(n===1?'':'s')}[q,sf,gf].forEach(x=>x.addEventListener(x===q?'input':'change',apply));cl.addEventListener('click',()=>{q.value='';sf.value='';gf.value='';apply()});document.querySelectorAll('a.gamejump').forEach(a=>a.addEventListener('click',()=>{const c=document.querySelector(a.getAttribute('href'));if(c){c.classList.remove('hidden-filter');c.open=true;setTimeout(()=>c.scrollIntoView({behavior:'smooth',block:'start'}),0)}}));apply()})();</script></body></html>""")
    return "".join(out)
def main():
    ap=argparse.ArgumentParser();ap.add_argument("--input",default="intelligence/current/nhl_intelligence.json");ap.add_argument("--out","--output",dest="out",default="intelligence.html");args=ap.parse_args()
    data=load(args.input); atomic(args.out,render(data)); print(f"Wrote {args.out}: {len(data.get('games',[]))} games")
if __name__=="__main__":main()

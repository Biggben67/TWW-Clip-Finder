#!/usr/bin/env python3
"""tww_sim/swim/_viz.py - self-contained animated trajectory viewer for the swim sim.

Split out of ``sim.py`` (the bulky HTML/JS emitter is its own topic, off the bit-exact path).
``emit_viz`` writes a standalone HTML page from a list of traces; re-exported through ``sim`` so
``from tww_sim.swim import sim as S`` callers keep ``S.emit_viz`` working.
"""
import json


def emit_viz(path_html, traces):
    """traces: list of {name,color,rows}. Writes a self-contained animated viewer."""
    payload = json.dumps([{"name": t["name"], "color": t["color"],
                           "rows": [{k: r[k] for k in ("x", "z", "v", "anim", "air", "step", "tag", "eff")}
                                    for r in t["rows"]]} for t in traces])
    html = _VIZ_TEMPLATE.replace("__DATA__", payload)
    with open(path_html, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"wrote {path_html}")

_VIZ_TEMPLATE = r"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>superswim</title>
<style>
 body{margin:0;background:#0d1117;color:#c9d1d9;font:13px system-ui,sans-serif}
 #wrap{display:flex;flex-direction:column;height:100vh}
 #top{flex:1;position:relative}
 canvas{position:absolute;inset:0;width:100%;height:100%}
 #hud{padding:8px 12px;background:#161b22;border-top:1px solid #30363d}
 .row{display:flex;gap:18px;align-items:center;flex-wrap:wrap}
 .gauge{min-width:120px}
 .bar{height:8px;background:#21262d;border-radius:4px;overflow:hidden;margin-top:3px}
 .bar>div{height:100%}
 button{background:#21262d;color:#c9d1d9;border:1px solid #30363d;border-radius:6px;padding:4px 10px;cursor:pointer}
 .leg{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px}
 input[type=range]{vertical-align:middle}
</style></head>
<body><div id="wrap">
 <div id="top"><canvas id="c"></canvas></div>
 <div id="hud">
   <div class="row">
     <button id="play">⏸ pause</button>
     <input id="scrub" type="range" min="0" max="100" value="0" style="flex:1">
     <span id="fnum">f 0</span>
     <label>speed <select id="rate"><option>0.5</option><option selected>1</option><option>2</option><option>4</option></select>×</label>
   </div>
   <div class="row" id="gauges"></div>
   <div class="row" id="legend"></div>
 </div>
</div>
<script>
const DATA = __DATA__;
const c = document.getElementById('c'), ctx = c.getContext('2d');
const N = Math.max(...DATA.map(t=>t.rows.length));
// world bounds across all traces
let minX=1e18,maxX=-1e18,minZ=1e18,maxZ=-1e18;
for(const t of DATA) for(const r of t.rows){minX=Math.min(minX,r.x);maxX=Math.max(maxX,r.x);minZ=Math.min(minZ,r.z);maxZ=Math.max(maxZ,r.z);}
let frame=0, playing=true, t0=null;
function resize(){c.width=c.clientWidth*devicePixelRatio;c.height=c.clientHeight*devicePixelRatio;}
window.addEventListener('resize',resize);resize();
function tf(x,z){ // world -> screen, fit with margin, keep aspect
  const W=c.width,H=c.height,m=40*devicePixelRatio;
  const sx=(W-2*m)/((maxX-minX)||1), sz=(H-2*m)/((maxZ-minZ)||1), s=Math.min(sx,sz);
  return [m+(x-minX)*s + (W-2*m-(maxX-minX)*s)/2, m+(z-minZ)*s + (H-2*m-(maxZ-minZ)*s)/2];
}
function draw(){
  ctx.clearRect(0,0,c.width,c.height);
  for(const t of DATA){
    const rows=t.rows, upto=Math.min(frame,rows.length-1);
    // trail
    ctx.lineWidth=2*devicePixelRatio;ctx.strokeStyle=t.color;ctx.globalAlpha=0.55;ctx.beginPath();
    for(let i=0;i<=upto;i++){const[px,py]=tf(rows[i].x,rows[i].z);i?ctx.lineTo(px,py):ctx.moveTo(px,py);}
    ctx.stroke();ctx.globalAlpha=1;
    // boost markers
    for(let i=0;i<=upto;i++) if(rows[i].tag==='CHG'){const[px,py]=tf(rows[i].x,rows[i].z);
      ctx.fillStyle='#f0883e';ctx.beginPath();ctx.arc(px,py,3*devicePixelRatio,0,7);ctx.fill();}
    // head
    if(upto>=0){const[hx,hy]=tf(rows[upto].x,rows[upto].z);
      ctx.fillStyle=t.color;ctx.beginPath();ctx.arc(hx,hy,6*devicePixelRatio,0,7);ctx.fill();
      ctx.fillStyle='#fff';ctx.beginPath();ctx.arc(hx,hy,2*devicePixelRatio,0,7);ctx.fill();}
  }
  // gauges + legend
  const g=document.getElementById('gauges');g.innerHTML='';
  for(const t of DATA){const r=t.rows[Math.min(frame,t.rows.length-1)];
    g.innerHTML+=`<div class="gauge"><b style="color:${t.color}">${t.name}</b><br>`+
      `v ${r.v.toFixed(1)} &nbsp; anim ${r.anim.toFixed(2)} &nbsp; air ${r.air}<br>`+
      `eff ${(r.eff*100).toFixed(1)}% step ${r.step.toFixed(0)}`+
      `<div class="bar"><div style="width:${((r.eff-0.6)/0.4*100).toFixed(0)}%;background:${t.color}"></div></div></div>`;}
  const lg=document.getElementById('legend');
  lg.innerHTML=DATA.map(t=>`<span><span class="leg" style="background:${t.color}"></span>${t.name}</span>`).join(' &nbsp; ')+
    ` &nbsp; <span><span class="leg" style="background:#f0883e"></span>boost frame</span>`;
  document.getElementById('fnum').textContent='f '+frame;
  document.getElementById('scrub').value=(frame/(N-1)*100)||0;
}
function tick(ts){
  if(t0===null)t0=ts;
  if(playing){const rate=parseFloat(document.getElementById('rate').value);
    const fps=30*rate; frame=Math.min(N-1,Math.floor((ts-t0)/1000*fps));
    if(frame>=N-1){playing=false;document.getElementById('play').textContent='↻ replay';}}
  draw();requestAnimationFrame(tick);
}
document.getElementById('play').onclick=()=>{
  if(frame>=N-1){frame=0;t0=null;}
  playing=!playing;document.getElementById('play').textContent=playing?'⏸ pause':'▶ play';
  if(playing)t0=null;
};
document.getElementById('scrub').oninput=e=>{playing=false;frame=Math.round(e.target.value/100*(N-1));
  document.getElementById('play').textContent='▶ play';draw();};
requestAnimationFrame(tick);
</script></body></html>"""

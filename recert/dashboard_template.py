"""HTML/CSS/JS template of the one-page dashboard (self-contained, works offline)."""

from __future__ import annotations



DASH_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{TITLE}}</title>
<style>
:root{
  color-scheme: light;
  --page:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
  --grid:#e1e0d9; --axis:#c3c2b7; --ring:rgba(11,11,11,0.10);
  --c-hh:#2a78d6; --c-remain:#2a78d6; --c-exit:#eb6834; --c-new:#1baf7a; --c-check:#eda100;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    color-scheme: dark;
    --page:#0d0d0d; --surface:#1a1a19; --ink:#ffffff; --ink2:#c3c2b7; --muted:#898781;
    --grid:#2c2c2a; --axis:#383835; --ring:rgba(255,255,255,0.10);
    --c-hh:#3987e5; --c-remain:#3987e5; --c-exit:#d95926; --c-new:#199e70; --c-check:#c98500;
  }
}
:root[data-theme="dark"]{
    color-scheme: dark;
    --page:#0d0d0d; --surface:#1a1a19; --ink:#ffffff; --ink2:#c3c2b7; --muted:#898781;
    --grid:#2c2c2a; --axis:#383835; --ring:rgba(255,255,255,0.10);
    --c-hh:#3987e5; --c-remain:#3987e5; --c-exit:#d95926; --c-new:#199e70; --c-check:#c98500;
}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:1240px;margin:0 auto;padding:28px 16px 60px}
header{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap;margin-bottom:20px}
h1{font-size:26px;margin:0 0 4px}
h2{font-size:18px;margin:0 0 4px}
.sub{color:var(--ink2)}
.btn{background:var(--surface);color:var(--ink);border:1px solid var(--ring);border-radius:8px;padding:6px 12px;cursor:pointer;font:inherit}
.grp{font-size:15px;color:var(--ink2);margin:8px 0 10px;font-weight:600}
.kpis{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:14px;margin-bottom:18px}
.kpi{background:var(--surface);border:1px solid var(--ring);border-radius:12px;padding:16px 18px}
.kpi-l{color:var(--ink2);font-size:14px}
.kpi-v{font-size:32px;font-weight:700;margin:4px 0}
.kpi-s{color:var(--muted);font-size:13px}
.kpi.k-remain{border-left:4px solid var(--c-remain)}
.kpi.k-exit{border-left:4px solid var(--c-exit)}
.kpi.k-new{border-left:4px solid var(--c-new)}
.kpi.k-flag{border-left:4px solid var(--c-check)}
.chart.solo{max-width:820px}
.card{background:var(--surface);border:1px solid var(--ring);border-radius:12px;padding:22px 24px;margin-bottom:18px}
.card p.desc{color:var(--ink2);margin:0 0 16px}
.findings{margin:0;padding-left:20px}.findings li{margin:6px 0}
.split{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1fr);gap:28px;align-items:start}
svg text{font-family:inherit}
.lbl{fill:var(--ink2);font-size:14px}
.val{fill:var(--ink);font-size:14px;font-weight:600;font-variant-numeric:tabular-nums}
.share{fill:var(--muted);font-weight:400}
line.axis{stroke:var(--axis);stroke-width:1}
.mark{outline:none;transition:opacity .12s}.mark:hover,.mark:focus{opacity:.8}
.tbl{border-collapse:collapse;width:100%;font-size:14px}
.tbl th,.tbl td{padding:8px 10px;border-bottom:1px solid var(--grid);text-align:left;vertical-align:top}
.tbl.compact{font-size:12.5px}.tbl.compact th,.tbl.compact td{padding:7px 5px}
.tbl th{color:var(--ink2);font-weight:600;background:var(--surface);position:sticky;top:0}
.tbl th.num,.tbl td.num{text-align:right;font-variant-numeric:tabular-nums}
.tbl tbody tr:last-child td{border-bottom:none}
.sortable th{cursor:pointer}.sortable th:hover{color:var(--ink)}
.scroll{max-height:420px;overflow:auto}
#tip{position:fixed;pointer-events:none;background:var(--ink);color:var(--surface);padding:6px 9px;border-radius:6px;
     font-size:13px;max-width:320px;opacity:0;transition:opacity .08s;z-index:9}
footer{color:var(--muted);font-size:13px;margin-top:8px}
@media (max-width:860px){.split{grid-template-columns:1fr}.kpi-v{font-size:26px}}
@media print{.btn{display:none}.card{break-inside:avoid}}
</style>
</head>
<body>
<div class="wrap">
<header>
  <div>
    <h1>Social Assistance Recertification Analysis · {{COUNCIL}}</h1>
    <div class="sub">{{DISTRICT}} · prepared {{RUNDATE}}</div>
  </div>
  <button class="btn" id="theme">Light / dark</button>
</header>

{{KPIS}}

<section class="card">
  <h2>Key findings</h2>
  <ul class="findings">{{FINDINGS}}</ul>
</section>

{{CARDS}}

<footer>Eligibility uses the updated community-based classification (CBC). CGP: current household members aged 0–17 in
Poor or Ultra-Poor households. PA: Poor or Ultra-Poor households with no member aged 0–17. OVC-B: current household
members aged 12–17 in Poor or Ultra-Poor households. Full lists are in the Excel workbook saved with this page.</footer>
</div>
<div id="tip" role="tooltip"></div>
<script>
(function(){
  var tip=document.getElementById('tip');
  function move(e,el){var x,y;if(e&&e.clientX!==undefined){x=e.clientX;y=e.clientY}else{var r=el.getBoundingClientRect();x=r.left+r.width/2;y=r.top}
    tip.style.left=Math.min(window.innerWidth-tip.offsetWidth-8,x+12)+'px';tip.style.top=(y-36)+'px'}
  document.querySelectorAll('[data-tip]').forEach(function(el){
    function show(e){tip.textContent=el.getAttribute('data-tip');tip.style.opacity=1;move(e,el)}
    el.addEventListener('mouseenter',show);el.addEventListener('focus',function(){show(null)});
    el.addEventListener('mousemove',function(e){move(e,el)});
    el.addEventListener('mouseleave',function(){tip.style.opacity=0});el.addEventListener('blur',function(){tip.style.opacity=0});
  });
  var root=document.documentElement;
  try{var t=localStorage.getItem('cgp-theme');if(t)root.setAttribute('data-theme',t)}catch(e){}
  document.getElementById('theme').addEventListener('click',function(){
    var cur=root.getAttribute('data-theme');var dark=cur?cur==='dark':matchMedia('(prefers-color-scheme: dark)').matches;
    var n=dark?'light':'dark';root.setAttribute('data-theme',n);try{localStorage.setItem('cgp-theme',n)}catch(e){}
  });
  document.querySelectorAll('table.sortable').forEach(function(tb){
    tb.querySelectorAll('th').forEach(function(th,i){var asc=false;th.addEventListener('click',function(){
      var rows=[].slice.call(tb.tBodies[0].rows);asc=!asc;
      rows.sort(function(a,b){var x=a.cells[i].textContent.replace(/,/g,''),y=b.cells[i].textContent.replace(/,/g,'');
        var nx=parseFloat(x),ny=parseFloat(y);var c=(!isNaN(nx)&&!isNaN(ny))?nx-ny:x.localeCompare(y);return asc?c:-c});
      rows.forEach(function(r){tb.tBodies[0].appendChild(r)});});});
  });
})();
</script>
</body>
</html>
"""

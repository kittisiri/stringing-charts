// Bench page: shows one precomputed cell from data/<id>.json. No stringing rules live here.
const ALPHAS = ["0.20", "0.35", "0.50"], MIN = 40, MAX = 55, KEY = "stringing-charts";
const $ = id => document.getElementById(id);
const f1 = x => x.toFixed(1).replace(/\.0$/, ""), f2 = x => x.toFixed(2);

let rackets = [], data = {};
let st = { r: null, tm: 52, tc: 52, am: "0.35", ac: "0.35", hi: null };
try { Object.assign(st, JSON.parse(localStorage.getItem(KEY) || "{}")); } catch (e) {}
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(st)); } catch (e) {} };

function seg(el, opts, get, set, label) {
  el.innerHTML = "";
  for (const o of opts) {
    const b = document.createElement("button");
    b.innerHTML = label(o);
    b.setAttribute("aria-pressed", get() === o);
    b.onclick = () => { set(o); render(); };
    el.appendChild(b);
  }
}

// Mains centre → edge. Crosses top → throat; neighbours in the same band with the same dial
// merge into one row, comp strings always stand alone.
function rows(D, cell) {
  const comp = D.layout.comp, band = {};
  for (const b of D.layout.cross_bands) for (const s of b.strings) band[s] = b.band;
  const mk = Object.keys(cell.m);
  const M = mk.map(k => ({ id: k, lab: k, t: cell.m[k], d: cell.mm[k], comp: comp[k] || 0,
    band: k === "M1" ? "centre" : k === mk.at(-1) ? "tie-off" : "" }));
  const C = [];
  for (const k of Object.keys(cell.c).reverse()) {
    const last = C.at(-1), cp = comp[k] || 0;
    if (last && !cp && !last.comp && last.band === band[k] && last.d === cell.cm[k]) { last.keys.push(k); continue; }
    C.push({ keys: [k], t: cell.c[k], d: cell.cm[k], comp: cp, band: band[k] });
  }
  for (const r of C) { r.id = r.keys[0]; r.lab = r.keys.length > 1 ? r.keys[0] + "–" + r.keys.at(-1).slice(1) : r.keys[0]; }
  C[0].band += " · start";
  C.at(-1).band += " · tie-off";
  return { M, C };
}

const table = (title, sub, R) => `<div class="card"><h2>${title}<small>${sub}</small></h2><table>
  <thead><tr><th>String</th><th>Dial</th><th class="t">Target</th></tr></thead><tbody>${R.map(r =>
  `<tr class="row${r.comp ? " comp" : ""}${st.hi === r.id ? " on" : ""}" data-id="${r.id}">
  <td class="s">${r.lab}${r.comp ? ` <span class="chip">+${r.comp}</span>` : ""}<span class="band">${r.band || "&nbsp;"}</span></td>
  <td class="d">${f1(r.d)}</td><td class="t">${f1(r.t)}</td></tr>`).join("")}</tbody></table></div>`;

async function load(id) {
  if (!data[id]) {
    const res = await fetch(`data/${id}.json`);
    if (!res.ok) throw new Error(`data/${id}.json: ${res.status}`);
    data[id] = await res.json();
  }
  return data[id];
}

async function render() {
  seg($("racket"), rackets.map(r => r.id), () => st.r, x => { if (x !== st.r) st.hi = null; st.r = x; },
    x => rackets.find(r => r.id === x).name);
  seg($("am"), ALPHAS, () => st.am, x => st.am = x, x => `<span class="a">α</span>${x}`);
  seg($("ac"), ALPHAS, () => st.ac, x => st.ac = x, x => `<span class="a">α</span>${x}`);
  for (const k of ["tm", "tc"]) {
    $(k).innerHTML = st[k] + "<small>lb</small>";
    $(k + "-").disabled = st[k] <= MIN;
    $(k + "+").disabled = st[k] >= MAX;
  }
  save();
  let D;
  try { D = await load(st.r); }
  catch (e) { $("out").innerHTML = `<p class="msg">Could not load chart data (${e.message}).</p>`; $("sum").innerHTML = ""; return; }
  if (D.racket.id !== st.r) return;  // a newer render picked another racket meanwhile
  const cell = D.cells[`${st.tm}-${st.tc}-${st.am}-${st.ac}`], R = rows(D, cell);
  $("sum").innerHTML = `<span>Avg <b>${f2(cell.avg[0])}</b> / <b>${f2(cell.avg[1])}</b></span>
    <span>mains α <b>${st.am}</b> design · <b>${f2(cell.alpha[0])}</b> true</span>
    <span>crosses α <b>${st.ac}</b> design · <b>${f2(cell.alpha[1])}</b> true</span>
    <span><span class="chip">+3</span> <span class="chip">+6</span> already in Dial</span>`;
  $("out").innerHTML = table("Mains", "M1 centre → edge · each side", R.M) + table("Crosses", "top → throat", R.C);
  for (const tr of document.querySelectorAll("tr.row"))
    tr.onclick = () => { st.hi = st.hi === tr.dataset.id ? null : tr.dataset.id; render(); };
}

for (const k of ["tm", "tc"]) for (const d of ["-", "+"])
  $(k + d).onclick = () => { st[k] = Math.min(MAX, Math.max(MIN, st[k] + (d === "+" ? 1 : -1))); render(); };

async function wake() { try { await navigator.wakeLock?.request("screen"); } catch (e) {} }
document.addEventListener("visibilitychange", () => document.visibilityState === "visible" && wake());

(async () => {
  try { rackets = (await (await fetch("rackets.json")).json()).rackets; }
  catch (e) { $("out").innerHTML = `<p class="msg">Could not load rackets.json.</p>`; return; }
  // Drop a remembered choice that no longer exists.
  if (!rackets.some(r => r.id === st.r)) { st.r = rackets[0].id; st.hi = null; }
  for (const k of ["tm", "tc"]) if (!(Number.isInteger(st[k]) && st[k] >= MIN && st[k] <= MAX)) st[k] = 52;
  for (const k of ["am", "ac"]) if (!ALPHAS.includes(st[k])) st[k] = "0.35";
  wake();
  render();
})();

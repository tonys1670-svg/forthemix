/* ForTheMix — v3 front end. Vanilla JS, no framework, fetch against /api/*. */
"use strict";

const S = {
  status: {}, settings: {},
  theme: "dark", density: "comfortable",
  pane: "library",
  query: "", crate: "all", sortBy: "title", sortDir: "asc", page: 0, total: 0,
  tracks: {}, pageRows: [],
  mix: [], transitions: [], health: {},
  devices: [], player: { id: null }, editing: null,
  statusTimer: null, analysisTimer: null, filterTimer: null,
};

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const pageSize = () => (S.density === "compact" ? 40 : 22);

async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!res.ok) { let d = res.statusText; try { d = (await res.json()).detail || d; } catch (e) {} throw new Error(d); }
  const ct = res.headers.get("content-type") || "";
  return ct.includes("application/json") ? res.json() : res;
}
function toast(msg) { const t = $("#toast"); t.textContent = msg; t.classList.remove("hidden"); clearTimeout(t._t); t._t = setTimeout(() => t.classList.add("hidden"), 2600); }
function fmtTime(s) { if (s == null) return "–"; s = Math.round(s); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; }

/* ------------------------- theme / density ------------------------- */
function applyTheme() {
  document.documentElement.setAttribute("data-theme", S.theme);
  $("#btn-theme").textContent = S.theme === "dark" ? "◐ Light" : "◑ Dark";
}
function applyDensity() {
  document.body.classList.toggle("compact", S.density === "compact");
  $("#btn-density").textContent = S.density === "compact" ? "▤ Compact" : "▥ Comfortable";
}
$("#btn-theme").addEventListener("click", async () => {
  S.theme = S.theme === "dark" ? "light" : "dark"; applyTheme();
  api("/api/settings", { method: "POST", body: JSON.stringify({ theme: S.theme }) }).catch(() => {});
});
$("#btn-density").addEventListener("click", async () => {
  S.density = S.density === "compact" ? "comfortable" : "compact"; applyDensity();
  S.page = 0; if (isDesktop()) loadLibrary();
  api("/api/settings", { method: "POST", body: JSON.stringify({ density: S.density }) }).catch(() => {});
});

/* ------------------------- state routing ------------------------- */
function isDesktop() { return $("#state-desktop").classList.contains("on"); }
function showState(name) {
  $$(".state").forEach((s) => s.classList.remove("on"));
  $("#state-" + name).classList.add("on");
}
function deriveState() {
  const s = S.status;
  if (!s.drive_connected || !s.drive_folder_id) return showFirstRun();
  if (s.analysis && s.analysis.running) return showAnalysing();
  return showDesktop();
}

/* ------------------------- header status ------------------------- */
async function refreshStatus() {
  try { S.status = await api("/api/status"); } catch (e) { return; }
  // fold in analysis status (running?) for state derivation
  try { S.status.analysis = await api("/api/analyze/status"); } catch (e) { S.status.analysis = { running: false }; }
  const s = S.status;
  $("#pill-drive").className = "pill " + (s.drive_connected ? "on" : "");
  $("#pill-ai").className = "pill " + (s.has_anthropic_key ? "on" : "");
  $("#track-count").textContent = (s.track_count || 0) + " tracks";
}

/* ============================ FIRST RUN ============================ */
async function showFirstRun() {
  showState("firstrun");
  const s = S.status;
  $("#step-drive").classList.toggle("done", !!s.drive_connected);
  $("#fr-connect").classList.toggle("hidden", !!s.drive_connected);
  $("#fr-disconnect").classList.toggle("hidden", !s.drive_connected);
  $("#step-folder").classList.toggle("done", !!s.drive_folder_id);
}
$("#fr-connect").addEventListener("click", async () => {
  toast("Opening Google sign-in…");
  try { await api("/api/drive/connect", { method: "POST" }); await refreshStatus(); showFirstRun(); toast("Drive connected"); }
  catch (e) { toast(e.message); }
});
$("#fr-disconnect").addEventListener("click", async () => { await api("/api/drive/disconnect", { method: "POST" }); await refreshStatus(); showFirstRun(); });
$("#fr-folder-search").addEventListener("input", (e) => {
  clearTimeout(S.filterTimer);
  const name = e.target.value.trim();
  S.filterTimer = setTimeout(async () => {
    if (!name) return;
    try {
      const data = await api("/api/drive/search?name=" + encodeURIComponent(name));
      const list = $("#fr-folder-list");
      list.classList.remove("hidden");
      list.innerHTML = data.folders.length
        ? data.folders.map((f) => `<div class="folder-row" data-fid="${f.id}" data-fname="${esc(f.name)}"><span class="fname">${esc(f.name)}</span><span class="fcount">folder</span></div>`).join("")
        : '<div class="folder-row"><span class="fcount">No folders found</span></div>';
    } catch (err) { toast(err.message); }
  }, 350);
});
$("#fr-folder-list").addEventListener("click", async (e) => {
  const row = e.target.closest(".folder-row[data-fid]"); if (!row) return;
  try {
    await api("/api/drive/select-folder", { method: "POST", body: JSON.stringify({ id: row.dataset.fid, name: row.dataset.fname }) });
    $$("#fr-folder-list .folder-row").forEach((x) => x.classList.remove("sel"));
    row.classList.add("sel");
    await refreshStatus(); $("#step-folder").classList.add("done");
    toast("Folder selected: " + row.dataset.fname);
  } catch (err) { toast(err.message); }
});
$("#fr-analyse").addEventListener("click", startAnalysis);

/* ============================ ANALYSING ============================ */
async function startAnalysis() {
  try { await api("/api/analyze", { method: "POST" }); toast("Analysis started"); showAnalysing(); }
  catch (e) { toast(e.message); }
}
function showAnalysing() {
  showState("analysing");
  pollAnalysis();
}
function pollAnalysis() {
  clearInterval(S.analysisTimer);
  const tick = async () => {
    let st; try { st = await api("/api/analyze/status"); } catch (e) { return; }
    const pct = st.total ? Math.round((st.done / st.total) * 100) : 0;
    $("#an-pct").textContent = pct + "%";
    $("#an-fill").style.width = pct + "%";
    const eta = st.eta_seconds ? ` · ~${Math.ceil(st.eta_seconds / 60)} min remaining` : "";
    $("#an-sub").textContent = st.paused ? "Paused" : `${st.done} of ${st.total} analysed${eta}`;
    $("#an-pause").textContent = st.paused ? "▶ Resume" : "❙❙ Pause";
    $("#an-feed").innerHTML = (st.recent || []).map((r) => {
      const cls = (r.status === "cached" || r.status === "analysed") ? "great" : (r.status === "tags_only" ? "" : "ok");
      return `<div class="frow"><span class="fdot ${cls}"></span><span class="ftitle">${esc(r.name)}</span><span class="fkey">${esc(r.key_camelot || "")}</span><span class="fbpm">${r.bpm ? Math.round(r.bpm) : ""}</span><span class="fstatus">${esc(r.status || "")}</span></div>`;
    }).join("");
    if (!st.running) { clearInterval(S.analysisTimer); await refreshStatus(); showDesktop(); toast("Analysis complete"); }
  };
  tick();
  S.analysisTimer = setInterval(tick, 900);
}
$("#an-pause").addEventListener("click", async () => {
  const st = await api("/api/analyze/status");
  await api(st.paused ? "/api/analyze/resume" : "/api/analyze/pause", { method: "POST" });
});
$("#an-skip").addEventListener("click", () => { clearInterval(S.analysisTimer); showDesktop(); });

/* ============================ DESKTOP ============================ */
async function showDesktop() {
  showState("desktop");
  await ensureMixLoaded();
  await rescore();
  applyDensity();
  await Promise.all([loadLibrary(), loadHealth()]);
  renderMetrics(); renderArc();
  setPane(S.pane);
}

async function ensureMixLoaded() {
  try { const m = await api("/api/mix"); S.mix = m.track_ids || []; } catch (e) { S.mix = []; }
  await hydrate(S.mix);
}
async function hydrate(ids) {
  const missing = ids.filter((id) => !S.tracks[id]);
  await Promise.all(missing.map(async (id) => { try { S.tracks[id] = await api("/api/tracks/" + id); } catch (e) {} }));
}

/* ---- panes ---- */
$$(".tab[data-pane]").forEach((b) => b.addEventListener("click", () => setPane(b.dataset.pane)));
function setPane(name) {
  S.pane = name;
  $$(".tab[data-pane]").forEach((b) => b.classList.toggle("on", b.dataset.pane === name));
  $("#pane-library").classList.toggle("hidden", name !== "library");
  $("#pane-set").classList.toggle("hidden", name !== "set");
  if (name === "set") renderSet();
}

/* ---- metrics strip ---- */
function renderMetrics() {
  const mix = S.mix.map((id) => S.tracks[id]).filter(Boolean);
  const mins = Math.round(mix.reduce((a, t) => a + (t.duration || 0), 0) / 60);
  const meanFit = S.transitions.length ? Math.round(S.transitions.reduce((a, c) => a + c.score, 0) / S.transitions.length) : 0;
  const tol = S.status.target_bpm_tolerance || (S.settings.target_bpm_tolerance) || 6;
  $("#metrics").textContent = `${mix.length} tracks · ${mins} min · Mean fit ${meanFit}/100 · Tolerance ±${tol} bpm`;
  $("#set-count").textContent = S.mix.length;
}

/* ---- energy arc ---- */
function renderArc() {
  const mix = S.mix.map((id) => S.tracks[id]).filter(Boolean);
  $("#arc-bars").innerHTML = mix.map((t) => {
    const e = t.energy || 0; const cls = e <= 4 ? "" : (e <= 7 ? "mid" : "hot");
    return `<div class="bar ${cls}" style="height:${Math.max(6, e / 10 * 78)}px" title="${esc(t.name)}: ${e}"></div>`;
  }).join("") || '<span class="mono" style="color:var(--ink2);font-size:11px">Add tracks to see the arc</span>';
  const tally = {};
  S.transitions.forEach((c) => { tally[c.rating] = (tally[c.rating] || 0) + 1; });
  const order = ["great", "good", "ok", "risky", "clash"];
  $("#arc-tally").innerHTML = order.filter((r) => tally[r]).map((r) =>
    `<span class="tchip" style="color:var(--${r})">${tally[r]} ${r}</span>`).join("");
}

/* ---- library health ---- */
async function loadHealth() {
  try { S.health = await api("/api/library/health"); } catch (e) { S.health = {}; }
  const h = S.health;
  const rows = [
    ["unanalysed", h.unanalysed, "Not yet analysed", "Analyse"],
    ["nogenre", h.missing_genre, "Missing genre tag", "Review"],
    ["lowconf", h.low_confidence_key, "Low-confidence key", "Review"],
    ["dupes", h.duplicates, "Probable duplicates", "Review"],
  ];
  $("#health-rows").innerHTML = rows.map(([crate, count, label, action]) =>
    `<div class="hrow"><span class="hc">${count || 0}</span><span class="hl">${label}</span><button class="btn" data-health="${crate}">${action}</button></div>`).join("");
}
$("#health-rows").addEventListener("click", (e) => {
  const crate = e.target.dataset.health; if (!crate) return;
  setCrate(crate); setPane("library");
  toast(`${(S.health[crate === "unanalysed" ? "unanalysed" : crate === "nogenre" ? "missing_genre" : crate === "lowconf" ? "low_confidence_key" : "duplicates"]) || 0} tracks`);
});

/* ---- curator ---- */
$$(".preset").forEach((b) => b.addEventListener("click", () => { $("#brief").value = b.dataset.preset; }));
$("#btn-curate").addEventListener("click", async () => {
  const description = $("#brief").value.trim();
  if (!description) return toast("Write a brief first");
  const minutes = parseInt($("#minutes").value, 10) || null;
  $("#btn-curate").textContent = "Curating…"; $("#btn-curate").disabled = true;
  try {
    const res = await api("/api/curate", { method: "POST", body: JSON.stringify({ description, target_minutes: minutes }) });
    S.mix = res.track_ids; await hydrate(S.mix); await saveMix();
    $("#reason").classList.remove("hidden");
    $("#reason").textContent = (res.used_ai ? "" : "(offline rules) ") + (res.reasoning || "");
    await rescore(); renderMetrics(); renderArc(); loadLibrary();
    setPane("set");
    toast(res.used_ai ? "Curated by Claude" : "Curated (offline)");
  } catch (e) { toast(e.message); }
  finally { $("#btn-curate").textContent = "Curate"; $("#btn-curate").disabled = false; }
});

/* ---- library grid ---- */
$("#filter").addEventListener("input", (e) => {
  clearTimeout(S.filterTimer);
  S.filterTimer = setTimeout(() => { S.query = e.target.value.trim(); S.page = 0; loadLibrary(); }, 300);
});
$$(".crate").forEach((b) => b.addEventListener("click", () => setCrate(b.dataset.crate)));
function setCrate(crate) {
  S.crate = crate; S.page = 0;
  $$(".crate").forEach((b) => b.classList.toggle("on", b.dataset.crate === crate));
  loadLibrary();
}
$$(".grid-head button[data-sort]").forEach((b) => b.addEventListener("click", () => {
  const col = b.dataset.sort;
  if (S.sortBy === col) S.sortDir = S.sortDir === "asc" ? "desc" : "asc";
  else { S.sortBy = col; S.sortDir = "asc"; }
  S.page = 0; loadLibrary();
}));
$("#pg-prev").addEventListener("click", () => { if (S.page > 0) { S.page--; loadLibrary(); } });
$("#pg-next").addEventListener("click", () => { if ((S.page + 1) * pageSize() < S.total) { S.page++; loadLibrary(); } });

async function loadLibrary() {
  const ps = pageSize();
  const p = new URLSearchParams({ offset: S.page * ps, limit: ps, sort: S.sortBy, dir: S.sortDir });
  if (S.query) p.set("q", S.query);
  if (S.crate === "bpm") { p.set("crate", "all"); p.set("bpm_min", "126"); p.set("bpm_max", "134"); }
  else p.set("crate", S.crate);
  let data;
  try { data = await api("/api/tracks?" + p.toString()); } catch (e) { return toast(e.message); }
  S.total = data.total; S.pageRows = data.tracks.map((t) => t.id);
  data.tracks.forEach((t) => { S.tracks[t.id] = t; });
  renderGrid(data.tracks);
  const start = S.total ? S.page * ps + 1 : 0;
  const end = Math.min(S.total, (S.page + 1) * ps);
  $("#foot-range").textContent = `${start}–${end} of ${S.total} · page ${S.page + 1}/${Math.max(1, Math.ceil(S.total / ps))}`;
  $("#pg-prev").disabled = S.page === 0;
  $("#pg-next").disabled = end >= S.total;
  // sort indicators
  $$(".grid-head button[data-sort]").forEach((b) => {
    const active = b.dataset.sort === S.sortBy;
    b.classList.toggle("active", active);
    b.textContent = b.textContent.replace(/[▾▴]/g, "").trim() + (active ? (S.sortDir === "asc" ? " ▾" : " ▴") : "");
  });
}
function renderGrid(tracks) {
  $("#grid-rows").innerHTML = tracks.map((t) => {
    const inmix = S.mix.includes(t.id);
    const genre = (t.genre && t.genre.trim())
      ? `<button class="cell-edit" data-edit="genre" data-id="${t.id}">${esc(t.genre)}</button>`
      : `<button class="cell-edit untagged" data-edit="genre" data-id="${t.id}">— untagged</button>`;
    const bpm = t.bpm ? `<button class="cell-edit" data-edit="bpm" data-id="${t.id}">${Math.round(t.bpm)}</button>` : `<button class="cell-edit dash" data-edit="bpm" data-id="${t.id}">—</button>`;
    const low = t.analyzed && t.key_confidence != null && t.key_confidence < 0.6;
    const key = t.key_camelot
      ? `<button class="cell-edit keyval ${low ? "lowconf" : ""}" data-edit="key_camelot" data-id="${t.id}" title="${low ? "Low confidence — double-check" : (t.key_name || "")}">${t.key_camelot}</button>`
      : `<button class="cell-edit dash" data-edit="key_camelot" data-id="${t.id}">—</button>`;
    const e = t.energy;
    const energy = e != null ? `<span class="energy"><span class="track"><i style="width:${e / 10 * 100}%"></i></span><span class="ev">${e.toFixed ? e.toFixed(1) : e}</span></span>` : `<span class="dash">—</span>`;
    return `<div class="grid-row ${inmix ? "inmix" : ""} ${S.crate === "dupes" ? "dupe" : ""}">
      <button class="addbtn ${inmix ? "in" : ""}" data-add="${t.id}">${inmix ? "−" : "+"}</button>
      <span class="rtitle">${esc(t.name)}</span>
      <span class="rartist">${esc(t.artist || "")}</span>
      <span class="gcell-genre">${genre}</span>
      <span>${bpm}</span>
      <span>${key}</span>
      <span>${energy}</span>
      <span class="rtime">${fmtTime(t.duration)}</span>
    </div>`;
  }).join("") || '<div class="grid-row"><span></span><span class="rtitle">No tracks match.</span></div>';
}

/* add / inline edit delegation */
$("#grid-rows").addEventListener("click", (e) => {
  const add = e.target.dataset.add;
  if (add) return toggleMix(add);
  const cell = e.target.closest(".cell-edit");
  if (cell && !S.editing) startEdit(cell);
});
function startEdit(cell) {
  const id = cell.dataset.id, field = cell.dataset.edit;
  const t = S.tracks[id];
  const cur = field === "bpm" ? (t.bpm || "") : field === "key_camelot" ? (t.key_camelot || "") : (t.genre || "");
  S.editing = { id, field };
  const input = document.createElement("input");
  input.className = "cell-input"; input.value = cur;
  cell.replaceWith(input); input.focus(); input.select();
  const commit = async () => {
    if (!S.editing) return; S.editing = null;
    let val = input.value.trim();
    const body = {};
    if (field === "bpm") { const n = parseFloat(val); if (!isNaN(n)) body.bpm = n; }
    else body[field] = val;
    try {
      const updated = await api("/api/tracks/" + id, { method: "PATCH", body: JSON.stringify(body) });
      S.tracks[id] = updated;
      toast(field === "key_camelot" ? "key saved — written back to cache.db" : "saved — written back to cache.db");
    } catch (err) { toast(err.message); }
    loadLibrary();
  };
  input.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") { ev.preventDefault(); input.blur(); }
    else if (ev.key === "Escape") { S.editing = null; loadLibrary(); }
  });
  input.addEventListener("blur", commit);
}

/* ---- mix operations ---- */
async function toggleMix(id) {
  if (S.mix.includes(id)) S.mix = S.mix.filter((x) => x !== id);
  else { S.mix.push(id); await hydrate([id]); }
  await saveMix(); await rescore();
  renderMetrics(); renderArc(); loadLibrary(); if (S.pane === "set") renderSet();
}
async function saveMix() { try { await api("/api/mix", { method: "PUT", body: JSON.stringify({ track_ids: S.mix }) }); } catch (e) {} }
async function rescore() {
  if (S.mix.length < 2) { S.transitions = []; return; }
  try { const d = await api("/api/transitions", { method: "POST", body: JSON.stringify({ track_ids: S.mix }) }); S.transitions = d.transitions; }
  catch (e) { S.transitions = []; }
}

$("#btn-clear-set").addEventListener("click", async () => { S.mix = []; await saveMix(); S.transitions = []; renderMetrics(); renderArc(); loadLibrary(); renderSet(); });
$("#btn-export").addEventListener("click", async () => {
  if (!S.mix.length) return toast("Set is empty");
  try {
    const res = await fetch("/api/export/m3u", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ track_ids: S.mix, filename: "forthemix_set" }) });
    const blob = await res.blob(); const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = "forthemix_set.m3u8"; document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    toast("Exported M3U");
  } catch (e) { toast(e.message); }
});

/* ---- set pane ---- */
function renderSet() {
  const box = $("#seq-list");
  $("#mixscript").classList.toggle("hidden", S.mix.length < 2);
  if (!S.mix.length) {
    box.innerHTML = '<div class="empty-seq"><h3>Empty sequence</h3><p>Add tracks from the library — transition scores appear between them.</p></div>';
    return;
  }
  let html = "";
  S.mix.forEach((id, i) => {
    const t = S.tracks[id]; if (!t) return;
    html += `<div class="seqrow">
      <span class="idx">${String(i + 1).padStart(2, "0")}</span>
      <div class="body">
        <div class="st">${esc(t.name)}</div>
        <div class="sm">${esc(t.artist || "")} — ${esc(t.genre || "untagged")} · energy ${t.energy != null ? t.energy : "–"}</div>
      </div>
      ${t.key_camelot ? `<span class="keychip">${t.key_camelot}</span>` : ""}
      <span class="sb">${t.bpm ? Math.round(t.bpm) + " BPM" : ""}</span>
      <span class="sb">${fmtTime(t.duration)}</span>
      <button class="sqbtn" data-play="${id}">▶</button>
      <button class="sqbtn" data-up="${id}">↑</button>
      <button class="sqbtn" data-down="${id}">↓</button>
      <button class="sqbtn x" data-rm="${id}">✕</button>
    </div>`;
    if (i < S.mix.length - 1 && S.transitions[i]) {
      const c = S.transitions[i];
      html += `<div class="trans r-${c.rating}">
        <div class="tt"><span class="chip">${c.score}</span><span class="rword">${esc(c.rating)}</span><span class="cmt">${esc(c.comment)}</span></div>
        <div class="detail"><span>🎹 ${esc(c.harmonic)}</span><span>⏱ ${esc(c.tempo)}</span><span>⚡ ${esc(c.energy)}</span></div>
      </div>`;
    }
  });
  box.innerHTML = html;
}
$("#pane-set").addEventListener("click", async (e) => {
  const d = e.target.dataset;
  if (d.play) return playTrack(d.play);
  if (d.rm) { S.mix = S.mix.filter((x) => x !== d.rm); }
  else if (d.up || d.down) {
    const id = d.up || d.down, i = S.mix.indexOf(id), j = i + (d.up ? -1 : 1);
    if (i < 0 || j < 0 || j >= S.mix.length) return;
    [S.mix[i], S.mix[j]] = [S.mix[j], S.mix[i]];
  } else return;
  await saveMix(); await rescore(); renderSet(); renderMetrics(); renderArc(); loadLibrary();
});

/* ---- mix script (timecoded transitions -> beatmatched render) ---- */
function fmtTC(s) { if (s == null) return "—"; s = Math.round(s); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; }

$("#ms-parse").addEventListener("click", async () => {
  if (S.mix.length < 2) return toast("Add at least 2 tracks");
  const text = ($("#ms-text").value || "").trim();
  if (!text) return toast("Write a transition line first");
  try {
    const res = await api("/api/mixplan/parse", { method: "POST", body: JSON.stringify({ text, track_ids: S.mix }) });
    S.mixPlan = res.instructions || [];
    renderPlan(res.instructions || [], res.warnings || []);
    $("#ms-status").textContent = `Parsed ${S.mixPlan.length} transition${S.mixPlan.length === 1 ? "" : "s"}`;
  } catch (e) { toast(e.message); }
});

function renderPlan(instructions, warnings) {
  $("#ms-warnings").innerHTML = warnings.map((w) =>
    `<div class="ms-warn ${w.kind === "key" ? "key" : ""}">⚠ ${esc(w.message)}` +
    (w.options && w.options.length ? `<div class="opts">${w.options.map(esc).join(" · ")}</div>` : "") + `</div>`).join("");
  $("#ms-plan").innerHTML = instructions.map((ins, i) => {
    const a = S.tracks[S.mix[ins.from_index - 1]], b = S.tracks[S.mix[ins.to_index - 1]];
    const an = a ? a.name : `track ${ins.from_index}`, bn = b ? b.name : `track ${ins.to_index}`;
    return `<div class="ms-planrow">
      <span class="pl-grow"><span class="pl-label">${esc(bn)} → ${esc(an)}</span>
        <span class="pl-tc"> @ ${fmtTC(ins.from_out_sec)} → ${fmtTC(ins.to_in_sec)}</span></span>
      ${ins.technique === "eq_bass_swap" ? '<span class="ms-tech">bass swap</span>' : ""}
      <button class="btn" data-preview="${i}">Audition ⏭</button>
    </div>`;
  }).join("");
}

$("#ms-plan").addEventListener("click", async (e) => {
  const i = e.target.dataset.preview; if (i === undefined) return;
  const ins = (S.mixPlan || [])[+i]; if (!ins) return;
  $("#ms-status").textContent = "Rendering preview…";
  try {
    const res = await fetch("/api/mixplan/preview", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ track_ids: S.mix, instruction: ins, beatmatch: $("#ms-beatmatch").checked }) });
    if (!res.ok) throw new Error((await res.json()).detail || "Preview failed");
    const blob = await res.blob(); const pa = $("#ms-preview"); pa.src = URL.createObjectURL(blob); pa.play();
    $("#ms-status").textContent = "Playing transition preview";
  } catch (err) { toast(err.message); $("#ms-status").textContent = ""; }
});

$("#ms-render").addEventListener("click", async () => {
  if (S.mix.length < 2) return toast("Add at least 2 tracks");
  const name = prompt("Name this rendered mix:", "My set"); if (!name) return;
  S.renderName = name;
  try {
    await api("/api/mixplan/render", { method: "POST", body: JSON.stringify({
      track_ids: S.mix, instructions: S.mixPlan || [], name, beatmatch: $("#ms-beatmatch").checked }) });
    $("#ms-status").textContent = "Rendering… this can take a little while";
    pollRender();
  } catch (e) { toast(e.message); }
});

function pollRender() {
  clearInterval(S.renderTimer);
  S.renderTimer = setInterval(async () => {
    let st; try { st = await api("/api/mixplan/render/status"); } catch (e) { return; }
    if (st.running) { $("#ms-status").textContent = (st.message || "Rendering…"); return; }
    clearInterval(S.renderTimer);
    if (st.phase === "error") { $("#ms-status").textContent = ""; return toast(st.error || "Render failed"); }
    if (st.phase === "done") {
      $("#ms-status").textContent = "Rendered ✓ — downloading";
      try {
        const res = await fetch("/api/mixplan/render/file"); const blob = await res.blob();
        const url = URL.createObjectURL(blob); const a = document.createElement("a");
        a.href = url; a.download = (S.renderName || "mix") + ".wav"; document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
        toast("Mix rendered & downloaded");
      } catch (e) { toast("Rendered, but download failed"); }
    }
  }, 900);
}

/* ---- player dock ---- */
const audio = $("#audio");
async function playTrack(id) {
  const t = S.tracks[id]; if (!t) return;
  S.player.id = id;
  $("#pl-title").textContent = (t.artist ? t.artist + " — " : "") + t.name;
  audio.src = "/api/audio/" + id;
  drawWave(id);
  try { await audio.play(); $("#pl-play").textContent = "❙❙"; } catch (e) { toast("Audio not available"); }
}
async function drawWave(id) {
  let peaks = [];
  try { const full = await api("/api/tracks/" + id); peaks = full.peaks || []; } catch (e) {}
  const bars = 48; const wrap = $("#pl-wave");
  const step = Math.max(1, Math.floor(peaks.length / bars));
  const reduced = [];
  for (let i = 0; i < bars; i++) { const seg = peaks.slice(i * step, (i + 1) * step); reduced.push(seg.length ? Math.max(...seg) : 0); }
  wrap.innerHTML = reduced.map((p) => `<i style="height:${Math.max(8, p * 100)}%"></i>`).join("");
}
$("#pl-play").addEventListener("click", () => {
  if (!S.player.id) return toast("Pick a track");
  if (audio.paused) { audio.play(); $("#pl-play").textContent = "❙❙"; } else { audio.pause(); $("#pl-play").textContent = "▶"; }
});
audio.addEventListener("timeupdate", () => {
  $("#pl-time").textContent = `${fmtTime(audio.currentTime)} / ${fmtTime(audio.duration)}`;
  const bars = $$("#pl-wave i"); if (!bars.length || !audio.duration) return;
  const on = Math.floor((audio.currentTime / audio.duration) * bars.length);
  bars.forEach((b, i) => b.classList.toggle("on", i <= on));
});
$("#pl-audition").addEventListener("click", () => {
  const i = S.mix.indexOf(S.player.id);
  if (i < 0 || i >= S.mix.length - 1) return toast("Play a set track, then audition into the next");
  // simple audition: jump to near the end of the outgoing track, then roll into the next
  const next = S.mix[i + 1];
  const roll = () => { if (audio.duration) { audio.currentTime = Math.max(0, audio.duration - 8); audio.onended = () => { audio.onended = null; playTrack(next); }; } else setTimeout(roll, 150); };
  if (S.player.id) roll(); else playTrack(S.mix[i]).then(() => setTimeout(roll, 200));
  toast("Auditioning transition");
});
async function loadDevices() {
  try {
    const d = await api("/api/audio/devices");
    S.devices = d.devices || [];
    const sel = $("#pl-device");
    sel.innerHTML = (S.devices.length ? S.devices : [{ id: "", name: "Default output", default: true }])
      .map((dev) => `<option value="${esc(dev.id)}" ${dev.id === d.selected_id ? "selected" : ""}>${esc(dev.name)}</option>`).join("");
  } catch (e) {}
}
$("#pl-device").addEventListener("change", async (e) => {
  try { await api("/api/audio/device", { method: "POST", body: JSON.stringify({ id: e.target.value, name: e.target.selectedOptions[0].textContent }) }); toast("Output device set"); }
  catch (err) { toast(err.message); }
});

/* ============================ SETTINGS MODAL ============================ */
$("#btn-settings").addEventListener("click", async () => {
  try {
    const s = await api("/api/settings"); S.settings = s;
    $("#set-gid").value = s.google_client_id || "";
    $("#set-model").value = s.anthropic_model || "claude-opus-4-8";
    $("#set-warn").value = s.beatmatch_warn_pct || 6;
  } catch (e) {}
  $("#settings-modal").classList.remove("hidden");
});
$("#settings-close").addEventListener("click", () => $("#settings-modal").classList.add("hidden"));
$("#settings-modal").addEventListener("click", (e) => { if (e.target.id === "settings-modal") e.target.classList.add("hidden"); });
$("#settings-save").addEventListener("click", async () => {
  const body = {
    google_client_id: $("#set-gid").value,
    anthropic_model: $("#set-model").value,
    beatmatch_warn_pct: parseInt($("#set-warn").value, 10) || 6,
  };
  if ($("#set-gsecret").value.trim()) body.google_client_secret = $("#set-gsecret").value.trim();
  if ($("#set-akey").value.trim()) body.anthropic_api_key = $("#set-akey").value.trim();
  try { await api("/api/settings", { method: "POST", body: JSON.stringify(body) }); $("#set-gsecret").value = ""; $("#set-akey").value = ""; toast("Settings saved"); await refreshStatus(); }
  catch (e) { toast(e.message); }
});
$("#settings-clearcache").addEventListener("click", async () => {
  if (!confirm("Clear all analysed tracks from the local cache?")) return;
  await api("/api/cache/clear", { method: "POST" });
  S.tracks = {}; S.mix = []; await saveMix(); await refreshStatus(); toast("Cache cleared"); deriveState();
});

/* ============================ BOOT ============================ */
(async function init() {
  try {
    const s = await api("/api/settings");
    S.settings = s; S.theme = s.theme === "light" ? "light" : "dark"; S.density = s.density === "compact" ? "compact" : "comfortable";
  } catch (e) {}
  applyTheme(); applyDensity();
  await refreshStatus();
  await loadDevices();
  deriveState();
  S.statusTimer = setInterval(async () => { await refreshStatus(); if (isDesktop()) { /* keep pills fresh */ } }, 6000);
})();

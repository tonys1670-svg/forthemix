/* ForTheMix — front-end controller */
"use strict";

const state = {
  tracks: {},        // id -> track (from /api/tracks, no peaks)
  order: [],         // library display order (ids)
  mix: [],           // ordered ids in the mix
  status: {},
  pollTimer: null,
  player: { id: null, auditionNext: null },
};

/* ------------------------- helpers ------------------------- */
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (e) {}
    throw new Error(detail);
  }
  const ct = res.headers.get("content-type") || "";
  return ct.includes("application/json") ? res.json() : res;
}

function toast(msg, kind = "") {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast " + kind;
  setTimeout(() => t.classList.add("hidden"), 4200);
}

function fmtTime(sec) {
  if (!sec && sec !== 0) return "–";
  sec = Math.round(sec);
  const m = Math.floor(sec / 60), s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function energyBar(e) {
  if (e === null || e === undefined) return '<span class="muted">–</span>';
  const pct = Math.min(100, (e / 10) * 100);
  return `<span class="energy-cell"><span class="energy-dot"><i style="width:${pct}%"></i></span>${e.toFixed(0)}</span>`;
}

function keyCell(t) {
  if (!t.key_camelot) return '<span class="muted">–</span>';
  const low = t.key_confidence !== null && t.key_confidence < 0.4;
  const cls = low ? "key-badge badge confidence-low" : "key-badge badge";
  const title = low ? "Low confidence — double-check / edit" : (t.key_name || "");
  return `<span class="${cls}" title="${title}">${t.key_camelot}</span>`;
}

/* ------------------------- tabs ------------------------- */
$$(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    $$(".tab").forEach((b) => b.classList.remove("active"));
    $$(".panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    $("#tab-" + btn.dataset.tab).classList.add("active");
    if (btn.dataset.tab === "mix") renderAvailable();
  });
});

/* ------------------------- status ------------------------- */
async function refreshStatus() {
  try {
    state.status = await api("/api/status");
  } catch (e) { return; }
  const s = state.status;
  $("#pill-drive").className = "pill " + (s.drive_connected ? "on" : "off");
  $("#pill-ai").className = "pill " + (s.has_anthropic_key ? "on" : "off");
  $("#library-folder").textContent = s.drive_folder_name
    ? `Folder: ${s.drive_folder_name}` + (s.track_count ? ` · ${s.track_count} tracks` : "")
    : "No folder selected — choose one in Settings";
  $("#drive-state").textContent = s.drive_connected ? "Connected" : "Not connected";
  $("#drive-state").className = "state " + (s.drive_connected ? "ok" : "");
  $("#btn-disconnect").classList.toggle("hidden", !s.drive_connected);
  $("#ai-state").textContent = s.has_anthropic_key ? "Key saved" : "No key";
  $("#ai-state").className = "state " + (s.has_anthropic_key ? "ok" : "");
  $("#selected-folder").textContent = s.drive_folder_name ? `Selected: ${s.drive_folder_name}` : "None selected";
}

/* ------------------------- library ------------------------- */
async function loadTracks() {
  const data = await api("/api/tracks");
  state.tracks = {};
  state.order = [];
  data.tracks.forEach((t) => { state.tracks[t.id] = t; state.order.push(t.id); });
  renderTracks();
  renderAvailable();
}

function renderTracks() {
  const tbody = $("#track-rows");
  if (!state.order.length) {
    tbody.innerHTML = '<tr><td colspan="9" class="empty">No tracks yet. Connect Drive in Settings, pick a folder, then Analyse.</td></tr>';
    return;
  }
  tbody.innerHTML = state.order.map((id) => {
    const t = state.tracks[id];
    const inMix = state.mix.includes(id);
    if (t.error) {
      return `<tr><td>⚠️</td><td>${esc(t.name)}</td><td colspan="6" class="warn">${esc(t.error)}</td><td></td></tr>`;
    }
    return `<tr>
      <td><button class="mini" data-play="${id}">▶</button></td>
      <td>${esc(t.name)}</td>
      <td class="muted">${esc(t.artist || "–")}</td>
      <td>${t.genre ? esc(t.genre) : '<span class="muted">unknown</span>'}</td>
      <td>${t.bpm ? t.bpm.toFixed(0) : '<span class="muted">–</span>'}</td>
      <td>${keyCell(t)}</td>
      <td>${energyBar(t.energy)}</td>
      <td class="muted">${fmtTime(t.duration)}</td>
      <td><button class="mini" data-add="${id}" ${inMix ? "disabled" : ""}>${inMix ? "✓ in mix" : "+ mix"}</button></td>
    </tr>`;
  }).join("");
}

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

$("#track-rows").addEventListener("click", (e) => {
  const add = e.target.dataset.add, play = e.target.dataset.play;
  if (add) addToMix(add);
  if (play) playTrack(play);
});

$("#btn-refresh-tracks").addEventListener("click", () => loadTracks().catch((e) => toast(e.message, "err")));

/* ------------------------- analysis job ------------------------- */
$("#btn-analyze").addEventListener("click", async () => {
  try {
    await api("/api/analyze", { method: "POST" });
    $("#analyze-progress").classList.remove("hidden");
    pollAnalysis();
  } catch (e) { toast(e.message, "err"); }
});

function pollAnalysis() {
  clearInterval(state.pollTimer);
  state.pollTimer = setInterval(async () => {
    let st;
    try { st = await api("/api/analyze/status"); } catch (e) { return; }
    const pct = st.total ? Math.round((st.current / st.total) * 100) : 0;
    $("#progress-fill").style.width = pct + "%";
    $("#progress-text").textContent =
      st.phase === "done" ? st.message
      : `${st.phase} — ${st.current}/${st.total} · ${st.message || ""}`;
    if (!st.running && (st.phase === "done" || st.phase === "error")) {
      clearInterval(state.pollTimer);
      if (st.phase === "error") toast(st.error || "Analysis failed", "err");
      else toast("Analysis complete", "ok");
      setTimeout(() => $("#analyze-progress").classList.add("hidden"), 1500);
      await loadTracks();
      await refreshStatus();
    }
  }, 700);
}

/* ------------------------- mix builder ------------------------- */
function renderAvailable() {
  const q = ($("#mix-search").value || "").toLowerCase();
  const ul = $("#available-list");
  const items = state.order
    .map((id) => state.tracks[id])
    .filter((t) => t && t.analyzed && !state.mix.includes(t.id))
    .filter((t) => !q || (t.name + " " + (t.artist || "") + " " + (t.genre || "")).toLowerCase().includes(q));
  ul.innerHTML = items.length ? items.map((t) => `
    <li>
      <span class="t-body"><span class="t-title">${esc(t.name)}</span>
        <span class="t-meta"> ${t.bpm ? t.bpm.toFixed(0) + " BPM" : ""} ${t.key_camelot || ""} ${t.energy != null ? "· E" + t.energy.toFixed(0) : ""}</span>
      </span>
      <span>
        <button class="mini" data-play="${t.id}">▶</button>
        <button class="mini" data-add="${t.id}">+</button>
      </span>
    </li>`).join("") : '<li class="muted">No analysed tracks. Run analysis first.</li>';
}

$("#mix-search").addEventListener("input", renderAvailable);
$("#available-list").addEventListener("click", (e) => {
  const add = e.target.dataset.add, play = e.target.dataset.play;
  if (add) addToMix(add);
  if (play) playTrack(play);
});

function addToMix(id) {
  if (!state.mix.includes(id)) {
    state.mix.push(id);
    renderMix();
    renderAvailable();
    renderTracks();
  }
}
function removeFromMix(id) {
  state.mix = state.mix.filter((x) => x !== id);
  renderMix(); renderAvailable(); renderTracks();
}
function moveMix(id, dir) {
  const i = state.mix.indexOf(id);
  const j = i + dir;
  if (i < 0 || j < 0 || j >= state.mix.length) return;
  [state.mix[i], state.mix[j]] = [state.mix[j], state.mix[i]];
  renderMix();
}

async function renderMix() {
  $("#mix-count").textContent = state.mix.length;
  const box = $("#mix-list");
  if (!state.mix.length) {
    box.innerHTML = '<p class="empty">Add tracks from the left to start building. Transition tips appear between them.</p>';
    return;
  }
  // fetch transition comments for the current sequence
  let trans = [];
  if (state.mix.length > 1) {
    try {
      const data = await api("/api/transitions", { method: "POST", body: JSON.stringify({ track_ids: state.mix }) });
      trans = data.transitions;
    } catch (e) { /* ignore */ }
  }

  let html = "";
  state.mix.forEach((id, i) => {
    const t = state.tracks[id];
    if (!t) return;
    html += `
      <div class="mix-item">
        <span class="idx">${i + 1}</span>
        <div class="m-body">
          <div class="m-title">${esc(t.name)}</div>
          <div class="m-meta">${esc(t.artist || "")} ${t.bpm ? "· " + t.bpm.toFixed(0) + " BPM" : ""} ${t.key_camelot ? "· " + t.key_camelot : ""} ${t.energy != null ? "· E" + t.energy.toFixed(0) : ""}</div>
        </div>
        <div class="m-tools">
          <button class="mini" data-play="${id}">▶</button>
          <button class="mini" data-up="${id}">↑</button>
          <button class="mini" data-down="${id}">↓</button>
          <button class="mini" data-rm="${id}">✕</button>
        </div>
      </div>`;
    if (i < state.mix.length - 1 && trans[i]) {
      const c = trans[i];
      html += `
        <div class="transition r-${c.rating}">
          <div class="t-head"><span class="score-chip">${c.score}</span> ${esc(c.comment)}
            <button class="mini" data-audition="${i}" title="Hear this transition">audition ⏭</button>
          </div>
          <div class="t-detail">🎹 ${esc(c.harmonic)}<br/>⏱ ${esc(c.tempo)}<br/>⚡ ${esc(c.energy)}</div>
        </div>`;
    }
  });
  box.innerHTML = html;
}

$("#mix-list").addEventListener("click", (e) => {
  const d = e.target.dataset;
  if (d.play) playTrack(d.play);
  else if (d.up) moveMix(d.up, -1);
  else if (d.down) moveMix(d.down, +1);
  else if (d.rm) removeFromMix(d.rm);
  else if (d.audition !== undefined) auditionTransition(parseInt(d.audition, 10));
});

$("#btn-clear-mix").addEventListener("click", () => { state.mix = []; renderMix(); renderAvailable(); renderTracks(); });

/* ------------------------- export ------------------------- */
$("#btn-export").addEventListener("click", async () => {
  if (!state.mix.length) return toast("Mix is empty", "err");
  try {
    const res = await fetch("/api/export/m3u", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ track_ids: state.mix, filename: "forthemix_set" }),
    });
    if (!res.ok) throw new Error("Export failed");
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "forthemix_set.m3u8";
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
    toast("Playlist exported", "ok");
  } catch (e) { toast(e.message, "err"); }
});

/* ------------------------- audio player ------------------------- */
const audio = $("#audio");
const canvas = $("#waveform");

async function playTrack(id, seekRatio = 0) {
  const t = state.tracks[id];
  if (!t) return;
  state.player.id = id;
  state.player.auditionNext = null;
  $("#player").classList.remove("hidden");
  $("#pl-title").textContent = (t.artist ? t.artist + " – " : "") + t.name;
  audio.src = `/api/audio/${id}`;
  await drawWaveform(id);
  audio.onloadedmetadata = () => { if (seekRatio) audio.currentTime = audio.duration * seekRatio; };
  try { await audio.play(); $("#pl-play").textContent = "⏸"; } catch (e) {}
}

async function drawWaveform(id) {
  let peaks = [];
  try {
    const full = await api(`/api/tracks/${id}`);
    peaks = full.peaks || [];
  } catch (e) {}
  const ctx = canvas.getContext("2d");
  const W = canvas.width = canvas.clientWidth * (window.devicePixelRatio || 1);
  const H = canvas.height;
  ctx.clearRect(0, 0, W, H);
  if (!peaks.length) return;
  const mid = H / 2;
  const bw = W / peaks.length;
  ctx.fillStyle = "#3a4658";
  peaks.forEach((p, i) => {
    const h = Math.max(1, p * (H - 6));
    ctx.fillRect(i * bw, mid - h / 2, Math.max(1, bw - 0.5), h);
  });
}

// progress overlay on the waveform
function drawProgress() {
  if (!audio.duration) return;
  const ratio = audio.currentTime / audio.duration;
  drawWaveformProgress(ratio);
}
function drawWaveformProgress(ratio) {
  // redraw a thin accent line — cheap: overlay a translucent rect via CSS-like approach
  const ctx = canvas.getContext("2d");
  // We simply re-tint the played portion by drawing an accent bar at the playhead.
  // (Full redraw omitted for performance; playhead line is enough visual feedback.)
  const W = canvas.width;
  const x = ratio * W;
  // draw a 2px playhead
  ctx.save();
  ctx.globalCompositeOperation = "source-over";
  ctx.fillStyle = "rgba(109,139,255,0.9)";
  ctx.fillRect(x, 0, 2, canvas.height);
  ctx.restore();
}

$("#pl-play").addEventListener("click", () => {
  if (audio.paused) { audio.play(); $("#pl-play").textContent = "⏸"; }
  else { audio.pause(); $("#pl-play").textContent = "▶"; }
});
$("#pl-close").addEventListener("click", () => { audio.pause(); $("#player").classList.add("hidden"); });
canvas.addEventListener("click", (e) => {
  if (!audio.duration) return;
  const rect = canvas.getBoundingClientRect();
  audio.currentTime = ((e.clientX - rect.left) / rect.width) * audio.duration;
});

audio.addEventListener("timeupdate", () => {
  $("#pl-time").textContent = `${fmtTime(audio.currentTime)} / ${fmtTime(audio.duration)}`;
  if (state.player.id) drawProgress();
});
audio.addEventListener("ended", () => {
  $("#pl-play").textContent = "▶";
  if (state.player.auditionNext) {
    const next = state.player.auditionNext;
    state.player.auditionNext = null;
    playTrack(next, 0);
  }
});

// "Audition transition" from the player button = current -> next in mix
$("#pl-audition").addEventListener("click", () => {
  const i = state.mix.indexOf(state.player.id);
  if (i >= 0 && i < state.mix.length - 1) auditionByIndex(i);
  else toast("Play a mix track first, then audition into the next.", "");
});

function auditionTransition(i) { auditionByIndex(i); }

function auditionByIndex(i) {
  const fromId = state.mix[i], toId = state.mix[i + 1];
  if (!fromId || !toId) return;
  // Play the last ~12 seconds of the outgoing track, then roll into the next.
  playTrack(fromId).then(() => {
    const startTail = () => {
      if (audio.duration && isFinite(audio.duration)) {
        audio.currentTime = Math.max(0, audio.duration - 12);
        state.player.auditionNext = toId;
      } else {
        setTimeout(startTail, 200);
      }
    };
    setTimeout(startTail, 250);
  });
}

/* ------------------------- curator ------------------------- */
$("#btn-curate").addEventListener("click", async () => {
  const description = $("#curate-desc").value.trim();
  if (!description) return toast("Describe the playlist first", "err");
  const minutes = parseInt($("#curate-minutes").value, 10) || null;
  $("#btn-curate").disabled = true;
  $("#curate-status").textContent = "Curating…";
  try {
    const result = await api("/api/curate", {
      method: "POST",
      body: JSON.stringify({ description, target_minutes: minutes }),
    });
    renderCuration(result);
    $("#curate-status").textContent = result.used_ai ? "Curated by Claude." : "Curated offline (rule-based).";
  } catch (e) {
    $("#curate-status").textContent = "";
    toast(e.message, "err");
  } finally {
    $("#btn-curate").disabled = false;
  }
});

let lastCuration = [];
function renderCuration(result) {
  lastCuration = result.track_ids;
  const r = $("#curate-reasoning");
  r.classList.remove("hidden");
  r.textContent = result.reasoning || "";
  const ul = $("#curate-result");
  ul.innerHTML = result.track_ids.map((id, i) => {
    const t = state.tracks[id];
    if (!t) return "";
    const note = result.per_track_notes[id];
    return `<li>
      <span class="t-body"><span class="t-title">${i + 1}. ${esc(t.name)}</span>
        <span class="t-meta"> ${t.bpm ? t.bpm.toFixed(0) + " BPM" : ""} ${t.key_camelot || ""} ${t.energy != null ? "· E" + t.energy.toFixed(0) : ""}${note ? " — " + esc(note) : ""}</span>
      </span>
      <button class="mini" data-play="${id}">▶</button>
    </li>`;
  }).join("");
  $("#btn-load-mix").classList.remove("hidden");
}

$("#curate-result").addEventListener("click", (e) => { if (e.target.dataset.play) playTrack(e.target.dataset.play); });

$("#btn-load-mix").addEventListener("click", () => {
  state.mix = [...lastCuration];
  renderMix();
  $$(".tab").forEach((b) => b.classList.remove("active"));
  $$(".panel").forEach((p) => p.classList.remove("active"));
  document.querySelector('.tab[data-tab="mix"]').classList.add("active");
  $("#tab-mix").classList.add("active");
  renderAvailable();
  toast("Loaded into Mix Builder", "ok");
});

/* ------------------------- settings ------------------------- */
async function loadSettings() {
  try {
    const s = await api("/api/settings");
    $("#set-gid").value = s.google_client_id || "";
    $("#set-model").value = s.anthropic_model || "claude-opus-4-8";
    $("#set-bpmtol").value = s.target_bpm_tolerance || 6;
  } catch (e) {}
}

$("#btn-save-google").addEventListener("click", async () => {
  try {
    await api("/api/settings", { method: "POST", body: JSON.stringify({
      google_client_id: $("#set-gid").value,
      google_client_secret: $("#set-gsecret").value,
    })});
    $("#set-gsecret").value = "";
    toast("Google client saved", "ok");
    refreshStatus();
  } catch (e) { toast(e.message, "err"); }
});

$("#btn-connect").addEventListener("click", async () => {
  toast("Opening Google sign-in… complete it in the browser window.");
  try {
    await api("/api/drive/connect", { method: "POST" });
    toast("Google Drive connected", "ok");
    refreshStatus();
  } catch (e) { toast(e.message, "err"); }
});
$("#btn-disconnect").addEventListener("click", async () => {
  await api("/api/drive/disconnect", { method: "POST" });
  toast("Disconnected");
  refreshStatus();
});

$("#btn-folder-search").addEventListener("click", async () => {
  const name = $("#folder-search").value.trim();
  if (!name) return;
  try {
    const data = await api("/api/drive/search?name=" + encodeURIComponent(name));
    const ul = $("#folder-results");
    ul.innerHTML = data.folders.length
      ? data.folders.map((f) => `<li data-fid="${f.id}" data-fname="${esc(f.name)}">${esc(f.name)}<span class="muted">select</span></li>`).join("")
      : '<li class="muted">No folders found</li>';
  } catch (e) { toast(e.message, "err"); }
});

$("#folder-results").addEventListener("click", async (e) => {
  const li = e.target.closest("li[data-fid]");
  if (!li) return;
  try {
    await api("/api/drive/select-folder", { method: "POST", body: JSON.stringify({ id: li.dataset.fid, name: li.dataset.fname }) });
    $$("#folder-results li").forEach((x) => x.classList.remove("sel"));
    li.classList.add("sel");
    toast("Folder selected: " + li.dataset.fname, "ok");
    refreshStatus();
  } catch (e) { toast(e.message, "err"); }
});

$("#btn-save-anthropic").addEventListener("click", async () => {
  try {
    await api("/api/settings", { method: "POST", body: JSON.stringify({
      anthropic_api_key: $("#set-akey").value,
      anthropic_model: $("#set-model").value,
    })});
    $("#set-akey").value = "";
    toast("Anthropic settings saved", "ok");
    refreshStatus();
  } catch (e) { toast(e.message, "err"); }
});

$("#btn-save-prefs").addEventListener("click", async () => {
  try {
    await api("/api/settings", { method: "POST", body: JSON.stringify({
      target_bpm_tolerance: parseInt($("#set-bpmtol").value, 10) || 6,
    })});
    toast("Preferences saved", "ok");
  } catch (e) { toast(e.message, "err"); }
});

$("#btn-clear-cache").addEventListener("click", async () => {
  if (!confirm("Clear all analysed tracks from the local cache?")) return;
  await api("/api/cache/clear", { method: "POST" });
  state.tracks = {}; state.order = []; state.mix = [];
  renderTracks(); renderMix(); renderAvailable();
  toast("Cache cleared", "ok");
  refreshStatus();
});

/* ------------------------- boot ------------------------- */
(async function init() {
  await refreshStatus();
  await loadSettings();
  await loadTracks().catch(() => {});
  setInterval(refreshStatus, 8000);
})();

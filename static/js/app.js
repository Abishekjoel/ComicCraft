// ComicCraft frontend. All AI calls happen on the server; this file only talks to our own API.
(() => {
  const $ = (id) => document.getElementById(id);
  const form = $("comic-form");
  const generateBtn = $("generate-btn");
  const loading = $("loading");
  const loadingMessage = $("loading-message");
  const progressBar = $("progress-bar");
  const result = $("result");
  const panelsEl = $("panels");
  const titleEl = $("comic-title");
  const exportBtn = $("export-btn");
  const regenBtn = $("regen-btn");
  const formError = $("form-error");
  const exportError = $("export-error");

  let currentComicId = null;
  let polling = null;

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text; // textContent: model output is never parsed as HTML
    return node;
  }

  function showError(node, message) {
    node.textContent = message;
    node.hidden = !message;
  }

  async function api(url, options) {
    let res;
    try {
      res = await fetch(url, options);
    } catch (err) {
      throw new Error("Could not reach the ComicCraft server. Is it still running?");
    }
    let data = null;
    try { data = await res.json(); } catch (_) { /* non-JSON error body */ }
    if (res.status === 405 || (res.status === 404 && !data)) {
      throw new Error("The ComicCraft server isn't answering here (Live Server or another static server?). " +
        "Start it with 'uvicorn app.main:app' and open http://127.0.0.1:8000 instead.");
    }
    if (!res.ok) throw new Error((data && data.detail) || `Request failed (${res.status})`);
    return data;
  }

  function readForm() {
    const data = new FormData(form);
    return {
      prompt: data.get("prompt").trim(),
      character_name: data.get("character_name").trim(),
      setting: data.get("setting").trim(),
      tone: data.get("tone"),
      art_style: data.get("art_style"),
      panel_count: Number(data.get("panel_count")),
    };
  }

  function validate(body) {
    if (body.prompt.length < 3) return "Please describe your story (at least 3 characters).";
    if (!body.character_name) return "Please enter a main character name.";
    if (!body.setting) return "Please enter a setting.";
    return "";
  }

  function buildPanel(panel, index) {
    const card = el("article", "panel");
    card.style.animationDelay = `${index * 80}ms`;
    card.appendChild(el("span", "panel-badge", `Panel ${panel.panel_number}`));
    card.appendChild(el("h3", "panel-title", panel.title));

    const frame = el("div", "panel-frame");
    const img = el("img");
    img.src = panel.image_url;
    img.alt = panel.scene_description;
    img.loading = "lazy";
    frame.appendChild(img);
    card.appendChild(frame);

    if (panel.narration) card.appendChild(el("p", "narration", panel.narration));
    (panel.dialogue || []).forEach((line, i) => {
      const bubble = el("div", "bubble" + (i % 2 ? " bubble-right" : ""));
      bubble.appendChild(el("strong", "bubble-name", line.character));
      bubble.appendChild(el("span", "bubble-text", line.text));
      card.appendChild(bubble);
    });
    return card;
  }

  function renderPanels(panels) {
    // Only append panels we haven't drawn yet, so finished images don't flicker while polling.
    for (let i = panelsEl.children.length; i < panels.length; i++) {
      panelsEl.appendChild(buildPanel(panels[i], i));
    }
  }

  function setBusy(busy) {
    generateBtn.disabled = busy;
    generateBtn.textContent = busy ? "Creating..." : "Create My Comic";
    if (busy) { exportBtn.disabled = true; regenBtn.disabled = true; }
  }

  function updateProgress(job) {
    loadingMessage.textContent = job.message;
    const total = job.total || 1;
    const pct = job.status === "done" ? 100 : Math.max(4, Math.round((job.current / total) * 100));
    progressBar.style.width = `${pct}%`;
    if (job.title) titleEl.textContent = job.title;
    if (job.panels && job.panels.length) {
      result.hidden = false;
      renderPanels(job.panels);
    }
  }

  function stopPolling() {
    if (polling) { clearTimeout(polling); polling = null; }
  }

  function poll(jobId) {
    polling = setTimeout(async () => {
      try {
        const job = await api(`/api/comic/jobs/${jobId}`);
        updateProgress(job);
        if (job.status === "done") return finish(job.comic);
        if (job.status === "error") return fail(job.error || "Generation failed.");
        poll(jobId);
      } catch (err) {
        fail(err.message);
      }
    }, 1000);
  }

  function finish(comic) {
    stopPolling();
    currentComicId = comic.comic_id;
    titleEl.textContent = comic.title;
    panelsEl.replaceChildren();
    renderPanels(comic.panels);
    loading.hidden = true;
    result.hidden = false;
    setBusy(false);
    exportBtn.disabled = false;
    regenBtn.disabled = false;
    result.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function fail(message) {
    stopPolling();
    loading.hidden = true;
    setBusy(false);
    showError(formError, message);
    if (panelsEl.children.length === 0) result.hidden = true;
  }

  async function startGeneration() {
    showError(formError, "");
    showError(exportError, "");
    const body = readForm();
    const problem = validate(body);
    if (problem) return showError(formError, problem);

    // Every click generates a brand-new story AND new images on the server.
    stopPolling();
    currentComicId = null;
    panelsEl.replaceChildren();
    titleEl.textContent = "";
    result.hidden = true;
    progressBar.style.width = "4%";
    loadingMessage.textContent = "Creating your story...";
    loading.hidden = false;
    setBusy(true);
    loading.scrollIntoView({ behavior: "smooth", block: "center" });

    try {
      const job = await api("/api/comic/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      poll(job.job_id);
    } catch (err) {
      fail(err.message);
    }
  }

  async function exportPdf() {
    if (!currentComicId) return;
    showError(exportError, "");
    exportBtn.disabled = true;
    exportBtn.textContent = "Building PDF...";
    try {
      const data = await api("/api/comic/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ comic_id: currentComicId }),
      });
      window.location.href = data.success_url;
    } catch (err) {
      showError(exportError, err.message);
      exportBtn.disabled = false;
      exportBtn.textContent = "Export PDF";
    }
  }

  // Reopen a saved comic via /?comic=<id> (e.g. "Back to ComicCraft" after exporting).
  async function loadSaved() {
    const id = new URLSearchParams(window.location.search).get("comic");
    if (!id) return;
    try {
      const comic = await api(`/api/comic/${encodeURIComponent(id)}`);
      finish(comic);
      form.elements.character_name.value = comic.character_name;
      form.elements.tone.value = comic.tone;
      form.elements.art_style.value = comic.art_style;
      form.elements.panel_count.value = String(comic.panels.length);
    } catch (err) {
      showError(formError, err.message);
    }
  }

  form.addEventListener("submit", (e) => { e.preventDefault(); startGeneration(); });
  regenBtn.addEventListener("click", startGeneration);
  exportBtn.addEventListener("click", exportPdf);
  loadSaved();
})();

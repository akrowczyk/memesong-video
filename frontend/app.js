(() => {
  const THEMES = {
    midnight: {
      label: "Midnight",
      bg1: "#090d1f",
      bg2: "#181242",
      orb1: "56, 189, 248",
      orb2: "168, 85, 247",
      accent: "#38bdf8",
    },
    sunset: {
      label: "Sunset",
      bg1: "#180a1c",
      bg2: "#40122c",
      orb1: "249, 115, 22",
      orb2: "236, 72, 153",
      accent: "#fb923c",
    },
    emerald: {
      label: "Emerald",
      bg1: "#061816",
      bg2: "#0c3630",
      orb1: "52, 211, 153",
      orb2: "45, 212, 191",
      accent: "#34d399",
    },
    gold: {
      label: "Gold",
      bg1: "#120f0b",
      bg2: "#2e2111",
      orb1: "251, 191, 36",
      orb2: "245, 158, 11",
      accent: "#fbbf24",
    },
    monochrome: {
      label: "Mono",
      bg1: "#0a0a0e",
      bg2: "#20212a",
      orb1: "148, 163, 184",
      orb2: "226, 232, 240",
      accent: "#f8fafc",
    },
  };

  // App state
  const state = {
    projectId: null,
    pendingAudioFile: null,
    pendingCoverFile: null,
    duration: 0,
    timings: null,
    settings: {
      title: "",
      artist: "",
      theme_name: "midnight",
      accent_color: "#38bdf8",
      use_cover_image: false,
      time_offset: 0.0,
      lyric_position: "center",
      bg_dim: 0.15,
      text_outline: "dark",
      show_neighbor_lines: false,
    },
    coverImg: null,
    selectedWord: null, // { lineIdx, wordIdx }
    dirty: false,
  };

  // DOM refs
  const $ = (id) => document.getElementById(id);
  const projectSelect = $("projectSelect");
  const newProjectBtn = $("newProjectBtn");
  const audioDropZone = $("audioDropZone");
  const audioInput = $("audioInput");
  const audioDropLabel = $("audioDropLabel");
  const titleInput = $("titleInput");
  const artistInput = $("artistInput");
  const lyricsInput = $("lyricsInput");
  const isolateVocalsInput = $("isolateVocalsInput");
  const modelSelect = $("modelSelect");
  const alignBtn = $("alignBtn");
  const alignStatus = $("alignStatus");
  const alignStatusText = $("alignStatusText");
  const alignStatusPct = $("alignStatusPct");
  const alignProgress = $("alignProgress");

  const bgModeRadios = document.querySelectorAll('input[name="bgMode"]');
  const gradientOptions = $("gradientOptions");
  const coverOptions = $("coverOptions");
  const themeGrid = $("themeGrid");
  const coverDropZone = $("coverDropZone");
  const coverInput = $("coverInput");
  const coverDropLabel = $("coverDropLabel");
  const coverPreviewRow = $("coverPreviewRow");
  const coverThumb = $("coverThumb");
  const removeCoverBtn = $("removeCoverBtn");
  const bgDimSlider = $("bgDimSlider");
  const bgDimValue = $("bgDimValue");
  const lyricPosRadios = document.querySelectorAll('input[name="lyricPosition"]');
  const textOutlineRadios = document.querySelectorAll('input[name="textOutline"]');
  const showNeighborsInput = $("showNeighborsInput");
  const accentColorInput = $("accentColorInput");
  const accentColorHex = $("accentColorHex");
  const offsetSlider = $("offsetSlider");
  const offsetValue = $("offsetValue");

  const previewCanvas = $("previewCanvas");
  const ctx = previewCanvas.getContext("2d");
  const previewTime = $("previewTime");
  const audioPlayer = $("audioPlayer");
  const saveBtn = $("saveBtn");
  const renderBtn = $("renderBtn");
  const downloadLink = $("downloadLink");
  const renderStatus = $("renderStatus");
  const renderStatusText = $("renderStatusText");
  const renderStatusPct = $("renderStatusPct");
  const renderProgress = $("renderProgress");

  const wordInspector = $("wordInspector");
  const inspWordText = $("inspWordText");
  const inspStart = $("inspStart");
  const inspEnd = $("inspEnd");
  const inspStartMinus = $("inspStartMinus");
  const inspStartPlus = $("inspStartPlus");
  const inspSetStartNow = $("inspSetStartNow");
  const inspEndMinus = $("inspEndMinus");
  const inspEndPlus = $("inspEndPlus");
  const inspSetEndNow = $("inspSetEndNow");
  const lyricsTimeline = $("lyricsTimeline");
  const toastEl = $("toast");

  // Web Audio analyser for live audio-reactive glow in preview
  let audioCtx = null;
  let analyser = null;
  let freqData = null;
  let smoothedEnergy = 0;

  function ensureAudioAnalyser() {
    if (audioCtx) {
      if (audioCtx.state === "suspended") audioCtx.resume();
      return;
    }
    try {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const src = audioCtx.createMediaElementSource(audioPlayer);
      analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      freqData = new Uint8Array(analyser.frequencyBinCount);
      src.connect(analyser);
      analyser.connect(audioCtx.destination);
    } catch {
      // Non-fatal if browser blocks AudioContext
    }
  }

  audioPlayer.addEventListener("play", ensureAudioAnalyser);

  function showToast(msg) {
    toastEl.textContent = msg;
    toastEl.classList.remove("hidden");
    clearTimeout(showToast._timer);
    showToast._timer = setTimeout(() => toastEl.classList.add("hidden"), 3200);
  }

  function formatTime(sec) {
    if (!Number.isFinite(sec) || sec < 0) return "0:00";
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    return `${m}:${String(s).padStart(2, "0")}`;
  }

  function hexToRgbTuple(hex) {
    const clean = (hex || "#38bdf8").replace("#", "");
    const r = parseInt(clean.slice(0, 2), 16) || 56;
    const g = parseInt(clean.slice(2, 4), 16) || 189;
    const b = parseInt(clean.slice(4, 6), 16) || 248;
    return [r, g, b];
  }

  // Render theme swatches
  function buildThemeSwatches() {
    themeGrid.innerHTML = "";
    Object.entries(THEMES).forEach(([key, theme]) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `theme-swatch${state.settings.theme_name === key ? " active" : ""}`;
      btn.dataset.theme = key;
      btn.innerHTML = `
        <span class="theme-chip" style="background: linear-gradient(135deg, ${theme.bg1}, ${theme.bg2}, ${theme.accent});"></span>
        <span>${theme.label}</span>
      `;
      btn.addEventListener("click", () => {
        state.settings.theme_name = key;
        state.settings.accent_color = theme.accent;
        accentColorInput.value = theme.accent;
        accentColorHex.textContent = theme.accent;
        updateThemeActiveUI();
        markDirty();
      });
      themeGrid.appendChild(btn);
    });
  }

  function updateThemeActiveUI() {
    themeGrid.querySelectorAll(".theme-swatch").forEach((el) => {
      el.classList.toggle("active", el.dataset.theme === state.settings.theme_name);
    });
  }

  function markDirty() {
    state.dirty = true;
    if (state.projectId) saveBtn.disabled = false;
  }

  // Load saved projects list
  async function refreshProjectList() {
    const res = await fetch("/api/projects");
    const data = await res.json();
    const current = state.projectId || "";
    projectSelect.innerHTML = '<option value="">New song…</option>';
    for (const p of data.projects || []) {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = `${p.title} (${formatTime(p.duration)})`;
      if (p.id === current) opt.selected = true;
      projectSelect.appendChild(opt);
    }
  }

  async function loadProject(projectId) {
    if (!projectId) {
      resetToNewProject();
      return;
    }
    const res = await fetch(`/api/projects/${projectId}`);
    if (!res.ok) {
      showToast("Could not load project.");
      return;
    }
    const data = await res.json();
    applyProjectData(data);
  }

  function resetToNewProject() {
    state.projectId = null;
    state.pendingAudioFile = null;
    state.pendingCoverFile = null;
    state.duration = 0;
    state.timings = null;
    state.coverImg = null;
    state.selectedWord = null;
    state.dirty = false;
    state.settings = {
      title: "",
      artist: "",
      theme_name: "midnight",
      accent_color: THEMES.midnight.accent,
      use_cover_image: false,
      time_offset: 0.0,
      lyric_position: "center",
      bg_dim: 0.15,
      text_outline: "dark",
      show_neighbor_lines: false,
    };

    projectSelect.value = "";
    audioDropLabel.innerHTML = "<strong>Drop .mp3 here</strong> or click to browse";
    titleInput.value = "";
    artistInput.value = "";
    lyricsInput.value = "";
    audioPlayer.removeAttribute("src");
    audioPlayer.load();
    coverPreviewRow.classList.add("hidden");
    downloadLink.classList.add("hidden");
    wordInspector.classList.add("hidden");
    saveBtn.disabled = true;
    renderBtn.disabled = true;
    alignBtn.textContent = "Align Lyrics to Audio";
    syncControlsFromSettings();
    renderTimeline();
  }

  function applyProjectData(data) {
    state.projectId = data.id;
    state.pendingAudioFile = null;
    state.duration = data.duration || 0;
    state.timings = data.timings || null;
    const normalizeOutline = (val) =>
      val === false || val === "none" ? "none" : val === "white" ? "white" : "dark";
    state.settings = {
      title: data.settings?.title ?? "",
      artist: data.settings?.artist ?? "",
      theme_name: data.settings?.theme_name ?? "midnight",
      accent_color: data.settings?.accent_color ?? THEMES.midnight.accent,
      use_cover_image: Boolean(data.settings?.use_cover_image && data.has_cover),
      time_offset: Number(data.settings?.time_offset ?? 0),
      lyric_position: data.settings?.lyric_position ?? (data.has_cover ? "bottom" : "center"),
      bg_dim: Number(data.settings?.bg_dim ?? 0.15),
      text_outline: normalizeOutline(data.settings?.text_outline),
      show_neighbor_lines: Boolean(data.settings?.show_neighbor_lines ?? false),
    };
    state.selectedWord = null;
    state.dirty = false;

    audioDropLabel.innerHTML = `<strong>${escapeHtml(data.audio_filename)}</strong> (${formatTime(state.duration)})`;
    titleInput.value = state.settings.title;
    artistInput.value = state.settings.artist;
    lyricsInput.value = data.lyrics || "";
    audioPlayer.src = data.audio_url;
    alignBtn.textContent = state.timings ? "Re-Align Lyrics" : "Align Lyrics to Audio";

    if (data.has_cover && data.cover_url) {
      loadCoverImageUrl(data.cover_url);
    } else {
      state.coverImg = null;
      coverPreviewRow.classList.add("hidden");
    }

    if (data.has_video && data.video_url) {
      downloadLink.href = data.video_url;
      downloadLink.classList.remove("hidden");
    } else {
      downloadLink.classList.add("hidden");
    }

    saveBtn.disabled = false;
    renderBtn.disabled = !state.timings;
    wordInspector.classList.add("hidden");
    syncControlsFromSettings();
    renderTimeline();
    refreshProjectList();
  }

  function loadCoverImageUrl(url) {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      state.coverImg = img;
    };
    img.src = url;
    coverThumb.src = url;
    coverPreviewRow.classList.remove("hidden");
  }

  function syncControlsFromSettings() {
    const mode = state.settings.use_cover_image ? "cover" : "gradient";
    bgModeRadios.forEach((r) => (r.checked = r.value === mode));
    gradientOptions.classList.toggle("hidden", mode === "cover");
    coverOptions.classList.toggle("hidden", mode !== "cover");

    accentColorInput.value = state.settings.accent_color;
    accentColorHex.textContent = state.settings.accent_color;
    offsetSlider.value = String(state.settings.time_offset);
    offsetValue.textContent = `${state.settings.time_offset >= 0 ? "+" : ""}${state.settings.time_offset.toFixed(2)}s`;
    updateRangeProgressVar(offsetSlider);

    const dimPct = Math.round((state.settings.bg_dim ?? 0.15) * 100);
    bgDimSlider.value = String(dimPct);
    bgDimValue.textContent = `${dimPct}%`;
    updateRangeProgressVar(bgDimSlider);

    lyricPosRadios.forEach((r) => (r.checked = r.value === (state.settings.lyric_position || "center")));
    const outlineVal = state.settings.text_outline === "white" ? "white" : state.settings.text_outline === "none" ? "none" : "dark";
    textOutlineRadios.forEach((r) => (r.checked = r.value === outlineVal));
    showNeighborsInput.checked = Boolean(state.settings.show_neighbor_lines);

    updateThemeActiveUI();
  }

  function updateRangeProgressVar(slider) {
    const min = Number(slider.min);
    const max = Number(slider.max);
    const val = Number(slider.value);
    const pct = ((val - min) / (max - min)) * 100;
    slider.style.setProperty("--progress", `${pct}%`);
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // Dropzone wiring
  function setupDropzone(zone, input, onFile) {
    zone.addEventListener("click", () => input.click());
    zone.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        input.click();
      }
    });
    ["dragenter", "dragover"].forEach((ev) =>
      zone.addEventListener(ev, (e) => {
        e.preventDefault();
        zone.classList.add("dragover");
      })
    );
    ["dragleave", "drop"].forEach((ev) =>
      zone.addEventListener(ev, (e) => {
        e.preventDefault();
        zone.classList.remove("dragover");
      })
    );
    zone.addEventListener("drop", (e) => {
      const file = e.dataTransfer?.files?.[0];
      if (file) onFile(file);
    });
    input.addEventListener("change", () => {
      const file = input.files?.[0];
      if (file) onFile(file);
      input.value = "";
    });
  }

  setupDropzone(audioDropZone, audioInput, (file) => {
    state.pendingAudioFile = file;
    state.projectId = null;
    state.timings = null;
    audioDropLabel.innerHTML = `<strong>${escapeHtml(file.name)}</strong> (ready to align)`;
    if (!titleInput.value.trim()) {
      titleInput.value = file.name.replace(/\.[^.]+$/, "");
      state.settings.title = titleInput.value;
    }
    const objUrl = URL.createObjectURL(file);
    audioPlayer.src = objUrl;
    audioPlayer.addEventListener(
      "loadedmetadata",
      () => {
        state.duration = audioPlayer.duration || 0;
      },
      { once: true }
    );
    renderBtn.disabled = true;
    downloadLink.classList.add("hidden");
    alignBtn.textContent = "Align Lyrics to Audio";
    renderTimeline();
  });

  setupDropzone(coverDropZone, coverInput, async (file) => {
    if (state.projectId) {
      const fd = new FormData();
      fd.append("cover", file);
      const res = await fetch(`/api/projects/${state.projectId}/cover`, {
        method: "POST",
        body: fd,
      });
      if (res.ok) {
        const data = await res.json();
        state.settings.use_cover_image = true;
        if (state.settings.lyric_position === "center") {
          state.settings.lyric_position = "bottom";
        }
        loadCoverImageUrl(data.cover_url);
        syncControlsFromSettings();
        markDirty();
        showToast("Background image uploaded (lyrics moved to Bottom — change anytime).");
      }
    } else {
      state.pendingCoverFile = file;
      state.settings.use_cover_image = true;
      if (state.settings.lyric_position === "center") {
        state.settings.lyric_position = "bottom";
      }
      loadCoverImageUrl(URL.createObjectURL(file));
      syncControlsFromSettings();
    }
  });

  // Allow dropping a .txt file directly onto the lyrics textarea
  lyricsInput.addEventListener("dragover", (e) => e.preventDefault());
  lyricsInput.addEventListener("drop", async (e) => {
    const file = e.dataTransfer?.files?.[0];
    if (file && file.name.endsWith(".txt")) {
      e.preventDefault();
      lyricsInput.value = await file.text();
      showToast(`Loaded lyrics from ${file.name}`);
    }
  });

  removeCoverBtn.addEventListener("click", async () => {
    state.pendingCoverFile = null;
    state.coverImg = null;
    state.settings.use_cover_image = false;
    coverPreviewRow.classList.add("hidden");
    if (state.projectId) {
      await fetch(`/api/projects/${state.projectId}/cover`, { method: "DELETE" });
    }
    syncControlsFromSettings();
  });

  // Style control listeners
  bgModeRadios.forEach((radio) => {
    radio.addEventListener("change", () => {
      state.settings.use_cover_image = radio.value === "cover";
      syncControlsFromSettings();
      markDirty();
    });
  });

  titleInput.addEventListener("input", () => {
    state.settings.title = titleInput.value;
    markDirty();
  });

  artistInput.addEventListener("input", () => {
    state.settings.artist = artistInput.value;
    markDirty();
  });

  accentColorInput.addEventListener("input", () => {
    state.settings.accent_color = accentColorInput.value;
    accentColorHex.textContent = accentColorInput.value;
    markDirty();
  });

  offsetSlider.addEventListener("input", () => {
    state.settings.time_offset = Number(offsetSlider.value);
    offsetValue.textContent = `${state.settings.time_offset >= 0 ? "+" : ""}${state.settings.time_offset.toFixed(2)}s`;
    updateRangeProgressVar(offsetSlider);
    markDirty();
  });

  bgDimSlider.addEventListener("input", () => {
    const pct = Number(bgDimSlider.value);
    state.settings.bg_dim = pct / 100;
    bgDimValue.textContent = `${pct}%`;
    updateRangeProgressVar(bgDimSlider);
    markDirty();
  });

  lyricPosRadios.forEach((radio) => {
    radio.addEventListener("change", () => {
      state.settings.lyric_position = radio.value;
      markDirty();
    });
  });

  textOutlineRadios.forEach((radio) => {
    radio.addEventListener("change", () => {
      state.settings.text_outline = radio.value;
      markDirty();
    });
  });

  showNeighborsInput.addEventListener("change", () => {
    state.settings.show_neighbor_lines = showNeighborsInput.checked;
    markDirty();
  });

  projectSelect.addEventListener("change", () => loadProject(projectSelect.value));
  newProjectBtn.addEventListener("click", resetToNewProject);

  // Job polling helper
  async function pollJob(jobId, statusBox, textEl, pctEl, progressEl) {
    statusBox.classList.remove("hidden");
    while (true) {
      const res = await fetch(`/api/jobs/${jobId}`);
      if (!res.ok) throw new Error("Lost connection to job status.");
      const job = await res.json();
      const pct = Math.round((job.progress || 0) * 100);
      textEl.textContent = job.message || "Working…";
      pctEl.textContent = `${pct}%`;
      progressEl.value = pct;

      if (job.status === "done") return job.result;
      if (job.status === "error") throw new Error(job.error || "Job failed");
      await new Promise((r) => setTimeout(r, 600));
    }
  }

  // Align button
  alignBtn.addEventListener("click", async () => {
    const lyrics = lyricsInput.value.trim();
    if (!lyrics) {
      showToast("Please paste your lyrics first.");
      lyricsInput.focus();
      return;
    }

    alignBtn.disabled = true;
    try {
      // Create project first if needed
      if (!state.projectId) {
        if (!state.pendingAudioFile) {
          showToast("Please drop or select an .mp3 audio file first.");
          return;
        }
        const fd = new FormData();
        fd.append("audio", state.pendingAudioFile);
        fd.append("lyrics", lyrics);
        fd.append("title", state.settings.title);
        fd.append("artist", state.settings.artist);
        if (state.pendingCoverFile) {
          fd.append("cover", state.pendingCoverFile);
        }
        const createRes = await fetch("/api/projects", { method: "POST", body: fd });
        if (!createRes.ok) {
          const err = await createRes.json().catch(() => ({}));
          throw new Error(err.detail || "Failed to upload audio");
        }
        const created = await createRes.json();
        applyProjectData(created);
      }

      const alignRes = await fetch(`/api/projects/${state.projectId}/align`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          lyrics,
          isolate_vocals: isolateVocalsInput.checked,
          model_name: modelSelect.value,
          language: "en",
        }),
      });
      if (!alignRes.ok) {
        const err = await alignRes.json().catch(() => ({}));
        throw new Error(err.detail || "Could not start alignment");
      }
      const { job_id } = await alignRes.json();
      const timings = await pollJob(
        job_id,
        alignStatus,
        alignStatusText,
        alignStatusPct,
        alignProgress
      );
      state.timings = timings;
      state.duration = timings.duration || state.duration;
      renderBtn.disabled = false;
      saveBtn.disabled = false;
      alignBtn.textContent = "Re-Align Lyrics";
      renderTimeline();
      showToast("Lyrics aligned! Hit Play to preview.");
    } catch (err) {
      showToast(err.message || "Alignment error");
      alignStatusText.textContent = err.message || "Alignment failed";
    } finally {
      alignBtn.disabled = false;
    }
  });

  // Save timings & settings
  async function saveCurrentProject(silent = false) {
    if (!state.projectId) return;
    const res = await fetch(`/api/projects/${state.projectId}/timings`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        timings: state.timings,
        settings: state.settings,
        lyrics: lyricsInput.value,
      }),
    });
    if (res.ok) {
      state.dirty = false;
      if (!silent) showToast("Saved timings and settings.");
    }
  }

  saveBtn.addEventListener("click", () => saveCurrentProject(false));

  // Render MP4 button
  renderBtn.addEventListener("click", async () => {
    if (!state.projectId || !state.timings) return;
    renderBtn.disabled = true;
    downloadLink.classList.add("hidden");
    try {
      await saveCurrentProject(true);
      const res = await fetch(`/api/projects/${state.projectId}/render`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ settings: state.settings }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Could not start video render");
      }
      const { job_id } = await res.json();
      const result = await pollJob(
        job_id,
        renderStatus,
        renderStatusText,
        renderStatusPct,
        renderProgress
      );
      if (result?.video_url) {
        downloadLink.href = result.video_url;
        downloadLink.classList.remove("hidden");
      }
      showToast("MP4 exported and ready for X!");
    } catch (err) {
      showToast(err.message || "Render failed");
      renderStatusText.textContent = err.message || "Render failed";
    } finally {
      renderBtn.disabled = false;
    }
  });

  // Word Timing Editor
  function renderTimeline() {
    if (!state.timings?.lines?.length) {
      lyricsTimeline.innerHTML = `
        <div class="empty-state">
          Upload an MP3, paste lyrics, and click <strong>Align Lyrics to Audio</strong> to generate word-level karaoke timings.
        </div>`;
      return;
    }

    lyricsTimeline.innerHTML = "";
    state.timings.lines.forEach((line, lineIdx) => {
      const row = document.createElement("div");
      row.className = "lyric-line-row";
      row.dataset.lineIdx = String(lineIdx);

      const meta = document.createElement("div");
      meta.className = "line-meta";
      meta.innerHTML = `<span>Line ${lineIdx + 1}</span><span class="mono">${line.start.toFixed(2)}s – ${line.end.toFixed(2)}s</span>`;

      const pills = document.createElement("div");
      pills.className = "word-pills";

      line.words.forEach((word, wordIdx) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "word-pill";
        btn.textContent = word.text;
        btn.dataset.lineIdx = String(lineIdx);
        btn.dataset.wordIdx = String(wordIdx);
        if (
          state.selectedWord &&
          state.selectedWord.lineIdx === lineIdx &&
          state.selectedWord.wordIdx === wordIdx
        ) {
          btn.classList.add("is-selected");
        }
        btn.addEventListener("click", () => selectWord(lineIdx, wordIdx, true));
        pills.appendChild(btn);
      });

      row.appendChild(meta);
      row.appendChild(pills);
      lyricsTimeline.appendChild(row);
    });
  }

  function selectWord(lineIdx, wordIdx, seekAudio = false) {
    const word = state.timings?.lines?.[lineIdx]?.words?.[wordIdx];
    if (!word) return;
    state.selectedWord = { lineIdx, wordIdx };

    lyricsTimeline.querySelectorAll(".word-pill.is-selected").forEach((el) => el.classList.remove("is-selected"));
    const pill = lyricsTimeline.querySelector(`.word-pill[data-line-idx="${lineIdx}"][data-word-idx="${wordIdx}"]`);
    if (pill) pill.classList.add("is-selected");

    wordInspector.classList.remove("hidden");
    inspWordText.textContent = word.text;
    inspStart.value = word.start.toFixed(2);
    inspEnd.value = word.end.toFixed(2);

    if (seekAudio && audioPlayer.src) {
      audioPlayer.currentTime = Math.max(0, word.start + state.settings.time_offset);
    }
  }

  function updateSelectedWord(newStart, newEnd) {
    if (!state.selectedWord || !state.timings) return;
    const { lineIdx, wordIdx } = state.selectedWord;
    const line = state.timings.lines[lineIdx];
    const word = line.words[wordIdx];
    word.start = Math.max(0, Number(newStart.toFixed(3)));
    word.end = Math.max(word.start + 0.05, Number(newEnd.toFixed(3)));
    line.start = line.words[0].start;
    line.end = line.words[line.words.length - 1].end;

    inspStart.value = word.start.toFixed(2);
    inspEnd.value = word.end.toFixed(2);

    const row = lyricsTimeline.querySelector(`.lyric-line-row[data-line-idx="${lineIdx}"] .line-meta .mono`);
    if (row) row.textContent = `${line.start.toFixed(2)}s – ${line.end.toFixed(2)}s`;
    markDirty();
  }

  inspStart.addEventListener("change", () => updateSelectedWord(Number(inspStart.value), Number(inspEnd.value)));
  inspEnd.addEventListener("change", () => updateSelectedWord(Number(inspStart.value), Number(inspEnd.value)));
  inspStartMinus.addEventListener("click", () => updateSelectedWord(Number(inspStart.value) - 0.1, Number(inspEnd.value)));
  inspStartPlus.addEventListener("click", () => updateSelectedWord(Number(inspStart.value) + 0.1, Number(inspEnd.value)));
  inspEndMinus.addEventListener("click", () => updateSelectedWord(Number(inspStart.value), Number(inspEnd.value) - 0.1));
  inspEndPlus.addEventListener("click", () => updateSelectedWord(Number(inspStart.value), Number(inspEnd.value) + 0.1));
  inspSetStartNow.addEventListener("click", () => {
    const now = Math.max(0, audioPlayer.currentTime - state.settings.time_offset);
    updateSelectedWord(now, Math.max(now + 0.2, Number(inspEnd.value)));
  });
  inspSetEndNow.addEventListener("click", () => {
    const now = Math.max(0, audioPlayer.currentTime - state.settings.time_offset);
    updateSelectedWord(Number(inspStart.value), Math.max(Number(inspStart.value) + 0.05, now));
  });

  // Spacebar toggles play/pause when not typing in an input
  window.addEventListener("keydown", (e) => {
    if (e.code === "Space" && !["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes(document.activeElement?.tagName)) {
      if (audioPlayer.src) {
        e.preventDefault();
        if (audioPlayer.paused) audioPlayer.play();
        else audioPlayer.pause();
      }
    }
  });

  // ---------- Live 1080x1080 Karaoke Canvas Preview ----------
  function findActiveLineIndex(lines, t) {
    if (!lines || !lines.length) return -1;
    for (let i = 0; i < lines.length; i++) {
      if (t >= lines[i].start && t <= lines[i].end) return i;
    }
    for (let i = 0; i < lines.length; i++) {
      if (t < lines[i].start) {
        if (i === 0) return lines[i].start - t <= 1.2 ? 0 : -1;
        const prev = lines[i - 1];
        if (lines[i].start - t <= 0.45) return i;
        if (t - prev.end <= 2.5) return i - 1;
        return i;
      }
    }
    return lines.length - 1;
  }

  function wrapWords(words, maxWidth, spaceW) {
    const rows = [];
    let row = [];
    let rowW = 0;
    for (const w of words) {
      const ww = ctx.measureText(w.text).width;
      const needed = row.length ? rowW + spaceW + ww : ww;
      if (row.length && needed > maxWidth) {
        rows.push({ items: row, width: rowW });
        row = [{ word: w, width: ww }];
        rowW = ww;
      } else {
        row.push({ word: w, width: ww });
        rowW = needed;
      }
    }
    if (row.length) rows.push({ items: row, width: rowW });
    return rows;
  }

  function getOutlineStyle(outlineMode, alpha) {
    if (outlineMode === "none" || outlineMode === false) return null;
    if (outlineMode === "white") return `rgba(255, 255, 255, ${alpha})`;
    return `rgba(0, 0, 0, ${alpha})`;
  }

  function drawPlainLine(text, yCenter, fontSize, alpha, maxWidth, outlineMode = "dark") {
    ctx.save();
    ctx.font = `400 ${fontSize}px -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif`;
    ctx.textBaseline = "top";
    ctx.lineJoin = "round";
    const spaceW = ctx.measureText(" ").width;
    const words = text.split(/\s+/).map((t) => ({ text: t }));
    const rows = wrapWords(words, maxWidth, spaceW);
    const lineH = fontSize * 1.26;
    let y = yCenter - (rows.length * lineH) / 2;
    const strokeStyle = getOutlineStyle(outlineMode, Math.min(0.76, alpha * 1.4));

    for (const r of rows) {
      const lineStr = r.items.map((i) => i.word.text).join(" ");
      const tw = ctx.measureText(lineStr).width;
      const x = (1080 - tw) / 2;
      ctx.fillStyle = `rgba(0, 0, 0, ${Math.min(0.6, alpha)})`;
      ctx.fillText(lineStr, x, y + 2);
      if (strokeStyle) {
        ctx.lineWidth = 4;
        ctx.strokeStyle = strokeStyle;
        ctx.strokeText(lineStr, x, y);
      }
      ctx.fillStyle = `rgba(255, 255, 255, ${alpha})`;
      ctx.fillText(lineStr, x, y);
      y += lineH;
    }
    ctx.restore();
  }

  function drawActiveKaraokeLine(line, lyricT, yCenter, fontSize, accentHex, maxWidth, outlineMode = "dark") {
    ctx.save();
    ctx.font = `700 ${fontSize}px -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif`;
    ctx.textBaseline = "top";
    ctx.lineJoin = "round";
    const spaceW = ctx.measureText(" ").width;
    const rows = wrapWords(line.words, maxWidth, spaceW);
    const lineH = fontSize * 1.30;
    let y = yCenter - (rows.length * lineH) / 2;
    const [ar, ag, ab] = hexToRgbTuple(accentHex);
    const strokeStyle = getOutlineStyle(outlineMode, 0.92);

    for (const r of rows) {
      let x = (1080 - r.width) / 2;
      for (const { word, width } of r.items) {
        ctx.fillStyle = "rgba(0, 0, 0, 0.72)";
        ctx.fillText(word.text, x, y + 3);
        if (strokeStyle) {
          ctx.lineWidth = 7;
          ctx.strokeStyle = strokeStyle;
          ctx.strokeText(word.text, x, y);
        }
        ctx.fillStyle = strokeStyle ? "rgba(255, 255, 255, 0.96)" : "rgba(255, 255, 255, 0.86)";
        ctx.fillText(word.text, x, y);

        if (lyricT >= word.end) {
          if (strokeStyle) {
            ctx.lineWidth = 7;
            ctx.strokeStyle = strokeStyle;
            ctx.strokeText(word.text, x, y);
          }
          ctx.fillStyle = accentHex;
          ctx.fillText(word.text, x, y);
        } else if (lyricT > word.start) {
          const prog = Math.max(0, Math.min(1, (lyricT - word.start) / Math.max(0.04, word.end - word.start)));
          ctx.save();
          ctx.shadowColor = `rgba(${ar}, ${ag}, ${ab}, 0.75)`;
          ctx.shadowBlur = 18;
          ctx.beginPath();
          ctx.rect(x - 6, y - 10, width * prog + 6, lineH + 20);
          ctx.clip();
          if (strokeStyle) {
            ctx.lineWidth = 7;
            ctx.strokeStyle = strokeStyle;
            ctx.strokeText(word.text, x, y);
          }
          ctx.fillStyle = accentHex;
          ctx.fillText(word.text, x, y);
          ctx.restore();
        }
        x += width + spaceW;
      }
      y += lineH;
    }
    ctx.restore();
  }

  let lastHighlightedKey = "";

  function renderFrame(nowMs) {
    const t = audioPlayer.src ? audioPlayer.currentTime : nowMs / 1000;
    const duration = audioPlayer.duration || state.duration || 1;
    previewTime.textContent = `${formatTime(audioPlayer.currentTime || 0)} / ${formatTime(state.duration || 0)}`;

    // Live audio energy
    let targetEnergy = 0.18 + 0.08 * Math.sin(nowMs / 700);
    if (analyser && !audioPlayer.paused) {
      analyser.getByteFrequencyData(freqData);
      let sum = 0;
      for (let i = 0; i < 40; i++) sum += freqData[i];
      targetEnergy = Math.min(1, sum / (40 * 180));
    }
    smoothedEnergy += (targetEnergy - smoothedEnergy) * 0.16;

    const theme = THEMES[state.settings.theme_name] || THEMES.midnight;
    const accentHex = state.settings.accent_color || theme.accent;
    const [ar, ag, ab] = hexToRgbTuple(accentHex);

    const pos = state.settings.lyric_position || "center";
    const outlineMode = state.settings.text_outline || "dark";
    const hasOutline = outlineMode !== "none" && outlineMode !== false;
    const showNeighbors = Boolean(state.settings.show_neighbor_lines);

    // 1. Background
    if (state.settings.use_cover_image && state.coverImg) {
      const img = state.coverImg;
      const cycle = 0.5 - 0.5 * Math.cos(t * ((2 * Math.PI) / Math.max(duration, 18)));
      const zoom = 1.0 + 0.07 * cycle + 0.015 * smoothedEnergy;
      const baseScale = Math.max(1080 / img.width, 1080 / img.height) * zoom;
      const dw = img.width * baseScale;
      const dh = img.height * baseScale;
      const shiftX = (dw - 1080) * (0.5 + 0.14 * Math.sin(t * 0.17));
      const shiftY = (dh - 1080) * (0.5 + 0.14 * Math.cos(t * 0.13));
      ctx.drawImage(img, -shiftX, -shiftY, dw, dh);

      const dim = Math.max(0, Math.min(0.85, Number(state.settings.bg_dim ?? 0.15)));
      if (dim > 0.005) {
        ctx.fillStyle = `rgba(8, 10, 18, ${dim})`;
        ctx.fillRect(0, 0, 1080, 1080);
      }

      // Localized dark gradient scrim behind the lyric region
      if (pos === "bottom") {
        const y0 = showNeighbors ? 600 : 750;
        const scrim = ctx.createLinearGradient(0, y0, 0, 1080);
        scrim.addColorStop(0, "rgba(6, 8, 16, 0)");
        scrim.addColorStop(0.55, "rgba(6, 8, 16, 0.52)");
        scrim.addColorStop(1, "rgba(6, 8, 16, 0.86)");
        ctx.fillStyle = scrim;
        ctx.fillRect(0, y0, 1080, 1080 - y0);
      } else if (pos === "top") {
        const h = showNeighbors ? 480 : 330;
        const scrim = ctx.createLinearGradient(0, 0, 0, h);
        scrim.addColorStop(0, "rgba(6, 8, 16, 0.86)");
        scrim.addColorStop(0.55, "rgba(6, 8, 16, 0.52)");
        scrim.addColorStop(1, "rgba(6, 8, 16, 0)");
        ctx.fillStyle = scrim;
        ctx.fillRect(0, 0, 1080, h);
      } else {
        const topY = showNeighbors ? 220 : 370;
        const bandH = showNeighbors ? 640 : 340;
        const scrim = ctx.createLinearGradient(0, topY, 0, topY + bandH);
        scrim.addColorStop(0, "rgba(6, 8, 16, 0)");
        scrim.addColorStop(0.5, "rgba(6, 8, 16, 0.65)");
        scrim.addColorStop(1, "rgba(6, 8, 16, 0)");
        ctx.fillStyle = scrim;
        ctx.fillRect(0, topY, 1080, bandH);
      }
    } else {
      const grad = ctx.createLinearGradient(
        540 - 540 * Math.cos(t * 0.15),
        540 - 540 * Math.sin(t * 0.15),
        540 + 540 * Math.cos(t * 0.15),
        540 + 540 * Math.sin(t * 0.15)
      );
      grad.addColorStop(0, theme.bg1);
      grad.addColorStop(1, theme.bg2);
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, 1080, 1080);

      // Ambient orb 1
      const o1x = (0.28 + 0.22 * Math.sin(t * 0.37)) * 1080;
      const o1y = (0.30 + 0.20 * Math.cos(t * 0.29)) * 1080;
      const g1 = ctx.createRadialGradient(o1x, o1y, 10, o1x, o1y, 520 + 90 * smoothedEnergy);
      g1.addColorStop(0, `rgba(${theme.orb1}, ${0.28 + 0.16 * smoothedEnergy})`);
      g1.addColorStop(1, `rgba(${theme.orb1}, 0)`);
      ctx.fillStyle = g1;
      ctx.fillRect(0, 0, 1080, 1080);

      // Ambient orb 2
      const o2x = (0.72 + 0.20 * Math.cos(t * 0.31)) * 1080;
      const o2y = (0.72 + 0.22 * Math.sin(t * 0.23)) * 1080;
      const g2 = ctx.createRadialGradient(o2x, o2y, 10, o2x, o2y, 500 + 80 * smoothedEnergy);
      g2.addColorStop(0, `rgba(${theme.orb2}, ${0.24 + 0.14 * smoothedEnergy})`);
      g2.addColorStop(1, `rgba(${theme.orb2}, 0)`);
      ctx.fillStyle = g2;
      ctx.fillRect(0, 0, 1080, 1080);
    }

    // 2. Optional Header (opposite lyrics when lyrics are at Top; subtle dark shadow only)
    ctx.save();
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    const hdrY = pos === "top" ? 896 : 42;
    if (state.settings.title.trim()) {
      ctx.font = '700 44px -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif';
      ctx.fillStyle = "rgba(0, 0, 0, 0.75)";
      ctx.fillText(state.settings.title.trim(), 540, hdrY + 3);
      ctx.fillStyle = "rgba(255, 255, 255, 0.98)";
      ctx.fillText(state.settings.title.trim(), 540, hdrY);
    }
    if (state.settings.artist.trim()) {
      ctx.font = '500 30px -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif';
      ctx.fillStyle = "rgba(0, 0, 0, 0.68)";
      ctx.fillText(state.settings.artist.trim(), 540, hdrY + 57);
      ctx.fillStyle = "rgba(255, 255, 255, 0.88)";
      ctx.fillText(state.settings.artist.trim(), 540, hdrY + 54);
    }
    ctx.restore();

    // 3. Karaoke Lyrics
    const activeSize = pos === "center" ? 62 : showNeighbors ? 54 : 58;
    const neighborSize = pos === "center" ? 38 : 32;
    const [yPrev, yActive, yNext] =
      pos === "bottom"
        ? showNeighbors
          ? [745, 845, 940]
          : [745, 900, 940]
        : pos === "top"
          ? showNeighbors
            ? [140, 235, 330]
            : [140, 165, 330]
          : [340, 540, 740];

    const lines = state.timings?.lines;
    const lyricT = (audioPlayer.src ? audioPlayer.currentTime : 0) - state.settings.time_offset;
    if (lines?.length) {
      const activeIdx = findActiveLineIndex(lines, lyricT);
      if (activeIdx >= 0) {
        if (showNeighbors && activeIdx > 0) {
          drawPlainLine(lines[activeIdx - 1].text, yPrev, neighborSize, hasOutline ? 0.45 : 0.32, 940, outlineMode);
        }
        drawActiveKaraokeLine(lines[activeIdx], lyricT, yActive, activeSize, accentHex, 940, outlineMode);
        if (showNeighbors && activeIdx + 1 < lines.length) {
          drawPlainLine(lines[activeIdx + 1].text, yNext, neighborSize, hasOutline ? 0.56 : 0.43, 940, outlineMode);
        }

        // Sync active highlight in timeline editor without DOM thrashing
        let activeWordIdx = -1;
        lines[activeIdx].words.forEach((w, idx) => {
          if (lyricT >= w.start && lyricT <= w.end) activeWordIdx = idx;
        });
        const key = `${activeIdx}:${activeWordIdx}`;
        if (key !== lastHighlightedKey) {
          lastHighlightedKey = key;
          lyricsTimeline.querySelectorAll(".lyric-line-row.is-active").forEach((el) => el.classList.remove("is-active"));
          lyricsTimeline.querySelectorAll(".word-pill.is-playing").forEach((el) => el.classList.remove("is-playing"));
          const activeRow = lyricsTimeline.querySelector(`.lyric-line-row[data-line-idx="${activeIdx}"]`);
          if (activeRow) activeRow.classList.add("is-active");
          if (activeWordIdx >= 0) {
            const activePill = lyricsTimeline.querySelector(
              `.word-pill[data-line-idx="${activeIdx}"][data-word-idx="${activeWordIdx}"]`
            );
            if (activePill) activePill.classList.add("is-playing");
          }
        }
      }
    } else {
      drawPlainLine("Your lyrics will glow here", yActive - 30, 42, 0.55, 900, outlineMode);
      drawPlainLine("word by word in karaoke sync", yActive + 32, 30, 0.42, 900, outlineMode);
    }

    // 4. Bottom progress bar
    const prog = audioPlayer.src && duration > 0 ? Math.max(0, Math.min(1, audioPlayer.currentTime / duration)) : 0.35;
    ctx.fillStyle = "rgba(255, 255, 255, 0.19)";
    ctx.beginPath();
    ctx.roundRect(96, 1016, 888, 6, 3);
    ctx.fill();
    if (prog > 0.005) {
      ctx.fillStyle = accentHex;
      ctx.beginPath();
      ctx.roundRect(96, 1016, 888 * prog, 6, 3);
      ctx.fill();
    }

    requestAnimationFrame(renderFrame);
  }

  // Init
  buildThemeSwatches();
  syncControlsFromSettings();
  refreshProjectList();
  requestAnimationFrame(renderFrame);
})();

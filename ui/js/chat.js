/**
 * ICICI Pru FAQ chat UI — wired to FastAPI backend.
 */

const API_BASE = window.location.origin;

const OPENING_GREETING_FALLBACK =
  "Welcome to IND money's intelligence bot, type question to begin";

const state = {
  config: null,
  sessionId: null,
  theme: localStorage.getItem("rag-ui-theme") || "light",
  fontScale: Number(localStorage.getItem("rag-ui-font-scale") || "1"),
  chatUserMessageCount: 0,
  experienceLevelChosen: false,
  awaitingExperience: false,
  greetingShown: false,
  pendingQuestion: null,
  loading: false,
  messages: [],
};

/** Single-flight session creation (prevents openChat + send racing and wiping messages). */
let sessionReadyPromise = null;

const els = {
  overlay: document.getElementById("chat-overlay"),
  backdrop: document.getElementById("chat-backdrop"),
  fab: document.getElementById("chat-fab"),
  close: document.getElementById("chat-close"),
  main: document.getElementById("chat-main"),
  messages: document.getElementById("messages"),
  input: document.getElementById("chat-input"),
  sendBtn: document.getElementById("send-btn"),
  disclaimer: document.getElementById("disclaimer-line"),
  learningsPrompt: document.getElementById("learnings-prompt"),
  learningsText: document.getElementById("learnings-text"),
  learningsDownload: document.getElementById("learnings-download"),
  a11yToggle: document.getElementById("a11y-toggle"),
  a11yPanel: document.getElementById("a11y-panel"),
  textSizeGroup: document.getElementById("text-size-group"),
  themeGroup: document.getElementById("theme-group"),
};

const TEXT_SCALES = [
  { id: "1", label: "Normal", value: 1 },
  { id: "1.12", label: "Large", value: 1.12 },
  { id: "1.25", label: "Extra large", value: 1.25 },
];

function escapeHtml(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatAnswerHtml(raw) {
  let text = escapeHtml(raw.trim());
  text = text.replace(
    /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>',
  );
  text = text.replace(
    /(?<!href="|">)(https?:\/\/[^\s<]+)/g,
    (url) => `<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`,
  );
  const parts = text.split(/\n\n+/);
  return parts.map((p) => `<p>${p.replace(/\n/g, "<br>")}</p>`).join("");
}

function formatTime(date = new Date()) {
  return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function openingGreetingText() {
  return state.config?.opening_greeting || OPENING_GREETING_FALLBACK;
}

function applyTheme(themeId) {
  state.theme = themeId;
  document.documentElement.setAttribute("data-theme", themeId);
  localStorage.setItem("rag-ui-theme", themeId);
  document.querySelectorAll("#theme-group .a11y-option").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.value === themeId);
  });
}

function applyFontScale(scale) {
  state.fontScale = scale;
  document.documentElement.style.setProperty("--font-scale", String(scale));
  localStorage.setItem("rag-ui-font-scale", String(scale));
  document.querySelectorAll("#text-size-group .a11y-option").forEach((btn) => {
    btn.classList.toggle("active", Number(btn.dataset.value) === scale);
  });
}

function setLoading(loading) {
  state.loading = loading;
  els.sendBtn.disabled = loading;
  els.sendBtn.classList.toggle("loading", loading);
  if (!loading) {
    els.input.disabled = false;
  }
}

function setInputEnabled(enabled) {
  if (!state.loading) {
    els.input.disabled = !enabled;
  }
}

function updateLearningsPrompt() {
  const show = state.chatUserMessageCount >= 2 && state.sessionId;
  els.learningsPrompt.classList.toggle("hidden", !show);
}

function scrollToBottom() {
  requestAnimationFrame(() => {
    els.main.scrollTop = els.main.scrollHeight;
  });
}

function renderMessages() {
  els.messages.innerHTML = "";

  state.messages.forEach((msg) => {
    const row = document.createElement("div");
    row.className = `message-row ${msg.role}`;

    if (msg.role === "bot") {
      const avatar = document.createElement("div");
      avatar.className = "message-avatar";
      avatar.innerHTML = '<img src="assets/indmoney-logo.svg" alt="" />';
      row.appendChild(avatar);
    }

    const wrap = document.createElement("div");
    wrap.className = "message-wrap";
    const bubble = document.createElement("div");
    bubble.className = `bubble ${msg.role}`;
    if (msg.role === "bot") {
      bubble.innerHTML = formatAnswerHtml(msg.text);
      if (msg.inlineChips?.length && !msg.levelResponded) {
        const chips = document.createElement("div");
        chips.className = "inline-chips";
        msg.inlineChips.forEach((chip) => {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "inline-chip";
          btn.textContent = chip.label;
          btn.addEventListener("click", () => handleExperienceSelect(chip.level));
          chips.appendChild(btn);
        });
        bubble.appendChild(chips);
      } else if (msg.selectedLevelLabel) {
        const picked = document.createElement("div");
        picked.className = "level-selection-note";
        picked.textContent = `Selected: ${msg.selectedLevelLabel}`;
        bubble.appendChild(picked);
      }
    } else {
      bubble.textContent = msg.text;
    }
    wrap.appendChild(bubble);

    const time = document.createElement("div");
    time.className = "message-time";
    time.textContent = formatTime(msg.time);
    wrap.appendChild(time);

    row.appendChild(wrap);
    els.messages.appendChild(row);
  });

  updateLearningsPrompt();
  scrollToBottom();
}

function markExperiencePromptResponded(selectedLabel) {
  const experienceMsg = state.messages.find((m) => m.inlineChips?.length);
  if (experienceMsg) {
    experienceMsg.levelResponded = true;
    experienceMsg.selectedLevelLabel = selectedLabel;
  }
}

function showExperiencePrompt() {
  if (state.experienceLevelChosen || !state.config || !state.pendingQuestion) return;
  if (state.awaitingExperience) return;
  state.awaitingExperience = true;
  const options = state.config.experience_level_options.map((o) => ({
    level: o.level,
    label: o.label,
  }));
  state.messages.push({
    role: "bot",
    text: state.config.experience_level_question,
    time: new Date(),
    inlineChips: options,
  });
  renderMessages();
}

function showOpeningGreeting() {
  if (state.greetingShown) return;
  state.greetingShown = true;
  state.messages.push({
    role: "bot",
    text: openingGreetingText(),
    time: new Date(),
  });
  renderMessages();
}

async function loadConfig() {
  const res = await fetch(`${API_BASE}/api/ui/config`);
  if (!res.ok) {
    throw new Error(`UI config failed (${res.status})`);
  }
  state.config = await res.json();

  els.input.placeholder = state.config.input_placeholder;
  els.learningsText.textContent = state.config.learnings_prompt;
  els.disclaimer.textContent = state.config.disclaimer_line;

  updateLearningsPrompt();

  TEXT_SCALES.forEach((s) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "a11y-option";
    btn.dataset.value = String(s.value);
    btn.textContent = s.label;
    btn.addEventListener("click", () => applyFontScale(s.value));
    els.textSizeGroup.appendChild(btn);
  });

  state.config.themes.forEach((t) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "a11y-option";
    btn.dataset.value = t.id;
    btn.textContent = t.label;
    btn.addEventListener("click", () => applyTheme(t.id));
    els.themeGroup.appendChild(btn);
  });
}

async function createSession() {
  const res = await fetch(`${API_BASE}/session`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ experience_level: "somewhat_familiar" }),
  });
  if (!res.ok) throw new Error("Failed to create session");
  const data = await res.json();
  state.sessionId = data.session_id;
  state.chatUserMessageCount = 0;
  state.experienceLevelChosen = false;
  state.awaitingExperience = false;
  state.greetingShown = false;
  state.pendingQuestion = null;
  state.messages = [];
  showOpeningGreeting();
}

async function ensureSession() {
  if (state.sessionId && state.greetingShown) return;
  if (sessionReadyPromise) {
    await sessionReadyPromise;
    return;
  }
  sessionReadyPromise = createSession();
  try {
    await sessionReadyPromise;
  } finally {
    sessionReadyPromise = null;
  }
}

async function callChat(question) {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: state.sessionId, message: question }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const detail = err.detail;
    if (detail && typeof detail === "object" && detail.error_category) {
      console.error(
        `chat API error [${detail.error_category}]:`,
        detail.message || detail,
      );
    }
    const detailText =
      typeof detail === "string" ? detail : JSON.stringify(detail);
    throw new Error(detailText || `Chat failed (${res.status})`);
  }
  return res.json();
}

async function fetchBotAnswer(question) {
  const data = await callChat(question);
  state.messages.push({
    role: "bot",
    text: data.answer,
    time: new Date(),
  });
  state.chatUserMessageCount += 1;
  renderMessages();
  return data;
}

async function answerPendingQuestion() {
  const question = state.pendingQuestion;
  if (!question || !state.sessionId) {
    setLoading(false);
    return;
  }
  state.pendingQuestion = null;

  setLoading(true);
  try {
    await fetchBotAnswer(question);
  } catch (err) {
    console.error("answerPendingQuestion failed:", err);
    state.messages.push({
      role: "bot",
      text: "Something went wrong while fetching a response. Please try again.",
      time: new Date(),
    });
    renderMessages();
  } finally {
    setLoading(false);
  }
}

async function handleExperienceSelect(level) {
  if (!state.sessionId || state.experienceLevelChosen || !state.awaitingExperience) return;

  const option = state.config?.experience_level_options?.find((o) => o.level === level);
  const selectedLabel = option?.label || level;

  if (!state.pendingQuestion) {
    state.messages.push({
      role: "bot",
      text: "Type your factual question first, then choose your experience level.",
      time: new Date(),
    });
    renderMessages();
    return;
  }

  state.experienceLevelChosen = true;
  state.awaitingExperience = false;
  markExperiencePromptResponded(selectedLabel);
  renderMessages();

  setLoading(true);
  try {
    const res = await fetch(`${API_BASE}/session/${state.sessionId}/experience-level`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ experience_level: level }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to set experience level");
    }
    await answerPendingQuestion();
  } catch (err) {
    console.error("handleExperienceSelect failed:", err);
    state.experienceLevelChosen = false;
    state.awaitingExperience = true;
    const experienceMsg = state.messages.find((m) => m.inlineChips?.length);
    if (experienceMsg) {
      experienceMsg.levelResponded = false;
      delete experienceMsg.selectedLevelLabel;
    }
    state.messages.push({
      role: "bot",
      text: "I couldn't update your experience level. Please try again.",
      time: new Date(),
    });
    renderMessages();
    setLoading(false);
  }
}

async function skipExperienceAndAnswerPending() {
  state.experienceLevelChosen = true;
  state.awaitingExperience = false;
  markExperiencePromptResponded("Skipped");
  renderMessages();
  await answerPendingQuestion();
}

function isExperienceLevelLabel(text) {
  const labels = state.config?.experience_level_options?.map((o) => o.label.toLowerCase()) || [];
  return labels.includes(text.trim().toLowerCase());
}

async function shouldPromptExperienceLevel(question) {
  try {
    const res = await fetch(`${API_BASE}/api/ui/experience-prompt-gate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: question }),
    });
    if (!res.ok) return false;
    const data = await res.json();
    return Boolean(data.prompt_experience_level);
  } catch (err) {
    console.error("shouldPromptExperienceLevel failed:", err);
    return false;
  }
}

async function sendUserMessage(text) {
  const trimmed = text.trim();
  if (!trimmed || state.loading) return;

  setInputEnabled(false);
  try {
    await ensureSession();
  } catch (err) {
    console.error(err);
    state.messages.push({
      role: "bot",
      text: "Could not start a session. Ensure Postgres is running (docker compose up -d postgres).",
      time: new Date(),
    });
    renderMessages();
    setInputEnabled(true);
    return;
  }

  els.input.value = "";

  if (state.awaitingExperience) {
    await skipExperienceAndAnswerPending();
    setInputEnabled(true);
    return;
  }

  if (isExperienceLevelLabel(trimmed) && !state.pendingQuestion) {
    state.messages.push({
      role: "bot",
      text: "Type your factual question first, then choose New, Somewhat familiar, or Expert.",
      time: new Date(),
    });
    renderMessages();
    setInputEnabled(true);
    return;
  }

  state.messages.push({ role: "user", text: trimmed, time: new Date() });
  renderMessages();

  if (!state.experienceLevelChosen) {
    const needsExperience = await shouldPromptExperienceLevel(trimmed);
    if (needsExperience) {
      state.pendingQuestion = trimmed;
      showExperiencePrompt();
      setInputEnabled(true);
      return;
    }
  }

  setLoading(true);
  try {
    await fetchBotAnswer(trimmed);
  } catch (err) {
    console.error("sendUserMessage failed:", err);
    state.messages.push({
      role: "bot",
      text: "Something went wrong while fetching a response. Please try again.",
      time: new Date(),
    });
    renderMessages();
  } finally {
    setLoading(false);
  }
}

async function downloadLearnings() {
  if (!state.sessionId) return;
  try {
    const res = await fetch(`${API_BASE}/learnings/${state.sessionId}`);
    if (!res.ok) throw new Error("Download failed");
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "icici_pru_chat_learnings.pdf";
    a.click();
    URL.revokeObjectURL(url);
  } catch (err) {
    console.error(err);
    alert("Could not download learnings PDF. Try again after more conversation.");
  }
}

async function openChat() {
  els.overlay.hidden = false;
  els.overlay.classList.add("open");
  document.body.style.overflow = "hidden";
  setInputEnabled(false);
  try {
    await ensureSession();
    els.input.focus();
  } catch (err) {
    console.error(err);
    if (state.messages.length === 0) {
      state.messages.push({
        role: "bot",
        text: "Could not start a chat session. Check that Postgres is running and DATABASE_URL is set.",
        time: new Date(),
      });
      renderMessages();
    }
  } finally {
    setInputEnabled(true);
  }
}

function closeChat() {
  els.overlay.classList.remove("open");
  els.overlay.hidden = true;
  document.body.style.overflow = "";
  els.a11yPanel.classList.remove("open");
  els.a11yToggle.setAttribute("aria-expanded", "false");
}

function bindEvents() {
  els.fab.addEventListener("click", () => openChat());
  els.close.addEventListener("click", closeChat);
  els.backdrop.addEventListener("click", closeChat);

  els.sendBtn.addEventListener("click", () => sendUserMessage(els.input.value));
  els.input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendUserMessage(els.input.value);
    }
  });

  els.learningsDownload.addEventListener("click", downloadLearnings);

  els.a11yToggle.addEventListener("click", () => {
    const open = els.a11yPanel.classList.toggle("open");
    els.a11yToggle.setAttribute("aria-expanded", open ? "true" : "false");
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && els.overlay.classList.contains("open")) {
      closeChat();
    }
  });
}

async function init() {
  applyTheme(state.theme);
  applyFontScale(state.fontScale);
  bindEvents();
  updateLearningsPrompt();
  try {
    await loadConfig();
  } catch (err) {
    console.error(err);
    els.disclaimer.textContent =
      "Could not connect to the FAQ API. Start the backend server first.";
  }
}

init();

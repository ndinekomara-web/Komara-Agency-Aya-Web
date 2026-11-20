/* Aya — client web (aucune dépendance) */
(() => {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const els = {
    app: $("#app"),
    splash: $("#splash"),
    thread: $("#messages"),
    welcome: $("#welcome"),
    input: $("#input"),
    form: $("#composer"),
    send: $("#send"),
    lang: $("#lang"),
    new: $("#new"),
    install: $("#install"),
    login: $("#login"),
    loginForm: $("#login-form"),
    loginToken: $("#login-token"),
    loginError: $("#login-error"),
    viewer: $("#viewer"),
    viewerImg: $("#viewer-img"),
    viewerClose: $("#viewer-close"),
    settings: $("#settings"),
    sheet: $("#settings-sheet"),
    sheetClose: $("#sheet-close"),
    sheetLang: $("#sheet-lang"),
    actInstall: $("#act-install"),
    actClear: $("#act-clear"),
    actAdmin: $("#act-admin"),
    toast: $("#toast"),
  };

  let config = { auth_required: false, languages: ["fr", "ar", "en"], default_language: "fr" };
  let sessionId = localStorage.getItem("aya_session") || "";
  let busy = false;
  let gallery = [];
  let installEvent = null;

  const AVATAR = "/static/icons/avatar.png";

  /* ------------------------------ réseau ------------------------------ */
  async function api(path, options = {}) {
    const response = await fetch(path, {
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    if (response.status === 401 && config.auth_required && path !== "/api/login") {
      showLogin();
      throw new Error("unauthorized");
    }
    if (!response.ok) {
      let detail = "";
      try { detail = (await response.json()).detail || ""; } catch { /* ignore */ }
      throw new Error(detail || `http_${response.status}`);
    }
    return response.status === 204 ? {} : response.json();
  }

  /* ------------------------------ rendu ------------------------------ */
  let lastDay = "";

  const timeNow = () =>
    new Date().toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });

  function dayKey(date = new Date()) {
    return date.toISOString().slice(0, 10);
  }

  function addDay(date = new Date()) {
    const key = dayKey(date);
    if (key === lastDay) return;
    lastDay = key;
    const label = document.createElement("div");
    label.className = "day";
    const today = dayKey();
    const yesterday = dayKey(new Date(Date.now() - 86400000));
    label.textContent = key === today ? "Aujourd'hui" : key === yesterday ? "Hier" : date.toLocaleDateString("fr-FR");
    els.thread.appendChild(label);
  }

  function toast(text) {
    els.toast.textContent = text;
    els.toast.hidden = false;
    clearTimeout(toast._t);
    toast._t = setTimeout(() => { els.toast.hidden = true; }, 1600);
  }

  function addMessage(role, text, when) {
    els.welcome.hidden = true;
    addDay(when ? new Date(when * 1000) : new Date());
    const row = document.createElement("div");
    row.className = `msg ${role}`;
    if (role === "assistant") {
      const face = document.createElement("img");
      face.src = AVATAR;
      face.alt = "";
      face.className = "face";
      row.appendChild(face);
    }
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = text;
    const meta = document.createElement("span");
    meta.className = "meta";
    meta.textContent = when ? new Date(when * 1000).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }) : timeNow();
    bubble.appendChild(meta);
    // Appui long / double-clic : copier le message
    let pressTimer;
    const copy = () => {
      navigator.clipboard?.writeText(text).then(() => toast("Message copié")).catch(() => {});
    };
    bubble.addEventListener("dblclick", copy);
    bubble.addEventListener("touchstart", () => { pressTimer = setTimeout(copy, 650); }, { passive: true });
    bubble.addEventListener("touchend", () => clearTimeout(pressTimer));
    bubble.addEventListener("touchmove", () => clearTimeout(pressTimer));
    row.appendChild(bubble);
    els.thread.appendChild(row);
    scrollDown();
    return bubble;
  }

  function addGallery(items) {
    if (!items || !items.length) return;
    const box = document.createElement("div");
    box.className = "gallery";
    items.forEach((item) => {
      const btn = document.createElement("button");
      btn.className = "shot";
      btn.type = "button";
      const img = document.createElement("img");
      img.src = item.url;
      img.alt = item.title || "";
      img.loading = "lazy";
      const caption = document.createElement("span");
      caption.textContent = item.title || "";
      btn.append(img, caption);
      btn.addEventListener("click", () => openViewer(item));
      box.appendChild(btn);
    });
    const row = document.createElement("div");
    row.className = "msg assistant";
    row.appendChild(box);
    els.thread.appendChild(row);
    scrollDown();
  }

  function addTyping() {
    const row = document.createElement("div");
    row.className = "msg assistant";
    row.id = "typing";
    const face = document.createElement("img");
    face.src = AVATAR;
    face.alt = "";
    face.className = "face";
    const bubble = document.createElement("div");
    bubble.className = "bubble typing";
    bubble.innerHTML = "<i></i><i></i><i></i>";
    row.append(face, bubble);
    els.thread.appendChild(row);
    scrollDown();
  }

  const removeTyping = () => $("#typing")?.remove();

  function scrollDown() {
    requestAnimationFrame(() => { els.thread.scrollTop = els.thread.scrollHeight; });
  }

  function openViewer(item) {
    els.viewerImg.src = item.url;
    els.viewerImg.alt = item.title || "";
    els.viewer.hidden = false;
  }

  /* ------------------------------ envoi ------------------------------ */
  async function send(text) {
    const message = (text ?? els.input.value).trim();
    if (!message || busy) return;
    busy = true;
    els.send.disabled = true;
    els.input.value = "";
    els.input.style.height = "auto";
    addMessage("user", message);
    addTyping();
    try {
      const data = await api("/api/chat", {
        method: "POST",
        body: JSON.stringify({ message, session_id: sessionId || undefined }),
      });
      removeTyping();
      if (data.session_id) {
        sessionId = data.session_id;
        localStorage.setItem("aya_session", sessionId);
      }
      addMessage("assistant", data.reply);
      if (data.gallery) addGallery(gallery);
    } catch (error) {
      removeTyping();
      if (error.message !== "unauthorized") {
        addMessage("assistant", "Problème de connexion. Réessaie dans un instant.");
      }
    } finally {
      busy = false;
      els.send.disabled = false;
      els.input.focus();
    }
  }

  /* ------------------------------ session ------------------------------ */
  async function loadHistory() {
    if (!sessionId) return;
    try {
      const data = await api(`/api/history?session_id=${encodeURIComponent(sessionId)}&limit=60`);
      (data.messages || []).forEach((m) =>
        addMessage(m.role === "user" ? "user" : "assistant", m.content, m.created_at));
    } catch { /* historique facultatif */ }
  }

  async function loadGallery() {
    try {
      const data = await api("/api/portfolio");
      gallery = data.items || [];
    } catch { gallery = []; }
  }

  function applyLanguage(lang) {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  }

  async function start() {
    config = await api("/api/config");
    if (config.auth_required) {
      try {
        await api("/api/history?session_id=probe&limit=1");
      } catch (error) {
        if (error.message === "unauthorized") return; // la modale prend le relais
      }
    }
    els.app.hidden = false;
    els.splash.classList.add("gone");
    els.lang.value = config.default_language || "fr";
    applyLanguage(els.lang.value);
    await Promise.all([loadHistory(), loadGallery(), checkAdmin()]);
    if (!els.thread.children.length) els.welcome.hidden = false;
  }

  async function checkAdmin() {
    try {
      const data = await api("/api/admin/status");
      els.actAdmin.hidden = !data.is_admin;
    } catch { els.actAdmin.hidden = true; }
  }

  function showLogin() {
    els.app.hidden = true;
    els.splash.classList.add("gone");
    els.login.hidden = false;
    els.loginToken.focus();
  }

  /* ------------------------------ événements ------------------------------ */
  els.form.addEventListener("submit", (event) => {
    event.preventDefault();
    send();
  });

  els.input.addEventListener("input", () => {
    els.input.style.height = "auto";
    els.input.style.height = `${Math.min(els.input.scrollHeight, 132)}px`;
  });

  els.input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && window.innerWidth > 720) {
      event.preventDefault();
      send();
    }
  });

  document.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", () => send(chip.dataset.say));
  });

  els.lang.addEventListener("change", async () => {
    applyLanguage(els.lang.value);
    try {
      await api("/api/language", {
        method: "POST",
        body: JSON.stringify({ session_id: sessionId, lang: els.lang.value }),
      });
    } catch { /* la langue s'applique quand même côté interface */ }
  });

  els.new.addEventListener("click", async () => {
    try {
      await api("/api/reset", {
        method: "POST",
        body: JSON.stringify({ session_id: sessionId }),
      });
    } catch { /* on repart quand même */ }
    sessionId = "";
    localStorage.removeItem("aya_session");
    els.thread.innerHTML = "";
    els.welcome.hidden = false;
    els.input.focus();
  });

  els.loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    els.loginError.hidden = true;
    try {
      await api("/api/login", {
        method: "POST",
        body: JSON.stringify({ token: els.loginToken.value }),
      });
      els.loginToken.value = "";
      els.login.hidden = true;
      els.login.remove();
      await start();
    } catch {
      els.loginError.textContent = "Mot de passe incorrect.";
      els.loginError.hidden = false;
    }
  });

  els.settings.addEventListener("click", () => {
    els.sheetLang.value = els.lang.value;
    els.actInstall.hidden = !installEvent;
    els.sheet.hidden = false;
  });
  els.sheetClose.addEventListener("click", () => { els.sheet.hidden = true; });
  els.sheet.addEventListener("click", (event) => {
    if (event.target === els.sheet) els.sheet.hidden = true;
  });
  els.sheetLang.addEventListener("change", () => {
    els.lang.value = els.sheetLang.value;
    els.lang.dispatchEvent(new Event("change"));
  });
  els.actClear.addEventListener("click", () => {
    els.sheet.hidden = true;
    els.new.click();
    toast("Conversation vidée");
  });
  els.actInstall.addEventListener("click", () => {
    els.sheet.hidden = true;
    els.install.click();
  });

  els.viewerClose.addEventListener("click", () => { els.viewer.hidden = true; });
  els.viewer.addEventListener("click", (event) => {
    if (event.target === els.viewer) els.viewer.hidden = true;
  });

  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    installEvent = event;
    els.install.hidden = false;
  });

  els.install.addEventListener("click", async () => {
    if (!installEvent) return;
    installEvent.prompt();
    await installEvent.userChoice;
    installEvent = null;
    els.install.hidden = true;
  });

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/service-worker.js").catch(() => {});
    });
  }

  start().catch(() => {
    els.splash.classList.add("gone");
    els.app.hidden = false;
    els.welcome.hidden = false;
  });
})();

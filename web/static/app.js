/* Aya — client de conversation (PWA, aucun framework). */
(() => {
  "use strict";

  const STORAGE_SESSION = "aya.session";
  const STORAGE_LANG = "aya.lang";

  const els = {
    messages: document.getElementById("messages"),
    welcome: document.getElementById("welcome"),
    form: document.getElementById("composer"),
    input: document.getElementById("input"),
    send: document.getElementById("send"),
    lang: document.getElementById("lang"),
    reset: document.getElementById("reset"),
    install: document.getElementById("install"),
    login: document.getElementById("login"),
    loginForm: document.getElementById("login-form"),
    loginToken: document.getElementById("login-token"),
    loginError: document.getElementById("login-error"),
  };

  let sessionId = localStorage.getItem(STORAGE_SESSION) || "";
  let lang = localStorage.getItem(STORAGE_LANG) || "fr";
  let busy = false;
  let config = { languages: ["fr", "en", "ar"], auth_required: false };
  let deferredPrompt = null;

  /* ----------------------------- Utilitaires ----------------------------- */
  const newSessionId = () =>
    (crypto.randomUUID && crypto.randomUUID()) ||
    "s-" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);

  async function api(path, options = {}) {
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      ...options,
    });
    if (response.status === 401 && config.auth_required) {
      showLogin();
      throw new Error("unauthorized");
    }
    if (!response.ok) {
      let detail = "Erreur " + response.status;
      try {
        const body = await response.json();
        if (body && body.detail) detail = body.detail;
      } catch (_) {}
      throw new Error(detail);
    }
    return response.json();
  }

  function applyDirection(code) {
    document.documentElement.lang = code;
    document.documentElement.dir = code === "ar" ? "rtl" : "ltr";
  }

  /* ------------------------------ Rendu --------------------------------- */
  function hideWelcome() {
    if (els.welcome && els.welcome.parentNode) els.welcome.remove();
  }

  function addBubble(role, text) {
    hideWelcome();
    const wrapper = document.createElement("div");
    wrapper.className = `msg ${role}`;
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = text;
    wrapper.appendChild(bubble);
    els.messages.appendChild(wrapper);
    els.messages.scrollTop = els.messages.scrollHeight;
    return wrapper;
  }

  function showTyping() {
    hideWelcome();
    const wrapper = document.createElement("div");
    wrapper.className = "msg assistant";
    wrapper.id = "typing";
    wrapper.innerHTML = '<div class="bubble"><span class="typing"><i></i><i></i><i></i></span></div>';
    els.messages.appendChild(wrapper);
    els.messages.scrollTop = els.messages.scrollHeight;
  }

  function removeTyping() {
    const node = document.getElementById("typing");
    if (node) node.remove();
  }

  async function loadHistory() {
    if (!sessionId) return;
    try {
      const data = await api(`/api/history?session_id=${encodeURIComponent(sessionId)}&limit=100`);
      if (!data.messages || !data.messages.length) return;
      data.messages.forEach((m) => addBubble(m.role === "user" ? "user" : "assistant", m.content));
    } catch (_) {
      /* historique indisponible : on démarre simplement une conversation */
    }
  }

  /* ---------------------------- Conversation ---------------------------- */
  async function sendMessage(text) {
    const content = (text || "").trim();
    if (!content || busy) return;

    if (!sessionId) {
      sessionId = newSessionId();
      localStorage.setItem(STORAGE_SESSION, sessionId);
    }

    busy = true;
    els.send.disabled = true;
    addBubble("user", content);
    els.input.value = "";
    autoGrow();
    showTyping();

    try {
      const data = await api("/api/chat", {
        method: "POST",
        body: JSON.stringify({ message: content, session_id: sessionId, lang }),
      });
      removeTyping();
      addBubble("assistant", data.reply);
      if (data.lang && data.lang !== lang && config.languages.includes(data.lang)) {
        lang = data.lang;
        els.lang.value = lang;
        localStorage.setItem(STORAGE_LANG, lang);
        applyDirection(lang);
      }
    } catch (error) {
      removeTyping();
      if (error.message !== "unauthorized") {
        addBubble("error", "Connexion impossible. Vérifiez qu'Aya est bien démarrée, puis réessayez.");
      }
    } finally {
      busy = false;
      els.send.disabled = false;
      els.input.focus();
    }
  }

  function autoGrow() {
    els.input.style.height = "auto";
    els.input.style.height = Math.min(els.input.scrollHeight, 160) + "px";
  }

  /* ------------------------------ Connexion ----------------------------- */
  function showLogin() {
    if (!els.login) return;
    els.login.hidden = false;
    els.loginToken.focus();
  }

  els.loginForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    els.loginError.hidden = true;
    try {
      await api("/api/login", {
        method: "POST",
        body: JSON.stringify({ token: els.loginToken.value.trim() }),
      });
      els.loginToken.value = "";
      els.login.hidden = true;
      // Ceinture et bretelles : on retire la fenêtre du DOM, quel que soit le CSS.
      els.login.remove();
      await start();
    } catch (_) {
      els.loginError.textContent = "Mot de passe incorrect.";
      els.loginError.hidden = false;
    }
  });

  /* ------------------------------- Événements --------------------------- */
  els.form.addEventListener("submit", (event) => {
    event.preventDefault();
    sendMessage(els.input.value);
  });

  els.input.addEventListener("input", autoGrow);
  els.input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      sendMessage(els.input.value);
    }
  });

  document.addEventListener("click", (event) => {
    const chip = event.target.closest(".chip");
    if (chip && chip.dataset.prompt) sendMessage(chip.dataset.prompt);
  });

  els.lang.addEventListener("change", async () => {
    lang = els.lang.value;
    localStorage.setItem(STORAGE_LANG, lang);
    applyDirection(lang);
    if (sessionId) {
      try {
        await api("/api/language", {
          method: "POST",
          body: JSON.stringify({ session_id: sessionId, lang }),
        });
      } catch (_) {}
    }
  });

  els.reset.addEventListener("click", async () => {
    if (sessionId) {
      try {
        await api("/api/reset", {
          method: "POST",
          body: JSON.stringify({ session_id: sessionId }),
        });
      } catch (_) {}
    }
    sessionId = newSessionId();
    localStorage.setItem(STORAGE_SESSION, sessionId);
    els.messages.innerHTML = "";
    location.reload();
  });

  /* ------------------------- Installation (PWA) ------------------------- */
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    deferredPrompt = event;
    if (els.install) els.install.hidden = false;
  });

  els.install?.addEventListener("click", async () => {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    await deferredPrompt.userChoice;
    deferredPrompt = null;
    els.install.hidden = true;
  });

  window.addEventListener("appinstalled", () => {
    if (els.install) els.install.hidden = true;
  });

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/service-worker.js").catch(() => {});
    });
  }

  /* -------------------------------- Démarrage --------------------------- */
  async function start() {
    try {
      config = await api("/api/config");
    } catch (_) {}

    els.lang.value = lang;
    applyDirection(lang);

    if (config.auth_required) {
      try {
        await api("/api/history?session_id=probe&limit=1");
      } catch (error) {
        if (error.message === "unauthorized") return;
      }
    }

    if (!sessionId) {
      sessionId = newSessionId();
      localStorage.setItem(STORAGE_SESSION, sessionId);
    } else {
      await loadHistory();
    }
    els.input.focus();
  }

  start();
})();

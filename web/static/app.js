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
    attach: $("#attach"),
    mic: $("#mic"),
    composer: $("#composer"),
    file: $("#file"),
    actContact: $("#act-contact"),
    actSearch: $("#act-search"),
    searchbar: $("#searchbar"),
    searchInput: $("#search-input"),
    searchClose: $("#search-close"),
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

  // Rendu sûr : on échappe le HTML, puis on met en gras le *texte* (comme
  // WhatsApp) et on garde les retours à la ligne.
  const FILE_MARK = /^\[\[file:(\d+):(img|doc|aud):([^\]]*)\]\]$/;
  const CITE_MARK = /^\[\[cite:([^:]*):([^\]]*)\]\]\n?/;

  function fileUrl(id) {
    return `/api/upload/${id}?session_id=${encodeURIComponent(sessionId)}`;
  }

  function escapeHtml(value) {
    return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  // Un fichier envoyé s'affiche : image en vignette (clic = agrandir), document en pastille.
  function renderFile(match) {
    const [, id, kind, name] = match;
    const safeName = escapeHtml(name);
    if (kind === "aud") {
      // Message vocal : lecteur natif, comme WhatsApp
      return `<div class="voice"><audio controls preload="metadata" src="${fileUrl(id)}"></audio></div>`;
    }
    if (kind === "img") {
      return `<a class="shot" href="${fileUrl(id)}" target="_blank" rel="noopener"><img src="${fileUrl(id)}" alt="${safeName}" loading="lazy"></a>`;
    }
    return `<a class="docchip" href="${fileUrl(id)}" target="_blank" rel="noopener">📎 ${safeName}</a>`;
  }

  function renderText(text) {
    let reste = String(text);
    let cite = "";
    const citeMatch = reste.match(CITE_MARK);
    if (citeMatch) {
      cite = `<span class="cite"><b>${escapeHtml(citeMatch[1] || "Message")}</b> ${escapeHtml(citeMatch[2])}</span>`;
      reste = reste.replace(CITE_MARK, "");
    }
    const fileMatch = reste.trim().match(FILE_MARK);
    if (fileMatch) return cite + renderFile(fileMatch);
    const escaped = String(reste)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    return cite + escaped
      .replace(/\*([^*\n]+)\*/g, "<strong>$1</strong>")
      .replace(/\n/g, "<br>");
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
    bubble.innerHTML = renderText(text);
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
    activerGlissement(bubble);
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
    const cite = reponseA ? { author: reponseA.auteur, excerpt: reponseA.extrait } : null;
    addMessage("user", message);
    if (reponseA) {
      const bar = document.getElementById("reply-bar");
      if (bar) bar.remove();
      reponseA = null;
    }
    addTyping();
    try {
      const data = await api("/api/chat", {
        method: "POST",
        body: JSON.stringify({ message, session_id: sessionId || undefined, reply_to: cite }),
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
  async function sendFile(file) {
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    form.append("session_id", sessionId);
    // Aperçu immédiat : le client voit tout de suite ce qu'il envoie.
    const isImage = (file.type || "").startsWith("image/");
    const localUrl = isImage ? URL.createObjectURL(file) : "";
    const previewBubble = addMessage("user", "");
    if (previewBubble) {
      previewBubble.insertAdjacentHTML(
        "afterbegin",
        isImage
          ? `<a class="shot"><img src="${localUrl}" alt="${escapeHtml(file.name)}"></a>`
          : `<span class="docchip">📎 ${escapeHtml(file.name)}</span>`
      );
    }
    addTyping();
    try {
      const response = await fetch("/api/upload", { method: "POST", body: form, credentials: "same-origin" });
      if (!response.ok) throw new Error("upload");
      const data = await response.json();
      // Le lien serveur remplace l'aperçu local : l'image reste cliquable.
      const link = previewBubble && previewBubble.querySelector("a");
      if (link && data.url) { link.href = data.url; link.target = "_blank"; link.rel = "noopener"; }
      removeTyping();
      addMessage("assistant", data.reply || "Bien reçu 📎 J'ai transmis le fichier à l'équipe Komara.");
    } catch {
      removeTyping();
      addMessage("assistant", "Le fichier n'est pas passé. Réessaie avec une image plus légère.");
    }
  }

  /* ---------------- glisser un message pour y répondre (comme WhatsApp) ---------------- */
  let reponseA = null;

  function afficherReponse(auteur, extrait) {
    reponseA = { auteur, extrait };
    let bar = document.getElementById("reply-bar");
    if (!bar) {
      bar = document.createElement("div");
      bar.id = "reply-bar";
      bar.className = "reply-bar";
      els.composer.insertBefore(bar, els.composer.firstChild);
    }
    bar.innerHTML = `<span><b>${escapeHtml(auteur)}</b> ${escapeHtml(extrait)}</span><button type="button" aria-label="Annuler la réponse">✕</button>`;
    bar.querySelector("button").addEventListener("click", () => { reponseA = null; bar.remove(); });
    els.input.focus();
  }

  function activerGlissement(bulle) {
    let debutX = 0, actif = false;
    bulle.addEventListener("pointerdown", (e) => { debutX = e.clientX; actif = true; });
    bulle.addEventListener("pointerup", (e) => {
      if (!actif) return;
      actif = false;
      if (e.clientX - debutX > 60) {
        const texte = bulle.textContent.replace(/\s+/g, " ").trim();
        const auteur = bulle.closest(".msg").classList.contains("user") ? "Toi" : "Aya";
        afficherReponse(auteur, texte.slice(0, 60));
      }
    });
  }

  els.attach.addEventListener("click", () => els.file.click());
  /* ---------------- message vocal ---------------- */
  let enregistreur = null, morceaux = [], debutEnregistrement = 0;

  async function basculerVocal() {
    if (enregistreur && enregistreur.state === "recording") {
      enregistreur.stop();
      return;
    }
    if (!navigator.mediaDevices || !window.MediaRecorder) {
      toast("Ton navigateur ne permet pas le vocal. Écris ton message.");
      return;
    }
    try {
      const flux = await navigator.mediaDevices.getUserMedia({ audio: true });
      enregistreur = new MediaRecorder(flux);
      morceaux = [];
      enregistreur.ondataavailable = (e) => { if (e.data.size) morceaux.push(e.data); };
      enregistreur.onstop = async () => {
        flux.getTracks().forEach((t) => t.stop());
        els.mic.classList.remove("recording");
        const duree = Math.round((Date.now() - debutEnregistrement) / 1000);
        if (duree < 1) { toast("Trop court, réessaie."); return; }
        const blob = new Blob(morceaux, { type: "audio/webm" });
        await envoyerVocal(blob, duree);
      };
      debutEnregistrement = Date.now();
      enregistreur.start();
      els.mic.classList.add("recording");
      toast("Enregistrement… appuie encore pour envoyer");
    } catch {
      toast("Micro refusé. Autorise le micro dans ton navigateur.");
    }
  }


  /* ---------- transcription gratuite (Web Speech API, zéro API, zéro coût) ---------- */
  function transcrire(blob) {
    return new Promise((resolve) => {
      const Reco = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!Reco) { resolve(""); return; }
      try {
        const rec = new Reco();
        rec.lang = (localStorage.getItem("aya_lang") || "fr") === "ar" ? "ar-MA" : "fr-FR";
        rec.interimResults = false;
        rec.maxAlternatives = 1;
        let fini = false;
        const finir = (texte) => { if (!fini) { fini = true; resolve((texte || "").trim()); } };
        rec.onresult = (e) => finir(e.results?.[0]?.[0]?.transcript || "");
        rec.onerror = () => finir("");
        rec.onend = () => finir("");
        setTimeout(() => finir(""), 12000);
        // Le navigateur transcrit ce qu'il entend pendant qu'on rejoue l'audio.
        const audio = new Audio(URL.createObjectURL(blob));
        audio.play().catch(() => {});
        rec.start();
      } catch { resolve(""); }
    });
  }

  async function envoyerVocal(blob, duree) {
    const form = new FormData();
    form.append("file", new File([blob], `vocal-${duree}s.webm`, { type: "audio/webm" }));
    form.append("session_id", sessionId);
    const bulle = addMessage("user", "");
    if (bulle) {
      bulle.insertAdjacentHTML("afterbegin", `<div class="voice"><audio controls src="${URL.createObjectURL(blob)}"></audio></div>`);
    }
    try {
      const reponse = await fetch("/api/upload", { method: "POST", body: form, credentials: "same-origin" });
      if (!reponse.ok) throw new Error("upload");
      const data = await reponse.json();
      const lien = bulle && bulle.querySelector("audio");
      if (lien && data.url) lien.src = data.url;
      const dit = await transcrire(blob);
      if (dit) {
        addMessage("user", dit);
        await send(dit);
      } else if (data.reply) {
        addMessage("assistant", data.reply);
      }
    } catch {
      toast("Le vocal n'est pas parti. Réessaie.");
    }
  }

  if (els.mic) els.mic.addEventListener("click", basculerVocal);

  els.file.addEventListener("change", () => {
    sendFile(els.file.files[0]);
    els.file.value = "";
  });

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
  els.actContact.addEventListener("click", () => {
    const phone = (config.contact_whatsapp || "").replace(/[^\d]/g, "");
    const text = encodeURIComponent("Bonjour Ndine, je viens de la part d'Aya.");
    els.actContact.href = `https://wa.me/${phone}?text=${text}`;
  });

  els.actSearch.addEventListener("click", () => {
    els.sheet.hidden = true;
    els.searchbar.hidden = false;
    els.searchInput.focus();
  });

  els.searchClose.addEventListener("click", () => {
    els.searchbar.hidden = true;
    els.searchInput.value = "";
    document.querySelectorAll(".mark").forEach((el) => {
      el.replaceWith(document.createTextNode(el.textContent));
    });
  });

  els.searchInput.addEventListener("keydown", async (event) => {
    if (event.key !== "Enter") return;
    const needle = els.searchInput.value.trim();
    if (needle.length < 2) return;
    try {
      const data = await api(`/api/search?session_id=${encodeURIComponent(sessionId)}&q=${encodeURIComponent(needle)}`);
      toast(data.messages.length ? `${data.messages.length} message(s) trouvé(s)` : "Aucun message trouvé");
    } catch {
      toast("Recherche indisponible");
    }
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

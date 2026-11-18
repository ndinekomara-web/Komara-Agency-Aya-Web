(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const form = $("form");
  const status = $("status");

  function showStatus(text, ok = true) {
    status.textContent = text;
    status.className = "status " + (ok ? "ok" : "err");
    status.hidden = false;
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      ...options,
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || "Erreur " + response.status);
    return body;
  }

  function formatDate(value) {
    if (!value) return "";
    const date = typeof value === "number" ? new Date(value * 1000) : new Date(value);
    return date.toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  }

  async function loadEntries() {
    const list = $("entries");
    try {
      const data = await api("/api/admin/knowledge");
      $("count").textContent = data.entries.length
        ? data.entries.length + " information(s) enregistrée(s)"
        : "Aucune information ajoutée pour l'instant.";
      list.innerHTML = "";
      data.entries.forEach((entry) => {
        const li = document.createElement("li");
        const head = document.createElement("div");
        head.className = "head";
        const title = document.createElement("strong");
        title.textContent = entry.title;
        const meta = document.createElement("span");
        meta.textContent = (entry.lang || "fr").toUpperCase() + " · " + formatDate(entry.created_at);
        const del = document.createElement("button");
        del.className = "del";
        del.textContent = "Supprimer";
        del.addEventListener("click", async () => {
          del.disabled = true;
          try {
            await api(`/api/admin/knowledge/${entry.id}`, { method: "DELETE" });
            await loadEntries();
          } catch (error) {
            showStatus(error.message, false);
          }
        });
        head.append(title, meta, del);
        const body = document.createElement("p");
        body.textContent = entry.content;
        li.append(head, body);
        list.appendChild(li);
      });
    } catch (error) {
      list.innerHTML = "";
      const li = document.createElement("li");
      li.textContent = error.message;
      list.appendChild(li);
    }
  }

  async function loadQuotes() {
    const list = $("quotes");
    try {
      const data = await api("/api/quotes");
      list.innerHTML = "";
      if (!data.quotes.length) {
        list.innerHTML = '<li class="muted">Aucune demande pour l\'instant.</li>';
        return;
      }
      data.quotes.forEach((quote) => {
        const li = document.createElement("li");
        const head = document.createElement("div");
        head.className = "head";
        const title = document.createElement("strong");
        title.textContent = quote.service || "Service non précisé";
        const meta = document.createElement("span");
        meta.textContent = formatDate(quote.created_at);
        head.append(title, meta);
        const body = document.createElement("p");
        body.textContent = "Budget : " + (quote.budget || "non précisé");
        li.append(head, body);
        list.appendChild(li);
      });
    } catch (error) {
      list.innerHTML = "";
      const li = document.createElement("li");
      li.textContent = error.message;
      list.appendChild(li);
    }
  }

  async function loadStatus() {
    try {
      const data = await api("/api/admin/status");
      $("ip").textContent = data.ip || "inconnue";
      $("allowed").textContent = data.allowed_ips.length ? data.allowed_ips.join(", ") : "aucune";
      $("who").textContent = "IP " + (data.ip || "?") + (data.is_admin ? " · autorisée" : " · non autorisée");
    } catch (_) {}
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = $("save");
    button.disabled = true;
    try {
      const payload = {
        lang: $("lang").value,
        title: $("title").value.trim(),
        content: $("content").value.trim(),
      };
      if (!payload.title || !payload.content) throw new Error("Sujet et information sont obligatoires.");
      await api("/api/admin/knowledge", { method: "POST", body: JSON.stringify(payload) });
      $("title").value = "";
      $("content").value = "";
      showStatus("Enregistré. Aya l'utilise dès maintenant.", true);
      await loadEntries();
    } catch (error) {
      showStatus(error.message, false);
    } finally {
      button.disabled = false;
    }
  });

  loadStatus();
  loadEntries();
  loadQuotes();
})();

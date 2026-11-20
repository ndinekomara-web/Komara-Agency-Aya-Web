(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
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

  const fmt = (value) => {
    if (!value) return "";
    const date = typeof value === "number" ? new Date(value * 1000) : new Date(value);
    return date.toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  };

  function entry(title, meta, body, extra) {
    const li = document.createElement("li");
    const head = document.createElement("div");
    head.className = "head";
    const strong = document.createElement("strong");
    strong.textContent = title;
    const span = document.createElement("span");
    span.textContent = meta;
    head.append(strong, span);
    if (extra) head.appendChild(extra);
    li.appendChild(head);
    if (body) {
      const p = document.createElement("p");
      p.textContent = body;
      li.appendChild(p);
    }
    return li;
  }

  async function loadAlerts() {
    const list = $("alerts");
    try {
      const data = await api("/api/admin/alerts");
      list.innerHTML = "";
      const unseen = data.alerts.filter((a) => !a.seen).length;
      $("alerts-count").textContent = data.alerts.length
        ? `${unseen} non lue(s) sur ${data.alerts.length}`
        : "Aucune alerte pour l'instant.";
      if (!data.alerts.length) return;
      data.alerts.forEach((alert) => {
        const li = entry(alert.title, fmt(alert.created_at), alert.body);
        if (!alert.seen) {
          li.style.borderColor = "rgba(245,189,100,.5)";
          const btn = document.createElement("button");
          btn.className = "del";
          btn.textContent = "Lu";
          btn.addEventListener("click", async () => {
            await api(`/api/admin/alerts/${alert.id}/seen`, { method: "POST" });
            loadAlerts();
          });
          li.querySelector(".head").appendChild(btn);
        }
        list.appendChild(li);
      });
    } catch (error) {
      list.innerHTML = `<li>${error.message}</li>`;
    }
  }

  async function loadAnalytics() {
    try {
      const data = await api("/api/admin/analytics");
      const box = $("stats");
      box.innerHTML = "";
      [
        ["Conversations", data.sessions],
        ["Messages", data.messages],
        ["Devis", data.quotes],
        ["Numéros", data.leads],
      ].forEach(([label, value]) => {
        const div = document.createElement("div");
        div.className = "stat";
        div.innerHTML = `<strong>${value}</strong><span>${label}</span>`;
        box.appendChild(div);
      });

      const list = $("services");
      list.innerHTML = "";
      const max = Math.max(1, ...data.per_day.map((d) => d.messages));
      data.per_day.slice(-7).forEach((day) => {
        const li = document.createElement("li");
        li.className = "bar";
        const width = Math.round((day.messages / max) * 100);
        li.innerHTML = `<span>${day.day.slice(5)}</span><i style="width:${width}%"></i><span>${day.messages}</span>`;
        list.appendChild(li);
      });
      data.services.slice(0, 5).forEach((service) => {
        list.appendChild(entry(service.service, service.times + " demande(s)", ""));
      });
    } catch (_) {}
  }

  async function loadUnanswered() {
    const list = $("unanswered");
    try {
      const data = await api("/api/admin/unanswered");
      list.innerHTML = "";
      if (!data.questions.length) {
        list.innerHTML = '<li class="muted">Rien pour l\'instant : Aya répond à tout.</li>';
        return;
      }
      data.questions.forEach((item) => {
        const btn = document.createElement("button");
        btn.className = "del";
        btn.textContent = "Répondre";
        btn.addEventListener("click", () => {
          $("title").value = item.question;
          $("lang").value = item.lang || "fr";
          $("content").focus();
          window.scrollTo({ top: $("form").offsetTop - 80, behavior: "smooth" });
        });
        list.appendChild(entry(item.question, `${item.times} fois · ${fmt(item.last_seen)}`, "", btn));
      });
    } catch (error) {
      list.innerHTML = `<li>${error.message}</li>`;
    }
  }

  async function loadEntries() {
    const list = $("entries");
    try {
      const data = await api("/api/admin/knowledge");
      list.innerHTML = "";
      if (!data.entries.length) {
        list.innerHTML = '<li class="muted">Aucune information ajoutée.</li>';
        return;
      }
      data.entries.forEach((row) => {
        const del = document.createElement("button");
        del.className = "del";
        del.textContent = "Supprimer";
        del.addEventListener("click", async () => {
          del.disabled = true;
          try {
            await api(`/api/admin/knowledge/${row.id}`, { method: "DELETE" });
            loadEntries();
          } catch (error) {
            showStatus(error.message, false);
          }
        });
        list.appendChild(entry(row.title, `${(row.lang || "fr").toUpperCase()} · ${fmt(row.created_at)}`, row.content, del));
      });
    } catch (error) {
      list.innerHTML = `<li>${error.message}</li>`;
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
        const link = document.createElement("a");
        link.className = "link";
        link.href = `/api/quotes/${quote.id}/invoice.pdf`;
        link.target = "_blank";
        link.textContent = "Facture PDF";
        list.appendChild(entry(quote.service || "Service non précisé", fmt(quote.created_at), "Budget : " + (quote.budget || "non précisé"), link));
      });
    } catch (error) {
      list.innerHTML = `<li>${error.message}</li>`;
    }
  }

  async function loadLeads() {
    const list = $("leads");
    try {
      const data = await api("/api/leads");
      list.innerHTML = "";
      if (!data.leads.length) {
        list.innerHTML = '<li class="muted">Aucun numéro pour l\'instant.</li>';
        return;
      }
      data.leads.forEach((lead) => {
        const link = document.createElement("a");
        link.className = "link";
        link.href = `https://wa.me/${(lead.phone || "").replace(/[^\d]/g, "")}`;
        link.target = "_blank";
        link.textContent = "WhatsApp";
        list.appendChild(entry(lead.phone, fmt(lead.created_at), lead.note || "", link));
      });
    } catch (error) {
      list.innerHTML = `<li>${error.message}</li>`;
    }
  }

  async function loadUploads() {
    const list = $("uploads");
    try {
      const data = await api("/api/admin/alerts").catch(() => null);
      const files = await api("/api/admin/uploads").catch(() => ({ uploads: [] }));
      list.innerHTML = "";
      if (!files.uploads || !files.uploads.length) {
        list.innerHTML = '<li class="muted">Aucun fichier reçu.</li>';
        return;
      }
      files.uploads.forEach((file) => {
        const link = document.createElement("a");
        link.className = "link";
        link.href = `/api/admin/uploads/${file.id}`;
        link.target = "_blank";
        link.textContent = "Ouvrir";
        list.appendChild(entry(file.filename, fmt(file.created_at), file.content_type || "", link));
      });
    } catch (_) {}
  }

  async function loadStatus() {
    try {
      const data = await api("/api/admin/status");
      $("ip").textContent = data.ip || "inconnue";
      $("allowed").textContent = data.allowed_ips.length ? data.allowed_ips.join(", ") : "aucune";
      $("who").textContent = "IP " + (data.ip || "?") + (data.is_admin ? " · autorisée" : " · non autorisée");
    } catch (_) {}
  }

  $("form").addEventListener("submit", async (event) => {
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
      await Promise.all([loadEntries(), loadUnanswered()]);
    } catch (error) {
      showStatus(error.message, false);
    } finally {
      button.disabled = false;
    }
  });

  loadStatus();
  loadAlerts();
  loadAnalytics();
  loadUnanswered();
  loadEntries();
  loadQuotes();
  loadLeads();
  loadUploads();
})();

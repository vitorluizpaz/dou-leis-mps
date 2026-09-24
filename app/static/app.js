const state = { scheduleHour: 10, scheduleMinute: 0, nextCheck: null };
const $ = (selector) => document.querySelector(selector);
const pad = (value) => String(value).padStart(2, "0");

function localDate() {
  const now = new Date();
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

function setStatus(message, kind = "") {
  const element = $("#scrape-status");
  element.textContent = message;
  element.className = `status-message ${kind}`;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>\'"]/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "'": "&#39;",
    '"': "&quot;",
  })[char]);
}

function safeSourceUrl(value) {
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase().replace(/\.$/, "");
    return url.protocol === "https:" && ["in.gov.br", "www.in.gov.br"].includes(host)
      ? url.href
      : "#";
  } catch (_) {
    return "#";
  }
}

function safeTelegramUrl(value) {
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase().replace(/\.$/, "");
    return url.protocol === "https:" && ["t.me", "www.t.me", "telegram.me", "www.telegram.me"].includes(host) && url.pathname !== "/"
      ? url.href
      : "";
  } catch (_) {
    return "";
  }
}

function scheduleNextCheck() {
  const now = new Date();
  const next = new Date(now);
  next.setHours(state.scheduleHour, state.scheduleMinute, 0, 0);
  if (next <= now) next.setDate(next.getDate() + 1);
  state.nextCheck = next;
  updateCountdown();
}

function updateCountdown() {
  if (!state.nextCheck) return;
  const remaining = Math.max(0, state.nextCheck.getTime() - Date.now());
  const totalSeconds = Math.floor(remaining / 1000);
  $("#countdown").textContent = `${pad(Math.floor(totalSeconds / 3600))}:${pad(Math.floor((totalSeconds % 3600) / 60))}:${pad(totalSeconds % 60)}`;
  $("#next-check-label").textContent = `Próxima verificação às ${state.nextCheck.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`;
  if (remaining === 0) scheduleNextCheck();
}

async function loadHealth() {
  try {
    const response = await fetch("/api/health");
    const health = await response.json();
    state.scheduleHour = Number.isInteger(health.schedule_hour) ? health.schedule_hour : 10;
    state.scheduleMinute = Number.isInteger(health.schedule_minute) ? health.schedule_minute : 0;
    scheduleNextCheck();
    const scheduleLabel = health.schedule_label || `Diariamente às ${pad(state.scheduleHour)}:${pad(state.scheduleMinute)}`;
    $("#schedule").textContent = scheduleLabel.replace(/\s*\(America\/Sao_Paulo\)\s*/gi, "").trim();
    $("#timezone").textContent = health.timezone || "—";
    $("#telegram").textContent = health.telegram_configured ? "Conectado" : "Não configurado";
    const latest = health.recent_checks?.[0];
    if (latest) {
      const checkedAt = new Date(`${latest.at}Z`);
      const when = Number.isNaN(checkedAt.getTime())
        ? latest.date
        : checkedAt.toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
      const outcome = latest.status === "success"
        ? (latest.found === 0 ? "nenhuma Lei ou MP encontrada" : "checagem concluída")
        : "falha na checagem ou no envio";
      $("#last-check").textContent = `Última verificação: ${when} · ${outcome}.`;
    } else {
      $("#last-check").textContent = "Ainda não há verificações registradas.";
    }
    $("#health-label").textContent = response.ok ? "Serviço online" : "Indisponível";
    $("#health-dot").style.background = response.ok ? "var(--green)" : "#ff9089";
  } catch (_) {
    scheduleNextCheck();
    $("#health-label").textContent = "Indisponível";
    $("#telegram").textContent = "Indisponível";
    $("#last-check").textContent = "Não foi possível consultar a última verificação.";
    $("#health-dot").style.background = "#ff9089";
  }
}

async function loadTelegramLink() {
  try {
    const response = await fetch("/api/telegram-link");
    const payload = await response.json();
    const url = safeTelegramUrl(payload.url);
    if (response.ok && url) {
      document.querySelectorAll(".telegram-link").forEach((link) => {
        link.href = url;
      });
    }
  } catch (_) {
    // The invitation link is already present in the static page.
  }
}

async function loadItems() {
  const readKey = $("#read-key").value.trim();
  const date = $("#date").value;
  const list = $("#items");
  if (!readKey) {
    list.innerHTML = '<div class="empty">Informe a chave de leitura para carregar as publicações.</div>';
    return;
  }
  list.innerHTML = '<div class="empty">Carregando publicações…</div>';
  try {
    const response = await fetch(`/api/laws?date=${encodeURIComponent(date)}`, {
      headers: { "X-API-Key": readKey },
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Não foi possível carregar os dados.");
    list.innerHTML = payload.length
      ? payload.map((item) => `<article class="publication"><a href="${escapeHtml(safeSourceUrl(item.source_url))}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.title)}</a><div class="meta">${escapeHtml(item.kind)} · ${escapeHtml(item.published_date)}</div></article>`).join("")
      : '<div class="empty">Nenhuma publicação salva para esta data.</div>';
  } catch (error) {
    list.innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
  }
}

async function scrape() {
  const key = $("#scrape-key").value.trim();
  const button = $("#scrape-button");
  if (!key) {
    setStatus("Informe a chave de scraping.", "error");
    return;
  }
  button.disabled = true;
  setStatus("Consultando o DOU…");
  try {
    const response = await fetch("/api/scrape", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": key },
      body: JSON.stringify({ date: $("#date").value }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Falha na coleta.");
    setStatus(`OK · ${payload.found} encontrada(s) · ${payload.new} nova(s) · ${payload.telegram_sent} enviada(s)`, "ok");
    await loadItems();
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    button.disabled = false;
  }
}

$("#date").value = localDate();
loadHealth();
loadTelegramLink();
setInterval(updateCountdown, 1000);

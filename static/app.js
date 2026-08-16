// ONLI-AIOPS ENTERPRISE SRE CLIENT CONTROLLER v2.0

const API_BASE = window.location.origin;
let currentConfig = {};
let currentIncidents = [];
let activeIncidentModalId = null;
let ws = null;

// INIT
document.addEventListener("DOMContentLoaded", () => {
  setupNavigation();
  setupEventListeners();
  loadAllData();
  initWebSocket();
});

// NAVIGATION
function setupNavigation() {
  const navItems = document.querySelectorAll(".nav-item");
  navItems.forEach(item => {
    item.addEventListener("click", () => {
      const tabId = item.getAttribute("data-tab");
      switchTab(tabId);
    });
  });
}

function switchTab(tabId) {
  document.querySelectorAll(".nav-item").forEach(el => el.classList.remove("active"));
  document.querySelectorAll(".tab-pane").forEach(el => el.classList.remove("active"));

  const targetBtn = document.querySelector(`.nav-item[data-tab="${tabId}"]`);
  const targetPane = document.getElementById(tabId);

  if (targetBtn) targetBtn.classList.add("active");
  if (targetPane) targetPane.classList.add("active");

  const titles = {
    "tab-overview": ["Visão Geral da Operação", "Status em tempo real, monitoramento e resposta autônoma"],
    "tab-incidents": ["Central de Incidentes & Diagnósticos", "Investigação detalhada, evidências coletadas e histórico auditável"],
    "tab-queue": ["Fila de Aprovação", "Incidentes que exigem confirmação humana antes da execução"],
    "tab-ai-config": ["Provedores & Modelos de IA", "Gerenciamento de chaves de API, modelos e conexões"],
    "tab-prompts": ["Prompts & Runbooks", "Diretrizes fundamentais dos 22 princípios e procedimentos operacionais"],
    "tab-autonomy": ["Autonomia & Regras de Segurança", "Controle granular de execução e limites operacionais"],
    "tab-chat": ["Terminal / Chat Interativo SRE", "Diálogo direto com o agente para diagnósticos sob demanda"]
  };

  if (titles[tabId]) {
    document.getElementById("page-title").textContent = titles[tabId][0];
    document.getElementById("page-subtitle").textContent = titles[tabId][1];
  }
}

function filterBySeverity(sev) {
  switchTab("tab-incidents");
  document.getElementById("filter-severity").value = sev;
  applyIncidentFilters();
}

// DATA LOADING
async function loadAllData() {
  await Promise.all([
    fetchStatus(),
    fetchConfig(),
    fetchPrompts(),
    fetchRunbooks(),
    fetchIncidents()
  ]);
}

async function fetchStatus() {
  try {
    const res = await fetch(`${API_BASE}/api/v1/status`);
    const data = await res.json();
    
    document.getElementById("ov-total").textContent = data.total_incidents;
    document.getElementById("ov-critical").textContent = data.critical_incidents || 0;
    document.getElementById("ov-pending").textContent = data.pending_approvals;
    
    if (data.triage) {
      const saved = (data.triage.stats?.ai_calls_saved_offline || 0) + (data.triage.stats?.ai_calls_saved_dedup || 0);
      const supCount = data.triage.suppressed_hosts?.length || 0;
      const elSaved = document.getElementById("triage-saved-count");
      const elSup = document.getElementById("triage-suppressed-count");
      if (elSaved) elSaved.textContent = saved;
      if (elSup) elSup.textContent = supCount;
    }
    document.getElementById("ov-provider").textContent = `${data.provider.toUpperCase()} (${data.model})`;
    
    document.getElementById("kpi-autonomy").textContent = `Nível: ${data.autonomy_level}`;
    document.getElementById("kpi-provider").textContent = `${data.provider.toUpperCase()}`;
    
    const badgeInc = document.getElementById("badge-incidents");
    if (data.total_incidents > 0) {
      badgeInc.textContent = data.total_incidents;
      badgeInc.style.display = "inline-block";
    } else {
      badgeInc.style.display = "none";
    }

    const badgePend = document.getElementById("badge-pending");
    if (data.pending_approvals > 0) {
      badgePend.textContent = data.pending_approvals;
      badgePend.style.display = "inline-block";
    } else {
      badgePend.style.display = "none";
    }
  } catch (err) {
    console.error("Erro ao carregar status:", err);
  }
}

async function fetchConfig() {
  try {
    const res = await fetch(`${API_BASE}/api/v1/config`);
    const cfg = await res.json();
    currentConfig = cfg;

    document.getElementById("cfg-provider").value = cfg.provider || "claude";
    document.getElementById("cfg-model").value = cfg.model || "claude-sonnet-4-5-20250929";
    document.getElementById("cfg-temp").value = cfg.temperature || 0.2;
    document.getElementById("cfg-base-url").value = cfg.base_url || "";
    document.getElementById("cfg-max-retries").value = cfg.max_retries_per_service || 2;
    document.getElementById("cfg-is-active").value = String(cfg.is_active !== false);

    if (cfg.has_api_key) {
      document.getElementById("cfg-key-hint").textContent = `Chave cadastrada: ${cfg.api_key_masked} (Preencha somente se desejar alterar)`;
    } else {
      document.getElementById("cfg-key-hint").textContent = "Nenhuma chave cadastrada para este provedor.";
    }

    const autoRadio = document.querySelector(`input[name="autonomy_level"][value="${cfg.autonomy_level || 'CONTROLLED'}"]`);
    if (autoRadio) autoRadio.checked = true;

    toggleBaseUrlField();
  } catch (err) {
    console.error("Erro ao carregar config:", err);
  }
}

async function fetchPrompts() {
  try {
    const res = await fetch(`${API_BASE}/api/v1/prompts`);
    const data = await res.json();
    document.getElementById("txt-system-prompt").value = data.custom_prompt || data.default_prompt;
  } catch (err) {
    console.error("Erro ao carregar prompts:", err);
  }
}

async function fetchRunbooks() {
  try {
    const res = await fetch(`${API_BASE}/api/v1/runbooks`);
    const data = await res.json();
    const tbody = document.getElementById("tbody-runbooks");
    tbody.innerHTML = "";

    for (const [name, rb] of Object.entries(data)) {
      const tr = document.createElement("tr");
      const allowed = rb.allowed_services ? rb.allowed_services.join(", ") : (rb.allowed_containers ? rb.allowed_containers.join(", ") : "Geral");
      tr.innerHTML = `
        <td><code>${name}</code></td>
        <td>${rb.description}</td>
        <td><span class="risk-tag ${rb.risk.toLowerCase()}">${rb.risk}</span></td>
        <td><small>${allowed}</small></td>
      `;
      tbody.appendChild(tr);
    }
  } catch (err) {
    console.error("Erro ao carregar runbooks:", err);
  }
}

async function fetchIncidents() {
  try {
    const res = await fetch(`${API_BASE}/api/v1/incidents`);
    const incidents = await res.json();
    currentIncidents = incidents;
    updateHostFilterDropdown(incidents);
    renderOverviewRecent(incidents);
    renderApprovalQueue(incidents);
    applyIncidentFilters();
  } catch (err) {
    console.error("Erro ao carregar incidentes:", err);
  }
}

function updateHostFilterDropdown(incidents) {
  const hostSelect = document.getElementById("filter-host");
  const currentVal = hostSelect.value;
  const hosts = new Set();

  incidents.forEach(i => {
    if (i.instance) hosts.add(i.instance);
    if (i.host_target) hosts.add(i.host_target);
  });

  hostSelect.innerHTML = `<option value="ALL">Todos os Servidores (${hosts.size})</option>`;
  Array.from(hosts).sort().forEach(h => {
    const opt = document.createElement("option");
    opt.value = h;
    opt.textContent = h;
    hostSelect.appendChild(opt);
  });

  if (currentVal && hosts.has(currentVal)) {
    hostSelect.value = currentVal;
  }
}

function renderOverviewRecent(incidents) {
  const tbodyRecent = document.getElementById("tbody-recent-incidents");
  tbodyRecent.innerHTML = "";

  if (incidents.length === 0) {
    tbodyRecent.innerHTML = `<tr><td colspan="6" class="text-center text-muted">Nenhum incidente registrado ainda. Tudo saudável.</td></tr>`;
    return;
  }

  incidents.slice(0, 6).forEach(inc => {
    const timeStr = new Date(inc.timestamp * 1000).toLocaleTimeString("pt-BR");
    const tr = document.createElement("tr");
    tr.style.cursor = "pointer";
    tr.onclick = () => openIncidentModal(inc.id);

    const sevClass = (inc.severity || 'info').toLowerCase();
    tr.innerHTML = `
      <td>${timeStr}</td>
      <td><strong>${inc.instance}</strong></td>
      <td>${inc.alertname}</td>
      <td><span class="sev-badge ${sevClass}">${inc.severity || 'INFO'}</span></td>
      <td><span class="badge ${inc.status.includes('RESOLVIDO') || inc.status.includes('ONLINE') ? 'bg-green' : (inc.status === 'AGUARDANDO_APROVACAO' ? 'badge-orange' : '')}">${inc.status}</span></td>
      <td><button class="btn btn-sm btn-outline" onclick="event.stopPropagation(); openIncidentModal('${inc.id}')">🔍 Detalhes</button></td>
    `;
    tbodyRecent.appendChild(tr);
  });
}

function renderApprovalQueue(incidents) {
  const queueList = document.getElementById("approval-queue-list");
  const pending = incidents.filter(i => i.status === "AGUARDANDO_APROVACAO");

  if (pending.length === 0) {
    queueList.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">✅</div>
        <h4>Nenhuma ação pendente de aprovação</h4>
        <p class="text-muted">Todas as operações estão estáveis ou foram resolvidas automaticamente dentro das regras de baixo risco.</p>
      </div>
    `;
    return;
  }

  queueList.innerHTML = "";
  pending.forEach(inc => {
    const card = document.createElement("div");
    card.className = "incident-card";
    card.innerHTML = `
      <div class="incident-header">
        <div>
          <span class="incident-host">${inc.instance} (${inc.host_target})</span>
          <small class="text-muted" style="margin-left:8px;">Alerta: <strong>${inc.alertname}</strong></small>
        </div>
        <span class="risk-tag ${(inc.risk_level || 'médio').toLowerCase()}">Risco: ${inc.risk_level || 'MÉDIO'}</span>
      </div>
      <div class="incident-body">
        <p><strong>Diagnóstico da IA:</strong> ${inc.ai_diagnosis || inc.summary}</p>
        <p><strong>Ação Proposta:</strong> <code>${inc.proposed_tool}(${JSON.stringify(inc.proposed_params)})</code></p>
      </div>
      <div class="incident-actions">
        <button class="btn btn-outline btn-sm btn-danger" onclick="rejectIncident('${inc.id}')">❌ Rejeitar / Escalar</button>
        <button class="btn btn-primary btn-sm" onclick="approveIncident('${inc.id}')">✅ Aprovar e Executar</button>
        <button class="btn btn-outline btn-sm" onclick="openIncidentModal('${inc.id}')">🔍 Ver Evidências</button>
      </div>
    `;
    queueList.appendChild(card);
  });
}

function applyIncidentFilters() {
  const search = (document.getElementById("inc-search").value || "").toLowerCase();
  const sevFilter = document.getElementById("filter-severity").value;
  const statusFilter = document.getElementById("filter-status").value;
  const hostFilter = document.getElementById("filter-host").value;

  const filtered = currentIncidents.filter(inc => {
    // Busca textual
    if (search) {
      const matchText = `${inc.alertname} ${inc.instance} ${inc.host_target} ${inc.ai_diagnosis} ${inc.summary} ${inc.id}`.toLowerCase();
      if (!matchText.includes(search)) return false;
    }
    // Severidade
    if (sevFilter !== "ALL" && (inc.severity || "").toUpperCase() !== sevFilter) {
      return false;
    }
    // Status
    if (statusFilter !== "ALL" && inc.status !== statusFilter) {
      return false;
    }
    // Host
    if (hostFilter !== "ALL" && inc.instance !== hostFilter && inc.host_target !== hostFilter) {
      return false;
    }
    return true;
  });

  renderIncidentsGrid(filtered);
}

function renderIncidentsGrid(incidents) {
  const container = document.getElementById("incidents-container");
  document.getElementById("inc-count-display").textContent = incidents.length;
  document.getElementById("inc-count-total").textContent = currentIncidents.length;

  if (incidents.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">🔍</div>
        <h4>Nenhum incidente corresponde aos filtros selecionados</h4>
        <p class="text-muted">Tente ajustar os termos de busca ou alterar os filtros acima.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = "";
  incidents.forEach(inc => {
    const card = document.createElement("div");
    const sev = (inc.severity || 'info').toLowerCase();
    const isResolved = inc.status.includes("RESOLVIDO") || inc.status.includes("ONLINE");
    card.className = `incident-card-rich ${isResolved ? 'resolved' : sev}`;
    card.onclick = () => openIncidentModal(inc.id);

    const dateStr = new Date(inc.timestamp * 1000).toLocaleString("pt-BR");
    const timeAgo = formatTimeAgo(inc.timestamp);

    card.innerHTML = `
      <div class="inc-card-top">
        <div class="inc-card-host-group">
          <span class="inc-host-name">🖥️ ${inc.instance}</span>
          ${inc.host_target && inc.host_target !== inc.instance ? `<small class="text-muted">(${inc.host_target})</small>` : ''}
        </div>
        <div class="inc-card-badges">
          <span class="sev-badge ${sev}">${inc.severity || 'INFO'}</span>
          <span class="risk-tag ${(inc.risk_level || 'baixo').toLowerCase()}">Risco: ${inc.risk_level || 'BAIXO'}</span>
          <span class="badge ${isResolved ? 'bg-green' : (inc.status === 'AGUARDANDO_APROVACAO' ? 'badge-orange' : (inc.status === 'SERVIDOR_OFFLINE_SEM_ACAO_IA' ? 'badge-gray' : (inc.status === 'SUPRIMIDO_OFFLINE_LIMITE_ATINGIDO' ? 'badge-purple' : '')))}">${inc.status === 'SERVIDOR_OFFLINE_SEM_ACAO_IA' ? '🔒 OFFLINE (0 TOKENS)' : (inc.status === 'SUPRIMIDO_OFFLINE_LIMITE_ATINGIDO' ? '🛑 SILENCIADO (>5x)' : inc.status)}</span>
        </div>
      </div>

      <div class="inc-card-body">
        <div class="inc-alert-title">🚨 ${inc.alertname}</div>
        <div class="inc-diag-preview">${formatCleanPreview(inc.ai_diagnosis || inc.summary || 'Diagnóstico automático registrado.')}</div>
      </div>

      <div class="inc-card-bottom">
        <span>🕒 Ocorrido: <strong>${timeAgo}</strong> (${dateStr})</span>
        <button class="btn btn-sm btn-outline" onclick="event.stopPropagation(); openIncidentModal('${inc.id}')">🔍 Ver Detalhes & Evidências ↗</button>
      </div>
    `;
    container.appendChild(card);
  });
}

// MODAL DE DETALHES DO INCIDENTE
async function openIncidentModal(id) {
  activeIncidentModalId = id;
  const inc = currentIncidents.find(i => i.id === id);
  if (!inc) return;

  document.getElementById("m-inc-id").textContent = `#${inc.id}`;
  document.getElementById("m-inc-title").textContent = inc.alertname;
  document.getElementById("m-inc-host").textContent = `🖥️ Servidor: ${inc.instance} (${inc.host_target || 'IP direto'})`;

  document.getElementById("m-inc-severity").textContent = inc.severity || 'INFO';
  document.getElementById("m-inc-severity").className = `meta-val sev-badge ${(inc.severity || 'info').toLowerCase()}`;
  document.getElementById("m-inc-risk").textContent = inc.risk_level || 'BAIXO';
  document.getElementById("m-inc-status").textContent = inc.status;
  document.getElementById("m-inc-time").textContent = new Date(inc.timestamp * 1000).toLocaleString("pt-BR");

  // Diagnóstico Formatado
  const diagBox = document.getElementById("m-inc-diagnosis");
  diagBox.innerHTML = formatMarkdown(inc.ai_diagnosis || inc.summary || "Sem diagnóstico textual.");

  // Hipóteses
  const hypSec = document.getElementById("m-section-hypotheses");
  const hypList = document.getElementById("m-inc-hypotheses");
  if (inc.hypotheses && inc.hypotheses.length > 0) {
    hypSec.style.display = "flex";
    hypList.innerHTML = inc.hypotheses.map(h => `<li>💡 ${h}</li>`).join("");
  } else {
    hypSec.style.display = "none";
  }

  // Evidências
  const evBox = document.getElementById("m-inc-evidence");
  if (inc.evidence && Object.keys(inc.evidence).length > 0) {
    let evHtml = "";
    for (const [k, v] of Object.entries(inc.evidence)) {
      evHtml += `=== EVIDÊNCIA: ${k.toUpperCase()} ===\n`;
      if (typeof v === "object") {
        if (v.stdout) evHtml += v.stdout + "\n";
        else if (v.output) evHtml += v.output + "\n";
        else evHtml += JSON.stringify(v, null, 2) + "\n";
      } else {
        evHtml += String(v) + "\n";
      }
      evHtml += "\n";
    }
    evBox.textContent = evHtml.trim();
  } else {
    evBox.textContent = "Nenhuma evidência adicional coletada.";
  }

  // Ação Proposta / Executada
  const actSec = document.getElementById("m-section-action");
  const actBox = document.getElementById("m-inc-action");
  if (inc.proposed_tool) {
    actSec.style.display = "flex";
    let actText = `<p><strong>Ferramenta:</strong> <code>${inc.proposed_tool}(${JSON.stringify(inc.proposed_params || {})})</code></p>`;
    if (inc.execution_result) {
      actText += `<p style="margin-top:6px;"><strong>Resultado:</strong> <pre class="terminal-box" style="margin-top:4px;">${JSON.stringify(inc.execution_result, null, 2)}</pre></p>`;
    }
    actBox.innerHTML = actText;
  } else {
    actSec.style.display = "none";
  }

  // Footer Actions
  const footerActions = document.getElementById("modal-footer-actions");
  if (inc.status === "AGUARDANDO_APROVACAO") {
    footerActions.innerHTML = `
      <button class="btn btn-outline btn-danger" onclick="rejectIncident('${inc.id}'); closeIncidentModal();">❌ Rejeitar Ação</button>
      <button class="btn btn-primary" onclick="approveIncident('${inc.id}'); closeIncidentModal();">✅ Aprovar e Executar</button>
      <button class="btn btn-outline" onclick="closeIncidentModal()">Fechar</button>
    `;
  } else {
    footerActions.innerHTML = `<button class="btn btn-outline" onclick="closeIncidentModal()">Fechar</button>`;
  }

  document.getElementById("incident-modal").style.display = "flex";
}

function closeIncidentModal() {
  document.getElementById("incident-modal").style.display = "none";
  activeIncidentModalId = null;
}

// FORMATTERS & HELPERS
function formatCleanPreview(text) {
  if (!text) return "";
  let clean = text.replace(/#+/g, '').replace(/\*+/g, '').replace(/```[\s\S]*?```/g, '').trim();
  return clean.length > 180 ? clean.substring(0, 180) + "..." : clean;
}

function formatTimeAgo(ts) {
  const diffSec = Math.floor(Date.now() / 1000 - ts);
  if (diffSec < 60) return "agora mesmo";
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `há ${diffMin} min`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `há ${diffHr}h`;
  const diffDays = Math.floor(diffHr / 24);
  return `há ${diffDays}d`;
}

function formatMarkdown(text) {
  if (!text) return "";
  let clean = text.trim();

  // Desempacotar blocos de código ```json ... ``` se existirem
  if (clean.startsWith("```")) {
    const lines = clean.split("\n");
    if (lines.length > 2 && lines[0].startsWith("```") && lines[lines.length - 1].trim() === "```") {
      const inner = lines.slice(1, -1).join("\n").trim();
      try {
        const parsed = JSON.parse(inner);
        if (parsed && typeof parsed === "object") {
          for (const k of ["resposta", "response", "content", "text", "mensagem", "message"]) {
            if (parsed[k] && typeof parsed[k] === "string") {
              clean = parsed[k];
              break;
            }
          }
        }
      } catch (e) {
        clean = inner;
      }
    }
  }

  // Desempacotar JSON cru se existir
  if (clean.startsWith("{") && clean.endsWith("}")) {
    try {
      const parsed = JSON.parse(clean);
      if (parsed && typeof parsed === "object") {
        for (const k of ["resposta", "response", "content", "text", "mensagem", "message"]) {
          if (parsed[k] && typeof parsed[k] === "string") {
            clean = parsed[k];
            break;
          }
        }
      }
    } catch (e) {}
  }

  if (window.marked && typeof window.marked.parse === "function") {
    return window.marked.parse(clean);
  }

  return clean
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>');
}

// ACTION HANDLERS
async function approveIncident(id) {
  try {
    showToast("Executando ação aprovada no servidor...", "info");
    const res = await fetch(`${API_BASE}/api/v1/incidents/approve`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({incident_id: id})
    });
    const data = await res.json();
    if (data.success) {
      showToast("✅ Ação executada com sucesso!", "success");
    } else {
      showToast("❌ Falha na execução da ação.", "error");
    }
    fetchIncidents();
    fetchStatus();
  } catch (err) {
    showToast(`Erro ao aprovar: ${err}`, "error");
  }
}

async function rejectIncident(id) {
  try {
    const res = await fetch(`${API_BASE}/api/v1/incidents/reject`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({incident_id: id})
    });
    showToast("Ação rejeitada pelo administrador.", "info");
    fetchIncidents();
    fetchStatus();
  } catch (err) {
    showToast(`Erro ao rejeitar: ${err}`, "error");
  }
}

// EVENT LISTENERS
function setupEventListeners() {
  document.getElementById("btn-refresh-all").addEventListener("click", () => {
    loadAllData();
    showToast("Dados atualizados!", "info");
  });

  // Filtros de Incidentes
  document.getElementById("inc-search").addEventListener("input", applyIncidentFilters);
  document.getElementById("filter-severity").addEventListener("change", applyIncidentFilters);
  document.getElementById("filter-status").addEventListener("change", applyIncidentFilters);
  document.getElementById("filter-host").addEventListener("change", applyIncidentFilters);

  // Limpeza de Incidentes
  document.getElementById("btn-clear-resolved").addEventListener("click", async () => {
    if (!confirm("Deseja limpar os incidentes já resolvidos e recuperados da lista?")) return;
    try {
      await fetch(`${API_BASE}/api/v1/incidents/clear`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({mode: "resolved"})
      });
      showToast("Incidentes resolvidos limpos com sucesso!", "success");
      fetchIncidents();
      fetchStatus();
    } catch (err) {
      showToast(`Erro ao limpar: ${err}`, "error");
    }
  });

  document.getElementById("btn-clear-all").addEventListener("click", async () => {
    if (!confirm("⚠️ Tem certeza que deseja limpar TODO o histórico de incidentes?")) return;
    try {
      await fetch(`${API_BASE}/api/v1/incidents/clear`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({mode: "all"})
      });
      showToast("Histórico de incidentes resetado!", "info");
      fetchIncidents();
      fetchStatus();
    } catch (err) {
      showToast(`Erro ao limpar: ${err}`, "error");
    }
  });

  // Re-diagnosticar no Modal
  document.getElementById("btn-modal-retest").addEventListener("click", async () => {
    if (!activeIncidentModalId) return;
    const btn = document.getElementById("btn-modal-retest");
    btn.disabled = true;
    btn.textContent = "⏳ Testando servidor em tempo real...";

    try {
      const res = await fetch(`${API_BASE}/api/v1/incidents/diagnose-now`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({incident_id: activeIncidentModalId})
      });
      const data = await res.json();
      if (data.success) {
        showToast(data.diagnostic.is_online ? "🟢 Servidor respondeu ao teste com sucesso!" : "🔴 Servidor continua inacessível.", "info");
        await fetchIncidents();
        openIncidentModal(activeIncidentModalId);
      }
    } catch (err) {
      showToast(`Erro ao re-testar: ${err}`, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "🔄 Diagnosticar Novamente Agora";
    }
  });

  // Fechar modal ao clicar fora
  document.getElementById("incident-modal").addEventListener("click", (e) => {
    if (e.target.id === "incident-modal") {
      closeIncidentModal();
    }
  });

  // Salvar IA Config
  document.getElementById("cfg-provider").addEventListener("change", () => {
    const p = document.getElementById("cfg-provider").value;
    const modelInput = document.getElementById("cfg-model");
    if (p === "gemini") modelInput.value = "gemini-1.5-flash";
    else if (p === "claude") modelInput.value = "claude-sonnet-4-5-20250929";
    else if (p === "openai") modelInput.value = "gpt-4o-mini";
    else if (p === "groq") modelInput.value = "llama-3.3-70b-versatile";
    else if (p === "ollama") modelInput.value = "llama3.1";
    toggleBaseUrlField();
  });

  document.getElementById("btn-toggle-key-visibility").addEventListener("click", () => {
    const inp = document.getElementById("cfg-api-key");
    inp.type = inp.type === "password" ? "text" : "password";
  });

  document.getElementById("form-ai-config").addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = {
      provider: document.getElementById("cfg-provider").value,
      api_key: document.getElementById("cfg-api-key").value,
      model: document.getElementById("cfg-model").value,
      temperature: parseFloat(document.getElementById("cfg-temp").value) || 0.2,
      base_url: document.getElementById("cfg-base-url").value
    };

    try {
      const res = await fetch(`${API_BASE}/api/v1/config`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      showToast(data.message || "Configurações salvas!", "success");
      fetchConfig();
      fetchStatus();
    } catch (err) {
      showToast(`Erro ao salvar: ${err}`, "error");
    }
  });

  document.getElementById("btn-test-ai-conn").addEventListener("click", async () => {
    const out = document.getElementById("ai-test-result");
    out.style.display = "block";
    out.className = "alert-box info";
    out.textContent = "Testando comunicação com a IA...";

    const payload = {
      provider: document.getElementById("cfg-provider").value,
      api_key: document.getElementById("cfg-api-key").value,
      model: document.getElementById("cfg-model").value,
      base_url: document.getElementById("cfg-base-url").value
    };

    try {
      const res = await fetch(`${API_BASE}/api/v1/config/test-ai`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (data.success) {
        out.className = "alert-box success";
        out.textContent = `🟢 Conexão com ${payload.provider.toUpperCase()} bem-sucedida!`;
      } else {
        out.className = "alert-box error";
        out.textContent = `🔴 Falha na conexão: ${data.error}`;
      }
    } catch (err) {
      out.className = "alert-box error";
      out.textContent = `Erro ao testar: ${err}`;
    }
  });

  // Salvar Prompts
  document.getElementById("form-prompt").addEventListener("submit", async (e) => {
    e.preventDefault();
    const prompt = document.getElementById("txt-system-prompt").value;
    try {
      const res = await fetch(`${API_BASE}/api/v1/prompts`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({custom_prompt: prompt})
      });
      showToast("System Prompt atualizado com sucesso!", "success");
    } catch (err) {
      showToast(`Erro: ${err}`, "error");
    }
  });

  document.getElementById("btn-restore-prompt").addEventListener("click", async () => {
    const res = await fetch(`${API_BASE}/api/v1/prompts`);
    const data = await res.json();
    document.getElementById("txt-system-prompt").value = data.default_prompt;
    showToast("Prompt restaurado para o padrão oficial.", "info");
  });

  // Salvar Autonomia
  document.getElementById("form-autonomy").addEventListener("submit", async (e) => {
    e.preventDefault();
    const level = document.querySelector('input[name="autonomy_level"]:checked').value;
    const maxRetries = parseInt(document.getElementById("cfg-max-retries").value);
    const isActive = document.getElementById("cfg-is-active").value === "true";

    try {
      await fetch(`${API_BASE}/api/v1/config`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          autonomy_level: level,
          max_retries_per_service: maxRetries,
          is_active: isActive
        })
      });
      showToast("Políticas de autonomia atualizadas!", "success");
      fetchStatus();
    } catch (err) {
      showToast(`Erro: ${err}`, "error");
    }
  });

  // Quick Tool Exec
  document.getElementById("form-quick-tool").addEventListener("submit", async (e) => {
    e.preventDefault();
    const tool = document.getElementById("quick-tool-select").value;
    const host = document.getElementById("quick-host-select").value;
    const outBox = document.getElementById("quick-tool-output");

    outBox.style.display = "block";
    outBox.textContent = `Executando ${tool}(host="${host}")...\n`;

    let params = {};
    if (tool.includes("ping")) params = {target_ip: host};
    else if (tool.includes("proxmox")) params = {host: host, resource: "vms"};
    else params = {host: host};

    try {
      const res = await fetch(`${API_BASE}/api/v1/tools/execute`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({tool: tool, params: params})
      });
      const data = await res.json();
      if (data.success) {
        const out = data.result.stdout || data.result.output || JSON.stringify(data.result, null, 2);
        outBox.textContent = out;
      } else {
        outBox.textContent = `ERRO: ${data.error || JSON.stringify(data.result)}`;
      }
    } catch (err) {
      outBox.textContent = `Falha na requisição: ${err}`;
    }
  });

  // Chat SRE
  document.getElementById("form-chat").addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = document.getElementById("chat-input");
    const msg = input.value.trim();
    if (!msg) return;

    appendChatMessage("user", "Você", msg);
    input.value = "";

    const loadingId = appendChatMessage("system", "🤖 ONLI-AIOPS", "Analisando infraestrutura e raciocinando...");

    try {
      const res = await fetch(`${API_BASE}/api/v1/chat`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({message: msg})
      });
      const data = await res.json();
      
      let reply = "";
      if (data.success) {
        reply = data.content;
      } else {
        reply = `⚠️ ${data.error || 'Não foi possível processar a resposta da IA.'}`;
      }

      document.getElementById(loadingId).querySelector(".msg-body").innerHTML = formatMarkdown(reply);
    } catch (err) {
      document.getElementById(loadingId).querySelector(".msg-body").textContent = `Erro de conexão: ${err}`;
    }
  });
}

function toggleBaseUrlField() {
  const p = document.getElementById("cfg-provider").value;
  const grp = document.getElementById("group-base-url");
  grp.style.display = (p === "ollama" || p === "openrouter") ? "flex" : "none";
}

function appendChatMessage(type, author, text) {
  const container = document.getElementById("chat-messages");
  const msgId = "msg-" + Math.random().toString(36).substr(2, 9);
  const div = document.createElement("div");
  div.id = msgId;
  div.className = `chat-msg ${type}`;
  div.innerHTML = `
    <div class="msg-author">${author}</div>
    <div class="msg-body">${formatMarkdown(text)}</div>
  `;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
  return msgId;
}

// WEBSOCKET FOR LIVE ALERTS
function initWebSocket() {
  const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${wsProtocol}//${window.location.host}/ws`;

  try {
    ws = new WebSocket(wsUrl);
    ws.onopen = () => console.log("WebSocket ONLI-AIOPS conectado!");
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === "new_incident" || msg.type === "incident_updated" || msg.type === "incidents_cleared") {
        fetchIncidents();
        fetchStatus();
        if (msg.incident) {
          showToast(`🚨 Incidente Atualizado: ${msg.incident.alertname} em ${msg.incident.instance}`, "info");
        }
      }
    };
    ws.onclose = () => {
      setTimeout(initWebSocket, 3000);
    };
  } catch (e) {
    console.warn("WebSocket indisponível, usando polling.");
  }
}

function showToast(text, type = "info") {
  const toast = document.getElementById("toast");
  toast.textContent = text;
  toast.style.display = "block";
  setTimeout(() => {
    toast.style.display = "none";
  }, 3500);
}

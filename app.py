import os
import json
import time
import uuid
import logging
import asyncio
from typing import Optional, List, Dict
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, Body, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from engine.ai_client import AIProviderClient
from engine.prompt_manager import get_system_prompt, DEFAULT_SYSTEM_PROMPT
from engine.risk_evaluator import evaluate_risk, RiskLevel
from engine.loop_breaker import LoopBreaker
from engine.smart_triage import SmartAlertTriage
from engine.runbooks import APPROVED_RUNBOOKS
from gateway.tool_gateway import ToolGateway

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("onli_aiops")

CONFIG_FILE = "/opt/monitoring/onli-aiops/data/config.json"
INCIDENTS_FILE = "/opt/monitoring/onli-aiops/data/incidents.json"

app = FastAPI(title="ONLI-AIOPS Management API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

gateway = ToolGateway()
loop_breaker = LoopBreaker(max_attempts=2, window_seconds=600)
smart_triage = SmartAlertTriage(max_offline_alerts=5, dedup_window_seconds=900)

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

ws_manager = ConnectionManager()

def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "provider": "claude",
        "api_key": "",
        "model": "claude-3-5-haiku-20241022",
        "base_url": "",
        "temperature": 0.2,
        "autonomy_level": "CONTROLLED",
        "auto_approval_max_risk": "BAIXO",
        "max_retries_per_service": 2,
        "is_active": True,
        "custom_system_prompt": ""
    }

def save_config(cfg: dict):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

def load_incidents() -> List[dict]:
    if os.path.exists(INCIDENTS_FILE):
        try:
            with open(INCIDENTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_incident(inc: dict):
    os.makedirs(os.path.dirname(INCIDENTS_FILE), exist_ok=True)
    incidents = load_incidents()
    incidents.insert(0, inc)
    incidents = incidents[:150]
    with open(INCIDENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(incidents, f, indent=2)

def get_ai_client(cfg: dict) -> AIProviderClient:
    return AIProviderClient(
        provider=cfg.get("provider", "claude"),
        api_key=cfg.get("api_key", ""),
        model=cfg.get("model", "claude-3-5-haiku-20241022"),
        base_url=cfg.get("base_url", ""),
        temperature=float(cfg.get("temperature", 0.2))
    )

def extract_clean_text(text: str) -> str:
    if not text:
        return ""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) > 2 and lines[0].startswith("```") and lines[-1] == "```":
            stripped = "\n".join(lines[1:-1]).strip()

    try:
        data = json.loads(stripped)
        if isinstance(data, dict):
            for k in ["resposta", "response", "content", "text", "mensagem", "message"]:
                if k in data and isinstance(data[k], str):
                    return data[k]
    except Exception:
        pass

    return text

# -------------------------------------------------------------
# API ROUTES
# -------------------------------------------------------------

@app.get("/api/v1/status")
async def get_status():
    cfg = load_config()
    incidents = load_incidents()
    pending = [i for i in incidents if i.get("status") == "AGUARDANDO_APROVACAO"]
    critical = [i for i in incidents if i.get("severity") == "CRITICAL"]
    triage_info = smart_triage.get_status_report()
    return {
        "status": "online",
        "is_active": cfg.get("is_active", True),
        "provider": cfg.get("provider", "claude"),
        "model": cfg.get("model", "claude-3-5-haiku-20241022"),
        "autonomy_level": cfg.get("autonomy_level", "CONTROLLED"),
        "has_api_key": bool(cfg.get("api_key", "")),
        "total_incidents": len(incidents),
        "critical_incidents": len(critical),
        "pending_approvals": len(pending),
        "triage": triage_info,
        "timestamp": time.time()
    }

@app.get("/api/v1/triage/status")
async def get_triage_status():
    return smart_triage.get_status_report()

@app.get("/api/v1/config")
async def get_config_endpoint():
    cfg = load_config()
    masked = dict(cfg)
    if masked.get("api_key"):
        raw = masked["api_key"]
        masked["api_key_masked"] = raw[:4] + "..." + raw[-4:] if len(raw) > 8 else "****"
        masked["has_api_key"] = True
    else:
        masked["api_key_masked"] = ""
        masked["has_api_key"] = False
    masked["api_key"] = ""
    return masked

@app.post("/api/v1/config")
async def save_config_endpoint(payload: dict = Body(...)):
    cfg = load_config()
    for k, v in payload.items():
        if k == "api_key" and not v:
            continue
        cfg[k] = v
    save_config(cfg)
    return {"success": True, "message": "Configurações atualizadas com sucesso!"}

@app.post("/api/v1/config/test-ai")
async def test_ai_connection(payload: dict = Body(...)):
    cfg = load_config()
    provider = payload.get("provider") or cfg.get("provider", "claude")
    api_key = payload.get("api_key") or cfg.get("api_key", "")
    model = payload.get("model") or cfg.get("model", "claude-3-5-haiku-20241022")
    base_url = payload.get("base_url") or cfg.get("base_url", "")
    
    client = AIProviderClient(provider=provider, api_key=api_key, model=model, base_url=base_url)
    res = await asyncio.to_thread(
        client.generate,
        "Você é o ONLI-AIOPS. Responda apenas com um JSON simples informando status OK.",
        "Teste de conectividade do agente. Retorne {\"status\": \"conectado\", \"mensagem\": \"IA Operacional\"}."
    )
    return res

@app.get("/api/v1/prompts")
async def get_prompts():
    cfg = load_config()
    return {
        "default_prompt": DEFAULT_SYSTEM_PROMPT,
        "custom_prompt": cfg.get("custom_system_prompt", ""),
        "active_prompt": get_system_prompt(cfg.get("custom_system_prompt", ""))
    }

@app.post("/api/v1/prompts")
async def save_prompts(payload: dict = Body(...)):
    cfg = load_config()
    cfg["custom_system_prompt"] = payload.get("custom_prompt", "")
    save_config(cfg)
    return {"success": True, "message": "System prompt atualizado!"}

@app.get("/api/v1/runbooks")
async def get_runbooks():
    return APPROVED_RUNBOOKS

@app.get("/api/v1/incidents")
async def get_incidents():
    return load_incidents()

@app.get("/api/v1/incidents/{incident_id}")
async def get_incident_detail(incident_id: str):
    incidents = load_incidents()
    for inc in incidents:
        if inc.get("id") == incident_id:
            return inc
    raise HTTPException(status_code=404, detail="Incidente não encontrado.")

@app.post("/api/v1/incidents/diagnose-now")
async def re_diagnose_incident(payload: dict = Body(...)):
    incident_id = payload.get("incident_id")
    incidents = load_incidents()
    target_inc = None
    for inc in incidents:
        if inc.get("id") == incident_id:
            target_inc = inc
            break
            
    if not target_inc:
        raise HTTPException(status_code=404, detail="Incidente não encontrado.")
    
    host = target_inc.get("host_target", target_inc.get("instance"))
    ping_res = await asyncio.to_thread(gateway.testar_ping, host)
    server_res = await asyncio.to_thread(gateway.consultar_servidor, host)
    
    is_online = ping_res.get("success", False) or server_res.get("success", False)
    
    if is_online:
        smart_triage.handle_recovery(host)
    
    re_diag = {
        "timestamp": time.time(),
        "ping": ping_res,
        "server": server_res,
        "is_online": is_online
    }
    
    target_inc["latest_re_diagnostic"] = re_diag
    if is_online and target_inc.get("status") not in ("RESOLVIDO", "RESOLVIDO_AUTOMATICAMENTE", "RESOLVIDO_RECOVERY"):
        target_inc["status"] = "RECUPERADO_ONLINE"
    
    with open(INCIDENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(incidents, f, indent=2)
    
    await ws_manager.broadcast({"type": "incident_updated", "incident": target_inc})
    return {"success": True, "diagnostic": re_diag, "incident": target_inc}

@app.post("/api/v1/incidents/clear")
async def clear_incidents(payload: dict = Body(...)):
    mode = payload.get("mode", "resolved")
    incidents = load_incidents()
    if mode == "all":
        incidents = []
    else:
        incidents = [i for i in incidents if i.get("status") not in ("RESOLVIDO", "RECUPERADO_ONLINE", "REJEITADO_PELO_ADMIN", "RESOLVIDO_AUTOMATICAMENTE", "RESOLVIDO_RECOVERY")]
    
    with open(INCIDENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(incidents, f, indent=2)
    
    await ws_manager.broadcast({"type": "incidents_cleared", "remaining": len(incidents)})
    return {"success": True, "remaining": len(incidents)}

@app.post("/api/v1/tools/execute")
async def execute_tool_endpoint(payload: dict = Body(...)):
    tool = payload.get("tool", "")
    params = payload.get("params", {})
    
    if not hasattr(gateway, tool):
        raise HTTPException(status_code=400, detail=f"Ferramenta {tool} não existe no Tool Gateway.")
    
    fn = getattr(gateway, tool)
    try:
        result = await asyncio.to_thread(fn, **params)
        return {"success": True, "tool": tool, "result": result}
    except Exception as e:
        return {"success": False, "tool": tool, "error": str(e)}

@app.post("/api/v1/chat")
async def chat_with_agent(payload: dict = Body(...)):
    user_msg = payload.get("message", "").strip()
    if not user_msg:
        raise HTTPException(status_code=400, detail="Mensagem não pode ser vazia.")
    
    cfg = load_config()
    ai_client = get_ai_client(cfg)
    sys_prompt = get_system_prompt(cfg.get("custom_system_prompt", ""))
    
    prompt = f"""O administrador de infraestrutura enviou a seguinte mensagem/solicitação:
"{user_msg}"

Analise a solicitação, verifique os 22 princípios do ONLI-AIOPS e forneça uma resposta técnica, clara, estruturada e orientada a dados.
Responda diretamente em texto com formatação Markdown profissional (com títulos, listas e blocos de código se aplicável). NÃO envolva sua resposta em JSON."""

    res = await asyncio.to_thread(ai_client.generate, sys_prompt, prompt)
    if res.get("success"):
        res["content"] = extract_clean_text(res.get("content", ""))
    return res

@app.post("/api/v1/incidents/approve")
async def approve_incident(payload: dict = Body(...)):
    incident_id = payload.get("incident_id")
    incidents = load_incidents()
    target_inc = None
    for inc in incidents:
        if inc.get("id") == incident_id:
            target_inc = inc
            break
            
    if not target_inc:
        raise HTTPException(status_code=404, detail="Incidente não encontrado.")
    
    tool = target_inc.get("proposed_tool")
    params = target_inc.get("proposed_params", {})
    
    if hasattr(gateway, tool):
        fn = getattr(gateway, tool)
        exec_res = await asyncio.to_thread(fn, **params)
        target_inc["status"] = "RESOLVIDO" if exec_res.get("success") else "FALHOU"
        target_inc["execution_result"] = exec_res
        target_inc["approved_at"] = time.time()
        
        with open(INCIDENTS_FILE, "w", encoding="utf-8") as f:
            json.dump(incidents, f, indent=2)
        await ws_manager.broadcast({"type": "incident_updated", "incident": target_inc})
        return {"success": True, "result": exec_res, "incident": target_inc}
    else:
        raise HTTPException(status_code=400, detail=f"Ferramenta {tool} inválida.")

@app.post("/api/v1/incidents/reject")
async def reject_incident(payload: dict = Body(...)):
    incident_id = payload.get("incident_id")
    incidents = load_incidents()
    for inc in incidents:
        if inc.get("id") == incident_id:
            inc["status"] = "REJEITADO_PELO_ADMIN"
            inc["rejected_at"] = time.time()
            with open(INCIDENTS_FILE, "w", encoding="utf-8") as f:
                json.dump(incidents, f, indent=2)
            await ws_manager.broadcast({"type": "incident_updated", "incident": inc})
            return {"success": True, "message": "Ação rejeitada com sucesso."}
    raise HTTPException(status_code=404, detail="Incidente não encontrado.")

# -------------------------------------------------------------
# ASYNC INCIDENT PROCESSOR COM TRIAGEM INTELIGENTE
# -------------------------------------------------------------
async def process_single_alert(alert: dict, cfg: dict):
    status = alert.get("status", "firing")
    labels = alert.get("labels", {})
    annotations = alert.get("annotations", {})
    
    alertname = labels.get("alertname", "UnknownAlert")
    instance = labels.get("instance", "unknown")
    severity = labels.get("severity", "warning").upper()
    summary = annotations.get("summary", "")
    description = annotations.get("description", "")
    host_target = labels.get("server_name") or instance.split(":")[0].split(" ")[0]
    
    # 1. TRATAMENTO DE RECOVERY (RESOLVED)
    if status == "resolved":
        smart_triage.handle_recovery(host_target)
        incidents = load_incidents()
        updated = False
        for inc in incidents:
            if inc.get("host_target") == host_target and inc.get("status") not in ("RESOLVIDO", "RESOLVIDO_RECOVERY"):
                inc["status"] = "RESOLVIDO_RECOVERY"
                inc["resolved_at"] = time.time()
                updated = True
        if updated:
            with open(INCIDENTS_FILE, "w", encoding="utf-8") as f:
                json.dump(incidents, f, indent=2)
            await ws_manager.broadcast({"type": "incidents_resolved_recovery", "host": host_target})
        return

    incident_id = str(uuid.uuid4())[:8]
    evidence = {}
    
    # Teste rápido preliminar de ping
    ping_res = await asyncio.to_thread(gateway.testar_ping, host_target)
    evidence["ping_test"] = ping_res
    is_ping_alive = ping_res.get("success", False)
    is_alert_offline = smart_triage.is_offline_type(alertname, labels, annotations)

    # 2. AVALIAÇÃO DA TRIAGEM INTELIGENTE (FILTRO OFFLINE & DEDUP)
    triage_dec = smart_triage.evaluate(host_target, alertname, is_ping_alive, is_alert_offline)

    # Se a triagem decidir ignorar por repetição (> 5 alertas offline já recebidos)
    if triage_dec["action"] == "IGNORE_REPEATED_OFFLINE":
        logger.info(f"[SmartTriage] {triage_dec[message]}")
        return

    # Se a triagem decidir registrar diagnóstico determinístico sem IA (Economia de 100% dos tokens)
    if not triage_dec["should_call_ai"]:
        incident_record = {
            "id": incident_id,
            "timestamp": time.time(),
            "alertname": alertname,
            "instance": instance,
            "host_target": host_target,
            "severity": severity,
            "summary": summary or f"Servidor {host_target} offline",
            "description": description or triage_dec["message"],
            "evidence": evidence,
            "ai_diagnosis": triage_dec.get("deterministic_diag", triage_dec["message"]),
            "hypotheses": triage_dec.get("hypotheses", ["Link de rede rompido ou host desligado fisicamente"]),
            "proposed_tool": None,
            "proposed_params": {},
            "risk_level": "ALTO" if is_alert_offline or not is_ping_alive else "BAIXO",
            "status": triage_dec["status"],
            "triage_action": triage_dec["action"],
            "offline_count": triage_dec.get("offline_count", 0)
        }
        save_incident(incident_record)
        await ws_manager.broadcast({"type": "new_incident", "incident": incident_record})
        return

    # 3. HOST ONLINE E ALERTA ELEGÍVEL -> COLETAR MAIS EVIDÊNCIAS E CHAMAR IA
    if "cpu" in alertname.lower():
        evidence["top_processes"] = await asyncio.to_thread(gateway.consultar_processos, host_target, top_n=5)
    elif "disk" in alertname.lower():
        evidence["disk_usage"] = await asyncio.to_thread(gateway.consultar_disco, host_target)
    elif not is_alert_offline:
        evidence["server_status"] = await asyncio.to_thread(gateway.consultar_servidor, host_target)

    ai_client = get_ai_client(cfg)
    sys_prompt = get_system_prompt(cfg.get("custom_system_prompt", ""))
    
    ai_prompt = f"""Um alerta de infraestrutura foi disparado:
- Alerta: {alertname}
- Servidor / Instância: {instance} ({host_target})
- Severidade: {severity}
- Resumo: {summary}
- Descrição: {description}
- Evidências Coletadas:
{json.dumps(evidence, indent=2)[:1000]}

Siga os 22 princípios do ONLI-AIOPS.
Forme hipóteses, avalie o risco e recomende a MENOR ação necessária para corrigir ou diagnosticar.
Selecione uma ferramenta:
[consultar_servidor, consultar_cpu, consultar_memoria, consultar_disco, consultar_logs, consultar_processos, testar_ping, testar_porta, reiniciar_servico, consultar_proxmox, consultar_mikrotik]

Responda em formato JSON com o seguinte schema:
{{
  "diagnostico": "Explicação detalhada e clara da causa provável em português",
  "probabilidade": "ALTA / MÉDIA / BAIXA",
  "hipoteses": ["Hipótese 1: Descrição", "Hipótese 2: Descrição"],
  "acao_proposta": "Descrição da ação",
  "ferramenta": "nome_da_ferramenta_ou_nenhuma",
  "parametros": {{"param": "valor"}},
  "nivel_risco": "BAIXO / MÉDIO / ALTO / CRÍTICO",
  "justificativa": "Por que esta ação é necessária"
}}"""

    ai_response = await asyncio.to_thread(ai_client.generate, sys_prompt, ai_prompt)
    ai_parsed = {}
    if ai_response.get("success"):
        try:
            raw_c = extract_clean_text(ai_response.get("content", "{}"))
            ai_parsed = json.loads(raw_c) if raw_c.startswith("{") else {"diagnostico": raw_c}
        except Exception:
            ai_parsed = {"diagnostico": ai_response.get("content", ""), "nivel_risco": "MÉDIO"}

    risk = ai_parsed.get("nivel_risco", "MÉDIO").upper()
    autonomy = cfg.get("autonomy_level", "CONTROLLED")
    tool = ai_parsed.get("ferramenta")
    params = ai_parsed.get("parametros", {})
    
    incident_record = {
        "id": incident_id,
        "timestamp": time.time(),
        "alertname": alertname,
        "instance": instance,
        "host_target": host_target,
        "severity": severity,
        "summary": summary,
        "description": description,
        "evidence": evidence,
        "ai_diagnosis": ai_parsed.get("diagnostico", summary or "Diagnóstico automático em andamento"),
        "hypotheses": ai_parsed.get("hipoteses", []),
        "proposed_tool": tool,
        "proposed_params": params,
        "risk_level": risk,
        "status": "PROCESSADO"
    }

    if autonomy == "OBSERVATION" or not tool or tool == "nenhuma":
        incident_record["status"] = "OBSERVACAO_GERADA"
    elif autonomy == "CONTROLLED" and risk == "BAIXO":
        if loop_breaker.can_execute(host_target, tool, str(params)):
            loop_breaker.record_attempt(host_target, tool, str(params))
            if hasattr(gateway, tool):
                fn = getattr(gateway, tool)
                exec_res = await asyncio.to_thread(fn, **params)
                incident_record["status"] = "RESOLVIDO_AUTOMATICAMENTE" if exec_res.get("success") else "FALHOU_EXECUCAO"
                incident_record["execution_result"] = exec_res
            else:
                incident_record["status"] = "FERRAMENTA_NAO_ENCONTRADA"
        else:
            incident_record["status"] = "LOOP_DETECTADO_ESCALADO"
    else:
        incident_record["status"] = "AGUARDANDO_APROVACAO"

    save_incident(incident_record)
    await ws_manager.broadcast({"type": "new_incident", "incident": incident_record})

@app.post("/api/v1/webhook/alertmanager")
async def alertmanager_webhook(request: Request, background_tasks: BackgroundTasks):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"status": "invalid json"}, status_code=400)
    
    cfg = load_config()
    if not cfg.get("is_active", True):
        return {"status": "ignored", "reason": "ONLI-AIOPS is paused"}

    alerts = data.get("alerts", [])
    for alert in alerts:
        background_tasks.add_task(process_single_alert, alert, cfg)

    return {"status": "queued", "count": len(alerts)}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)

app.mount("/", StaticFiles(directory="/opt/monitoring/onli-aiops/static", html=True), name="static")

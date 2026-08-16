import time
import logging
from collections import defaultdict

logger = logging.getLogger("onli_aiops_triage")

class SmartAlertTriage:
    """
    Sistema Inteligente de Triagem e Supressão de Alertas:
    1. Detecta servidores offline/inacessíveis e impede chamadas desnecessárias de IA.
    2. Após N alertas consecutivos de offline (padrão: 5), suprime novos alertas para evitar poluição e gasto de tokens.
    3. Reabilita o monitoramento automaticamente quando o host volta a responder (recovery).
    4. Deduplica alertas idênticos dentro de uma janela de tempo.
    """

    def __init__(self, max_offline_alerts: int = 5, dedup_window_seconds: int = 900):
        self.max_offline_alerts = max_offline_alerts
        self.dedup_window_seconds = dedup_window_seconds
        
        # host -> int (contador de alertas offline seguidos)
        self.host_offline_counts = defaultdict(int)
        
        # host -> bool (se está em estado de supressão ativa)
        self.host_suppressed = defaultdict(bool)
        
        # host -> float (timestamp do primeiro alerta offline)
        self.host_offline_since = {}
        
        # key (host:alertname) -> timestamp da última chamada de IA
        self.alert_cache = {}
        
        # Métricas de economia
        self.stats = {
            "total_alerts_received": 0,
            "ai_calls_executed": 0,
            "ai_calls_saved_offline": 0,
            "ai_calls_saved_dedup": 0,
            "suppressed_alerts_dropped": 0
        }

    def is_offline_type(self, alertname: str, labels: dict = None, annotations: dict = None) -> bool:
        labels = labels or {}
        annotations = annotations or {}
        text = f"{alertname} {labels.get('alertname', '')} {labels.get('job', '')} {annotations.get('summary', '')} {annotations.get('description', '')}".lower()
        keywords = [
            "offline", "hostdown", "targetdown", "instancedown", 
            "probefailed", "probe_failed", "ping_failed", "pingtimeout", 
            "packetloss", "unreachable", "down", "no_route", "host is down"
        ]
        return any(k in text for k in keywords)

    def evaluate(self, host: str, alertname: str, is_ping_alive: bool, is_alert_offline: bool) -> dict:
        self.stats["total_alerts_received"] += 1
        now = time.time()
        
        # 1. CASO HOST INACESSÍVEL / OFFLINE
        if not is_ping_alive or is_alert_offline:
            if host not in self.host_offline_since or self.host_offline_counts[host] == 0:
                self.host_offline_since[host] = now

            self.host_offline_counts[host] += 1
            count = self.host_offline_counts[host]
            
            # Se excedeu o limite máximo de alertas offline repetidos (ex: > 5)
            if count > self.max_offline_alerts:
                self.host_suppressed[host] = True
                self.stats["suppressed_alerts_dropped"] += 1
                self.stats["ai_calls_saved_offline"] += 1
                return {
                    "should_call_ai": False,
                    "action": "IGNORE_REPEATED_OFFLINE",
                    "status": "SUPRIMIDO_OFFLINE_LIMITE_ATINGIDO",
                    "offline_count": count,
                    "message": f"Host '{host}' permanece offline ({count} alertas consecutivos). Alertas repetidos suprimidos pelo filtro inteligente.",
                    "deterministic_diag": (
                        f"⚠️ ALERTA SUPRIMIDO POR REPETIÇÃO: O host '{host}' continua inacessível na rede após {count} notificações. "
                        "A IA não atua em hosts desligados/offline. Novos alertas deste host serão silenciados até o restabelecimento (Recovery)."
                    )
                }
            else:
                self.stats["ai_calls_saved_offline"] += 1
                return {
                    "should_call_ai": False,
                    "action": "DETERMINISTIC_OFFLINE_LOG",
                    "status": "SERVIDOR_OFFLINE_SEM_ACAO_IA",
                    "offline_count": count,
                    "message": f"Host '{host}' está offline ou inacessível. Ações de IA suprimidas (Tokens economizados).",
                    "deterministic_diag": (
                        f"🔴 DIAGNÓSTICO DETERMINÍSTICO: O servidor/instância '{host}' está offline ou não responde a pacotes ICMP/TCP na rede. "
                        "Como não há conectividade física/IP com o host, ações de software, comandos SSH ou restarts de serviços remotos não podem ser executados. "
                        "A chamada à API de IA foi suprimida para economia de tokens. Verifique o link de rede, energia física ou status do hipervisor."
                    ),
                    "hypotheses": [
                        "Cabo de rede desconectado, queda de energia física ou nó desligado",
                        "Problema no switch local, VLAN ou rota de gateway",
                        "Bloqueio de firewall perimetral ou rota estática ausente"
                    ]
                }

        # 2. CASO HOST ONLINE / RECUPERADO
        if host in self.host_offline_counts and self.host_offline_counts[host] > 0:
            logger.info(f"[SmartTriage] Host '{host}' recuperou conectividade. Resetando contadores.")
            self.host_offline_counts[host] = 0
            self.host_suppressed[host] = False
            self.host_offline_since.pop(host, None)

        # 3. DEDUPLICAÇÃO DE ALERTAS NORMAIS REPETIDOS
        cache_key = f"{host}:{alertname}"
        if cache_key in self.alert_cache:
            last_call = self.alert_cache[cache_key]
            if now - last_call < self.dedup_window_seconds:
                self.stats["ai_calls_saved_dedup"] += 1
                return {
                    "should_call_ai": False,
                    "action": "DEDUP_RECENT_AI_CALL",
                    "status": "ALERTA_REPETIDO_CONSOLIDADO",
                    "message": f"Alerta '{alertname}' em '{host}' já analisado recentemente ({int(now - last_call)}s atrás). Chamada de IA suprimida.",
                    "deterministic_diag": f"Alerta repetido '{alertname}' consolidado. Última análise recente ainda válida."
                }

        # 4. ALERTA NOVO E HOST ONLINE -> CHAMA IA PARA DIAGNÓSTICO PROFUNDO
        self.alert_cache[cache_key] = now
        self.stats["ai_calls_executed"] += 1
        return {
            "should_call_ai": True,
            "action": "CALL_AI",
            "status": "DIAGNOSTICANDO_IA",
            "message": f"Host '{host}' online. Enviando para análise inteligente da IA."
        }

    def handle_recovery(self, host: str):
        """Limpa o estado de offline e cancela supressão quando o host fica online"""
        if host in self.host_offline_counts:
            self.host_offline_counts[host] = 0
        if host in self.host_suppressed:
            self.host_suppressed[host] = False
        self.host_offline_since.pop(host, None)
        keys_to_del = [k for k in self.alert_cache if k.startswith(f"{host}:")]
        for k in keys_to_del:
            del self.alert_cache[k]
        logger.info(f"[SmartTriage] Recovery processado para '{host}'. Monitoramento normal reativado.")

    def get_status_report(self) -> dict:
        suppressed_list = [h for h, is_sup in self.host_suppressed.items() if is_sup]
        offline_tracking = {h: c for h, c in self.host_offline_counts.items() if c > 0}
        return {
            "stats": self.stats,
            "suppressed_hosts": suppressed_list,
            "offline_hosts_tracking": offline_tracking,
            "max_offline_alerts_threshold": self.max_offline_alerts,
            "dedup_window_minutes": self.dedup_window_seconds // 60
        }

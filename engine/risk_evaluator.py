# Classificador de Risco Operacional para ONLI-AIOPS

class RiskLevel:
    LOW = "BAIXO"
    MEDIUM = "MÉDIO"
    HIGH = "ALTO"
    CRITICAL = "CRÍTICO"

def evaluate_risk(action_type: str, target: str, command: str = "") -> str:
    action_type = action_type.lower()
    command = command.lower()

    # CRÍTICO: Comandos destrutivos
    destructive_keywords = ["rm ", "rmdir", "destroy", "mkfs", "wipefs", "fdisk", "parted", "drop table", "truncate", "iptables -f", "firewall reset", "remove"]
    if any(kw in command for kw in destructive_keywords) or any(kw in action_type for kw in destructive_keywords):
        return RiskLevel.CRITICAL

    # ALTO: Reinício de nós de infraestrutura, Proxmox, MikroTik, Storage, DNS, Firewall
    if any(kw in action_type for kw in ["reboot_server", "reboot_vm", "alterar_firewall", "alterar_rotas", "alterar_dns", "modificar_proxmox"]):
        return RiskLevel.HIGH
    if any(kw in command for kw in ["reboot", "shutdown", "pveceph", "zpool destroy", "pct destroy", "qm destroy"]):
        return RiskLevel.HIGH

    # MÉDIO: Reiniciar serviço de produção, alterar parâmetros de configuração, reiniciar aplicação
    if any(kw in action_type for kw in ["restart_critical_service", "restart_db", "alterar_config", "executar_playbook"]):
        return RiskLevel.MEDIUM
    if "restart" in action_type and any(crit in target.lower() for crit in ["mysql", "postgres", "pve-cluster", "docker", "tailscaled"]):
        return RiskLevel.MEDIUM

    # BAIXO: Consultas, diagnósticos, logs, ping, restart de serviços não-críticos previamente aprovados
    if any(kw in action_type for kw in ["consultar", "status", "logs", "ping", "testar_porta", "restart_service", "restart_container", "limpar_temp"]):
        return RiskLevel.LOW

    return RiskLevel.MEDIUM

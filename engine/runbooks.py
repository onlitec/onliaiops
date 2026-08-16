# Catálogo de Procedimentos Operacionais Padrão (Runbooks) do ONLI-AIOPS

APPROVED_RUNBOOKS = {
    "restart_service": {
        "description": "Reiniciar serviço do sistema com verificação prévia e pós-validação de status",
        "risk": "BAIXO",
        "allowed_services": ["node_exporter", "promtail", "nginx", "apache2", "cadvisor", "snmpd", "pdm-exporter"],
        "steps": ["Verificar status", "Coletar logs de erro", "Executar systemctl restart", "Aguardar 3s", "Validar systemctl is-active"]
    },
    "restart_container": {
        "description": "Reiniciar container Docker após inspeção de logs e dependências",
        "risk": "BAIXO",
        "allowed_containers": ["monitoring-cadvisor", "monitoring-promtail", "monitoring-snmp-exporter", "monitoring-blackbox-exporter", "monitoring-loki"],
        "steps": ["Coletar últimas 30 linhas de log", "Verificar container health", "Executar docker restart", "Validar container running"]
    },
    "cleanup_temp_files": {
        "description": "Limpeza segura de arquivos temporários autorizados em caso de disco alto",
        "risk": "BAIXO",
        "allowed_paths": ["/tmp/prometheus-*", "/var/log/journal/rotated", "/var/cache/apt/archives/*.deb"],
        "steps": ["Verificar uso do disco", "Limpar caches autorizados", "Validar novo espaço em disco"]
    },
    "zfs_scrub_status": {
        "description": "Verificar saúde de pools ZFS e status de resilvering/scrub",
        "risk": "BAIXO",
        "steps": ["Executar zpool status -x", "Coletar erros de I/O", "Alertar se houver pool degradado"]
    },
    "proxmox_vm_restart": {
        "description": "Reinício seguro de VM no Proxmox após falha persistente",
        "risk": "ALTO",
        "requires_approval": True,
        "steps": ["Verificar qm status", "Solicitar aprovação", "Executar qm reboot / qm start", "Validar ping e SSH"]
    }
}

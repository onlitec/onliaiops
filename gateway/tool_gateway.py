import subprocess
import json
import logging
import socket
import ssl
import urllib.request

logger = logging.getLogger("onli_aiops_gateway")

FORBIDDEN_COMMANDS = [
    "rm ", "rmdir", "destroy", "mkfs", "wipefs", "fdisk", "parted",
    "drop table", "truncate", "iptables -f", "firewall reset", "shutdown -h"
]

SERVER_TARGETS = {
    "pve1": "192.168.0.200",
    "pve-1-gerencial": "192.168.0.200",
    "pve2": "192.168.0.235",
    "pve-2-gerencial": "192.168.0.235",
    "pve2-onlitec": "172.20.120.128",
    "pve2.onlitec.corp": "172.20.120.128",
    "pdm": "127.0.0.1",
    "pdm-onlitec-local": "127.0.0.1",
    "pbs": "100.100.4.115",
    "pbs-deb12": "100.100.4.115",
    "relayservergerencial": "100.101.166.8",
    "relayserver-helpseg": "100.72.185.126",
    "onlihost-vps-8gb": "100.111.0.33",
    "intranet-esqualyvale": "100.104.52.101",
    "mikrotik": "172.20.120.1",
    "mikrotik-rb750gr3": "172.20.120.1",
    "truenas-gerencial": "100.71.17.44",
    "truenas-scale-1-esqualyvale": "100.104.220.102"
}

# Credenciais Dedicadas do ONLI-AIOPS (Zero-Root Policy)
PBS_TOKEN = "onliaiops@pbs!AIOPS-TOKEN:ec6e28d2-d37c-4990-8fa8-28cf64a738a8"

class ToolGateway:
    def __init__(self):
        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE

    def _resolve_ip(self, host: str) -> str:
        return SERVER_TARGETS.get(host.lower(), host)

    def _execute_ssh(self, host_ip: str, cmd: str, user: str = "onliaiops", timeout: int = 15) -> dict:
        # Segurança: Bloquear comandos destrutivos
        cmd_lower = cmd.lower()
        if any(f in cmd_lower for f in FORBIDDEN_COMMANDS):
            return {
                "success": False,
                "error": "BLOQUEIO DE SEGURANÇA: O comando contém instrução destrutiva proibida.",
                "command": cmd
            }

        # Se for local
        if host_ip in ("127.0.0.1", "localhost"):
            try:
                res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
                return {"success": res.returncode == 0, "stdout": res.stdout, "stderr": res.stderr, "returncode": res.returncode}
            except Exception as e:
                return {"success": False, "error": str(e)}

        # Se for MikroTik (MikroTik usa usuário alfreire)
        if host_ip == "172.20.120.1":
            ssh_cmd = ["ssh", "-p", "2222", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5", f"alfreire@{host_ip}", cmd]
        else:
            ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5", f"{user}@{host_ip}", cmd]

        try:
            res = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=timeout)
            return {
                "success": res.returncode == 0,
                "stdout": res.stdout,
                "stderr": res.stderr,
                "returncode": res.returncode
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"Timeout após {timeout}s ao conectar em {host_ip}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # 1. Consultar Servidor Geral
    def consultar_servidor(self, host: str) -> dict:
        ip = self._resolve_ip(host)
        cmd = "hostname && uptime && free -h && df -h /"
        return self._execute_ssh(ip, cmd, user="onliaiops")

    # 2. Consultar CPU
    def consultar_cpu(self, host: str) -> dict:
        ip = self._resolve_ip(host)
        cmd = "top -b -n 1 | head -n 15"
        return self._execute_ssh(ip, cmd, user="onliaiops")

    # 3. Consultar Memória
    def consultar_memoria(self, host: str) -> dict:
        ip = self._resolve_ip(host)
        cmd = "free -m && vmstat 1 2"
        return self._execute_ssh(ip, cmd, user="onliaiops")

    # 4. Consultar Disco e I/O
    def consultar_disco(self, host: str) -> dict:
        ip = self._resolve_ip(host)
        cmd = "df -hT && (sudo zpool list 2>/dev/null || true) && (iostat -xz 1 2 2>/dev/null || true)"
        return self._execute_ssh(ip, cmd, user="onliaiops")

    # 5. Consultar Logs de Serviço
    def consultar_logs(self, host: str, service: str, lines: int = 30) -> dict:
        ip = self._resolve_ip(host)
        lines = min(int(lines), 100)
        cmd = f"sudo journalctl -u {service} -n {lines} --no-pager"
        return self._execute_ssh(ip, cmd, user="onliaiops")

    # 6. Consultar Processos
    def consultar_processos(self, host: str, top_n: int = 10) -> dict:
        ip = self._resolve_ip(host)
        top_n = min(int(top_n), 30)
        cmd = f"ps aux --sort=-%cpu | head -n {top_n + 1}"
        return self._execute_ssh(ip, cmd, user="onliaiops")

    # 7. Testar Ping
    def testar_ping(self, target_ip: str, count: int = 3) -> dict:
        ip = self._resolve_ip(target_ip)
        try:
            res = subprocess.run(["ping", "-c", str(count), "-W", "2", ip], capture_output=True, text=True, timeout=10)
            return {"success": res.returncode == 0, "output": res.stdout, "target": ip}
        except Exception as e:
            return {"success": False, "error": str(e), "target": ip}

    # 8. Testar Porta TCP
    def testar_porta(self, target_ip: str, port: int, timeout: int = 3) -> dict:
        ip = self._resolve_ip(target_ip)
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            result = s.connect_ex((ip, int(port)))
            s.close()
            is_open = (result == 0)
            return {"success": is_open, "port": port, "target": ip, "status": "ABERTA" if is_open else "FECHADA/INACESSIVEL"}
        except Exception as e:
            return {"success": False, "error": str(e), "port": port, "target": ip}

    # 9. Reiniciar Serviço Seguro
    def reiniciar_servico(self, host: str, service: str) -> dict:
        ip = self._resolve_ip(host)
        service = "".join(c for c in service if c.isalnum() or c in "-_.")
        cmd = f"sudo systemctl restart {service} && sleep 2 && sudo systemctl is-active {service}"
        return self._execute_ssh(ip, cmd, user="onliaiops")

    # 10. Consultar Proxmox VE
    def consultar_proxmox(self, host: str, resource: str = "vms") -> dict:
        ip = self._resolve_ip(host)
        if resource == "vms":
            cmd = "sudo qm list && sudo pct list"
        elif resource == "storage":
            cmd = "sudo pvesm status"
        else:
            cmd = "sudo pveversion && sudo pvesubscription get 2>/dev/null || true"
        return self._execute_ssh(ip, cmd, user="onliaiops")

    # 11. Consultar Proxmox Backup Server (PBS API com Token onliaiops)
    def consultar_pbs(self, resource: str = "status") -> dict:
        base = "https://100.100.4.115:8007/api2/json"
        headers = {"Authorization": f"PBSAPIToken={PBS_TOKEN}"}
        try:
            if resource == "datastore":
                url = f"{base}/admin/datastore/STORAGEBOX-01/status"
            else:
                url = f"{base}/nodes/localhost/status"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, context=self.ctx, timeout=8) as r:
                return {"success": True, "data": json.loads(r.read().decode()).get("data")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # 12. Consultar MikroTik
    def consultar_mikrotik(self, command: str) -> dict:
        cmd_clean = command.strip()
        if any(w in cmd_clean.lower() for w in ["remove", "disable", "set", "add", "reset"]):
            return {"success": False, "error": "Comandos de modificação no MikroTik exigem aprovação e não podem ser rodados diretamente."}
        return self._execute_ssh("172.20.120.1", cmd_clean, user="alfreire")

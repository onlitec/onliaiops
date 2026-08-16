import urllib.request
import urllib.parse
import urllib.error
import json
import ssl
import logging

logger = logging.getLogger("onli_aiops_ai")

CLAUDE_MODEL_MAP = {
    "claude-3-5-sonnet-20241022": "claude-sonnet-4-5-20250929",
    "claude-3-5-sonnet-20240620": "claude-sonnet-4-5-20250929",
    "claude-3-5-sonnet": "claude-sonnet-4-5-20250929",
    "claude-3.5-sonnet": "claude-sonnet-4-5-20250929",
    "claude-sonnet": "claude-sonnet-4-5-20250929",
    "claude-3-5-haiku-20241022": "claude-haiku-4-5-20251001",
    "claude-3-haiku-20240307": "claude-haiku-4-5-20251001",
    "claude-3-5-haiku": "claude-haiku-4-5-20251001",
    "claude-haiku": "claude-haiku-4-5-20251001",
    "claude-opus": "claude-opus-4-5-20251101",
    "claude-3-opus": "claude-opus-4-5-20251101"
}

class AIProviderClient:
    def __init__(self, provider: str = "gemini", api_key: str = "", model: str = "", base_url: str = "", temperature: float = 0.2):
        self.provider = provider.lower()
        self.api_key = api_key.strip()
        self.model = model.strip() if model else ""
        self.base_url = base_url
        self.temperature = temperature
        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE

    def generate(self, system_prompt: str, user_prompt: str) -> dict:
        if not self.api_key and self.provider != "ollama":
            return {
                "success": False,
                "error": f"Chave de API não configurada para o provedor '{self.provider}'. Cadastre a chave no Painel Web.",
                "content": ""
            }

        try:
            if self.provider == "gemini":
                return self._call_gemini(system_prompt, user_prompt)
            elif self.provider in ("openai", "groq", "openrouter"):
                return self._call_openai_compatible(system_prompt, user_prompt)
            elif self.provider in ("claude", "anthropic"):
                return self._call_claude(system_prompt, user_prompt)
            elif self.provider == "ollama":
                return self._call_ollama(system_prompt, user_prompt)
            else:
                return {"success": False, "error": f"Provedor '{self.provider}' não suportado.", "content": ""}
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_raw = e.read().decode("utf-8")
                err_json = json.loads(err_raw)
                if "error" in err_json:
                    if isinstance(err_json["error"], dict):
                        err_body = err_json["error"].get("message", err_raw)
                    else:
                        err_body = str(err_json["error"])
                elif "message" in err_json:
                    err_body = err_json["message"]
                else:
                    err_body = err_raw
            except Exception:
                err_body = str(e)
            
            logger.error(f"Erro HTTP {e.code} ({self.provider}): {err_body}")
            return {"success": False, "error": f"Erro HTTP {e.code}: {err_body}", "content": ""}
        except Exception as e:
            logger.error(f"Erro na chamada do modelo IA ({self.provider}): {e}")
            return {"success": False, "error": str(e), "content": ""}

    def _call_gemini(self, system_prompt: str, user_prompt: str) -> dict:
        model_name = self.model or "gemini-1.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.api_key}"
        
        payload = {
            "system_instruction": {
                "parts": [{"text": system_prompt}]
            },
            "contents": [
                {"role": "user", "parts": [{"text": user_prompt}]}
            ],
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": 2048,
                "responseMimeType": "application/json"
            }
        }
        
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        
        with urllib.request.urlopen(req, context=self.ctx, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            candidates = data.get("candidates", [])
            if not candidates:
                return {"success": False, "error": "Nenhuma resposta retornada pelo Gemini", "content": ""}
            
            text_response = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            return {"success": True, "content": text_response, "raw": data}

    def _call_openai_compatible(self, system_prompt: str, user_prompt: str) -> dict:
        base_urls = {
            "openai": "https://api.openai.com/v1/chat/completions",
            "groq": "https://api.groq.com/openai/v1/chat/completions",
            "openrouter": "https://openrouter.ai/api/v1/chat/completions"
        }
        url = self.base_url or base_urls.get(self.provider, "https://api.openai.com/v1/chat/completions")
        
        payload = {
            "model": self.model or ("gpt-4o-mini" if self.provider == "openai" else "llama-3.3-70b-versatile"),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": self.temperature,
            "response_format": {"type": "json_object"}
        }
        
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
        )
        
        with urllib.request.urlopen(req, context=self.ctx, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return {"success": True, "content": content, "raw": data}

    def _call_claude(self, system_prompt: str, user_prompt: str) -> dict:
        url = "https://api.anthropic.com/v1/messages"
        raw_model = self.model or "claude-sonnet-4-5-20250929"
        model_name = CLAUDE_MODEL_MAP.get(raw_model.lower(), raw_model)
        
        payload = {
            "model": model_name,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": 2048,
            "temperature": self.temperature
        }
        
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01"
            }
        )
        
        with urllib.request.urlopen(req, context=self.ctx, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data.get("content", [{}])[0].get("text", "")
            return {"success": True, "content": content, "raw": data}

    def _call_ollama(self, system_prompt: str, user_prompt: str) -> dict:
        url = self.base_url or "http://localhost:11434/api/generate"
        payload = {
            "model": self.model or "llama3.1",
            "system": system_prompt,
            "prompt": user_prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": self.temperature}
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, context=self.ctx, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {"success": True, "content": data.get("response", ""), "raw": data}

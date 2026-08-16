# Prevenção de Loops de Execução (Máximo 2 tentativas antes de escalar)
import time
from collections import defaultdict

class LoopBreaker:
    def __init__(self, max_attempts=2, window_seconds=600):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        # Estrutura: key=(host, action_type, target) -> [timestamp1, timestamp2]
        self.history = defaultdict(list)

    def can_execute(self, host: str, action_type: str, target: str) -> bool:
        key = (host, action_type, target)
        now = time.time()
        # Limpar tentativas fora da janela
        self.history[key] = [t for t in self.history[key] if now - t < self.window_seconds]
        
        if len(self.history[key]) >= self.max_attempts:
            return False
        return True

    def record_attempt(self, host: str, action_type: str, target: str):
        key = (host, action_type, target)
        self.history[key].append(time.time())

    def reset(self, host: str, action_type: str, target: str):
        key = (host, action_type, target)
        if key in self.history:
            del self.history[key]

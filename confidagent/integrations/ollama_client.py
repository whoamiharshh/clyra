import os
from kernel.gateway import make_openai_client
from dotenv import load_dotenv

load_dotenv()

class OllamaClient:
    
    def __init__(self):
        self.base_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434/v1')
        self.model = os.getenv('OLLAMA_MODEL','llama3.2:3b')
        self.client = make_openai_client(
    
            base_url=self.base_url,
            api_key='ollama'
        )
        self._available = None
    
    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            import httpx
            url = self.base_url.replace('/v1', '')
            r = httpx.get(f"{url}/api/tags", timeout=3)
            self._available = r.status_code == 200
        except Exception:
            self._available = False
        return self._available
    
    def call(self, messages: list) -> tuple:
        if not self.is_available():
            raise Exception(
                "Ollama not running. Start it with: ollama serve\n"
                "Then pull model: ollama pull qwen2.5-coder:3b"
            )
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=2000,
            temperature=0.1
        )
        
        content = response.choices[0].message.content
        tokens = response.usage.total_tokens if response.usage else len(str(messages)) // 4
        
        return content, tokens, 0.0
    
    def get_status(self) -> str:
        if self.is_available():
            return f"AVAILABLE ({self.model})"
        return "UNAVAILABLE - run: ollama serve && ollama pull llama3.2:3b"
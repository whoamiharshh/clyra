import os
from kernel.gateway import make_openai_client
from dotenv import load_dotenv

load_dotenv()

PROVIDERS = [
    {
        'name': 'groq',
        'base_url': 'https://api.groq.com/openai/v1',
        'api_key_env': 'GROQ_API_KEY',
        'cheap_model': os.getenv('GROQ_MODEL_CHEAP', 'llama-3.1-8b-instant'),
        'powerful_model': os.getenv('GROQ_MODEL_POWERFUL', 'llama-3.3-70b-versatile')
    },
    {
        'name': 'gemini',
        'base_url': 'https://generativelanguage.googleapis.com/v1beta/openai/',
        'api_key_env': 'GEMINI_API_KEY',
        'cheap_model': 'gemini-1.5-flash',
        'powerful_model': 'gemini-1.5-pro'
    },
    {
        'name': 'openrouter',
        'base_url': 'https://openrouter.ai/api/v1',
        'api_key_env': 'OPENROUTER_API_KEY',
        'cheap_model': 'meta-llama/llama-3.1-8b-instruct:free',
        'powerful_model': 'meta-llama/llama-3.3-70b-instruct:free'
    }
]

class BifrostClient:
    
    def __init__(self, state_manager):
        self.state = state_manager
        self.current_index = 0
        self.bifrost_url = os.getenv('BIFROST_BASE_URL', 'http://localhost:8080/v1')
        self.bifrost_key = os.getenv('BIFROST_API_KEY', 's')
        self.use_bifrost = self._check_bifrost()
    
    def _check_bifrost(self) -> bool:
        try:
            import httpx
            r = httpx.get(f"{self.bifrost_url.replace('/v1', '')}/health", timeout=2)
            return r.status_code == 200
        except Exception:
            return False
    
    def _get_client(self, provider: dict):
        api_key = os.getenv(provider['api_key_env'], '')
        
        if self.use_bifrost:
            return make_openai_client(
                base_url=self.bifrost_url,
                api_key=self.bifrost_key
            )
        else:
            return make_openai_client(
                base_url=provider['base_url'],
                api_key=api_key
            )
    
    def _get_model(self, provider: dict, use_powerful: bool) -> str:
        if use_powerful:
            return provider['powerful_model']
        return provider['cheap_model']
    
    def call_model(self, messages: list, use_powerful: bool = False) -> tuple:
        last_error = None
        
        for attempt in range(len(PROVIDERS)):
            provider = PROVIDERS[self.current_index]
            api_key = os.getenv(provider['api_key_env'], '')
            
            if not api_key and not self.use_bifrost:
                self.current_index = (self.current_index + 1) % len(PROVIDERS)
                continue
            
            try:
                client = self._get_client(provider)
                model = self._get_model(provider, use_powerful)
                
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=2000,
                    temperature=0.1
                )
                
                content = response.choices[0].message.content
                tokens = response.usage.total_tokens if response.usage else len(str(messages)) // 4
                cost = tokens * (0.000001 if use_powerful else 0.0000001)
                
                return content, tokens, cost
                
            except Exception as e:
                last_error = e
                old_provider = provider['name']
                self.current_index = (self.current_index + 1) % len(PROVIDERS)
                new_provider = PROVIDERS[self.current_index]['name']
                self.state.record_provider_switch(new_provider)
                print(f"⚡ Switching: {old_provider} → {new_provider} ({str(e)[:50]})")
                continue
        
        raise Exception(f"All providers failed. Last error: {last_error}")
    
    def call_cheap(self, messages: list) -> tuple:
        return self.call_model(messages, use_powerful=False)
    
    def call_powerful(self, messages: list) -> tuple:
        return self.call_model(messages, use_powerful=True)
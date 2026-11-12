import os
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
from dotenv import load_dotenv

load_dotenv()

LIBRARY_PATTERNS = [
    r'import\s+(\w+)',
    r'from\s+(\w+)\s+import',
    r'(\w+)==[\d\.]+',
    r'pip\s+install\s+(\w[\w\-]*)',
]

COMMON_LIBRARIES = [
    'flask', 'fastapi', 'django', 'requests', 'httpx', 'aiohttp',
    'sqlalchemy', 'pymongo', 'redis', 'celery', 'pydantic',
    'openai', 'anthropic', 'langchain', 'pytest', 'bcrypt',
    'jwt', 'flask-limiter', 'motor', 'uvicorn', 'gunicorn',
    'boto3', 'stripe', 'twilio', 'alembic', 'tortoise'
]

class TavilyClient:
    
    def __init__(self):
        self.api_key = os.getenv('TAVILY_API_KEY', '')
        self.client = None
        self._init_client()
    
    def _init_client(self):
        if self.api_key:
            try:
                from tavily import TavilyClient as TavilySDK
                self.client = TavilySDK(api_key=self.api_key)
            except Exception as e:
                print(f"[dim]Tavily init warning: {e}[/dim]")
    
    def verify_claim(self, claim: str) -> dict:
        base_result = {
            'claim': claim,
            'status': 'UNKNOWN',
            'current_version': None,
            'correction': None,
            'source_url': None,
            'freshness_score': 0.5
        }
        
        if not self.client:
            return base_result
        
        try:
            query = f"{claim} current version syntax documentation 2025 2026"
            results = self.client.search(
                query=query,
                search_depth="basic",
                max_results=3
            )
            
            if not results or not results.get('results'):
                return base_result
            
            full_text = ' '.join([
                r.get('content', '') + ' ' + r.get('title', '')
                for r in results['results']
            ]).lower()
            
            is_deprecated = any(word in full_text for word in [
                'deprecated', 'removed', 'no longer', 'discontinued',
                'replaced by', 'use instead', 'migration guide'
            ])
            
            versions = re.findall(r'(\d+\.\d+\.?\d*)', full_text)
            current_version = versions[0] if versions else None
            
            if is_deprecated:
                status = 'STALE'
                freshness = 0.2
                for r in results['results']:
                    content = r.get('content', '').lower()
                    if 'instead' in content or 'replace' in content:
                        sentences = content.split('.')
                        for s in sentences:
                            if 'instead' in s or 'replace' in s:
                                base_result['correction'] = s.strip()[:100]
                                break
            else:
                status = 'CURRENT'
                freshness = 0.9
            
            source_url = results['results'][0].get('url', '') if results['results'] else ''
            
            # Reject low-quality corrections that are clearly junk search snippets
            correction = base_result.get('correction')
            if correction:
                junk_markers = [
                    'egg', 'easy_install', 'pip install', 'download',
                    'stackoverflow', 'click here', 'read more',
                    'subscribe', 'cookie', 'privacy policy'
                ]
                too_short = len(correction.strip()) < 10
                looks_junk = any(marker in correction.lower() for marker in junk_markers)
                # A useful correction should mention a version number OR
                # explicitly name a replacement library
                has_version = any(ch.isdigit() for ch in correction)
                has_replacement = any(w in correction.lower() for w in [
                    'use ', 'instead', 'replace', 'migrate', 'upgrade', '>='
                ])
                if too_short or looks_junk or not (has_version or has_replacement):
                    correction = None

            return {
                'claim': claim,
                'status': status,
                'current_version': current_version,
                'correction': correction,
                'source_url': source_url,
                'freshness_score': freshness
            }
            
        except Exception as e:
            base_result['status'] = 'UNKNOWN'
            return base_result
    
    def verify_all_parallel(self, claims: list) -> list:
        if not claims:
            return []
        
        results = [None] * len(claims)
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_index = {
                executor.submit(self.verify_claim, claim): i
                for i, claim in enumerate(claims)
            }
            
            for future in as_completed(future_to_index, timeout=10):
                index = future_to_index[future]
                try:
                    results[index] = future.result(timeout=5)
                except Exception:
                    results[index] = {
                        'claim': claims[index],
                        'status': 'UNKNOWN',
                        'current_version': None,
                        'correction': None,
                        'source_url': None,
                        'freshness_score': 0.5
                    }
        
        return [r for r in results if r is not None]
    
    def extract_library_claims(self, text: str) -> list:
        claims = set()
        
        for pattern in LIBRARY_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if len(match) > 2 and match.lower() not in ['the', 'and', 'for', 'with']:
                    claims.add(match.lower())
        
        text_lower = text.lower()
        for lib in COMMON_LIBRARIES:
            if lib in text_lower:
                claims.add(lib)
        
        return list(claims)[:6]
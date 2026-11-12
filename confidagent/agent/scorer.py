import os
import re
from dotenv import load_dotenv

load_dotenv()

LIBRARY_KEYWORDS = [
    'import', 'from', 'install', 'pip', 'library', 'package',
    'version', 'api', 'sdk', 'framework', 'module', 'dependency'
]

FAST_CHANGING_LIBRARIES = [
    'flask', 'fastapi', 'django', 'sqlalchemy', 'pymongo',
    'redis', 'celery', 'pydantic', 'langchain', 'openai',
    'anthropic', 'requests', 'httpx', 'aiohttp', 'pytest',
    'alembic', 'bcrypt', 'jwt', 'flask-limiter', 'motor',
    'tortoise', 'beanie', 'starlette', 'uvicorn', 'gunicorn',
    'boto3', 'google-cloud', 'azure', 'stripe', 'twilio'
]

SECURITY_KEYWORDS = [
    'password', 'hash', 'encrypt', 'decrypt', 'token', 'jwt',
    'auth', 'oauth', 'secret', 'key', 'ssl', 'tls', 'cors',
    'sanitize', 'validate', 'xss', 'sql injection', 'csrf',
    'bcrypt', 'md5', 'sha', 'salt', 'session', 'cookie'
]

STABLE_PATTERNS = [
    'for loop', 'if else', 'class definition', 'function definition',
    'variable assignment', 'print statement', 'return statement',
    'list comprehension', 'dictionary', 'string formatting',
    'file open', 'exception handling', 'try except', 'with statement',
    'basic arithmetic', 'comparison operator', 'logical operator'
]

class ConfidenceScorer:
    
    def __init__(self):
        self.low_threshold = float(os.getenv('CONFIDENCE_THRESHOLD_LOW', '0.4'))
        self.med_threshold = float(os.getenv('CONFIDENCE_THRESHOLD_MED', '0.65'))
    
    def score_decision(self, decision: dict) -> float:
        description = decision.get('description', '').lower()
        name = decision.get('name', '').lower()
        combined = description + ' ' + name
        
        score = 0.70
        
        if any(kw in combined for kw in LIBRARY_KEYWORDS):
            score -= 0.15
        
        if any(lib in combined for lib in FAST_CHANGING_LIBRARIES):
            score -= 0.20
        
        if any(kw in combined for kw in SECURITY_KEYWORDS):
            score -= 0.25
        
        if any(pat in combined for pat in STABLE_PATTERNS):
            score += 0.15
        
        if re.search(r'\d+\.\d+', combined):
            score -= 0.10
        
        if 'deprecated' in combined or 'outdated' in combined:
            score -= 0.20
        
        if 'fix' in combined or 'bug' in combined:
            score -= 0.05
        
        return round(max(0.10, min(0.95, score)), 2)
    
    def get_action(self, score: float) -> dict:
        if score < self.low_threshold:
            return {
                'confidence': 'LOW',
                'model': 'powerful',
                'tavily_verify': True,
                'color': 'red'
            }
        elif score < self.med_threshold:
            return {
                'confidence': 'MED',
                'model': 'powerful',
                'tavily_verify': True,
                'color': 'yellow'
            }
        else:
            return {
                'confidence': 'HIGH',
                'model': 'cheap',
                'tavily_verify': False,
                'color': 'green'
            }
    
    def score_all(self, decisions: list) -> list:
        for d in decisions:
            score = self.score_decision(d)
            d['score'] = score
            d['action'] = self.get_action(score)
        return decisions

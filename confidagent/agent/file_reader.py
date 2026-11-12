import os
import ast
import hashlib
from pathlib import Path

IGNORE_DIRS = {
    '__pycache__', '.git', 'node_modules', '.env',
    'venv', '.venv', 'env', 'dist', 'build', '.idea',
    '.vscode', 'eggs', '.eggs', '*.egg-info'
}

IGNORE_FILES = {'.pyc', '.pyo', '.pyd', '.so', '.dll'}

class FileReader:
    
    def __init__(self):
        self.cache = {}
    
    def get_file_hash(self, filepath: str) -> str:
        try:
            with open(filepath, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception:
            return ''
    
    def read_file(self, filepath: str) -> str:
        current_hash = self.get_file_hash(filepath)
        
        if filepath in self.cache:
            if self.cache[filepath]['hash'] == current_hash:
                return self.cache[filepath]['content']
        
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            self.cache[filepath] = {'hash': current_hash, 'content': content}
            return content
        except Exception as e:
            return f"# Could not read file: {e}"
    
    def read_relevant_functions(self, filepath: str, keywords: list) -> str:
        content = self.read_file(filepath)
        
        try:
            tree = ast.parse(content)
        except SyntaxError:
            lines = content.split('\n')
            return '\n'.join(lines[:50])
        
        relevant_parts = []
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_name = node.name.lower()
                if any(kw.lower() in func_name for kw in keywords):
                    start = node.lineno - 1
                    end = node.end_lineno
                    lines = content.split('\n')[start:end]
                    relevant_parts.append('\n'.join(lines))
            
            elif isinstance(node, ast.ClassDef):
                class_name = node.name.lower()
                if any(kw.lower() in class_name for kw in keywords):
                    start = node.lineno - 1
                    end = min(node.end_lineno, node.lineno + 30)
                    lines = content.split('\n')[start:end]
                    relevant_parts.append('\n'.join(lines))
        
        import_lines = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                line_idx = node.lineno - 1
                import_lines.append(content.split('\n')[line_idx])
        
        result = '\n'.join(import_lines)
        if relevant_parts:
            result += '\n\n' + '\n\n'.join(relevant_parts)
        
        if not result.strip():
            full = content.split('\n')
            if len(full) <= 120:
                return content
            return '\n'.join(full[:120])
        
        return result
    
    def scan_repo_structure(self, repo_path: str) -> dict:
        python_files = []
        all_files = []
        structure_lines = []
        
        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            
            level = root.replace(repo_path, '').count(os.sep)
            indent = '  ' * level
            folder_name = os.path.basename(root)
            structure_lines.append(f"{indent}{folder_name}/")
            
            for file in files:
                ext = Path(file).suffix
                if ext in IGNORE_FILES:
                    continue
                
                file_path = os.path.join(root, file)
                all_files.append(file_path)
                sub_indent = '  ' * (level + 1)
                structure_lines.append(f"{sub_indent}{file}")
                
                if ext == '.py':
                    python_files.append(file_path)
        
        return {
            'python_files': python_files,
            'total_files': len(all_files),
            'structure': '\n'.join(structure_lines[:50])
        }
    
    def find_relevant_files(self, repo_path: str, keywords: list) -> list:
        repo_info = self.scan_repo_structure(repo_path)
        relevant = []
        
        for filepath in repo_info['python_files']:
            filename = os.path.basename(filepath).lower()
            if any(kw.lower() in filename for kw in keywords):
                relevant.append(filepath)
                continue
            
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    first_lines = ''.join(f.readlines()[:15]).lower()
                if any(kw.lower() in first_lines for kw in keywords):
                    relevant.append(filepath)
            except Exception:
                pass
        
        return relevant[:5]
    
    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    def extract_version_pins(self, repo_path: str) -> list:
        import re
        pins = []
        seen_libs = set()
        for root, _, files in os.walk(repo_path):
            for fname in files:
                if fname == 'requirements.txt':
                    fp = os.path.join(root, fname)
                    try:
                        with open(fp, 'r', encoding='utf-8') as f:
                            for line in f:
                                line = line.strip()
                                if line and '==' in line and not line.startswith('#'):
                                    lib, ver = line.split('==', 1)
                                    lib_clean = lib.strip().lower()
                                    ver_clean = ver.strip().split()[0]
                                    if lib_clean not in seen_libs:
                                        pins.append({
                                            'library': lib_clean,
                                            'version': ver_clean,
                                            'file': fname,
                                            'claim': f"{lib_clean} {ver_clean} is current"
                                        })
                                        seen_libs.add(lib_clean)
                    except Exception:
                        pass
        return pins

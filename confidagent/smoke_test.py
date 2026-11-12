"""
Smoke test - verifies all modules import correctly
Run: python smoke_test.py
"""
import sys

errors = []

def test_import(module_path, name):
    try:
        parts = module_path.split('.')
        if len(parts) == 1:
            __import__(module_path)
        else:
            mod = __import__('.'.join(parts[:-1]), fromlist=[parts[-1]])
            getattr(mod, parts[-1])
        print(f"✓ {name}")
        return True
    except Exception as e:
        print(f"✗ {name}: {e}")
        errors.append((name, str(e)))
        return False

def main():
    # Avoid UnicodeEncodeError on Windows consoles using legacy code pages.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    print("ConfidAgent Smoke Test")
    print("=" * 40)

    test_import('rich', 'Rich library')
    test_import('tavily', 'Tavily SDK')
    test_import('dotenv', 'Python-dotenv')
    test_import('openai', 'OpenAI library')
    test_import('httpx', 'HTTPX')
    test_import('aiohttp', 'AIOHttp')

    print()

    test_import('output.terminal_display', 'Terminal Display')
    test_import('core.state_manager', 'State Manager')
    test_import('core.confidence_scorer', 'Confidence Scorer')
    test_import('core.file_reader', 'File Reader')
    test_import('integrations.bifrost_client', 'Bifrost Client')
    test_import('integrations.tavily_client', 'Tavily Client')
    test_import('integrations.ollama_client', 'Ollama Client')
    test_import('security.privacy_checker', 'Privacy Checker')
    test_import('security.budget_gate', 'Budget Gate')
    test_import('security.approval_gate', 'Approval Gate')

    print()
    print("=" * 40)

    if errors:
        print(f"✗ {len(errors)} error(s) found:")
        for name, err in errors:
            print(f"  {name}: {err}")
        return 1
    print("✓ All imports successful. Ready to run.")
    print()
    print("Next step:")
    print("  python main.py fix \"fix security vulnerabilities\" --repo ./demo_repo")
    return 0
if __name__ == "__main__":
    sys.exit(main())

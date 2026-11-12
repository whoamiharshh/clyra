"""
Automated verification for ConfidAgent fixes.
Run: python verify.py
"""
import os
import sys
import json
import shutil
import tempfile
from datetime import datetime

CONFIDAGENT_DIR = os.path.dirname(os.path.abspath(__file__))
DEMO_REPO = os.path.join(CONFIDAGENT_DIR, 'demo_repo')
BACKUP_DIR = os.path.join(CONFIDAGENT_DIR, 'demo_repo_backup')
STATE_FILE = os.path.join(CONFIDAGENT_DIR, '.confidagent_state.json')


def backup_demo():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now().strftime('run-%Y%m%d-%H%M%S-%f')
    dst = os.path.join(BACKUP_DIR, stamp)
    shutil.copytree(DEMO_REPO, dst)
    return dst


def restore_demo(src):
    for fname in os.listdir(src):
        s = os.path.join(src, fname)
        d = os.path.join(DEMO_REPO, fname)
        if os.path.isfile(s):
            shutil.copy2(s, d)


def test_syntax():
    try:
        from agent.planner import TaskAnalyzer
        print("PASS: agent.planner imports cleanly")
        return True
    except Exception as e:
        print(f"FAIL: task_analyzer import - {e}")
        return False


def test_imports():
    try:
        from agent.loop import ConfidAgent
        print("PASS: agent.loop imports cleanly")
        return True
    except Exception as e:
        print(f"FAIL: core.agent import - {e}")
        return False


def test_demo_files():
    ok = True
    auth = os.path.join(DEMO_REPO, 'auth.py')
    req = os.path.join(DEMO_REPO, 'requirements.txt')
    if not os.path.exists(auth):
        print("FAIL: demo_repo/auth.py missing")
        ok = False
    else:
        content = open(auth).read()
        if 'md5' not in content:
            print("FAIL: demo_repo/auth.py has no md5 (unexpected)")
            ok = False
        else:
            print("PASS: demo_repo/auth.py contains md5 (bug present)")
    if not os.path.exists(req):
        print("FAIL: demo_repo/requirements.txt missing")
        ok = False
    else:
        content = open(req).read()
        if 'pymongo==3.12.0' not in content:
            print("FAIL: demo_repo/requirements.txt missing stale pymongo pin")
            ok = False
        else:
            print("PASS: demo_repo/requirements.txt has stale pins")
    return ok


def main():
    print("=" * 50)
    print("ConfidAgent Verification")
    print("=" * 50)
    backup = backup_demo()
    print(f"Backed up demo_repo to: {backup}")
    print()
    results = []
    results.append(("Syntax check", test_syntax()))
    results.append(("Import check", test_imports()))
    results.append(("Demo files", test_demo_files()))
    print()
    restore_demo(backup)
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
    print("Restored demo_repo and cleared state.")
    print()
    passed = sum(1 for _, v in results if v)
    total = len(results)
    print(f"RESULT: {passed}/{total} passed")
    sys.exit(0 if passed == total else 1)


if __name__ == '__main__':
    main()

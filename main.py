import argparse
import os
import sys
from dotenv import load_dotenv

load_dotenv()

def main():
    parser = argparse.ArgumentParser(
        description='ConfidAgent - Token-efficient coding agent with staleness detection',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py fix "fix security vulnerabilities" --repo ./demo_repo
  python main.py implement "add rate limiting" --repo ./my_project
  python main.py refactor "clean up authentication code" --repo .
  python main.py explain "how does the auth system work" --repo .
        """
    )
    
    parser.add_argument('command', 
        choices=['fix', 'implement', 'refactor', 'explain'],
        help='What to do')
    parser.add_argument('task',
        help='Task description in quotes')
    parser.add_argument('--repo',
        default='.',
        help='Path to repository (default: current directory)')
    parser.add_argument('--budget',
        type=float,
        default=None,
        help='Override budget in USD')
    parser.add_argument('--clear-state',
        action='store_true',
        help='Clear saved state and start fresh')
    parser.add_argument('--confidential',
        action='store_true',
        help='Force confidential mode (local model only)')
    parser.add_argument('--no-cache',
        action='store_true',
        help='Disable decision and verification caches (LLM completion caching stays in Bifrost)')
    parser.add_argument('--dry-run',
        action='store_true',
        help='Auto-deny all write operations (no files modified)')

    args = parser.parse_args()

    if args.no_cache:
        os.environ['CONFIDAGENT_NO_CACHE'] = '1'
    if args.confidential:
        os.environ['CONFIDENTIAL'] = 'true'

    if args.clear_state:
        state_file = '.confidagent_state.json'
        if os.path.exists(state_file):
            os.remove(state_file)
            print('State cleared.')
        else:
            print('No state file found.')

    if not os.path.exists(args.repo):
        print(f'Error: Repository path {args.repo} does not exist.')
        sys.exit(1)

    from agent.loop import ConfidAgent
    
    agent = ConfidAgent(
        repo_path=args.repo,
        task=f"{args.command}: {args.task}",
        budget_override=args.budget,
        force_confidential=args.confidential,
        dry_run=args.dry_run
    )
    
    success = agent.run()
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
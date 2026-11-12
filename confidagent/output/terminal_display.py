from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.rule import Rule
from rich import box
import time

console = Console()

class TerminalDisplay:
    
    def show_banner(self):
        banner = """
  ██████╗ ██████╗ ███╗   ██╗███████╗██╗██████╗      
 ██╔════╝██╔═══██╗████╗  ██║██╔════╝██║██╔══██╗     
 ██║     ██║   ██║██╔██╗ ██║█████╗  ██║██║  ██║     
 ██║     ██║   ██║██║╚██╗██║██╔══╝  ██║██║  ██║     
 ╚██████╗╚██████╔╝██║ ╚████║██║     ██║██████╔╝     
  ╚═════╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝     ╚═╝╚═════╝      
        """
        console.print(Panel(
            f"[bold green]{banner}[/bold green]\n[dim]The coding agent that knows what it doesn't know[/dim]\n[dim]PS01: Token Efficiency + PS06: Staleness Detection[/dim]",
            border_style="green",
            expand=False
        ))

    def show_task_start(self, task: str, repo_path: str):
        console.print()
        console.print(Rule("[bold blue]TASK ANALYSIS[/bold blue]"))
        console.print(f"[bold]Task:[/bold] {task}")
        console.print(f"[bold]Repo:[/bold] {repo_path}")
        console.print()

    def show_privacy_status(self, is_confidential: bool):
        if is_confidential:
            console.print(Panel(
                "[bold red]🔒 CONFIDENTIAL MODE[/bold red]\n[dim]All processing via local Ollama model only\nNo data leaves your machine[/dim]",
                border_style="red"
            ))
        else:
            console.print(Panel(
                "[bold green]🌐 STANDARD MODE[/bold green]\n[dim]Cloud routing enabled via Bifrost\nGroq → Gemini → OpenRouter failover[/dim]",
                border_style="green"
            ))

    def show_budget_status(self, remaining: float, estimated: float):
        color = "green" if remaining > estimated * 2 else "yellow" if remaining > estimated else "red"
        console.print(f"[{color}]💰 Budget: ${remaining:.4f} remaining | Estimated: ${estimated:.4f}[/{color}]")

    def show_confidence_scores(self, decisions: list):
        console.print()
        console.print(Rule("[bold blue]CONFIDENCE ANALYSIS[/bold blue]"))
        
        table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
        table.add_column("Decision", style="white", min_width=25)
        table.add_column("Score", justify="center", min_width=8)
        table.add_column("Level", justify="center", min_width=8)
        table.add_column("Model", justify="center", min_width=12)
        table.add_column("Verify", justify="center", min_width=8)

        for d in decisions:
            action = d.get('action', {})
            score = d.get('score', 0.5)
            confidence = action.get('confidence', 'MED')
            
            if confidence == 'LOW':
                score_color = "red"
                level_text = "[red]🔴 LOW[/red]"
            elif confidence == 'MED':
                score_color = "yellow"
                level_text = "[yellow]🟡 MED[/yellow]"
            else:
                score_color = "green"
                level_text = "[green]🟢 HIGH[/green]"
            
            model = "[dim]cheap[/dim]" if action.get('model') == 'cheap' else "[bold]powerful[/bold]"
            verify = "[green]✓[/green]" if action.get('tavily_verify') else "[dim]-[/dim]"
            
            table.add_row(
                d.get('name', 'Unknown')[:40],
                f"[{score_color}]{score:.2f}[/{score_color}]",
                level_text,
                model,
                verify
            )
        
        console.print(table)
        console.print()

    def show_tavily_result(self, claim: str, status: str, correction: str = None):
        if status == 'CURRENT':
            console.print(f"  [green]✓[/green] {claim[:50]} → [green]Current[/green]")
        elif status == 'STALE':
            console.print(f"  [red]✗[/red] {claim[:50]} → [red]STALE[/red]")
            if correction:
                console.print(f"    [dim]→ Use: {correction}[/dim]")
        else:
            console.print(f"  [yellow]?[/yellow] {claim[:50]} → [yellow]Unverifiable[/yellow]")

    def show_approval_request(self, operation: str, target: str, diff: str = None) -> bool:
        console.print()
        console.print(Panel(
            f"[bold yellow]⚠️  APPROVAL REQUIRED[/bold yellow]\n\nOperation: [bold]{operation}[/bold]\nTarget: [bold]{target}[/bold]",
            border_style="yellow"
        ))
        
        if diff:
            console.print(Panel(diff, title="[dim]Proposed Changes[/dim]", border_style="dim"))
        
        while True:
            response = console.input("[bold yellow]Approve? (y/n): [/bold yellow]").strip().lower()
            if response in ['y', 'yes']:
                return True
            elif response in ['n', 'no']:
                console.print("[dim]Skipped.[/dim]")
                return False

    def show_provider_switch(self, from_provider: str, to_provider: str):
        console.print(f"[yellow]⚡ Provider switch: {from_provider} → {to_provider}[/yellow]")

    def show_step(self, step: str, detail: str = None):
        console.print(f"[cyan]→[/cyan] {step}" + (f" [dim]{detail}[/dim]" if detail else ""))

    def show_error(self, error: str):
        console.print(f"[red]✗ Error: {error}[/red]")

    def show_success(self, message: str):
        console.print(f"[green]✓ {message}[/green]")

    def show_completion(self, tokens_used: int, baseline_tokens: int, cost_usd: float, stale_caught: int, provider_switches: int):
        saved = baseline_tokens - tokens_used
        saved_pct = (saved / baseline_tokens * 100) if baseline_tokens > 0 else 0
        
        summary = f"""
[bold green]✅ Task Complete[/bold green]

[bold]Token Efficiency:[/bold]
  Tokens used:    {tokens_used:,}
  Naive baseline: {baseline_tokens:,}
  Tokens saved:   {saved:,} ([bold green]{saved_pct:.0f}%[/bold green])

[bold]Cost:[/bold]
  This task:      ${cost_usd:.4f}

[bold]Quality:[/bold]
  Stale claims caught & corrected: {stale_caught}
  Provider switches: {provider_switches}
        """
        
        console.print()
        console.print(Panel(summary, border_style="green", title="[bold green]ConfidAgent Report[/bold green]"))

    def show_tavily_section(self):
        console.print()
        console.print(Rule("[bold blue]TAVILY FRESHNESS VERIFICATION[/bold blue]"))

    def show_generating(self, decision_name: str):
        console.print(f"[dim]⚙ Generating: {decision_name}...[/dim]")
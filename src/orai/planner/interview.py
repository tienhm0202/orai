from __future__ import annotations

from rich.console import Console
from rich.prompt import Confirm, Prompt

console = Console()


def interview() -> dict:
    """Gather project requirements interactively."""
    console.print("\n[bold cyan]orai — Project Planning Interview[/bold cyan]\n")

    answers: dict = {}

    answers["description"] = Prompt.ask(
        "[bold]Describe your project in 1-2 sentences[/bold]"
    )

    features_raw = Prompt.ask(
        "[bold]List the main features[/bold] (comma-separated)"
    )
    answers["features"] = [f.strip() for f in features_raw.split(",") if f.strip()]

    answers["has_auth"] = Confirm.ask("Does it need authentication?", default=False)
    if answers["has_auth"]:
        answers["auth_type"] = Prompt.ask(
            "Auth type?",
            choices=["jwt", "session", "oauth", "clerk", "nextauth"],
            default="jwt",
        )

    answers["has_db"] = Confirm.ask("Does it need a database?", default=False)
    if answers["has_db"]:
        answers["db_type"] = Prompt.ask(
            "Which DB?",
            choices=["postgres", "sqlite", "mysql", "mongo"],
            default="postgres",
        )

    answers["has_api"] = Confirm.ask("Does it expose an API?", default=True)

    answers["num_phases"] = int(
        Prompt.ask(
            "How many phases?",
            choices=["2", "3", "4", "5"],
            default="3",
        )
    )

    answers["extra"] = Prompt.ask(
        "Any other requirements?", default=""
    )

    console.print("\n[green]Interview complete.[/green]\n")
    return answers

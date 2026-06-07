"""CLI entrypoint for the outreach pipeline."""
import sys
from dotenv import load_dotenv
from rich.console import Console
from pipeline.outreach_pipeline import OutreachPipeline
from config.settings import Settings

console = Console()


def main():
    load_dotenv()
    
    # Parse simple CLI arguments
    dry_run = "--dry-run" in sys.argv
    async_run = "--async-run" in sys.argv
    demo_mode = "--demo-mode" in sys.argv
    domain = None
    
    # Extract domain from arguments (first positional arg)
    for arg in sys.argv[1:]:
        if not arg.startswith("-"):
            domain = arg
            break
    
    if demo_mode:
        from demo_runner import main as demo_main
        console.print("[bold yellow]Demo mode enabled: running fallback pipeline with sample data[/]")
        demo_main()
        return

    settings = Settings()
    pipeline = OutreachPipeline(settings)
    console.print("[bold green]Outreach pipeline starting...[/]")
    
    if not domain:
        if async_run:
            pipeline.run_async_interactive(dry_run=dry_run)
        else:
            pipeline.run_interactive(dry_run=dry_run)
    else:
        if async_run:
            import asyncio
            asyncio.run(pipeline.run_async(domain, dry_run=dry_run))
        else:
            pipeline.run(domain, dry_run=dry_run)


if __name__ == "__main__":
    main()

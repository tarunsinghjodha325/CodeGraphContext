# src/codegraphcontext/cli/main.py
import typer
from rich.console import Console
import asyncio
import logging
from dotenv import load_dotenv 

from .setup_wizard import run_setup_wizard
from codegraphcontext.server import MCPServer

# Set the log level for the noisy neo4j logger to WARNING
logging.getLogger("neo4j").setLevel(logging.WARNING) # <-- ADD THIS LINE

# Load environment variables from .env file at the very beginning
load_dotenv()

app = typer.Typer(
    name="cgc",
    help="CodeGraphContext: An MCP server for AI-powered code analysis.",
    add_completion=False,
)
console = Console()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')

@app.command()
def setup():
    """
    Run the interactive setup wizard to configure the server and database.
    """
    run_setup_wizard()

@app.command()
def start():
    """
    Start the CodeGraphContext MCP server.
    """
    console.print("[bold green]Starting CodeGraphContext Server...[/bold green]")
    server = None
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        server = MCPServer(loop=loop)
        loop.run_until_complete(server.run())
    except ValueError as e:
        console.print(f"[bold red]Configuration Error:[/bold red] {e}")
        console.print("Please run `cgc setup` to configure the server.")
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Server stopped by user.[/bold yellow]")
    finally:
        if server:
            server.shutdown()
        loop.close()


@app.command()
def tool(
    name: str = typer.Argument(..., help="The name of the tool to call."),
    args: str = typer.Argument("{}", help="A JSON string of arguments for the tool."),
):
    """
    Directly call a server tool (for debugging and scripting).
    """
    # This is a placeholder for a more advanced tool caller that would
    # connect to the running server via a different mechanism (e.g., a socket).
    # For now, it's a conceptual part of the CLI.
    console.print(f"Calling tool [bold cyan]{name}[/bold cyan] with args: {args}")
    console.print("[yellow]Note: This is a placeholder for direct tool invocation.[/yellow]")

if __name__ == "__main__":
    app()
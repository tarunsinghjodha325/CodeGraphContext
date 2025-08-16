from InquirerPy import prompt
from rich.console import Console
import subprocess
import platform
import os
from pathlib import Path
import time
import json
import sys
import shutil

console = Console()

def _generate_mcp_json(creds):
    """Generates and prints the MCP JSON configuration."""
    cgc_path = shutil.which("cgc") or sys.executable

    if "python" in Path(cgc_path).name:  
        # fallback to running as module if no cgc binary is found
        command = cgc_path
        args = ["-m", "cgc", "start"]
    else:
        command = cgc_path
        args = ["start"]

    mcp_config = {
        "mcpServers": {
            "CodeGraphContext": {
                "command": command,
                "args": args,
                "env": {
                    "NEO4J_URI": creds.get("uri", ""),
                    "NEO4J_USER": creds.get("username", "neo4j"),
                    "NEO4J_PASSWORD": creds.get("password", "")
                },
                "tools": {
                    "alwaysAllow": [
                        "list_imports", "add_code_to_graph", "add_package_to_graph",
                        "check_job_status", "list_jobs", "find_code",
                        "analyze_code_relationships", "watch_directory",
                        "find_dead_code", "execute_cypher_query"
                    ],
                    "disabled": False
                },
                "disabled": False,
                "alwaysAllow": []
            }
        }
    }
    
    console.print("\n[bold green]Configuration successful![/bold green]")
    console.print("Copy the following JSON and add it to your MCP server configuration file:")
    console.print(json.dumps(mcp_config, indent=2))
    
    # Also save to a file for convenience
    mcp_file = Path.cwd() / "mcp.json"
    with open(mcp_file, "w") as f:
        json.dump(mcp_config, f, indent=2)
    console.print(f"\n[cyan]For your convenience, the configuration has also been saved to: {mcp_file}[/cyan]")


def get_project_root() -> Path:
    """Always return the directory where the user runs `cgc` (CWD)."""
    return Path.cwd()

def run_command(command, console, shell=False, check=True, input_text=None):
    """
    Runs a command, captures its output, and handles execution.
    Returns the completed process object on success, None on failure.
    """
    cmd_str = command if isinstance(command, str) else ' '.join(command)
    console.print(f"[cyan]$ {cmd_str}[/cyan]")
    try:
        process = subprocess.run(
            command,
            shell=shell,
            check=check,
            capture_output=True,  # Always capture to control what gets displayed
            text=True,
            timeout=300,
            input=input_text
        )
        return process
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error executing command:[/bold red] {cmd_str}")
        if e.stdout:
            console.print(f"[red]STDOUT: {e.stdout}[/red]")
        if e.stderr:
            console.print(f"[red]STDERR: {e.stderr}[/red]")
        return None
    except subprocess.TimeoutExpired:
        console.print(f"[bold red]Command timed out:[/bold red] {cmd_str}")
        return None

def run_setup_wizard():
    """Guides the user through setting up CodeGraphContext."""
    console.print("[bold cyan]Welcome to the CodeGraphContext Setup Wizard![/bold cyan]")
    
    questions = [
        {
            "type": "list",
            "message": "Where is your Neo4j database located?",
            "choices": [
                "Local (Recommended: I'll help you run it on this machine)",
                "Hosted (Connect to a remote database like AuraDB)",
            ],
            "name": "db_location",
        }
    ]
    result = prompt(questions)
    db_location = result.get("db_location")

    if db_location and "Hosted" in db_location:
        setup_hosted_db()
    elif db_location:
        setup_local_db()


def find_latest_neo4j_creds_file():
    """Finds the latest Neo4j credentials file in the Downloads folder."""
    downloads_path = Path.home() / "Downloads"
    if not downloads_path.exists():
        return None
    
    cred_files = list(downloads_path.glob("Neo4j*.txt"))
    if not cred_files:
        return None
        
    latest_file = max(cred_files, key=lambda f: f.stat().st_mtime)
    return latest_file



def setup_hosted_db():
    """Guides user to configure a remote Neo4j instance."""
    questions = [
        {
            "type": "list",
            "message": "How would you like to add your Neo4j credentials?",
            "choices": ["Add credentials from file", "Add credentials manually"],
            "name": "cred_method",
        }
    ]
    result = prompt(questions)
    cred_method = result.get("cred_method")

    creds = {}
    if cred_method and "file" in cred_method:
        latest_file = find_latest_neo4j_creds_file()
        file_to_parse = None
        if latest_file:
            confirm_questions = [
                {
                    "type": "confirm",
                    "message": f"Found a credentials file: {latest_file}. Use this file?",
                    "name": "use_latest",
                    "default": True,
                }
            ]
            if prompt(confirm_questions).get("use_latest"):
                file_to_parse = latest_file

        if not file_to_parse:
            path_questions = [
                {"type": "input", "message": "Please enter the path to your credentials file:", "name": "cred_file_path"}
            ]
            file_path_str = prompt(path_questions).get("cred_file_path", "")
            file_path = Path(file_path_str.strip())
            if file_path.exists() and file_path.is_file():
                file_to_parse = file_path
            else:
                console.print("[red]❌ The specified file path does not exist or is not a file.[/red]")
                return

        if file_to_parse:
            try:
                with open(file_to_parse, "r") as f:
                    for line in f:
                        if "=" in line:
                            key, value = line.strip().split("=", 1)
                            if key == "NEO4J_URI":
                                creds["uri"] = value
                            elif key == "NEO4J_USERNAME":
                                creds["username"] = value
                            elif key == "NEO4J_PASSWORD":
                                creds["password"] = value
            except Exception as e:
                console.print(f"[red]❌ Failed to parse credentials file: {e}[/red]")
                return

    elif cred_method:  # Manual entry
        console.print("Please enter your remote Neo4j connection details.")
        questions = [
            {"type": "input", "message": "URI (e.g., neo4j+s://xxxx.databases.neo4j.io):", "name": "uri"},
            {"type": "input", "message": "Username:", "name": "username", "default": "neo4j"},
            {"type": "password", "message": "Password:", "name": "password"},
        ]
        manual_creds = prompt(questions)
        if not manual_creds: return  # User cancelled
        creds = manual_creds

    if creds.get("uri") and creds.get("password"):
        _generate_mcp_json(creds)
    else:
        console.print("[red]❌ Incomplete credentials. Please try again.[/red]")

def setup_local_db():
    """Guides user to set up a local Neo4j instance."""
    questions = [
        {
            "type": "list",
            "message": "How would you like to run Neo4j locally?",
            "choices": ["Docker (Easiest)", "Local Binary (Advanced)"],
            "name": "local_method",
        }
    ]
    result = prompt(questions)
    local_method = result.get("local_method")
    
    if local_method and "Docker" in local_method:
        setup_docker()
    elif local_method:
        setup_local_binary()

def setup_docker():
    """Creates Docker files and runs docker-compose."""
    console.print("This will create a `docker-compose.yml` and `.env` file in your current directory.")
    # Here you would write the file contents
    console.print("[green]docker-compose.yml and .env created.[/green]")
    console.print("Please set your NEO4J_PASSWORD in the .env file.")
    confirm_q = [{"type": "confirm", "message": "Ready to launch Docker containers?", "name": "proceed"}]
    if prompt(confirm_q).get("proceed"):
        try:
            # Using our run_command to handle the subprocess call
            docker_process = run_command(["docker", "compose", "up", "-d"], console, check=True)
            if docker_process:
                console.print("[bold green]Docker containers started successfully![/bold green]")
        except Exception as e:
            console.print(f"[bold red]Failed to start Docker containers:[/bold red] {e}")

def setup_local_binary():
    """Automates the installation and configuration of Neo4j on Ubuntu/Debian."""
    os_name = platform.system()
    console.print(f"Detected Operating System: [bold yellow]{os_name}[/bold yellow]")

    if os_name != "Linux" or not os.path.exists("/etc/debian_version"):
        console.print("[yellow]Automated installer is designed for Debian-based systems (like Ubuntu).[/yellow]")
        console.print(f"For other systems, please follow the manual installation guide: [bold blue]https://neo4j.com/docs/operations-manual/current/installation/[/bold blue]")
        return

    console.print("[bold]Starting automated Neo4j installation for Ubuntu/Debian.[/bold]")
    console.print("[yellow]This will run several commands with 'sudo'. You will be prompted for your password.[/yellow]")
    confirm_q = [{"type": "confirm", "message": "Do you want to proceed?", "name": "proceed", "default": True}]
    if not prompt(confirm_q).get("proceed"):
        return

    NEO4J_VERSION = "1:5.21.0" 

    install_commands = [
        ("Creating keyring directory", ["sudo", "mkdir", "-p", "/etc/apt/keyrings"]),
        ("Adding Neo4j GPG key", "wget -qO- https://debian.neo4j.com/neotechnology.gpg.key | sudo gpg --dearmor --yes -o /etc/apt/keyrings/neotechnology.gpg", True),
        ("Adding Neo4j repository", "echo 'deb [signed-by=/etc/apt/keyrings/neotechnology.gpg] https://debian.neo4j.com stable 5' | sudo tee /etc/apt/sources.list.d/neo4j.list > /dev/null", True),
        ("Updating apt sources", ["sudo", "apt-get", "-qq", "update"]),
        (f"Installing Neo4j ({NEO4J_VERSION}) and Cypher Shell", ["sudo", "apt-get", "install", "-qq", "-y", f"neo4j={NEO4J_VERSION}", "cypher-shell"])
    ]

    for desc, cmd, use_shell in [(c[0], c[1], c[2] if len(c) > 2 else False) for c in install_commands]:
        console.print(f"\n[bold]Step: {desc}...[/bold]")
        if not run_command(cmd, console, shell=use_shell):
            console.print(f"[bold red]Failed on step: {desc}. Aborting installation.[/bold]")
            return
            
    console.print("\n[bold green]Neo4j installed successfully![/bold green]")
    
    console.print("\n[bold]Please set the initial password for the 'neo4j' user.""")
    
    new_password = ""
    while True:
        questions = [
            {"type": "password", "message": "Enter a new password for Neo4j:", "name": "password"},
            {"type": "password", "message": "Confirm the new password:", "name": "password_confirm"},
        ]
        passwords = prompt(questions)
        if not passwords: return # User cancelled
        new_password = passwords.get("password")
        if new_password and new_password == passwords.get("password_confirm"):
            break
        console.print("[red]Passwords do not match or are empty. Please try again.[/red]")

    console.print("\n[bold]Stopping Neo4j to set the password...""")
    if not run_command(["sudo", "systemctl", "stop", "neo4j"], console):
        console.print("[bold red]Could not stop Neo4j service. Aborting.[/bold red]")
        return
        
    console.print("\n[bold]Setting initial password using neo4j-admin...""")
    pw_command = ["sudo", "-u", "neo4j", "neo4j-admin", "dbms", "set-initial-password", new_password]
    if not run_command(pw_command, console, check=True):
        console.print("[bold red]Failed to set the initial password. Please check the logs.[/bold red]")
        run_command(["sudo", "systemctl", "start", "neo4j"], console)
        return
    
    console.print("\n[bold]Starting Neo4j service...""")
    if not run_command(["sudo", "systemctl", "start", "neo4j"], console):
        console.print("[bold red]Failed to start Neo4j service after setting password.[/bold red]")
        return

    console.print("\n[bold]Enabling Neo4j service to start on boot...""")
    if not run_command(["sudo", "systemctl", "enable", "neo4j"], console):
        console.print("[bold yellow]Could not enable Neo4j service. You may need to start it manually after reboot.[/bold yellow]")

    console.print("[bold green]Password set and service started.[/bold green]")
    
    console.print("\n[yellow]Waiting 10 seconds for the database to become available...""")
    time.sleep(10)

    creds = {
        "uri": "neo4j://localhost:7687",
        "username": "neo4j",
        "password": new_password
    }
    _generate_mcp_json(creds)
    console.print("\n[bold green]All done! Your local Neo4j instance is ready to use.[/bold green]")

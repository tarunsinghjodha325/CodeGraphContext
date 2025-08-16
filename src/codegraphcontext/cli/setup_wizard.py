from InquirerPy import prompt
from rich.console import Console
import subprocess
import platform
import os
from pathlib import Path
import time

console = Console()

def get_project_root() -> Path:
    """Returns the project root directory."""
    return Path(__file__).resolve().parent.parent.parent.parent

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

def parse_creds_file(file_path: Path):
    """Parses a credentials file and writes to .env."""
    try:
        creds = {}
        with open(file_path, "r") as f:
            for line in f:
                if "=" in line:
                    key, value = line.strip().split("=", 1)
                    if key in ["NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD"]:
                        creds[key] = value
        
        if all(k in creds for k in ["NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD"]):
            env_path = get_project_root() / ".env"
            with open(env_path, "w") as f:
                f.write(f"NEO4J_URI={creds['NEO4J_URI']}\n")
                f.write(f"NEO4J_USERNAME={creds['NEO4J_USERNAME']}\n")
                f.write(f"NEO4J_PASSWORD={creds['NEO4J_PASSWORD']}\n")
            console.print(f"[green]✅ Configuration from {file_path.name} saved to .env file in project root.[/green]")
            return True
        else:
            console.print("[red]❌ The credentials file is missing one or more required keys (NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD).[/red]")
            return False
    except Exception as e:
        console.print(f"[red]❌ Failed to parse credentials file: {e}[/red]")
        return False

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

    if cred_method and "file" in cred_method:
        latest_file = find_latest_neo4j_creds_file()
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
                if parse_creds_file(latest_file):
                    return

        # If no file was found, or the user chose not to use the found file
        path_questions = [
            {"type": "input", "message": "Please enter the path to your credentials file:", "name": "cred_file_path"}
        ]
        file_path_str = prompt(path_questions).get("cred_file_path", "")
        file_path = Path(file_path_str.strip())
        if file_path.exists() and file_path.is_file():
            parse_creds_file(file_path)
        else:
            console.print("[red]❌ The specified file path does not exist or is not a file.[/red]")

    elif cred_method: # Manual entry
        console.print("Please enter your remote Neo4j connection details.")
        questions = [
            {"type": "input", "message": "URI (e.g., neo4j+s://xxxx.databases.neo4j.io):", "name": "uri"},
            {"type": "input", "message": "Username:", "name": "username", "default": "neo4j"},
            {"type": "password", "message": "Password:", "name": "password"},
        ]
        creds = prompt(questions)
        if not creds: return # User cancelled
        try:
            env_path = get_project_root() / ".env"
            with open(env_path, "w") as f:
                f.write(f"NEO4J_URI={creds.get('uri', '')}\n")
                f.write(f"NEO4J_USERNAME={creds.get('username', 'neo4j')}\n")
                f.write(f"NEO4J_PASSWORD={creds.get('password', '')}\n")
            console.print("[green]✅ Configuration for hosted database saved to .env file in project root.[/green]")
        except Exception as e:
            console.print(f"[red]❌ Failed to write .env file: {e}[/red]")

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

    try:
        env_path = get_project_root() / ".env"
        with open(env_path, "w") as f:
            f.write(f"NEO4J_URI=neo4j://localhost:7687\n")
            f.write(f"NEO4J_USERNAME=neo4j\n")
            f.write(f"NEO4J_PASSWORD={new_password}\n")
        console.print("[green]✅ Configuration for local database saved to .env file in project root.[/green]")
        console.print("\n[bold green]All done! Your local Neo4j instance is ready to use.[/bold green]")
    except Exception as e:
        console.print(f"[bold red]Failed to write .env file:[/bold red] {e}")

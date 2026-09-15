import os
import sys
import subprocess
import shutil
import json
from pathlib import Path

#: Everything is resolved against the script, not the caller's directory: run as
#: `python /path/to/install.py` from anywhere else, the relative paths created a
#: second virtualenv and installed into it.
PROJECT_ROOT = Path(__file__).parent.absolute()


def venv_dir() -> Path:
    return PROJECT_ROOT / "venv"


def pip_executable() -> Path:
    parts = ("Scripts", "pip.exe") if os.name == "nt" else ("bin", "pip")
    return venv_dir().joinpath(*parts)


def install_command() -> list:
    """`fulltext` is not optional in practice: without `pypdf` the PDF leg of the
    full-text step finds nothing, and reports that as "no open access copy"."""
    return [str(pip_executable()), "install", "-e", ".[fulltext]"]


def print_banner():
    print("=" * 60)
    print("🎯 ACADEMIC HUNTER V2 - Auto-Installer")
    print("=" * 60)

def check_python():
    print(">> Checking Python version...")
    # Matches `requires-python` in pyproject.toml. Accepting less meant the check
    # passed and then `pip install` failed with a message about the package.
    if sys.version_info < (3, 10):
        print("❌ Error: Python 3.10 or higher is required.")
        print("   (pyproject.toml declares requires-python >= 3.10)")
        sys.exit(1)
    print("✅ Python version OK.")

def setup_venv():
    print("\n>> Setting up virtual environment (venv)...")
    target = venv_dir()
    if not target.exists():
        subprocess.run([sys.executable, "-m", "venv", str(target)], check=True)
        print("✅ Virtual environment created.")
    else:
        print("✅ Virtual environment already exists. Skipping.")

    print("\n>> Installing dependencies...")
    subprocess.run(install_command(), cwd=str(PROJECT_ROOT), check=True)
    print("✅ Dependencies installed successfully.")
    print("   Clustering, novelty detection and RAG need the ML stack, which is a")
    print("   large download and is not installed by default:")
    print(f"   {pip_executable()} install -e '.[ml]'")

def setup_config():
    print("\n>> Setting up config.json...")
    config = PROJECT_ROOT / "config.json"
    example = PROJECT_ROOT / "config.example.json"
    if not config.exists():
        if example.exists():
            shutil.copy(example, config)
            print("✅ Copied config.example.json to config.json.")
        else:
            print("⚠️ Warning: config.example.json not found.")
    else:
        print("✅ config.json already exists. Skipping.")

def install_mcp_claude():
    print("\n" + "=" * 60)
    ans = input("Do you want to automatically configure Academic Hunter for Claude Desktop (MCP)? [Y/n]: ").strip().lower()
    if ans == 'n':
        return

    # Determine Claude config path
    if sys.platform == "darwin": # macOS
        config_path = Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    elif sys.platform == "win32": # Windows
        appdata = os.environ.get("APPDATA", "")
        config_path = Path(appdata) / "Claude" / "claude_desktop_config.json"
    else: # Linux
        print("⚠️ Warning: Auto-install for Claude Desktop is primarily supported on macOS and Windows.")
        config_path = Path.home() / ".config" / "Claude" / "claude_desktop_config.json"

    # Read existing config or create new
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            config = {"mcpServers": {}}
    else:
        config = {"mcpServers": {}}
        # Ensure parent directory exists
        config_path.parent.mkdir(parents=True, exist_ok=True)

    if "mcpServers" not in config:
        config["mcpServers"] = {}

    # Define absolute paths
    python_exe = str(
        venv_dir().joinpath(*(
            ("Scripts", "python.exe") if os.name == "nt" else ("bin", "python")
        ))
    )
    src_dir = str(PROJECT_ROOT / "src")

    # Inject Academic Hunter server
    config["mcpServers"]["academic-hunter"] = {
        "command": python_exe,
        "args": [
            "-m",
            "academic_hunter.interfaces.mcp.server"
        ],
        "env": {
            "PYTHONPATH": src_dir
        }
    }

    # Write back
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        print(f"✅ Success! MCP Server injected into: {config_path}")
        print("🔔 Please RESTART Claude Desktop to load the tools.")
    except Exception as e:
        print(f"❌ Failed to write Claude config: {e}")

if __name__ == "__main__":
    print_banner()
    check_python()
    setup_venv()
    setup_config()
    install_mcp_claude()
    print("\n✨ Installation Complete! The Academic Hunter tools are now available inside Claude Desktop.")

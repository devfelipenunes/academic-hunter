import os
import sys
import subprocess
import shutil
import json
from pathlib import Path

def print_banner():
    print("=" * 60)
    print("🎯 ACADEMIC HUNTER V2 - Auto-Installer")
    print("=" * 60)

def check_python():
    print(">> Checking Python version...")
    if sys.version_info < (3, 8):
        print("❌ Error: Python 3.8 or higher is required.")
        sys.exit(1)
    print("✅ Python version OK.")

def setup_venv():
    print("\n>> Setting up virtual environment (venv)...")
    venv_dir = Path("venv")
    if not venv_dir.exists():
        subprocess.run([sys.executable, "-m", "venv", "venv"], check=True)
        print("✅ Virtual environment created.")
    else:
        print("✅ Virtual environment already exists. Skipping.")

    print("\n>> Installing dependencies...")
    pip_exe = "venv\\Scripts\\pip" if os.name == "nt" else "venv/bin/pip"
    subprocess.run([pip_exe, "install", "-e", "."], check=True)
    print("✅ Dependencies installed successfully.")

def setup_config():
    print("\n>> Setting up config.json...")
    if not Path("config.json").exists():
        if Path("config.example.json").exists():
            shutil.copy("config.example.json", "config.json")
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
    project_root = Path(__file__).parent.absolute()
    python_exe = str(project_root / "venv" / "Scripts" / "python" if os.name == "nt" else project_root / "venv" / "bin" / "python")
    src_dir = str(project_root / "src")

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
    print("\n✨ Installation Complete! You can now run `academic-hunter` or use the tools inside Claude Desktop.")

"""Academic Hunter installer.

Creates the venv, installs the package, writes the MCP client configs from the
versioned `.example` templates, and finally starts the server to confirm it
answers. Installing without error proves nothing here: a stdio MCP server that
cannot start exits silently, with no output at all.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

#: Everything is resolved against the script, not the caller's directory: run as
#: `python /path/to/install.py` from anywhere else, the relative paths created a
#: second virtualenv and installed into it.
PROJECT_ROOT = Path(__file__).parent.absolute()

#: `fulltext` (pypdf) is the PDF leg of full-text. Measured cold at 439 MB and
#: six seconds, and it is everything the search needs: the semantic screener
#: embeds with ChromaDB's ONNX model, which comes with the base install.
DEFAULT_EXTRAS = ("fulltext",)

#: What `--ml` adds: sentence-transformers, scikit-learn, umap, bertopic and
#: hdbscan, for the analysis tools — clustering, visualisation, dedup, novelty,
#: summarize. Those tools name this extra when it is missing rather than failing
#: silently, so leaving it out costs nothing but the tools themselves.
ML_EXTRAS = ("ml", "fulltext")

#: The path the versioned `.example` configs carry. It is replaced by this
#: checkout's real path when the working config is written: an absolute literal
#: is correct in exactly one clone, and a config naming the wrong one is
#: indistinguishable from a broken server — the client says "failed to connect".
MCP_COMMAND_PLACEHOLDER = "/absolute/path/to/academic-hunter/venv/bin/academic-mcp"

#: (working config, versioned template). Neither working config is tracked: both
#: name the machine they were written on.
MCP_CONFIG_FILES = (
    (".mcp.json", ".mcp.json.example"),
    (".codex/config.toml", ".codex/config.toml.example"),
)

#: The command the published package is run with, with no clone and no venv. The
#: `--from` is required: the distribution is `academic-hunter` and the console
#: script is `academic-mcp`, so the bare name resolves to nothing.
UVIX_COMMAND = "uvx --from 'academic-hunter[fulltext]' academic-mcp"

#: What the installer prints about that path. One constant, because the same
#: command is documented in `docs/mcp_setup.md` and `README.md`, and a copy that
#: drifts is a command that resolves to nothing.
NEXT_STEPS_UVX = (
    "This checkout is now wired up. Without a clone, the published package",
    "needs no venv and no absolute path — user scope, so it connects with no",
    "approval prompt:",
    "  claude mcp add --scope user academic-hunter -- \\",
    f"    {UVIX_COMMAND}",
    "Warm the cache outside the client first — that is where the 439 MB is",
    "downloaded, and where the client would otherwise wait with no progress bar:",
    f"  {UVIX_COMMAND} --help",
)

#: Sent in order over stdio, newline-delimited, which is MCP's JSON-RPC framing.
HANDSHAKE_MESSAGES = (
    {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "academic-hunter-installer", "version": "1.0"},
        },
    },
    {"jsonrpc": "2.0", "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
)


def venv_dir() -> Path:
    return PROJECT_ROOT / "venv"


def script_path(name: str) -> Path:
    """Where a console script lands inside the venv, per platform."""
    scripts, suffix = ("Scripts", ".exe") if os.name == "nt" else ("bin", "")
    return venv_dir() / scripts / f"{name}{suffix}"


def pip_executable() -> Path:
    return script_path("pip")


def mcp_server_command() -> str:
    """The command an MCP client should run, derived from this checkout.

    The console script, not `python -m ... ` plus a `PYTHONPATH`: an editable
    install already resolves the package, and one form is one thing to get wrong.
    """
    return str(script_path("academic-mcp"))


def mcp_server_entry() -> dict:
    """The server entry, for clients configured by hand or by another installer."""
    return {"command": mcp_server_command(), "args": ["--transport", "stdio"]}


def install_command(ml: bool = False) -> list[str]:
    """The `pip install` line, extras included."""
    extras = ML_EXTRAS if ml else DEFAULT_EXTRAS
    return [str(pip_executable()), "install", "-e", f".[{','.join(extras)}]"]


def print_banner() -> None:
    print("=" * 60)
    print("🎯 ACADEMIC HUNTER V2 - Auto-Installer")
    print("=" * 60)


def check_python() -> None:
    print(">> Checking Python version...")
    # Deliberately a runtime check: this script is the thing that has to be able
    # to run on a Python too old for the package and say so. Matches
    # `requires-python` in pyproject.toml — accepting less meant the check passed
    # and then `pip install` failed with a message about the package.
    if sys.version_info < (3, 10):  # noqa: UP036
        print("❌ Error: Python 3.10 or higher is required.")
        print("   (pyproject.toml declares requires-python >=3.10)")
        sys.exit(1)
    print("✅ Python version OK.")


def setup_venv(ml: bool = False) -> None:
    print("\n>> Setting up virtual environment (venv)...")
    target = venv_dir()
    if not target.exists():
        # noqa: S603 — sys.executable, an absolute path, and no shell.
        subprocess.run([sys.executable, "-m", "venv", str(target)], check=True)  # noqa: S603
        print("✅ Virtual environment created.")
    else:
        print("✅ Virtual environment already exists. Skipping.")

    command = install_command(ml)
    print("\n>> Installing dependencies...")
    if ml:
        print("   `ml` pulls torch, which on Linux resolves to the CUDA build and the")
        print("   whole NVIDIA runtime: 3.15 GB measured, ~2.5 GB of it CUDA that a")
        print("   CPU-only tool never loads.")
    print(f"   $ {' '.join(command)}")
    subprocess.run(command, cwd=str(PROJECT_ROOT), check=True)  # noqa: S603
    print("✅ Dependencies installed successfully.")


def setup_config() -> None:
    print("\n>> Setting up config.json...")
    config = PROJECT_ROOT / "config.json"
    example = PROJECT_ROOT / "config.example.json"
    if config.exists():
        print("✅ config.json already exists. Skipping.")
        return
    if example.exists():
        shutil.copy(example, config)
        print("✅ Copied config.example.json to config.json.")
    else:
        print("⚠️  Warning: config.example.json not found.")


def render_client_config(template: Path) -> str:
    """The versioned template, with this checkout's command in place of the placeholder."""
    return template.read_text(encoding="utf-8").replace(MCP_COMMAND_PLACEHOLDER, mcp_server_command())


def write_mcp_configs() -> list[str]:
    """Write `.mcp.json` (Claude Code) and `.codex/config.toml` (Codex).

    Both used to be tracked with the author's absolute path baked in, which is
    correct in one checkout out of all of them, and there was nothing that
    generated them. A client that cannot start the server reports nothing more
    specific than "failed to connect".
    """
    written = []
    for target_name, template_name in MCP_CONFIG_FILES:
        template = PROJECT_ROOT / template_name
        if not template.exists():
            print(f"⚠️  {template_name} not found; skipping {target_name}.")
            continue
        target = PROJECT_ROOT / target_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render_client_config(template), encoding="utf-8")
        written.append(target_name)
        print(f"✅ Wrote {target_name}")
    return written


def claude_desktop_config_path() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", "")) / "Claude" / "claude_desktop_config.json"
    return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def install_mcp_claude_desktop(assume_yes: bool = False) -> bool:
    """Inject the server into Claude Desktop's own config file.

    Opt-in, and only asked when there is a terminal to ask on. The installer
    called `input()` unconditionally, so `install.py < /dev/null` raised EOFError
    *after* creating the venv — leaving the install half-finished, which is what
    made it unusable from CI and Docker.
    """
    if not assume_yes:
        if not sys.stdin.isatty():
            print("\n⚠️  No terminal to ask on; skipping Claude Desktop (pass --yes to force).")
            return False
        answer = input("\nConfigure Claude Desktop as well? [y/N]: ").strip().lower()
        if answer not in ("y", "yes", "s", "sim"):
            return False

    if sys.platform not in ("darwin", "win32"):
        print("⚠️  Claude Desktop auto-config is primarily supported on macOS and Windows;")
        print("   trying the Linux path anyway (see docs/mcp_setup.md).")

    config_path = claude_desktop_config_path()
    config: dict = {"mcpServers": {}}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            config = {"mcpServers": {}}
    if not isinstance(config, dict):
        config = {"mcpServers": {}}
    config.setdefault("mcpServers", {})
    config["mcpServers"]["academic-hunter"] = mcp_server_entry()

    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    except OSError as exc:
        print(f"❌ Failed to write Claude Desktop config: {exc}")
        return False
    print(f"✅ MCP server written to: {config_path}")
    print("🔔 Restart Claude Desktop to load the tools.")
    return True


def smoke_test(timeout: float = 90.0) -> int:
    """Start the server and speak to it: `initialize`, then `tools/list`.

    Returns the number of tools, or -1 if the server never answered. The
    `mcp>=1.0.0,<2` ceiling in pyproject.toml exists because 2.x makes this
    server "exit silently, with no output on stdio" — installed cleanly and still
    useless — and the only way to tell those two states apart is to talk to it.
    """
    command = [mcp_server_command(), "--transport", "stdio"]
    try:
        # noqa: S603 — absolute path, list argv, no shell.
        process = subprocess.Popen(  # noqa: S603
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
    except OSError as exc:
        print(f"⚠️  Could not start {command[0]}: {exc}")
        return -1

    tools = -1

    def read_stdout() -> None:
        """The tools/list reply ends the wait; anything else is skipped."""
        nonlocal tools
        for line in process.stdout:
            try:
                payload = json.loads(line)
            except ValueError:
                continue
            if payload.get("id") == 2:
                tools = len(payload.get("result", {}).get("tools", []))
                return

    # Both pipes are drained on threads. A server that fills a pipe buffer while
    # nobody reads it blocks forever, and this check would then report its own
    # deadlock as "the server did not answer".
    err: list[str] = []
    threading.Thread(target=lambda: err.extend(process.stderr), daemon=True).start()
    reader = threading.Thread(target=read_stdout, daemon=True)
    reader.start()

    try:
        for message in HANDSHAKE_MESSAGES:
            process.stdin.write(json.dumps(message) + "\n")
        process.stdin.flush()
    except OSError:
        pass

    # Joined, not slept on: the wait ends the moment the reply arrives, and only
    # runs to `timeout` when the server really is silent.
    reader.join(timeout)

    process.kill()
    process.wait(timeout=10)

    if tools < 0 and err:
        print(f"   server said: {err[0].strip()[:160]}")
    return tools


def check_uv() -> None:
    print("\n>> Checking for uv...")
    if shutil.which("uv"):
        print("✅ uv is on PATH.")
        return
    print("ℹ️  uv is not on PATH. This install does not need it — the venv above")
    print("   is complete. It is what the published package is installed with:")
    print("       curl -LsSf https://astral.sh/uv/install.sh | sh")


def print_next_steps() -> None:
    print("\n" + "=" * 60)
    print("Next steps")
    print("=" * 60)
    if shutil.which("claude"):
        print("Claude Code is on PATH. The `.mcp.json` is in place, but a")
        print("project-scoped server is only loaded once you approve it:")
        print("  1. Restart Claude Code in this directory.")
        print("  2. Approve the `academic-hunter` server when it is offered.")
        print("  3. Check with: claude mcp list")
    else:
        print("Connect the server to your agent — Claude Code, Claude Desktop,")
        print("Codex or Cursor: docs/mcp_setup.md has the entry for each.")

    print()
    for line in NEXT_STEPS_UVX:
        print(line)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install Academic Hunter and wire it into an MCP client.")
    parser.add_argument(
        "--ml",
        action="store_true",
        help="add the analysis extras, and with them a 3.15 GB torch/CUDA download",
    )
    parser.add_argument("--yes", action="store_true", help="answer yes to every prompt, for unattended runs")
    parser.add_argument("--skip-mcp", action="store_true", help="do not write the MCP client configs")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    print_banner()
    check_python()
    check_uv()
    setup_venv(ml=args.ml)
    setup_config()

    if args.skip_mcp:
        print("\n>> Skipping the MCP client configs (--skip-mcp).")
    else:
        print("\n>> Writing MCP client configs...")
        write_mcp_configs()

    install_mcp_claude_desktop(assume_yes=args.yes)

    print("\n>> Verifying that the server answers...")
    tools = smoke_test()
    if tools > 0:
        print(f"✅ Server answered: {tools} tools available.")
    elif tools == 0:
        print("⚠️  Server started but exposed no tools.")
    else:
        print("⚠️  The server did not answer the MCP handshake.")
        print("   It is installed on disk, but connecting a client will not work.")

    print_next_steps()
    print("\n✨ Installation complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

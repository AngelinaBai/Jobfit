from __future__ import annotations

import argparse
import os
import plistlib
import stat
import subprocess
import sys
from pathlib import Path

LABEL = "com.jobfit.scanner"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install or remove the JobFit macOS schedule")
    subparsers = parser.add_subparsers(dest="command", required=True)
    install = subparsers.add_parser("install")
    install.add_argument("--interval-hours", type=int, default=6)
    subparsers.add_parser("remove")
    subparsers.add_parser("status")
    return parser.parse_args()


def _paths() -> tuple[Path, Path, Path]:
    project_dir = Path.cwd().resolve()
    support_dir = Path.home() / ".jobfit"
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    return project_dir, support_dir, plist_path


def install(interval_hours: int) -> None:
    if interval_hours < 1:
        raise SystemExit("interval-hours must be at least 1")

    project_dir, support_dir, plist_path = _paths()
    env_path = project_dir / ".env"
    compose_path = project_dir / "docker-compose.yml"
    if not env_path.exists() or not compose_path.exists():
        raise SystemExit("Run this command from the jobfit-ingestion folder containing .env.")

    support_dir.mkdir(parents=True, exist_ok=True)
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    runner = support_dir / "run_scan.sh"
    stdout_log = support_dir / "scheduled-scan.log"
    stderr_log = support_dir / "scheduled-scan-error.log"

    runner.write_text(
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        f"cd {project_dir!s}\n"
        "export PATH=/usr/local/bin:/opt/homebrew/bin:/Applications/Docker.app/Contents/Resources/bin:$PATH\n"
        "docker compose up -d postgres\n"
        "set -a\n"
        "source .env\n"
        "set +a\n"
        f"{sys.executable} -m jobfit.cli --show-new\n",
        encoding="utf-8",
    )
    runner.chmod(runner.stat().st_mode | stat.S_IXUSR)

    plist = {
        "Label": LABEL,
        "ProgramArguments": ["/bin/bash", str(runner)],
        "StartInterval": interval_hours * 3600,
        "RunAtLoad": True,
        "StandardOutPath": str(stdout_log),
        "StandardErrorPath": str(stderr_log),
        "WorkingDirectory": str(project_dir),
    }
    with plist_path.open("wb") as handle:
        plistlib.dump(plist, handle)

    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}", str(plist_path)], check=False)
    subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(plist_path)], check=True)
    print(f"Installed JobFit scan every {interval_hours} hour(s).")
    print(f"New-job log: {stdout_log}")


def remove() -> None:
    _, _, plist_path = _paths()
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}", str(plist_path)], check=False)
    plist_path.unlink(missing_ok=True)
    print("Removed the JobFit schedule.")


def status() -> None:
    result = subprocess.run(
        ["launchctl", "print", f"gui/{os.getuid()}/{LABEL}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print("JobFit schedule is installed and loaded.")
    else:
        print("JobFit schedule is not loaded.")


def main() -> None:
    args = parse_args()
    if args.command == "install":
        install(args.interval_hours)
    elif args.command == "remove":
        remove()
    else:
        status()


if __name__ == "__main__":
    main()

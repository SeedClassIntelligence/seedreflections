#!/usr/bin/env python3
"""Configure hosted SMTP without putting the mailbox password in shell history."""

import argparse
import getpass
import json
import os
from pathlib import Path
import smtplib
import ssl
import subprocess
import sys
import tempfile


APP = Path("/opt/seedreflections")
ENV = APP / ".env"
COMPOSE = APP / "docker-compose.prod.yml"


def write_private(path: Path, content: str) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=".env-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            os.fchmod(output.fileno(), 0o600)
            output.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def replace_settings(content: str, settings: dict[str, str]) -> str:
    lines = content.splitlines()
    seen = set()
    for index, line in enumerate(lines):
        name = line.split("=", 1)[0]
        if name in settings:
            lines[index] = f"{name}={settings[name]}"
            seen.add(name)
    for name in settings.keys() - seen:
        lines.append(f"{name}={settings[name]}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--from-address", required=True)
    parser.add_argument("--port", type=int, default=465)
    args = parser.parse_args()
    if not ENV.is_file() or not COMPOSE.is_file():
        parser.error("run this on the deployed SeedReflections VM")
    password = getpass.getpass("Mailbox password (hidden): ")
    if not password or "\n" in password or "\r" in password:
        print("Password must be nonempty and on one line.", file=sys.stderr)
        return 1
    try:
        with smtplib.SMTP_SSL(args.host, args.port, timeout=20,
                              context=ssl.create_default_context()) as client:
            client.login(args.user, password)
    except (OSError, smtplib.SMTPException) as error:
        print(f"SMTP login failed ({type(error).__name__}); configuration unchanged.", file=sys.stderr)
        return 1

    original = ENV.read_text(encoding="utf-8")
    # Compose treats single-quoted env-file values literally, including dollar signs.
    quoted_password = "'" + password.replace("'", "\\'") + "'"
    settings = {
        "SEED_REFLECTIONS_SMTP_HOST": args.host,
        "SEED_REFLECTIONS_SMTP_PORT": str(args.port),
        "SEED_REFLECTIONS_SMTP_SECURITY": "ssl",
        "SEED_REFLECTIONS_SMTP_USER": args.user,
        "SEED_REFLECTIONS_SMTP_PASSWORD": quoted_password,
        "SEED_REFLECTIONS_SMTP_FROM": args.from_address,
    }
    write_private(ENV, replace_settings(original, settings))
    try:
        rendered = subprocess.run(
            ["docker", "compose", "-f", str(COMPOSE), "config", "--format", "json"],
            cwd=APP, capture_output=True, text=True, check=True,
        )
        actual = json.loads(rendered.stdout)["services"]["seed-reflections"]["environment"]
        if actual.get("SEED_REFLECTIONS_SMTP_PASSWORD") != password:
            raise ValueError("Compose did not preserve the password exactly")
    except (subprocess.CalledProcessError, KeyError, ValueError, json.JSONDecodeError) as error:
        write_private(ENV, original)
        print(f"Compose validation failed ({type(error).__name__}); configuration restored.", file=sys.stderr)
        return 1
    subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE), "up", "-d", "--no-deps", "--force-recreate", "seed-reflections"],
        cwd=APP, check=True,
    )
    print("SMTP login passed; app restarted. Check readiness and send a test password reset.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

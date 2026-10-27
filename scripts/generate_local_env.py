#!/usr/bin/env python3
"""Generate the local dev stack's TLS cert + dev credentials once, print
them to the terminal, and save them to scripts/.local-stack/local.env —
so run_local_stack.py and any broker test/script read the SAME values
instead of each hardcoding their own. Re-running without --force reuses
the existing file, so the whole stack stays on one consistent set of
values across multiple `up`/test runs.

Usage:
    python scripts/generate_local_env.py            # generate once, reuse if it already exists
    python scripts/generate_local_env.py --force     # always regenerate (new cert + new token)
"""
import argparse
import pathlib
import secrets
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
STATE_DIR = REPO_ROOT / "scripts" / ".local-stack"  # gitignored — never committed
ENV_FILE = STATE_DIR / "local.env"
CERT_FILE = STATE_DIR / "broker.crt"
KEY_FILE = STATE_DIR / "broker.key"


def generate_cert():
    # SAN must cover both names clients actually connect with: "localhost"
    # from the host (e.g. tests/test_smoke.py), and "host.docker.internal"
    # from inside the other containers (backend's mqtt_ingest.py) — a
    # CN-only cert fails TLS hostname verification for whichever name
    # isn't the CN.
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-keyout", str(KEY_FILE), "-out", str(CERT_FILE),
        "-days", "1", "-subj", "//CN=localhost",
        "-addext", "subjectAltName=DNS:localhost,DNS:host.docker.internal",
    ], check=True)


def generate(force: bool = False) -> dict:
    """Returns the generated values as a dict. Writes/reuses ENV_FILE."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    if not force and ENV_FILE.exists():
        return load()

    if force or not (CERT_FILE.exists() and KEY_FILE.exists()):
        generate_cert()

    values = {
        "LOCAL_STACK_BROKER_TLS_CERT": str(CERT_FILE),
        "LOCAL_STACK_BROKER_TLS_KEY": str(KEY_FILE),
        "LOCAL_STACK_MQTT_TEST_EMAIL": "dev@local-stack.test",
        "LOCAL_STACK_MQTT_TEST_DEVICE_TOKEN": secrets.token_hex(16),
        "LOCAL_STACK_JWT_SECRET": secrets.token_hex(32),
        "LOCAL_STACK_ADMIN_USER": "admin",
        "LOCAL_STACK_ADMIN_PASSWORD": secrets.token_urlsafe(12),
    }

    with open(ENV_FILE, "w") as f:
        for k, v in values.items():
            f.write(f"{k}={v}\n")

    return values


def load() -> dict:
    values = {}
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            values[k] = v
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true",
                         help="regenerate the cert and dev credentials even if local.env already exists")
    args = parser.parse_args()

    existed = ENV_FILE.exists() and not args.force
    values = generate(force=args.force)

    print(f"{'Reusing' if existed else 'Generated'} {ENV_FILE}:")
    for k, v in values.items():
        print(f"  {k}={v}")
    print()
    print("Other scripts (run_local_stack.py, broker tests) read this file "
          "so they all share the same cert + credentials. "
          "Delete scripts/.local-stack/ or pass --force to start over.")


if __name__ == "__main__":
    main()

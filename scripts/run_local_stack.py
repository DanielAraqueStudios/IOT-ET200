#!/usr/bin/env python3
"""Spin up the whole IOT-ET200 cloud stack locally for dev/testing:
cloud/broker + cloud/dashboard/backend + cloud/dashboard/frontend, each
built from their own Dockerfile and wired to each other and to their
own throwaway dev Postgres containers.

Tool choice: plain `docker` CLI via subprocess, not the `docker` Python
SDK — no extra pip dependency, and it mirrors the manual docker
build/run smoke-test steps already used against cloud/broker, so the
commands this script runs are the same ones a human would type by
hand to reproduce or debug a failure.

Usage:
    python scripts/run_local_stack.py up      # build, start, wait for health, print URLs, block until Ctrl+C
    python scripts/run_local_stack.py down    # stop and remove everything this script creates
    python scripts/run_local_stack.py up --seed-token   # also insert a test User/deviceToken row

`up` blocks and cleans everything up (containers + images + the
generated cert/state dir) on Ctrl+C or `down`, same discipline as the
earlier manual smoke test teardown.
"""
import argparse
import json
import pathlib
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
BROKER_DIR = REPO_ROOT / "cloud" / "broker"
BACKEND_DIR = REPO_ROOT / "cloud" / "dashboard" / "backend"
FRONTEND_DIR = REPO_ROOT / "cloud" / "dashboard" / "frontend"
STATE_DIR = REPO_ROOT / "scripts" / ".local-stack"  # generated certs; gitignored, not committed

PREFIX = "iot-et200-local"

NAMES = {
    "broker_pg": f"{PREFIX}-broker-pg",
    "broker_app": f"{PREFIX}-broker-app",
    "backend_pg": f"{PREFIX}-backend-pg",
    "backend_app": f"{PREFIX}-backend-app",
    "frontend_app": f"{PREFIX}-frontend-app",
}
IMAGES = {
    "broker": f"{PREFIX}-broker:local",
    "backend": f"{PREFIX}-backend:local",
    "frontend": f"{PREFIX}-frontend:local",
}

PORTS = {
    "broker_health": 18000,
    "broker_mqtt": 18830,
    "broker_pg": 55441,
    "backend_http": 18001,
    "backend_pg": 55442,
    "frontend_http": 18080,
}

# Dev-only credentials, wired consistently between the broker's seeded
# row (with --seed-token) and the backend's mqtt_ingest connection.
# Not real secrets; local-stack only.
DEV_MQTT_EMAIL = "dev@local-stack.test"
DEV_MQTT_DEVICE_TOKEN = "dev-local-stack-token"
DEV_JWT_SECRET = "dev-local-stack-jwt-secret"
DEV_ADMIN_USER = "admin"
DEV_ADMIN_PASSWORD = "admin"


def run(cmd, **kwargs):
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, **kwargs)


def docker(*args, **kwargs):
    return run(["docker", *args], **kwargs)


def cert_paths():
    return STATE_DIR / "broker.crt", STATE_DIR / "broker.key"


def ensure_cert():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    crt, key = cert_paths()
    if crt.exists() and key.exists():
        return
    run([
        "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-keyout", str(key), "-out", str(crt),
        "-days", "1", "-subj", "//CN=localhost",
    ], check=True)


def build_image(name, context_dir):
    docker("build", "-t", IMAGES[name], str(context_dir), check=True)


def container_exists(name):
    result = docker("ps", "-a", "-q", "-f", f"name=^{name}$", capture_output=True, text=True, check=True)
    return bool(result.stdout.strip())


def rm_container(name):
    if container_exists(name):
        docker("rm", "-f", name, check=False)


def wait_http(url, timeout=60, expect_statuses=(200, 401, 404)):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status in expect_statuses:
                    return True
        except urllib.error.HTTPError as e:
            if e.code in expect_statuses:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def wait_pg_ready(container_name, user, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = docker("exec", container_name, "pg_isready", "-U", user,
                         capture_output=True, text=True, check=False)
        if result.returncode == 0:
            return True
        time.sleep(1)
    return False


def start_postgres(name, port, db, user, password):
    rm_container(name)
    docker("run", "-d", "--name", name,
           "-e", f"POSTGRES_USER={user}",
           "-e", f"POSTGRES_PASSWORD={password}",
           "-e", f"POSTGRES_DB={db}",
           "-p", f"{port}:5432",
           "postgres:16-alpine", check=True)
    if not wait_pg_ready(name, user):
        sys.exit(f"FATAL: {name} did not become ready in time")


def bcrypt_hash_via_backend_image(password):
    """Reuse the backend's own image (passlib[bcrypt] already installed
    there) instead of adding a local Python dependency just to hash a
    dev password."""
    result = subprocess.run(
        ["docker", "run", "--rm", IMAGES["backend"], "python3", "-c",
         "from passlib.context import CryptContext;"
         f"print(CryptContext(schemes=['bcrypt']).hash({password!r}))"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def seed_device_token():
    docker("exec", NAMES["broker_pg"], "psql", "-U", "broker", "-d", "broker", "-c",
           f"INSERT INTO \"User\" (email, \"passwordHash\", \"deviceToken\") "
           f"VALUES ('{DEV_MQTT_EMAIL}', 'x', '{DEV_MQTT_DEVICE_TOKEN}') "
           f"ON CONFLICT (email) DO UPDATE SET \"deviceToken\" = EXCLUDED.\"deviceToken\";",
           check=True)


def up(seed_token):
    ensure_cert()
    crt, key = cert_paths()

    print("== Building images ==")
    build_image("broker", BROKER_DIR)
    build_image("backend", BACKEND_DIR)
    build_image("frontend", FRONTEND_DIR)

    print("== Starting broker's dev Postgres ==")
    start_postgres(NAMES["broker_pg"], PORTS["broker_pg"], "broker", "broker", "broker")

    print("== Starting broker ==")
    rm_container(NAMES["broker_app"])
    docker("run", "-d", "--name", NAMES["broker_app"],
           "-e", f"DATABASE_URL=postgresql://broker:broker@host.docker.internal:{PORTS['broker_pg']}/broker",
           "-e", "MQTT_PORT=1883",
           "-e", "MQTT_TLS_CERT=/certs/broker.crt",
           "-e", "MQTT_TLS_KEY=/certs/broker.key",
           "-e", "PORT=8000",
           "-p", f"{PORTS['broker_health']}:8000",
           "-p", f"{PORTS['broker_mqtt']}:1883",
           "-v", f"{STATE_DIR}:/certs",
           IMAGES["broker"], check=True)

    if seed_token:
        print("== Seeding a dev device-token row in the broker's DB ==")
        seed_device_token()

    print("== Starting dashboard backend's dev Postgres ==")
    start_postgres(NAMES["backend_pg"], PORTS["backend_pg"], "plc", "plc", "plc")

    print("== Hashing dev admin password via the backend image ==")
    admin_hash = bcrypt_hash_via_backend_image(DEV_ADMIN_PASSWORD)

    print("== Starting dashboard backend ==")
    rm_container(NAMES["backend_app"])
    docker("run", "-d", "--name", NAMES["backend_app"],
           "-e", f"DATABASE_URL=postgresql://plc:plc@host.docker.internal:{PORTS['backend_pg']}/plc",
           "-e", f"MQTT_URL=mqtts://host.docker.internal:{PORTS['broker_mqtt']}",
           "-e", f"MQTT_USERNAME={DEV_MQTT_EMAIL}",
           "-e", f"MQTT_DEVICE_TOKEN={DEV_MQTT_DEVICE_TOKEN}",
           "-e", "MQTT_TLS_CA_CERT=/certs/broker.crt",
           "-e", f"JWT_SECRET={DEV_JWT_SECRET}",
           "-e", f"DASHBOARD_ADMIN_USER={DEV_ADMIN_USER}",
           "-e", f"DASHBOARD_ADMIN_PASSWORD_HASH={admin_hash}",
           "-e", "PORT=8000",
           "-p", f"{PORTS['backend_http']}:8000",
           "-v", f"{STATE_DIR}:/certs",
           IMAGES["backend"], check=True)

    print("== Starting dashboard frontend ==")
    rm_container(NAMES["frontend_app"])
    docker("run", "-d", "--name", NAMES["frontend_app"],
           "-e", f"PORT={PORTS['frontend_http']}",
           "-p", f"{PORTS['frontend_http']}:{PORTS['frontend_http']}",
           IMAGES["frontend"], check=True)
    # Note: the Angular build bakes in src/environment.ts's apiUrl at
    # BUILD time (http://localhost:8000 by default) — it does not read
    # PORT or any env var at runtime for API calls, only nginx uses
    # PORT to pick its listen port. If backend_http above is changed
    # from 8000, rebuild the frontend after editing environment.ts.

    print("== Waiting for health checks ==")
    ok_broker = wait_http(f"http://localhost:{PORTS['broker_health']}/health")
    ok_backend = wait_http(f"http://localhost:{PORTS['backend_http']}/openapi.json")
    ok_frontend = wait_http(f"http://localhost:{PORTS['frontend_http']}/")

    print()
    print("== Status ==")
    print(f"broker     health: {'OK' if ok_broker else 'NOT READY'}  http://localhost:{PORTS['broker_health']}/health")
    print(f"broker     mqtt:   mqtts://localhost:{PORTS['broker_mqtt']}  (cert: {crt})")
    print(f"backend    health: {'OK' if ok_backend else 'NOT READY'}  http://localhost:{PORTS['backend_http']}/docs")
    print(f"frontend   health: {'OK' if ok_frontend else 'NOT READY'}  http://localhost:{PORTS['frontend_http']}/")
    print(f"dashboard admin login: {DEV_ADMIN_USER} / {DEV_ADMIN_PASSWORD}")
    if seed_token:
        print(f"seeded MQTT dev credentials: {DEV_MQTT_EMAIL} / {DEV_MQTT_DEVICE_TOKEN}")
    else:
        print("NOTE: no device token seeded (pass --seed-token) — backend's "
              "mqtt_ingest will retry/fail auth against the broker until one exists.")

    if not (ok_broker and ok_backend and ok_frontend):
        print("\nWARNING: one or more services did not pass their health check in time.", file=sys.stderr)

    print("\nStack is up. Press Ctrl+C to tear it down.")


def down():
    print("== Tearing down local stack ==")
    for name in NAMES.values():
        rm_container(name)
    for image in IMAGES.values():
        docker("image", "rm", image, check=False)
    if STATE_DIR.exists():
        shutil.rmtree(STATE_DIR, ignore_errors=True)
    print("Done — no containers, images, or generated state left behind.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["up", "down"])
    parser.add_argument("--seed-token", action="store_true",
                         help="insert a dev User/deviceToken row into the broker's DB")
    args = parser.parse_args()

    if args.action == "down":
        down()
        return

    def _teardown_and_exit(*_):
        print()
        down()
        sys.exit(0)

    signal.signal(signal.SIGINT, _teardown_and_exit)
    signal.signal(signal.SIGTERM, _teardown_and_exit)

    up(args.seed_token)
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Run tests/test_smoke.py against the local dev stack (scripts/run_local_stack.py),
wiring its MQTT_* env vars from scripts/.local-stack/local.env instead of
making you type them by hand — single source of truth stays
generate_local_env.py, same as run_local_stack.py itself.

Usage:
    python scripts/run_smoke_test_local.py
    # or via the VS Code task "IOT-ET200: MQTT smoke test (local stack)"

Requires the stack to already be up (see run_local_stack.py "up").
"""
import os
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import generate_local_env  # noqa: E402
import run_local_stack  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def main():
    if not generate_local_env.ENV_FILE.exists():
        sys.exit(
            "FATAL: scripts/.local-stack/local.env not found — run the "
            "stack first: `python scripts/run_local_stack.py up --seed-token`"
        )

    values = generate_local_env.load()
    env = {
        **os.environ,
        "MQTT_HOST": "localhost",
        "MQTT_PORT": str(run_local_stack.PORTS["broker_mqtt"]),
        "MQTT_TLS_CA_CERT": values["LOCAL_STACK_BROKER_TLS_CERT"],
        "MQTT_USERNAME": values["LOCAL_STACK_MQTT_TEST_EMAIL"],
        "MQTT_DEVICE_TOKEN": values["LOCAL_STACK_MQTT_TEST_DEVICE_TOKEN"],
        # Must fall under the broker's MQTT_TOPIC_PREFIX ACL (default "plant/").
        "MQTT_TEST_TOPIC": "plant/smoke/test",
    }
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tests" / "test_smoke.py")], env=env
    )
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()

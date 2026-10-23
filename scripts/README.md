# scripts/

Repo-wide dev tooling (not specific to one service — see
`cloud/broker/README.md` and `cloud/dashboard/README.md` for
per-service setup).

## run_local_stack.py

Builds and runs `cloud/broker`, `cloud/dashboard/backend`, and
`cloud/dashboard/frontend` together locally via Docker, each with its
own throwaway dev Postgres container, wired to each other the same
way the Railway Shared Variables are documented (broker's self-signed
cert shared as `MQTT_TLS_CERT`/`MQTT_TLS_CA_CERT`, `MQTT_URL` pointing
at the broker's local port). Uses the `docker` CLI via `subprocess`
(no extra Python dependency) — see the module docstring for why.

```bash
python scripts/run_local_stack.py up                # build + run everything, print URLs, block
python scripts/run_local_stack.py up --seed-token    # also insert a dev User/deviceToken row
python scripts/run_local_stack.py down               # tear everything down
```

`up` blocks and tears itself down on Ctrl+C. Nothing it creates
(containers, images, the generated TLS cert under
`scripts/.local-stack/`, gitignored) is left behind after `down` or a
clean Ctrl+C exit.

Requires Docker and `openssl` on PATH. Prints each container's local
URL/port and the dev admin login once everything passes its health
check.

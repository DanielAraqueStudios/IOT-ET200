#!/usr/bin/env python3
"""Generate a self-signed TLS cert/key pair for the broker, for any host
(e.g. a Railway TCP Proxy hostname) — unlike generate_local_env.py, which
is hardcoded to localhost/host.docker.internal for the local Docker stack.

Pure Python (uses the `cryptography` package) so it works on Windows
without the `openssl` CLI on PATH.

Usage:
    python scripts/generate_broker_cert.py
        (prompts for the TCP Proxy host at the terminal)
    python scripts/generate_broker_cert.py --host viaduct.proxy.rlwy.net
        (skips the prompt)
"""
import argparse
import datetime
import pathlib

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def normalize_host(host: str) -> str:
    """Reduce common copy-paste variants down to a bare hostname — TLS
    hostname verification matches the cert's SAN against exactly what the
    client connects to, so a scheme, path, port, or stray whitespace baked
    into the SAN would silently break every connection.
    """
    host = host.strip().strip("'\"")

    for scheme in ("mqtts://", "mqtt://", "https://", "http://", "tcp://"):
        if host.lower().startswith(scheme):
            print(f"Note: dropping {scheme!r} prefix.")
            host = host[len(scheme):]
            break

    host = host.strip("/")

    if "/" in host:
        bare, _, rest = host.partition("/")
        print(f"Note: dropping path {rest!r} after the host.")
        host = bare

    if ":" in host:
        # e.g. an accidentally-pasted "host:port" — a SAN containing the
        # port never matches the bare hostname the client actually verifies
        # against.
        bare_host, _, port = host.partition(":")
        print(f"Note: dropping ':{port}' — certs are bound to the hostname only, not the port.")
        host = bare_host

    host = host.strip()
    if not host:
        raise SystemExit("Nothing left after stripping scheme/path/port — re-run with just the bare hostname.")

    return host


def generate(host: str, out_dir: pathlib.Path, days: int) -> tuple[pathlib.Path, pathlib.Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    cert_file = out_dir / "broker.crt"
    key_file = out_dir / "broker.key"

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host)])
    now = datetime.datetime.now(datetime.timezone.utc)

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=days))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(host)]), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )

    key_file.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return cert_file, key_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", help="CN/SAN for the cert, e.g. a Railway TCP Proxy hostname. Prompted for if omitted.")
    parser.add_argument("--out", default="scripts/.broker-cert", help="output directory (default: scripts/.broker-cert, gitignored)")
    parser.add_argument("--days", type=int, default=825, help="validity in days (default: 825)")
    args = parser.parse_args()

    host = args.host
    while not host:
        host = input("MQTT broker host (e.g. the Railway TCP Proxy hostname, without the port): ").strip()

    host = normalize_host(host)

    cert_file, key_file = generate(host, pathlib.Path(args.out), args.days)
    print(f"Using host: {host!r}")

    print(f"Wrote {cert_file} and {key_file}\n")
    print("MQTT_TLS_CERT / MQTT_TLS_CERT_PEM (paste full contents, including BEGIN/END lines):")
    print(cert_file.read_text())
    print("MQTT_TLS_KEY (broker service only — never shared):")
    print(key_file.read_text())


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""PyQt6 desktop tool for exercising the deployed MQTT broker by hand —
connect, watch the live connection/event flow, simulate the gateway's
side of a remote command, and publish arbitrary values, all from one
window instead of a terminal prompt.

This is a GUI superset of interactive_probe.py: same broker, same
topics, same credential model, but with a visible connection-state
timeline and a "simulated gateway" panel that auto-answers ON/OFF
commands the way edge/small_scope's real gateway will once it's
deployed (see that script's docstring for why nothing in production
currently answers the command topic on its own).

Usage:
    python tests/mqtt_test_gui.py

Defaults match interactive_probe.py: MQTT_HOST/MQTT_PORT point at the
deployed Railway broker, MQTT_TLS_CA_CERT defaults to
scripts/.broker-cert-final/broker.crt if present. Username/device token
are entered in the UI, never defaulted or hardcoded.
"""
import os
import pathlib
import ssl
import sys
import time
from dataclasses import dataclass

import paho.mqtt.client as mqtt
from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QFormLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QGroupBox,
    QCheckBox, QFrame, QFileDialog, QSizePolicy,
)

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_DEFAULT_CERT = _REPO_ROOT / "scripts" / ".broker-cert-final" / "broker.crt"
_DEFAULT_HOST = os.environ.get("MQTT_HOST", "viaduct.proxy.rlwy.net")
_DEFAULT_PORT = os.environ.get("MQTT_PORT", "52805")
_DEFAULT_OUTPUT_TOPIC = "plant/small_scope/output/state"
_DEFAULT_INPUT_TOPIC = "plant/small_scope/input/state"
_DEFAULT_COMMAND_TOPIC = "plant/small_scope/output/command"

# ── Theme — same tokens as cloud/dashboard/frontend's styles.css ───────────
BG = "#09090b"
PANEL = "#18181b"
BORDER = "#27272a"
TEXT = "#f4f4f5"
TEXT_DIM = "#a1a1aa"
TEXT_FAINT = "#71717a"
AMBER = "#fbbf24"
AMBER_HOVER = "#fcd34d"
GREEN = "#4ade80"
GREEN_BG = "#14532d"
RED = "#f87171"
RED_BG = "#450a0a"
BLUE = "#60a5fa"

STYLESHEET = f"""
QWidget {{ background: {BG}; color: {TEXT}; font-family: 'Segoe UI', sans-serif; font-size: 13px; }}
QMainWindow {{ background: {BG}; }}
QGroupBox {{
    border: 1px solid {BORDER}; border-radius: 10px; margin-top: 14px;
    padding: 14px 12px 12px 12px; font-weight: 600; color: {TEXT_DIM};
}}
QGroupBox::title {{
    subcontrol-origin: margin; left: 10px; padding: 0 6px;
    color: {TEXT_FAINT}; text-transform: uppercase; font-size: 10px; letter-spacing: 1px;
}}
QLineEdit {{
    background: {PANEL}; border: 1px solid {BORDER}; border-radius: 8px;
    padding: 7px 10px; color: {TEXT}; selection-background-color: {AMBER};
}}
QLineEdit:focus {{ border-color: {BLUE}; }}
QLineEdit:disabled {{ color: {TEXT_FAINT}; }}
QPushButton {{
    background: {PANEL}; border: 1px solid {BORDER}; border-radius: 8px;
    padding: 8px 16px; color: {TEXT};
}}
QPushButton:hover {{ border-color: {TEXT_FAINT}; }}
QPushButton:disabled {{ color: {TEXT_FAINT}; border-color: {BORDER}; }}
QPushButton#connectBtn {{ background: {AMBER}; color: {BG}; font-weight: 700; border: none; }}
QPushButton#connectBtn:hover {{ background: {AMBER_HOVER}; }}
QPushButton#onBtn {{ background: {GREEN}; color: #052e16; font-weight: 700; border: none; }}
QPushButton#onBtn:hover {{ background: #86efac; }}
QPushButton#offBtn {{ background: {RED}; color: {RED_BG}; font-weight: 700; border: none; }}
QPushButton#offBtn:hover {{ background: #fca5a5; }}
QTextEdit {{
    background: {BG}; border: 1px solid {BORDER}; border-radius: 10px;
    padding: 8px; color: {TEXT_DIM}; font-family: 'Cascadia Mono', Consolas, monospace; font-size: 12px;
}}
QCheckBox {{ color: {TEXT_DIM}; spacing: 8px; }}
QLabel#statusLabel {{ font-weight: 600; }}
QLabel#sectionHint {{ color: {TEXT_FAINT}; font-size: 11px; }}
"""


def _dot_html(color: str) -> str:
    return f'<span style="color:{color};">&#9679;</span>'


@dataclass
class ConnectionState:
    connected: bool = False


class MqttBridge(QObject):
    """Runs paho's client on its own network thread; re-emits every
    callback as a Qt signal so the GUI thread never touches the socket
    directly (paho's callbacks fire on its own thread)."""
    connected = pyqtSignal(int)
    disconnected = pyqtSignal(int)
    message = pyqtSignal(str, str)
    log = pyqtSignal(str, str)  # level, text

    def __init__(self):
        super().__init__()
        self.client: "mqtt.Client | None" = None

    def connect_to(self, host, port, cert_path, username, password, topics):
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv311)
        self.client.username_pw_set(username, password)
        if cert_path:
            self.client.tls_set(ca_certs=cert_path, cert_reqs=ssl.CERT_REQUIRED)
            self.client.tls_insecure_set(True)  # self-signed, pinned via ca_certs above
        else:
            self.log.emit("warn", "No TLS cert set — connecting without certificate validation")
            self.client.tls_set()
            self.client.tls_insecure_set(True)

        def on_connect(c, userdata, flags, reason_code, properties=None):
            rc = getattr(reason_code, "value", reason_code)
            self.connected.emit(rc)
            if rc == 0:
                for t in topics:
                    c.subscribe(t)

        def on_disconnect(c, userdata, flags, reason_code, properties=None):
            rc = getattr(reason_code, "value", reason_code)
            self.disconnected.emit(rc)

        def on_message(c, userdata, msg):
            self.message.emit(msg.topic, msg.payload.decode(errors="replace"))

        self.client.on_connect = on_connect
        self.client.on_disconnect = on_disconnect
        self.client.on_message = on_message
        self.client.connect(host, port, keepalive=30)
        self.client.loop_start()

    def publish(self, topic, payload):
        if self.client:
            self.client.publish(topic, payload)

    def disconnect(self):
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            self.client = None


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("IOT-ET200 — MQTT Test Console")
        self.resize(880, 680)
        self.setStyleSheet(STYLESHEET)

        self.bridge = MqttBridge()
        self.bridge.connected.connect(self._on_connected)
        self.bridge.disconnected.connect(self._on_disconnected)
        self.bridge.message.connect(self._on_message)
        self.bridge.log.connect(self._log)

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setSpacing(14)
        layout.setContentsMargins(18, 18, 18, 18)

        layout.addWidget(self._build_header())
        layout.addWidget(self._build_connection_group())

        mid = QHBoxLayout()
        mid.setSpacing(14)
        mid.addWidget(self._build_gateway_sim_group(), 1)
        mid.addWidget(self._build_publish_group(), 1)
        layout.addLayout(mid)

        layout.addWidget(self._build_log_group(), 1)

        self._set_controls_enabled(connected=False)

    # ── UI builders ──────────────────────────────────────────────────────

    def _build_header(self) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        title = QLabel('<span style="font-size:20px; font-weight:700;">IOT-ET200</span> '
                        f'<span style="font-size:20px; font-weight:700; font-style:italic; color:{AMBER};">MQTT Console</span>')
        h.addWidget(title)
        h.addStretch()
        self.status_dot = QLabel(_dot_html(TEXT_FAINT))
        self.status_text = QLabel("Disconnected")
        self.status_text.setObjectName("statusLabel")
        h.addWidget(self.status_dot)
        h.addWidget(self.status_text)
        return w

    def _build_connection_group(self) -> QGroupBox:
        box = QGroupBox("Broker connection")
        form = QFormLayout()
        form.setSpacing(8)

        self.host_edit = QLineEdit(_DEFAULT_HOST)
        self.port_edit = QLineEdit(str(_DEFAULT_PORT))
        self.cert_edit = QLineEdit(str(_DEFAULT_CERT) if _DEFAULT_CERT.exists() else "")
        cert_row = QHBoxLayout()
        cert_row.addWidget(self.cert_edit)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_cert)
        cert_row.addWidget(browse_btn)
        cert_row_w = QWidget()
        cert_row_w.setLayout(cert_row)

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("device email")
        self.token_edit = QLineEdit()
        self.token_edit.setPlaceholderText("device token")
        self.token_edit.setEchoMode(QLineEdit.EchoMode.Password)

        form.addRow("Host", self.host_edit)
        form.addRow("Port", self.port_edit)
        form.addRow("TLS cert", cert_row_w)
        form.addRow("Username", self.username_edit)
        form.addRow("Device token", self.token_edit)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setObjectName("connectBtn")
        self.connect_btn.clicked.connect(self._toggle_connection)

        outer = QVBoxLayout()
        outer.addLayout(form)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(self.connect_btn)
        outer.addLayout(btn_row)
        box.setLayout(outer)
        return box

    def _build_gateway_sim_group(self) -> QGroupBox:
        box = QGroupBox("Simulated gateway")
        v = QVBoxLayout()
        hint = QLabel(
            "Nothing in production answers the command topic until the real\n"
            "edge/small_scope gateway is deployed. Enable this to have this\n"
            "window stand in for it: any ON/OFF command received here is\n"
            "automatically echoed back to the state topic, same as the real\n"
            "gateway would after writing to the PLC."
        )
        hint.setObjectName("sectionHint")
        hint.setWordWrap(True)
        v.addWidget(hint)

        self.auto_respond_check = QCheckBox("Auto-respond to commands (simulate the gateway)")
        v.addWidget(self.auto_respond_check)

        self.last_command_label = QLabel("No command received yet")
        self.last_command_label.setObjectName("sectionHint")
        v.addWidget(self.last_command_label)

        v.addStretch()
        box.setLayout(v)
        return box

    def _build_publish_group(self) -> QGroupBox:
        box = QGroupBox("Manual publish")
        v = QVBoxLayout()

        form = QFormLayout()
        self.topic_edit = QLineEdit(_DEFAULT_OUTPUT_TOPIC)
        self.value_edit = QLineEdit()
        self.value_edit.setPlaceholderText("value to publish")
        form.addRow("Topic", self.topic_edit)
        form.addRow("Value", self.value_edit)
        v.addLayout(form)

        btn_row = QHBoxLayout()
        on_btn = QPushButton("ON")
        on_btn.setObjectName("onBtn")
        on_btn.clicked.connect(lambda: self._quick_publish("ON"))
        off_btn = QPushButton("OFF")
        off_btn.setObjectName("offBtn")
        off_btn.clicked.connect(lambda: self._quick_publish("OFF"))
        publish_btn = QPushButton("Publish")
        publish_btn.clicked.connect(self._publish_custom)
        btn_row.addWidget(on_btn)
        btn_row.addWidget(off_btn)
        btn_row.addWidget(publish_btn)
        v.addLayout(btn_row)

        self.publish_buttons = [on_btn, off_btn, publish_btn]
        v.addStretch()
        box.setLayout(v)
        return box

    def _build_log_group(self) -> QGroupBox:
        box = QGroupBox("Connection & message flow")
        v = QVBoxLayout()
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        v.addWidget(self.log_view)
        box.setLayout(v)
        return box

    # ── Actions ──────────────────────────────────────────────────────────

    def _browse_cert(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select broker cert", str(_REPO_ROOT), "Cert files (*.crt *.pem)")
        if path:
            self.cert_edit.setText(path)

    def _toggle_connection(self):
        if self.bridge.client is not None:
            self.bridge.disconnect()
            self._set_controls_enabled(connected=False)
            self._set_status("Disconnected", TEXT_FAINT)
            self._log("info", "Disconnected by user")
            return

        host = self.host_edit.text().strip()
        try:
            port = int(self.port_edit.text().strip())
        except ValueError:
            self._log("error", f"Invalid port: {self.port_edit.text()!r}")
            return
        cert = self.cert_edit.text().strip() or None
        username = self.username_edit.text().strip()
        token = self.token_edit.text()
        if not username or not token:
            self._log("error", "Username and device token are required")
            return

        self._set_status("Connecting…", AMBER)
        self._log("info", f"Connecting to {host}:{port} as {username!r}…")
        self.connect_btn.setEnabled(False)
        topics = [_DEFAULT_OUTPUT_TOPIC, _DEFAULT_INPUT_TOPIC, _DEFAULT_COMMAND_TOPIC]
        try:
            self.bridge.connect_to(host, port, cert, username, token, topics)
        except Exception as e:
            self._log("error", f"Connect failed: {e}")
            self._set_status("Disconnected", RED)
            self.connect_btn.setEnabled(True)

    def _quick_publish(self, value: str):
        topic = self.topic_edit.text().strip() or _DEFAULT_OUTPUT_TOPIC
        self.bridge.publish(topic, value)
        self._log("sent", f"{topic} = {value!r}")

    def _publish_custom(self):
        topic = self.topic_edit.text().strip()
        value = self.value_edit.text()
        if not topic or not value:
            self._log("error", "Topic and value are both required to publish")
            return
        self.bridge.publish(topic, value)
        self._log("sent", f"{topic} = {value!r}")

    def _set_controls_enabled(self, connected: bool):
        self.connect_btn.setText("Disconnect" if connected else "Connect")
        self.connect_btn.setEnabled(True)
        for w in (self.host_edit, self.port_edit, self.cert_edit, self.username_edit, self.token_edit):
            w.setEnabled(not connected)
        for b in self.publish_buttons:
            b.setEnabled(connected)

    def _set_status(self, text: str, color: str):
        self.status_dot.setText(_dot_html(color))
        self.status_text.setText(text)

    # ── Bridge signal handlers (run on the GUI thread) ──────────────────

    def _on_connected(self, rc: int):
        if rc == 0:
            self._set_status("Connected", GREEN)
            self._log("ok", "Connected — subscribed to output/state, input/state, output/command")
            self._set_controls_enabled(connected=True)
        else:
            self._set_status("Rejected", RED)
            self._log("error", f"Broker rejected connection (rc={rc}) — check username/device token")
            self._set_controls_enabled(connected=False)
            self.bridge.client = None

    def _on_disconnected(self, rc: int):
        self._set_status("Disconnected", TEXT_FAINT if rc == 0 else RED)
        self._log("warn" if rc != 0 else "info", f"Disconnected (rc={rc})")
        self._set_controls_enabled(connected=False)

    def _on_message(self, topic: str, payload: str):
        self._log("recv", f"{topic} = {payload!r}")
        if topic == _DEFAULT_COMMAND_TOPIC:
            self.last_command_label.setText(f"Last command: {payload!r} at {time.strftime('%H:%M:%S')}")
            if self.auto_respond_check.isChecked():
                self.bridge.publish(_DEFAULT_OUTPUT_TOPIC, payload)
                self._log("sent", f"(auto) {_DEFAULT_OUTPUT_TOPIC} = {payload!r} — simulating the gateway's write")

    def _log(self, level: str, text: str):
        colors = {"info": TEXT_DIM, "ok": GREEN, "warn": AMBER, "error": RED, "recv": BLUE, "sent": AMBER}
        color = colors.get(level, TEXT_DIM)
        ts = time.strftime("%H:%M:%S")
        self.log_view.append(f'<span style="color:{TEXT_FAINT};">{ts}</span> '
                              f'<span style="color:{color};">[{level.upper()}]</span> {text}')

    def closeEvent(self, event):
        self.bridge.disconnect()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

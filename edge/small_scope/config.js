// Single source of truth for this small-scope gateway's settings.
// Edit these values for your actual PLC/broker before running.
//
// MQTT broker: cloud/broker in this repo, deployed to Railway,
// connected over TLS + device-token auth (defense in depth — TLS is on
// top of check_device_token auth, not a replacement for it). Set
// MQTT_URL / MQTT_USERNAME / MQTT_DEVICE_TOKEN / MQTT_TLS_CA_FILE as
// env vars on this gateway (see cloud/broker/README.md "Deploying to
// Railway" for where MQTT_URL's host:port and the cert come from —
// the TCP Proxy host:port, not the broker's own public HTTP domain).
module.exports = {
  opcua: {
    endpointUrl: "opc.tcp://192.168.0.3:4840", // PLC's OPC UA server, plant-local
    // NodeId of FB_RemoteOutput's Static variable RemoteCmd_Output,
    // inside its own instance DB (default "FB_RemoteOutput_DB") — NOT
    // the physical output. FB_RemoteOutput.scl moves this onto
    // Q_RemoteOutput inside the PLC program. See TagTable_IoTOutput.md
    // for why. Browse the live server (e.g. UaExpert) to confirm the
    // exact NodeId TIA assigned rather than assuming this string.
    outputNodeId: "ns=3;s=\"FB_RemoteOutput_DB\".\"RemoteCmd_Output\"",
    // NodeId of the plain input tag I_RemoteStatus (%I3.0, Bool) — no FB,
    // read-only. Placeholder; browse the live server (e.g. UaExpert) to
    // confirm the exact NodeId TIA assigned rather than assuming this string.
    inputNodeId: "ns=3;s=\"I_RemoteStatus\"",
    inputPollMs: 1000, // how often to read inputNodeId over OPC UA
  },
  mqtt: {
    // mqtts:// (TLS) once the broker side terminates TLS. Host/port:
    // the web $PORT stays the HTTP API; the broker's MQTT_PORT (TLS)
    // needs its own Railway TCP Proxy to be reachable from here.
    url: process.env.MQTT_URL || "mqtts://your-app.up.railway.app:1884",
    // The broker still requires check_device_token auth (TLS is on top
    // of this, not instead of it) — username is the account email,
    // password is that account's device token from Paint-mixer's
    // GET /api/auth/device-token. Never hardcode the token; set
    // MQTT_USERNAME / MQTT_DEVICE_TOKEN as env vars.
    username: process.env.MQTT_USERNAME || "",
    deviceToken: process.env.MQTT_DEVICE_TOKEN || "",
    // Broker cert is self-signed (not CA-issued), same posture as the
    // OPC UA side's endpointMustExist:false. Point this at a saved copy
    // of that exact cert so the client trusts it specifically — public
    // CA validation will always fail against a self-signed cert.
    // Leaving it unset falls back to rejectUnauthorized:false (no cert
    // validation at all) — logged as a warning, lab/POC only.
    tlsCaFile: process.env.MQTT_TLS_CA_FILE || "",
    commandTopic: "plant/small_scope/output/command", // payload: "ON" or "OFF"
    stateTopic: "plant/small_scope/output/state", // published back after each write
    inputStateTopic: "plant/small_scope/input/state", // published when I_RemoteStatus changes
  },
};

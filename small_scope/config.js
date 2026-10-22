// Single source of truth for this small-scope gateway's settings.
// Edit these values for your actual PLC/broker before running.
//
// MQTT broker: your own custom broker (Paint-mixer repo's api/broker.py),
// connected over TLS — no device-token auth. The broker side needs its
// own TLS change (wrap the asyncio server with an SSL context) before
// this will actually connect; see README.md.
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
    // No username/password — TLS only, no device-token auth.
    commandTopic: "plant/small_scope/output/command", // payload: "ON" or "OFF"
    stateTopic: "plant/small_scope/output/state", // published back after each write
    inputStateTopic: "plant/small_scope/input/state", // published when I_RemoteStatus changes
  },
};

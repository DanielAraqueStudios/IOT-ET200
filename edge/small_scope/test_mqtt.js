// Standalone MQTT connectivity check for this gateway, deliberately
// skipping OPC UA entirely. index.js's main() connects to OPC UA first
// and only sets up MQTT once that succeeds — useful in production, but
// it means you can't use index.js itself to confirm the gateway can
// even reach the broker before the PLC is wired up / reachable. This
// script reuses the exact same config.js and `mqtt` library index.js
// does, so a pass here means the real gateway's MQTT half will behave
// identically once OPC UA is in place too.
//
// Usage:
//   node test_mqtt.js
//     Connects, subscribes to the command topic, and publishes a
//     marker value to the output state topic to prove PUBLISH works.
//     Leave it running and either watch the cloud dashboard for the
//     marker value, or publish to the command topic from elsewhere
//     (e.g. tests/interactive_probe.py) to confirm SUBSCRIBE works too.
//
// Requires the same env vars as index.js/config.js: MQTT_URL,
// MQTT_USERNAME, MQTT_DEVICE_TOKEN, MQTT_TLS_CA_FILE.
const fs = require("fs");
const mqtt = require("mqtt");
const config = require("./config");

if (!config.mqtt.username || !config.mqtt.deviceToken) {
  console.error(
    "FAIL: MQTT_USERNAME and MQTT_DEVICE_TOKEN must be set — issue a " +
      "device token via the dashboard's 'Issue device token' form first."
  );
  process.exit(1);
}

const tlsOptions = config.mqtt.tlsCaFile
  ? { ca: fs.readFileSync(config.mqtt.tlsCaFile) }
  : (() => {
      console.warn(
        "[mqtt] MQTT_TLS_CA_FILE not set — falling back to " +
          "rejectUnauthorized:false (no cert validation, insecure, " +
          "lab/POC only)."
      );
      return { rejectUnauthorized: false };
    })();

console.log(`[mqtt] connecting to ${config.mqtt.url} as ${config.mqtt.username}...`);

const client = mqtt.connect(config.mqtt.url, {
  protocolVersion: 4,
  reconnectPeriod: 2000,
  username: config.mqtt.username,
  password: config.mqtt.deviceToken,
  ...tlsOptions,
});

client.on("connect", () => {
  console.log("[mqtt] CONNECTED — broker reachable and credentials accepted.");
  client.subscribe(config.mqtt.commandTopic, (err) => {
    if (err) {
      console.error("[mqtt] subscribe failed:", err.message);
    } else {
      console.log("[mqtt] subscribed:", config.mqtt.commandTopic);
    }
  });

  const marker = `test_mqtt-${Date.now()}`;
  client.publish(config.mqtt.stateTopic, marker, (err) => {
    if (err) {
      console.error("[mqtt] publish failed:", err.message);
    } else {
      console.log(`[mqtt] published ${JSON.stringify(marker)} to ${config.mqtt.stateTopic}`);
      console.log("       -> check the dashboard's Tag state card for this value.");
    }
  });

  console.log(
    `\nListening on ${config.mqtt.commandTopic} — publish "ON" or "OFF" there ` +
      "from another client (e.g. tests/interactive_probe.py) to confirm " +
      "SUBSCRIBE works too. Ctrl+C to stop.\n"
  );
});

client.on("message", (topic, payload) => {
  console.log(`[RECEIVED] ${topic} = ${payload.toString()}`);
});

client.on("error", (err) => {
  console.error("[mqtt] error:", err.message);
});

client.on("reconnect", () => {
  console.log("[mqtt] reconnecting...");
});

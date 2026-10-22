// Small scope: one MQTT command ("ON"/"OFF") writes one PLC output tag
// over OPC UA. No telemetry, no other tags, no interlock — matches the
// LAB4/small_scope pattern of this repo (minimal, single-purpose).
const mqtt = require("mqtt");
const { OPCUAClient, DataType, StatusCodes } = require("node-opcua-client");
const config = require("./config");

async function connectOpcua() {
  const client = OPCUAClient.create({ endpointMustExist: false });
  await client.connect(config.opcua.endpointUrl);
  const session = await client.createSession();
  console.log("[opcua] connected:", config.opcua.endpointUrl);
  return { client, session };
}

async function writeOutput(session, on) {
  const result = await session.write({
    nodeId: config.opcua.outputNodeId,
    attributeId: 13, // AttributeIds.Value
    value: {
      value: { dataType: DataType.Boolean, value: !!on },
    },
  });
  if (result !== StatusCodes.Good) {
    throw new Error(`OPC UA write failed: ${result.toString()}`);
  }
}

async function main() {
  const { session } = await connectOpcua();

  // protocolVersion: 4 (3.1.1) — the Paint-mixer broker (api/broker.py)
  // only implements CONNECT/PUBLISH/SUBSCRIBE/PINGREQ/DISCONNECT for
  // that version; no retained messages, no QoS 2. TLS only — no
  // username/password, no device-token auth.
  const mqttClient = mqtt.connect(config.mqtt.url, {
    protocolVersion: 4,
    reconnectPeriod: 2000,
  });

  mqttClient.on("connect", () => {
    console.log("[mqtt] connected:", config.mqtt.url);
    mqttClient.subscribe(config.mqtt.commandTopic, (err) => {
      if (err) console.error("[mqtt] subscribe failed:", err.message);
      else console.log("[mqtt] subscribed:", config.mqtt.commandTopic);
    });
  });

  mqttClient.on("message", async (topic, payload) => {
    if (topic !== config.mqtt.commandTopic) return;
    const command = payload.toString().trim().toUpperCase();
    if (command !== "ON" && command !== "OFF") {
      console.warn("[mqtt] ignoring unknown command:", command);
      return;
    }
    try {
      await writeOutput(session, command === "ON");
      console.log("[opcua] wrote output:", command);
      // No `retain` — the Paint-mixer broker doesn't implement it; a
      // late subscriber won't get the last state automatically.
      mqttClient.publish(config.mqtt.stateTopic, command);
    } catch (err) {
      console.error("[opcua] write error:", err.message);
    }
  });

  mqttClient.on("error", (err) => console.error("[mqtt] error:", err.message));

  // Poll the read-only input tag and publish only when its value changes,
  // to avoid flooding the state topic every poll with an identical value.
  let lastPublishedInput;
  setInterval(async () => {
    try {
      const result = await session.read({
        nodeId: config.opcua.inputNodeId,
        attributeId: 13, // AttributeIds.Value
      });
      if (result.statusCode !== StatusCodes.Good) {
        console.error("[opcua] input read failed:", result.statusCode.toString());
        return;
      }
      const value = result.value.value;
      if (value === lastPublishedInput) return;
      lastPublishedInput = value;
      mqttClient.publish(config.mqtt.inputStateTopic, value ? "ON" : "OFF");
      console.log("[opcua] input changed, published:", value);
    } catch (err) {
      console.error("[opcua] input poll error:", err.message);
    }
  }, config.opcua.inputPollMs);
}

main().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});

# TIA Portal V18 Build Guide — small_scope (Q_RemoteOutput + I_RemoteStatus)

Step-by-step, click-by-click instructions for a plant engineer to build
the PLC side of this scope in TIA Portal V18, for the S7-1500 CPU. This
assumes the project already exists and you have the CPU open in the
Devices & networks / Program blocks view. Background and rationale are
in `README.md` and `TagTable_IoTOutput.md` — this file is the ordered
checklist only.

## 1. Create `Q_RemoteOutput` (output tag, %Q3.0)

Skip this step if the tag already exists from earlier work.

1. In the project tree, expand **PLC_1 → PLC tags** and open the
   default tag table.
2. Add a new row:
   - **Name**: `Q_RemoteOutput`
   - **Data type**: `Bool`
   - **Address**: `%Q3.0`
3. In the tag's properties (right side of the row, or the "Accessible
   from HMI/OPC UA/Web API" column), confirm the **Access** (visible)
   and **Writable** checkboxes are both checked. These are checked by
   default for a new tag — just verify, don't assume.

## 2. Create `I_RemoteStatus` (input tag, %I3.0)

This is a plain tag, same tag table, no FB — physical inputs are
inherently read-only in hardware (nothing in the PLC program, including
OPC UA, can write back to a physical input terminal), so there is no
"Writable" concern here the way there was for the output in step 1.

1. In the same default tag table, add a new row:
   - **Name**: `I_RemoteStatus`
   - **Data type**: `Bool`
   - **Address**: `%I3.0`
2. Confirm the **Access** (visible) checkbox is checked so it's exposed
   over OPC UA. There is no Writable box to worry about for an input.

## 3. Create/verify FB `FB_RemoteOutput`

Skip the creation parts if this FB already exists from earlier work —
just verify the interface variable and OB1 call.

1. In **Program blocks**, add a new block → **Function Block** →
   name it `FB_RemoteOutput` → OK.
2. Open its interface table. Under the **Static** section, add:
   - **Name**: `RemoteCmd_Output`
   - **Data type**: `Bool`
3. On that same `RemoteCmd_Output` row, check both **Access** (visible)
   and **Writable** — this is what actually exposes it to OPC UA write
   access. This is the real `opcua.outputNodeId` target, not
   `Q_RemoteOutput` itself.
4. In the FB's code editor, enter only the body (TIA already knows the
   block type — don't type `FUNCTION_BLOCK`/`VAR`/`BEGIN`/`END_FUNCTION_BLOCK`):
   ```
   "Q_RemoteOutput" := #RemoteCmd_Output;
   ```
5. Open **OB1**, and if not already done, call `FB_RemoteOutput` once
   with a default instance (drag it into the OB1 code editor from the
   project tree; accept the default instance DB name, normally
   `FB_RemoteOutput_DB`).

## 4. Enable the OPC UA server — check the license FIRST

**Before configuring anything else**, check the license. This was the
actual blocker encountered in this project's prior testing: the server
starts and accepts client connections normally even with no license,
but the address space stays structurally present and completely empty.

1. Double-click **PLC_1** to open **Device configuration**.
2. Select the CPU, open **Properties → General → Runtime licenses →
   OPC UA**.
3. Check **Type of purchased license**. If it shows **"No license"**
   (in red, with a tooltip about the license not being sufficient),
   stop here and fix this first:
   - Open **Automation License Manager (ALM)** on the engineering PC.
   - Search the available key-image source (e.g. a "Yellow Disk" or
     equivalent key source) for **"OPC UA"**, the same way you'd search
     for any other STEP7/WinCC key.
   - Install a matching `SIMATIC OPC UA S7-1500 small` (or whatever tier
     matches the CPU) key.
   - Return to CPU Properties → Runtime licenses → OPC UA — TIA detects
     the newly installed license automatically; the "No license" red
     state should clear with no manual selection needed.
4. Once the license shows a valid purchased type, go to **CPU
   Properties → OPC UA → Server → General** and check **Enable OPC UA
   server**.
5. Confirm the **port** is `4840` (default) under the server's endpoint
   settings, unless you have a specific reason to change it.

## 5. Compile and download

1. Right-click **PLC_1** → **Compile → Hardware and software (only
   changes)** (or rebuild all if this is the first compile). Confirm
   **0 errors**.
2. Download to the device (**Online → Download to device**, or the
   download toolbar button). Confirm "Loading completed (errors: 0;
   warnings: 0)".

## 6. Browse the live OPC UA server and update `config.js`

The placeholder NodeId strings already in `small_scope\config.js` are
guesses based on TIA's usual naming pattern — do not assume they are
correct. Confirm them by browsing the live server.

1. Open **UaExpert** (or any OPC UA test client).
2. Create a new server connection to `opc.tcp://<plc-ip>:4840` (the same
   IP as `config.js`'s `opcua.endpointUrl`). Use security policy
   **None** / **Anonymous** for this first test (see README.md's
   "Judgment call" note about tightening this later).
3. Trust the PLC's self-signed certificate on first connect.
4. In the **Address Space** tree, browse to find:
   - `RemoteCmd_Output`, inside `FB_RemoteOutput_DB` (the FB's instance
     DB) — this is the output side.
   - `I_RemoteStatus`, as a plain tag — this is the input side.
5. For each node, select it and read its exact **NodeId** string from
   UaExpert's attribute/properties panel (it will look like
   `ns=3;s="FB_RemoteOutput_DB"."RemoteCmd_Output"` and
   `ns=3;s="I_RemoteStatus"`, but confirm the exact namespace index and
   quoting TIA actually assigned — don't copy the example strings from
   this guide or from `config.js`'s comments without checking).
6. Edit `small_scope\config.js`:
   - Set `opcua.outputNodeId` to the exact string read for
     `RemoteCmd_Output`.
   - Set `opcua.inputNodeId` to the exact string read for
     `I_RemoteStatus`.

## 7. Verification checklist

- [ ] In UaExpert, drag `RemoteCmd_Output` into the Data Access View
      and write `TRUE`. Confirm `Q_RemoteOutput` (watch it in TIA
      Portal's online watch table, or physically if wired) follows
      within one PLC scan.
- [ ] Write `FALSE` and confirm `Q_RemoteOutput` follows back.
- [ ] In TIA Portal's watch table (or by physically toggling the wired
      input), change `I_RemoteStatus`'s value.
- [ ] Confirm the gateway (`node index.js`, with the updated
      `config.js`) picks up the change via its input-poll loop and
      publishes `"ON"`/`"OFF"` to `mqtt.inputStateTopic`
      (`plant/small_scope/input/state` by default) — check the MQTT
      broker/subscriber side for the published message.

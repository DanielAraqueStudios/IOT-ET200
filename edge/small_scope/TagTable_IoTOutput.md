# Tag Table — IOT small_scope

Per project architecture ([[tia-portal-project-architecture]]): Tag
Table (I/O) / FB (logic + the OPC UA write target) / OB1 (one call).
This scope now covers both directions: a remote **output** write and a
read-only **input** status, with different reliability requirements.
**Revised design for the output** (changed from an earlier version of
this scope that had OPC UA write the physical output directly — see
`src/FB_RemoteOutput.scl` for why that proved unreliable): OPC UA
writes a **Static variable inside the FB's own instance DB**, and the
FB moves that value onto the physical output every scan. The **input**
needs none of this — see the note below the table.

## Tag table

| Tag name       | Area | Address | Type | Description |
|-----------------|------|---------|------|--------------|
| Q_RemoteOutput   | Q    | %Q0.3   | Bool | Physical output — written only by `FB_RemoteOutput`, mirrors its `RemoteCmd_Output` static variable |
| I_RemoteStatus   | I    | %I3.0   | Bool | Read-only placeholder input, exposed directly via OPC UA (plain tag, no FB) |

**Why the input needs no FB while the output does:** the reliability
problem documented in `src/FB_RemoteOutput.scl` was specific to OPC UA
*writing* to a plain tag — no such issue was ever observed on *reads*.
`I_RemoteStatus` is only ever read (by this gateway, over OPC UA), so
it can stay a plain tag in the default tag table with no FB and no
OB1 call.

Address `%Q0.3` — used in this project's `IOT-TEST` build (the PLC was
free of other scopes, so no collision check against LAB4/LAB5 was
needed here). If loading alongside LAB4/LAB5 in the same project,
`%Q3.0` is the next clear byte instead (LAB4 uses `%Q0.0`–`%Q0.6`,
LAB5 uses all of `%Q2.x`).

## FB interface (not a global tag — see `src/FB_RemoteOutput.scl`)

| Variable          | Section | Type | Description |
|--------------------|---------|------|--------------|
| RemoteCmd_Output    | Static  | Bool | Written directly by OPC UA (the IOT2050 gateway) — this is the real `opcua.outputNodeId` target |

This lives in `FB_RemoteOutput`'s instance DB (default name
`FB_RemoteOutput_DB` if called with a default instance from OB1), not
in the default tag table. Its NodeId in the OPC UA address space will
look like `ns=3;s="FB_RemoteOutput_DB"."RemoteCmd_Output"` — browse the
live server to confirm the exact string TIA assigns rather than
guessing.

## Building it in TIA Portal

1. Create `Q_RemoteOutput` in the default tag table. Leave its
   "Accessible from HMI/OPC UA/Web API" checkbox checked (default) —
   though it doesn't strictly need OPC UA write access anymore, since
   the FB is what sets it, not an external client.
2. Add `src/FB_RemoteOutput.scl` as a new FB named `FB_RemoteOutput`.
   In its interface table, add `RemoteCmd_Output` (Bool) under
   **Static**, and check its "Accessible from HMI/OPC UA/Web API"
   (Access) and Writable boxes — this is what actually exposes it to
   OPC UA. Call it once from `OB1` with a default instance, same
   pattern as every LAB4/LAB5 FB.
3. Enable the OPC UA server on the CPU (see `../../Arquitecture.md` and
   `README.md`'s step-by-step), and **check CPU Properties → Runtime
   licenses → OPC UA first** — this was the actual blocker in earlier
   testing.
4. Compile, download. Browse the live OPC UA server (e.g. with
   UaExpert) to find `RemoteCmd_Output`'s exact NodeId inside
   `FB_RemoteOutput_DB` — copy that into `config.js`'s
   `opcua.outputNodeId`, don't assume the string.
5. Wire `%Q0.3`'s physical terminal to whatever lamp/relay you're
   testing with, or just watch both values in TIA Portal's watch table
   for a first test with nothing physically wired — write
   `RemoteCmd_Output` from OPC UA and confirm `Q_RemoteOutput` follows
   it within one scan.
6. Create `I_RemoteStatus` (Bool, `%I3.0`) in the default tag table —
   no FB, no OB1 call needed, same as step 1's reasoning for the
   output tag's address choice. Leave "Accessible from HMI/OPC UA/Web
   API" checked. Browse the live OPC UA server to confirm its NodeId
   and copy it into `config.js`'s `opcua.inputNodeId`.

# `src/` — PLC-side SCL source

This folder holds the **body-only** SCL source for TIA Portal function
blocks used by this scope — not standalone compilable files, and not
something TIA Portal imports directly as a `.scl` project file. They're
reference copies of exactly what goes in a block's code editor, kept
in version control so the logic isn't only visible inside a TIA Portal
project archive.

## `FB_RemoteOutput.scl`

The function block that lets the IOT2050 gateway's OPC UA write
actually reach the physical output `Q_RemoteOutput`, without OPC UA
touching that `%Q` tag directly.

**Why this FB exists instead of a direct OPC UA write to `%Q`:** a
plain output tag worked in isolated UaExpert testing, but proved
unreliable across project reloads/power cycles — the server's address
space intermittently stopped exposing `%Q` tags even with the license
and Access/Writable both confirmed correct. Writing to a `Static`
interface variable instead, and letting the PLC's own SCL logic move
that value onto the physical output, is the more robust pattern — it
also keeps remote and local control as two explicit, separate inputs
to real PLC logic, instead of OPC UA silently overwriting a physical
output behind the program's back. See the file's own header comment
for the full reasoning, including why a `Static` instance-DB member
was chosen over a plain global `M` tag.

### Using this file in TIA Portal

This is **not** a complete, importable block — it's the function
block's body only. TIA Portal's block editor already knows the
surrounding `FUNCTION_BLOCK` / `VAR` / `BEGIN` / `END_FUNCTION_BLOCK`
structure from the block's own interface table; typing those wrapper
keywords into the code pane yourself will fail to compile. Copy only
the executable line(s) below the header comment into the function
block's code editor.

Full click-by-click creation steps (interface table setup, the
`RemoteCmd_Output` Static variable, the OB1 call) are in
[`../TIA_PORTAL_BUILD_GUIDE.md`](../TIA_PORTAL_BUILD_GUIDE.md), section
"3. Create/verify FB `FB_RemoteOutput`" — follow that, not this file
alone, since the interface variable (`RemoteCmd_Output : Bool`, with
**Access** and **Writable** both checked) has to exist before this
body does anything useful, and this file doesn't declare it.

Required tags (declared separately, not in this file):

| Name | Where declared | Role |
|---|---|---|
| `RemoteCmd_Output` | `FB_RemoteOutput`'s own interface table, Static section | Write target for OPC UA (`config.js`'s `opcua.outputNodeId`) |
| `Q_RemoteOutput` | Default PLC tag table — see [`../TagTable_IoTOutput.md`](../TagTable_IoTOutput.md) | The actual physical output this scope controls |

### Logic

A single unconditional assignment — the physical output always mirrors
the remote command variable. **No interlock** with any physical
pushbutton exists in this minimal scope (see "Judgment calls" in
[`../README.md`](../README.md)); if this output ever needs to coexist
with a local control source, OR the two together here instead of a
straight assignment — not handled in this file as-is.

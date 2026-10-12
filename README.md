# legion-lock — pin MCP server tools in a lockfile, fail CI on tool drift

An MCP server can change a tool's description or input schema after you approved it, and a model reads those
descriptions as instructions (tool drift, "rug pull"). `legion-lock` pins the approved tool list of each MCP server in
`.mcp-tools.lock.json`. `check` fails as soon as a server changed, and names the change: tool added, removed,
description changed, schema paths changed.

Fingerprints come from the public LEGION transparency log of MCP tool lists (`https://tlog.legion-api.com/tlog/v1`).
Each one is signed (Ed25519), included in an append-only Merkle tree (RFC 9162) and checked against a root key
fingerprint you pin. The lockfile keeps the proofs: `verify` re-checks them offline.

[Version française](README.fr.md)

## Pin in 3 commands
```bash
python3 legion_lock.py add io.guestgraph/mental-model   # pin the current state (verified proof) in .mcp-tools.lock.json
python3 legion_lock.py check                            # 0 = matches · 1 = DRIFT (per-tool diff) · 2 = invalid proof
python3 legion_lock.py verify                           # offline: re-check the proofs stored in the lockfile
```
The id is the one of the official MCP registry. To approve an earlier version: `add ID --at-leaf N`. To prove it
against a specific signed head: `--at-head S`.

Requirements: Python 3.8+, no dependency (`cryptography` is used if installed, otherwise pure-Python Ed25519).
Files: `legion_lock.py`, plus `vendor/legion_tlog_verify.py` and `vendor/legion_verify_mirror.py`, LEGION's two public
verifiers.

## Check one live server in one command: `legion_verify_server.py`
```bash
python3 legion_verify_server.py https://mcp.example.com/mcp --save proof.json   # live tools/list vs the signed history
python3 legion_verify_server.py --offline proof.json                            # re-check the saved proof, no network
```
Verdict: `UNCHANGED` (live list = latest signed version) · `CHANGED` (per-tool diff) · `UNKNOWN` (never signed by the
log) · `AUTH` (server requires auth). It only sends `initialize` and `tools/list`, never calls a tool. No score.

## Demo (real drift, public log)
`demo/demo_drift.sh` pins two servers to a state BEFORE a change they really made, then runs `check`:
`io.guestgraph/mental-model` (tool `diagram`: description and 2 schema paths changed, leaf 16044 → 17659) and
`ai.daystruct.api/daystruct` (tool `plan_project_development` added, leaf 121 → 14516). Expected: exit 1 with the drift
named; offline `verify` = 0; hand-edited lockfile = 2. Transcript: `demo/transcript_drift_*.txt`.
Adversarial tests (lying log, forged archive, rewritten history, forged lockfile): `tests/test_adversarial.py`, 15/15.

## What `check` verifies, in order
1. The log keyring starts from the pinned root fingerprint `a7c6a35b…`.
2. Your pin and the current state are both signed records, included in signed heads (RFC 9162).
3. The current head extends the head of your pin (consistency proof). Otherwise: rewritten history, fork or rollback,
   exit 2.
4. Is the current fingerprint the approved one? If not, `check` fetches the archived definitions of both versions,
   accepts them only if they hash back to the signed fingerprints, then names the drift field by field.

## Limits (read them)
- This is **the signed observation of a single observer** (LEGION). It does not show what the server serves to other
  clients.
- Only `name`, `description` and `inputSchema` are fingerprinted. A change limited to `annotations`, `outputSchema` or
  `title` is not seen.
- Delay: a change appears only after LEGION's next observation, then the next signed head (one to three signed cycles a
  day, measured 9–11 Oct 2026). `check --strict` also fails when a newer observation is not signed yet.
- Servers that require authentication are not observed.
- The log's Bitcoin anchors are `pending` (no `ots verify` on a full node). `legion-lock` does not rely on them.

## Integrations (`integrations/`)
- `github/mcp-tools-lock.yml`: on every pull request and daily, `verify` then `check`. The job fails on drift.
- `pre-commit/pre-commit.sh` (raw git hook).
- `claude-code/settings.json` + `legion_lock_hook.sh`: `PreToolUse` hook on `mcp__.*`. Claude Code blocks the MCP tool
  call if a pinned server drifted. Result cached 10 min.

Lockfile format: [FORMAT.md](FORMAT.md). Read-only MCP server on the same log:
[legion-mcp](https://github.com/Legion33shadow/legion-mcp). License: MIT.

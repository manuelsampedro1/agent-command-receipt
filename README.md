# Agent Command Receipt

Create and verify command evidence receipts for coding-agent handoffs.

Agent closeouts often say "tests passed" with only a sentence as evidence. `agent-command-receipt` records caller-provided command outcomes together with SHA-256 hashes of evidence files, then verifies those hashes before a closeout, proof packet, or run ledger reuses the claim.

The tool is dependency-free and local-first. It does not execute shell commands or read private shell history; it only records the command result and evidence files you provide.

## What It Records

- The exact command claim.
- Status: `pass`, `fail`, `skipped`, or `unknown`.
- Optional exit code, working directory, notes, and fixed creation time.
- Evidence file paths, sizes, and SHA-256 hashes.
- A verification report that fails when evidence files are missing or changed.
- Optional strict gates for required receipt status and minimum verified evidence.

## Install

```sh
python3 -m pip install --upgrade pip
python3 -m pip install -e .
```

Or run without installing:

```sh
PYTHONPATH=src python3 -m agent_command_receipt create \
  --command "make test" \
  --status pass \
  --exit-code 0 \
  --evidence examples/test-output.log
```

## Usage

Record evidence after you have actually run a check:

```sh
make test > /tmp/test-output.log
PYTHONPATH=src python3 -m agent_command_receipt create \
  --command "make test" \
  --status pass \
  --exit-code 0 \
  --base-dir /tmp \
  --evidence test-output.log \
  --output /tmp/agent-command-receipt.json
```

Verify the receipt before reusing the claim:

```sh
PYTHONPATH=src python3 -m agent_command_receipt verify \
  /tmp/agent-command-receipt.json \
  --base-dir /tmp
```

For closeout, ledger, or claim-check reuse, verify both integrity and claim
strength:

```sh
PYTHONPATH=src python3 -m agent_command_receipt verify \
  /tmp/agent-command-receipt.json \
  --base-dir /tmp \
  --require-status pass \
  --min-evidence 1
```

Verify the included example receipt:

```sh
PYTHONPATH=src python3 -m agent_command_receipt verify examples/passing-receipt.json
```

Render a Markdown receipt for a proof packet:

```sh
PYTHONPATH=src python3 -m agent_command_receipt create \
  --command "make lint" \
  --status pass \
  --exit-code 0 \
  --evidence examples/test-output.log \
  --format markdown
```

## Example Output

```md
# Agent Command Receipt

Status: `pass`
Exit code: `0`
CWD: `.`

## Command

```sh
make test
```

## Evidence

| Path | Size | SHA-256 |
| --- | ---: | --- |
| `examples/test-output.log` | 27 | `...` |
```

## Development

```sh
make test
make lint
make build
make smoke
```

## Fit With The Agent Workflow Stack

- `agent-claim-check`: checks closeout claims against exact command evidence.
- `agent-command-receipt`: hashes the evidence files behind those command claims.
- `agent-proof-packet`: packages command receipts with diffs, risks, and decisions.
- `agent-run-ledger`: preserves receipts as durable run evidence.

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

SCHEMA_VERSION = "agent-command-receipt.v1"
VALID_STATUSES = ("fail", "pass", "skipped", "unknown")


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    message: str
    path: str | None = None

    def as_dict(self) -> dict[str, str]:
        result = {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
        }
        if self.path:
            result["path"] = self.path
        return result


def utc_now() -> str:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return now.isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_evidence_path(base_dir: Path, path_text: str) -> Path:
    candidate = Path(path_text)
    if candidate.is_absolute():
        return candidate
    return base_dir / candidate


def evidence_record(base_dir: Path, path_text: str) -> dict[str, Any]:
    path = resolve_evidence_path(base_dir, path_text)
    if not path.exists():
        raise FileNotFoundError(f"evidence file not found: {path_text}")
    if not path.is_file():
        raise ValueError(f"evidence path is not a file: {path_text}")
    stat = path.stat()
    return {
        "path": Path(path_text).as_posix(),
        "size_bytes": stat.st_size,
        "sha256": sha256_file(path),
    }


def build_receipt(
    *,
    command: str,
    status: str,
    exit_code: int | None,
    cwd: str,
    created_at: str,
    notes: list[str],
    evidence_paths: list[str],
    base_dir: Path,
) -> dict[str, Any]:
    if status not in VALID_STATUSES:
        raise ValueError(f"unsupported status: {status}")
    if not command.strip():
        raise ValueError("command must not be empty")

    return {
        "schema_version": SCHEMA_VERSION,
        "command": command,
        "status": status,
        "exit_code": exit_code,
        "cwd": cwd,
        "created_at": created_at,
        "notes": notes,
        "evidence": [
            evidence_record(base_dir, evidence_path)
            for evidence_path in evidence_paths
        ],
    }


def receipt_to_markdown(receipt: dict[str, Any]) -> str:
    lines = [
        "# Agent Command Receipt",
        "",
        f"Status: `{receipt.get('status', 'unknown')}`",
        f"Exit code: `{receipt.get('exit_code')}`",
        f"CWD: `{receipt.get('cwd', '.')}`",
        f"Created at: `{receipt.get('created_at', '')}`",
        "",
        "## Command",
        "",
        "```sh",
        str(receipt.get("command", "")),
        "```",
    ]

    notes = receipt.get("notes") or []
    if notes:
        lines.extend(["", "## Notes", ""])
        lines.extend(f"- {note}" for note in notes)

    evidence = receipt.get("evidence") or []
    if evidence:
        lines.extend([
            "",
            "## Evidence",
            "",
            "| Path | Size | SHA-256 |",
            "| --- | ---: | --- |",
        ])
        for item in evidence:
            digest = str(item.get("sha256", ""))
            lines.append(
                f"| `{item.get('path', '')}` | {item.get('size_bytes', 0)} | "
                f"`{digest}` |"
            )
    else:
        lines.extend(["", "## Evidence", "", "- No evidence files recorded."])

    return "\n".join(lines)


def verify_receipt(
    receipt: dict[str, Any],
    base_dir: Path,
    *,
    require_status: str | None = None,
    min_evidence: int = 0,
) -> dict[str, Any]:
    findings: list[Finding] = []
    checked = 0
    receipt_status = str(receipt.get("status") or "")

    if receipt.get("schema_version") != SCHEMA_VERSION:
        findings.append(
            Finding(
                "invalid-schema",
                "error",
                f"Expected schema_version {SCHEMA_VERSION}.",
            )
        )

    if receipt_status and receipt_status not in VALID_STATUSES:
        findings.append(
            Finding(
                "invalid-status",
                "error",
                f"Receipt status is not supported: {receipt_status}",
            )
        )
    if require_status and receipt_status != require_status:
        findings.append(
            Finding(
                "status-mismatch",
                "error",
                f"Receipt status is {receipt_status or 'missing'}; expected {require_status}.",
            )
        )

    evidence = receipt.get("evidence")
    if not isinstance(evidence, list):
        evidence = []
        findings.append(
            Finding("invalid-evidence", "error", "Receipt evidence must be a list.")
        )

    for item in evidence:
        if not isinstance(item, dict):
            findings.append(
                Finding("invalid-evidence", "error", "Evidence item is not an object.")
            )
            continue

        path_text = str(item.get("path") or "")
        expected_sha = str(item.get("sha256") or "")
        expected_size = item.get("size_bytes")
        if not path_text:
            findings.append(
                Finding("missing-path", "error", "Evidence item is missing a path.")
            )
            continue

        path = resolve_evidence_path(base_dir, path_text)
        if not path.exists():
            findings.append(
                Finding(
                    "missing-evidence",
                    "error",
                    f"Evidence file is missing: {path_text}",
                    path_text,
                )
            )
            continue
        if not path.is_file():
            findings.append(
                Finding(
                    "invalid-evidence-path",
                    "error",
                    f"Evidence path is not a file: {path_text}",
                    path_text,
                )
            )
            continue

        checked += 1
        actual_size = path.stat().st_size
        actual_sha = sha256_file(path)
        if expected_size != actual_size:
            findings.append(
                Finding(
                    "size-mismatch",
                    "error",
                    (
                        f"Evidence size changed for {path_text}: "
                        f"expected {expected_size}, got {actual_size}."
                    ),
                    path_text,
                )
            )
        if expected_sha != actual_sha:
            findings.append(
                Finding(
                    "hash-mismatch",
                    "error",
                    f"Evidence hash changed for {path_text}.",
                    path_text,
                )
            )

    if checked < min_evidence:
        findings.append(
            Finding(
                "insufficient-evidence",
                "error",
                (
                    f"Receipt verified {checked} evidence file(s); "
                    f"expected at least {min_evidence}."
                ),
            )
        )

    verdict = "passed" if not findings else "failed"
    return {
        "schema_version": "agent-command-receipt.verify.v1",
        "verdict": verdict,
        "receipt_command": receipt.get("command", ""),
        "receipt_status": receipt_status,
        "checked_evidence": checked,
        "requirements": {
            "required_status": require_status,
            "min_evidence": min_evidence,
        },
        "findings": [finding.as_dict() for finding in findings],
    }


def verification_to_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Agent Command Receipt Verification",
        "",
        f"Verdict: `{report.get('verdict', 'failed')}`",
        f"Receipt status: `{report.get('receipt_status', '')}`",
        f"Checked evidence files: `{report.get('checked_evidence', 0)}`",
        "",
        "## Command",
        "",
        "```sh",
        str(report.get("receipt_command", "")),
        "```",
    ]

    findings = report.get("findings") or []
    if findings:
        lines.extend(["", "## Findings", ""])
        for finding in findings:
            path = f" `{finding['path']}`" if finding.get("path") else ""
            lines.append(
                f"- {finding['severity']} `{finding['code']}`{path}: "
                f"{finding['message']}"
            )
    else:
        lines.extend(["", "## Findings", "", "- No evidence drift found."])

    return "\n".join(lines)


def write_payload(payload: str, output: str | None) -> None:
    if output:
        Path(output).write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)


def parse_receipt(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("receipt JSON must be an object")
    return data


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-command-receipt",
        description="Create and verify hashed command evidence receipts.",
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    create = subparsers.add_parser("create", help="create a command receipt")
    create.add_argument("--command", required=True, help="exact command being claimed")
    create.add_argument(
        "--status",
        required=True,
        choices=VALID_STATUSES,
        help="caller-provided command status",
    )
    create.add_argument("--exit-code", type=int, help="caller-provided exit code")
    create.add_argument("--cwd", default=".", help="working directory label to record")
    create.add_argument(
        "--base-dir",
        default=".",
        help="base directory used to resolve relative evidence paths",
    )
    create.add_argument(
        "--evidence",
        action="append",
        default=[],
        help="evidence file to hash; may be passed more than once",
    )
    create.add_argument(
        "--note",
        action="append",
        default=[],
        help="human note to include in the receipt; may be passed more than once",
    )
    create.add_argument(
        "--created-at",
        help="fixed creation timestamp; defaults to current UTC time",
    )
    create.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="receipt output format",
    )
    create.add_argument("--output", help="write output to this path")

    verify = subparsers.add_parser("verify", help="verify evidence hashes")
    verify.add_argument("receipt", help="JSON receipt path")
    verify.add_argument(
        "--base-dir",
        default=".",
        help="base directory used to resolve relative evidence paths",
    )
    verify.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
        help="verification output format",
    )
    verify.add_argument(
        "--require-status",
        choices=VALID_STATUSES,
        help="fail verification unless the receipt has this status",
    )
    verify.add_argument(
        "--min-evidence",
        type=int,
        default=0,
        help="fail verification unless at least this many evidence files verify",
    )
    verify.add_argument("--output", help="write output to this path")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.action == "create":
            exit_code = args.exit_code
            if exit_code is None and args.status == "pass":
                exit_code = 0
            receipt = build_receipt(
                command=args.command,
                status=args.status,
                exit_code=exit_code,
                cwd=args.cwd,
                created_at=args.created_at or utc_now(),
                notes=args.note,
                evidence_paths=args.evidence,
                base_dir=Path(args.base_dir),
            )
            if args.format == "json":
                payload = json.dumps(receipt, indent=2, sort_keys=True)
            else:
                payload = receipt_to_markdown(receipt)
            write_payload(payload, args.output)
            return 0

        if args.min_evidence < 0:
            raise ValueError("min-evidence must not be negative")
        receipt = parse_receipt(Path(args.receipt))
        report = verify_receipt(
            receipt,
            Path(args.base_dir),
            require_status=args.require_status,
            min_evidence=args.min_evidence,
        )
        if args.format == "json":
            payload = json.dumps(report, indent=2, sort_keys=True)
        else:
            payload = verification_to_markdown(report)
        write_payload(payload, args.output)
        return 0 if report["verdict"] == "passed" else 1
    except (FileNotFoundError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"agent-command-receipt: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

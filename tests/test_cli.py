from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from agent_command_receipt import cli


def run_cli(args: list[str]) -> tuple[int, str, str]:
    stdout = StringIO()
    stderr = StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = cli.main(args)
    return code, stdout.getvalue(), stderr.getvalue()


class CommandReceiptTests(unittest.TestCase):
    def test_create_json_hashes_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp) / "test-output.log"
            evidence.write_text("Ran 5 tests\nOK\n", encoding="utf-8")

            code, stdout, stderr = run_cli(
                [
                    "create",
                    "--command",
                    "make test",
                    "--status",
                    "pass",
                    "--exit-code",
                    "0",
                    "--created-at",
                    "2026-06-02T00:00:00Z",
                    "--base-dir",
                    tmp,
                    "--evidence",
                    "test-output.log",
                ]
            )

            self.assertEqual(code, 0, stderr)
            receipt = json.loads(stdout)
            self.assertEqual(receipt["schema_version"], cli.SCHEMA_VERSION)
            self.assertEqual(receipt["command"], "make test")
            self.assertEqual(receipt["status"], "pass")
            self.assertEqual(receipt["exit_code"], 0)
            self.assertEqual(receipt["evidence"][0]["path"], "test-output.log")
            self.assertEqual(receipt["evidence"][0]["size_bytes"], evidence.stat().st_size)
            self.assertEqual(len(receipt["evidence"][0]["sha256"]), 64)

    def test_verify_passes_for_unchanged_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp) / "lint.log"
            receipt_path = Path(tmp) / "receipt.json"
            evidence.write_text("lint ok\n", encoding="utf-8")

            code, _, stderr = run_cli(
                [
                    "create",
                    "--command",
                    "make lint",
                    "--status",
                    "pass",
                    "--created-at",
                    "2026-06-02T00:00:00Z",
                    "--base-dir",
                    tmp,
                    "--evidence",
                    "lint.log",
                    "--output",
                    str(receipt_path),
                ]
            )
            self.assertEqual(code, 0, stderr)

            code, stdout, stderr = run_cli(
                ["verify", str(receipt_path), "--base-dir", tmp]
            )

            self.assertEqual(code, 0, stderr)
            self.assertIn("Verdict: `passed`", stdout)
            self.assertIn("No evidence drift found", stdout)

    def test_verify_can_require_passing_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp) / "lint.log"
            receipt_path = Path(tmp) / "receipt.json"
            evidence.write_text("lint failed\n", encoding="utf-8")

            code, _, stderr = run_cli(
                [
                    "create",
                    "--command",
                    "make lint",
                    "--status",
                    "fail",
                    "--exit-code",
                    "1",
                    "--created-at",
                    "2026-06-02T00:00:00Z",
                    "--base-dir",
                    tmp,
                    "--evidence",
                    "lint.log",
                    "--output",
                    str(receipt_path),
                ]
            )
            self.assertEqual(code, 0, stderr)

            code, stdout, stderr = run_cli(
                [
                    "verify",
                    str(receipt_path),
                    "--base-dir",
                    tmp,
                    "--require-status",
                    "pass",
                    "--format",
                    "json",
                ]
            )

            self.assertEqual(code, 1, stderr)
            report = json.loads(stdout)
            self.assertEqual(report["receipt_status"], "fail")
            self.assertEqual(report["requirements"]["required_status"], "pass")
            self.assertEqual(report["findings"][0]["code"], "status-mismatch")

    def test_verify_can_require_minimum_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            receipt_path = Path(tmp) / "receipt.json"

            code, _, stderr = run_cli(
                [
                    "create",
                    "--command",
                    "make test",
                    "--status",
                    "pass",
                    "--created-at",
                    "2026-06-02T00:00:00Z",
                    "--base-dir",
                    tmp,
                    "--output",
                    str(receipt_path),
                ]
            )
            self.assertEqual(code, 0, stderr)

            code, stdout, stderr = run_cli(
                [
                    "verify",
                    str(receipt_path),
                    "--base-dir",
                    tmp,
                    "--min-evidence",
                    "1",
                ]
            )

            self.assertEqual(code, 1, stderr)
            self.assertIn("insufficient-evidence", stdout)
            self.assertIn("expected at least 1", stdout)

    def test_verify_fails_when_evidence_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp) / "build.log"
            receipt_path = Path(tmp) / "receipt.json"
            evidence.write_text("build ok\n", encoding="utf-8")

            code, _, stderr = run_cli(
                [
                    "create",
                    "--command",
                    "make build",
                    "--status",
                    "pass",
                    "--created-at",
                    "2026-06-02T00:00:00Z",
                    "--base-dir",
                    tmp,
                    "--evidence",
                    "build.log",
                    "--output",
                    str(receipt_path),
                ]
            )
            self.assertEqual(code, 0, stderr)

            evidence.write_text("build changed\n", encoding="utf-8")
            code, stdout, stderr = run_cli(
                ["verify", str(receipt_path), "--base-dir", tmp]
            )

            self.assertEqual(code, 1, stderr)
            self.assertIn("hash-mismatch", stdout)
            self.assertIn("size-mismatch", stdout)

    def test_create_markdown_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp) / "smoke.log"
            evidence.write_text("smoke ok\n", encoding="utf-8")

            code, stdout, stderr = run_cli(
                [
                    "create",
                    "--command",
                    "make smoke",
                    "--status",
                    "pass",
                    "--base-dir",
                    tmp,
                    "--evidence",
                    "smoke.log",
                    "--format",
                    "markdown",
                    "--note",
                    "Generated after local smoke run.",
                ]
            )

            self.assertEqual(code, 0, stderr)
            self.assertIn("# Agent Command Receipt", stdout)
            self.assertIn("make smoke", stdout)
            self.assertIn("smoke.log", stdout)
            self.assertIn("Generated after local smoke run.", stdout)

    def test_create_rejects_missing_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, stdout, stderr = run_cli(
                [
                    "create",
                    "--command",
                    "make test",
                    "--status",
                    "pass",
                    "--base-dir",
                    tmp,
                    "--evidence",
                    "missing.log",
                ]
            )

            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("evidence file not found", stderr)


if __name__ == "__main__":
    unittest.main()

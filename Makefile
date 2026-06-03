.PHONY: test lint build smoke

test:
	PYTHONPATH=src python3 -m unittest discover -s tests

lint:
	python3 -m py_compile src/agent_command_receipt/*.py tests/*.py

build:
	python3 -m compileall -q src tests

smoke:
	PYTHONPATH=src python3 -m agent_command_receipt create --command "make test" --status pass --exit-code 0 --created-at 2026-06-02T00:00:00Z --base-dir . --evidence README.md --format json --output /tmp/agent-command-receipt.json
	PYTHONPATH=src python3 -m agent_command_receipt verify /tmp/agent-command-receipt.json --base-dir . --require-status pass --min-evidence 1 >/tmp/agent-command-receipt-verify.md
	PYTHONPATH=src python3 -m agent_command_receipt verify examples/passing-receipt.json --require-status pass --min-evidence 1 >/tmp/agent-command-receipt-example.md
	PYTHONPATH=src python3 -m agent_command_receipt create --command "make lint" --status pass --exit-code 0 --created-at 2026-06-02T00:00:00Z --base-dir . --evidence README.md --format markdown >/tmp/agent-command-receipt.md

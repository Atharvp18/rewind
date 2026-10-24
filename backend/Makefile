PY ?= /Library/Frameworks/Python.framework/Versions/3.10/bin/python3

.PHONY: orchestrator product payment test

orchestrator:
	$(PY) -m agents.orchestrator_agent

product:
	$(PY) -m agents.product_agent

payment:
	$(PY) -m agents.payment_agent

test:
	$(PY) -m pytest -q tests

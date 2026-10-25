PY ?= /Library/Frameworks/Python.framework/Versions/3.10/bin/python3

.PHONY: orchestrator product payment history local test

# Each agent in its own terminal, connected to Agentverse through its mailbox.
orchestrator:
	$(PY) -m agents.orchestrator_agent

product:
	$(PY) -m agents.product_agent

payment:
	$(PY) -m agents.payment_agent

history:
	$(PY) -m agents.history_agent

# All agents in one process plus a scripted shopper. No Agentverse needed.
local:
	$(PY) scripts/local_chat.py

test:
	$(PY) -m pytest -q tests

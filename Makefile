.PHONY: setup test smoke release report docker-agent verify-env

PYTHON ?= python

setup:
	$(PYTHON) -m pip install -r requirements.txt

test:
	$(PYTHON) -m pytest -q

smoke:
	bash scripts/reproduce_all.sh --smoke

release:
	bash scripts/reproduce_all.sh --release --config configs/config.release.yaml

report:
	$(PYTHON) -m agentmem report --results-dir results

docker-agent:
	docker build -f docker/Dockerfile.agent-openeuler -t agentmem-openeuler-agent .

verify-env:
	$(PYTHON) scripts/verify_environment.py --output results/environment.json

# AgentMem Engineering Upgrade Plan

## Current Implemented Capabilities

- Agent runtime with multi-step loops, tool routing/execution, local deterministic test client, and OpenAI-compatible/vLLM client.
- Baseline, optimized, full-history, summary-memory, and event-sourced memory benchmark modes.
- Event log, Task State View projection, memory_delta parsing, artifact refs, tool result externalization, and stable prompt rendering.
- Agent-side `agent_meta` construction and OpenAI-compatible `extra_body.agent_meta` transmission.
- Benchmark scenarios for tool-heavy, long-session, multi-stage, branching, prefix-cache, ablation, cache-pressure, and ttl-priority.
- Best-effort cache stats and vLLM Prometheus metric readers.
- Existing tests for CLI, event memory, benchmark CSV generation, agent_meta client behavior, and cache experiment scaffolding.

## Discovered Problems

- `configs/config.yaml`, README, docs, and generated `results/report.md` contained machine-specific IPs, private absolute model paths, fixed proxy ports, and `EMPTY` API key examples without clear placeholder semantics.
- Runtime config loading did not expand `${ENV_NAME}` values, did not validate required URLs or positive numeric fields, and silently used defaults that can mask misconfiguration.
- Benchmark identity was locally generated in several places and did not consistently include experiment/run/trial/session/model/seed/git metadata across CSV, reports, events, and memory plans.
- Metrics used `-1` for unavailable values, causing missing GPU/KV/prefix-cache data to be mixed into means and reports.
- Negative count fields were not validated before summary/report generation; historical `results/report.md` showed negative extractor counts.
- Local `nvidia-smi` was treated as model GPU memory even when the model server can run remotely.
- `agent_meta` was sent by the client, but this repository does not contain a verified vLLM server patch proving priority/TTL enforcement or per-agent KV accounting.
- `scripts/run_all.sh` cleared global results before running, which is unsafe for reproducibility.
- openEuler documentation did not clearly distinguish userspace-container compatibility from native-host or full GPU deployment verification.
- Tracked legacy `results/` artifacts were generated files containing private local paths and obsolete `-1` unavailable sentinels; they must be removed from version control or replaced by sanitized experiment-scoped evidence.

## Files Modified Or Added In This Pass

- Configuration: `.env.example`, `configs/config.yaml`, `configs/config.example.yaml`, `configs/config.smoke.yaml`, `configs/config.release.yaml`, `configs/models/*.yaml`, `agentmem/config.py`, `agentmem/runtime/llm_factory.py`.
- Experiment identity and isolation: `agentmem/experiment.py`, `agentmem/benchmark.py`, `agentmem/runtime/agent.py`, `agentmem/vllm/agent_meta.py`, `agentmem/vllm/memory_plan.py`.
- Metrics and validation: `agentmem/metrics/metric_models.py`, `agentmem/metrics/server_metrics.py`, `agentmem/metrics/snapshot.py`, `agentmem/metrics/validation.py`, `agentmem/metrics/vllm_metrics.py`, `agentmem/metrics/gpu_monitor.py`, `agentmem/metrics/hardware.py`, `agentmem/metrics/summarizer.py`.
- Reproduction and deployment: `scripts/reproduce_all.sh`, `scripts/verify_environment.py`, `scripts/collect_environment.sh`, `scripts/verify_openeuler.sh`, `scripts/run_all.sh`, `docker/*`.
- vLLM integration audit/skeleton: `docs/vllm_integration_status.md`, `vllm_integration/*`.
- Tests: configuration, experiment identity, metric validation/statistics, fake metrics server, cache contamination, report constraints, openEuler environment detection, and manifest generation tests.
- Documentation and project metadata: README, deployment/openEuler docs, Makefile, CI, LICENSE, CHANGELOG, CONTRIBUTING, SECURITY.
- Result artifacts: old generated top-level results are removed from the working tree; `results/LEGACY_DATA_NOTE.md` documents the cleanup and `results/final-release-sanitized/` keeps commit-safe evidence.

## P0 Priority

- Remove hardcoded machine-specific config and add strict env-aware config validation.
- Generate and propagate reproducible experiment/run/trial/session IDs and fixed seeds.
- Replace `-1` unavailable metric semantics with explicit value/status/source/reason fields.
- Validate non-negative counters and exclude invalid trials from summaries.
- Collect model-server metrics from vLLM `/metrics` and `/v1/agentmem/cache_stats`; only use local `nvidia-smi` when explicitly configured.
- Audit vLLM server integration status and add a versioned integration skeleton without claiming unverified priority/TTL enforcement.
- Add openEuler agent container and environment collection scripts.
- Add `scripts/reproduce_all.sh` with smoke/release behavior, manifest/environment/config/raw/report outputs, and no global result deletion.

## P1 Priority

- Add model matrix configs and `--models` handling.
- Add `concurrent-agents` scenario with isolated agent/session/cache namespaces and timeout classification.
- Add protected fact fields, protected fact retention, conflict versioning, and evidence refill tests.
- Restructure generated reports so unavailable/invalid/estimated metrics are shown honestly and unsupported conclusions are not inferred.
- Extend default tests with fake OpenAI-compatible and fake metrics servers.

## P2 Priority

- Add Makefile, GitHub Actions, license/security/contribution docs, architecture diagram source, and capability matrix.
- Verify README commands and keep release instructions copy/pasteable.

## External Dependencies Not Verifiable In Current Environment

- No installed `vllm` Python package was detected.
- No separately writable vLLM source tree with a precise upstream commit was detected beyond this AgentMem repository path.
- No real remote model endpoint or GPU metrics endpoint was exercised in this environment.
- openEuler native host and full openEuler GPU deployment cannot be marked verified here; only scripts/container files can be provided.

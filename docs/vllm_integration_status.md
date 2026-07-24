# vLLM Integration Status

Generated for this repository upgrade.

## Detection Result

- Repository-local vLLM source: not detected. `agentmem/vllm/` is AgentMem client-side integration code, not upstream vLLM server source.
- Parent/sibling vLLM source: no distinct writable upstream vLLM source tree with a verified commit was detected from this workspace scan.
- Python environment vLLM package: not installed in the current Python 3.11 environment.
- Installed vLLM version/path/commit: unavailable.
- Custom `/v1/agentmem/cache_stats` source: no verified server implementation exists in this repository. Client code can request this endpoint, but cannot prove server-side parsing, KV ownership, priority, or TTL enforcement.

## Verified Capabilities

- Client can build `extra_body.agent_meta` and send it through OpenAI-compatible requests.
- AgentMem records memory plans with run/session/context/segment/priority/TTL metadata.
- AgentMem can collect model-server metrics from `/metrics` and `/v1/agentmem/cache_stats` when those endpoints exist.

## Not Verified

- vLLM server parsing of `extra_body.agent_meta`.
- Per-agent/per-session KV cache accounting inside vLLM.
- Priority or TTL enforcement affecting real vLLM eviction policy.
- Branch release or protected-prefix enforcement in vLLM.

These items are marked `server_patch_required`. Reports must not claim they are implemented unless a compatible vLLM patch is applied and verified.

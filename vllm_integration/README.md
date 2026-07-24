# AgentMem vLLM Integration

This directory contains a versioned integration skeleton for adding AgentMem-aware request metadata and cache accounting to upstream vLLM. It is intentionally separate from the AgentMem client package.

Current status: `server_patch_required`. The current workspace does not contain a verified upstream vLLM source tree or installed vLLM package, so no real server patch is claimed.

Goals for a compatible patch:

1. Parse OpenAI-compatible `extra_body.agent_meta`.
2. Validate metadata length and allowed enum values.
3. Attach metadata to internal request objects without changing standard requests.
4. Account cache observations by experiment/run/agent/session/branch/namespace/segment.
5. Expose `/v1/agentmem/cache_stats` with real internal cache data and explicit unavailable fields.
6. Keep priority/TTL enforcement disabled or experimental unless stable hooks exist.

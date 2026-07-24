# Compatibility

No vLLM version is patched by default in this repository.

## Required Binding Before Patch

A real patch must record:

- vLLM package version.
- vLLM git commit.
- Patch file checksum.
- Detection logic proving the target files match expected preimages.
- Re-apply detection.
- Rollback instructions.

## Current Recommendation

Implement metadata parsing and cache ownership accounting first. Priority/TTL eviction enforcement should remain experimental until the target vLLM version exposes stable hooks for KV block lifecycle and eviction policy.

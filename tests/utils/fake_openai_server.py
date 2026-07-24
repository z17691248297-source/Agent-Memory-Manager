from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeAgentMemServer(BaseHTTPRequestHandler):
    server_version = "FakeAgentMemOpenAI/0.1"
    protocol_version = "HTTP/1.1"
    request_count = 0
    prefix_hits = 0
    prefix_misses = 0

    def log_message(self, fmt, *args):
        return

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, text: str, status: int = 200) -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "text/plain; version=0.0.4")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        cls = self.__class__
        if self.path.endswith("/v1/models") or self.path == "/v1/models":
            self._send_json({"object": "list", "data": [{"id": "fake-agentmem-model", "object": "model"}]})
            return
        if self.path == "/metrics":
            text = "\n".join([
                "# HELP vllm:gpu_cache_usage_perc Fake vLLM metric for tests",
                "vllm:gpu_cache_usage_perc 0.25",
                f"vllm:prefix_cache_hits_total {cls.prefix_hits}",
                f"vllm:prefix_cache_misses_total {cls.prefix_misses}",
                f"vllm:cached_prompt_tokens_total {cls.prefix_hits * 16}",
                "vllm:num_requests_running 0",
            ])
            self._send_text(text)
            return
        if self.path == "/v1/agentmem/cache_stats":
            total = cls.prefix_hits + cls.prefix_misses
            self._send_json({
                "version": "fake-test-server",
                "scope": "global",
                "kv_cache_usage": 0.25,
                "kv_cache_used_blocks": 8 + cls.request_count,
                "kv_cache_total_blocks": 128,
                "prefix_cache_hits": cls.prefix_hits,
                "prefix_cache_misses": cls.prefix_misses,
                "prefix_cache_hit_rate": (cls.prefix_hits / total) if total else None,
                "cached_prompt_tokens": cls.prefix_hits * 16,
                "evicted_blocks": 0,
                "active_requests": 0,
                "waiting_requests": 0,
                "running_requests": 0,
                "segments": {"shared_prefix": {"blocks": cls.prefix_hits}, "tool_result": {"blocks": 1}},
            })
            return
        self._send_json({"error": "not_found", "path": self.path}, status=404)

    def do_POST(self):
        length = int(self.headers.get("content-length", "0") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {}
        self.__class__.request_count += 1
        meta = dict(payload.get("extra_body", {}).get("agent_meta", {}) or {})
        if meta.get("segment_type") == "shared_prefix":
            self.__class__.prefix_hits += 1
        else:
            self.__class__.prefix_misses += 1
        if self.path.endswith("/chat/completions"):
            content = json.dumps({
                "assistant_response": "fake server response: OOM timeout KV cache allocation failed; use tool result externalization and result_id evidence",
                "next_action": None,
                "memory_delta": {"facts": [{"content": "fake server smoke response", "source": "fake_server", "confidence": 1.0, "importance": 0.5}]},
            }, ensure_ascii=False)
            prompt_tokens = max(1, len(json.dumps(payload.get("messages", []), ensure_ascii=False)) // 4)
            completion_tokens = max(1, len(content) // 4)
            self._send_json({
                "id": f"chatcmpl-fake-{int(time.time()*1000)}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": payload.get("model", "fake-agentmem-model"),
                "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "total_tokens": prompt_tokens + completion_tokens},
            })
            return
        self._send_json({"error": "not_found", "path": self.path}, status=404)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18080)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), FakeAgentMemServer)
    print(f"fake AgentMem OpenAI server listening on http://{args.host}:{args.port}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

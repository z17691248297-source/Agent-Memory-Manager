"""
玩具版 vLLM 调度器。

这不是真实 vLLM 源码，而是一个可以运行的小模型，用来理解下面几个核心概念：

1. 请求进入系统后先等待调度。
2. prefill 阶段消耗 prompt token，并分配 KV cache block。
3. decode 阶段每个 step 为已完成 prefill 的请求生成新 token。
4. scheduler 同时受 token budget 和可用 KV block 限制。
5. 请求完成后释放自己的 KV cache block。

运行：
    python3 experiments/toy_vllm_scheduler.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import ceil


BLOCK_SIZE = 4
TOTAL_KV_BLOCKS = 10
STEP_TOKEN_BUDGET = 8


class RequestState(str, Enum):
    WAITING = "waiting"
    RUNNING = "running"
    FINISHED = "finished"


@dataclass
class Request:
    request_id: str
    prompt_tokens: int
    max_new_tokens: int
    state: RequestState = RequestState.WAITING
    computed_prompt_tokens: int = 0
    generated_tokens: int = 0
    kv_blocks: list[int] = field(default_factory=list)

    @property
    def total_tokens_in_cache(self) -> int:
        return self.computed_prompt_tokens + self.generated_tokens

    @property
    def required_blocks(self) -> int:
        if self.total_tokens_in_cache == 0:
            return 0
        return ceil(self.total_tokens_in_cache / BLOCK_SIZE)

    @property
    def prefill_done(self) -> bool:
        return self.computed_prompt_tokens >= self.prompt_tokens

    @property
    def finished(self) -> bool:
        return self.generated_tokens >= self.max_new_tokens


class KVCacheManager:
    def __init__(self, total_blocks: int) -> None:
        self.total_blocks = total_blocks
        self.free_blocks = list(range(total_blocks))

    def ensure_blocks(self, request: Request, tokens_after_step: int) -> bool:
        """确保请求增长到新长度后仍有足够 KV block。"""
        required_blocks = ceil(tokens_after_step / BLOCK_SIZE)
        missing = required_blocks - len(request.kv_blocks)

        if missing <= 0:
            return True

        if missing > len(self.free_blocks):
            return False

        for _ in range(missing):
            request.kv_blocks.append(self.free_blocks.pop(0))
        return True

    def release(self, request: Request) -> None:
        self.free_blocks.extend(request.kv_blocks)
        self.free_blocks.sort()
        request.kv_blocks.clear()

    @property
    def used_blocks(self) -> int:
        return self.total_blocks - len(self.free_blocks)


class ToyScheduler:
    def __init__(self, requests: list[Request]) -> None:
        self.waiting = requests[:]
        self.running: list[Request] = []
        self.finished: list[Request] = []
        self.kv_cache = KVCacheManager(TOTAL_KV_BLOCKS)
        self.step_id = 0

    def step(self) -> None:
        self.step_id += 1
        budget = STEP_TOKEN_BUDGET
        events: list[str] = []

        # 只要 token budget 和 KV block 还够，就把 waiting 请求接纳进 running。
        # 真实 vLLM 里这里会更复杂，还会考虑优先级、抢占、chunked prefill 等。
        for request in self.waiting[:]:
            if budget <= 0:
                break

            prefill_chunk = min(
                request.prompt_tokens - request.computed_prompt_tokens,
                budget,
            )
            tokens_after_step = request.total_tokens_in_cache + prefill_chunk

            if not self.kv_cache.ensure_blocks(request, tokens_after_step):
                events.append(f"{request.request_id}: wait, no KV block")
                continue

            request.state = RequestState.RUNNING
            request.computed_prompt_tokens += prefill_chunk
            budget -= prefill_chunk
            self.waiting.remove(request)
            self.running.append(request)
            events.append(f"{request.request_id}: prefill {prefill_chunk}")

        # 对还没完成 prefill 的 running 请求，继续处理 prompt。
        for request in self.running[:]:
            if budget <= 0:
                break
            if request.prefill_done:
                continue

            prefill_chunk = min(
                request.prompt_tokens - request.computed_prompt_tokens,
                budget,
            )
            tokens_after_step = request.total_tokens_in_cache + prefill_chunk

            if not self.kv_cache.ensure_blocks(request, tokens_after_step):
                events.append(f"{request.request_id}: pause prefill, no KV block")
                continue

            request.computed_prompt_tokens += prefill_chunk
            budget -= prefill_chunk
            events.append(f"{request.request_id}: prefill+ {prefill_chunk}")

        # decode：已完成 prefill 的请求，每轮最多生成一个 token。
        for request in self.running[:]:
            if budget <= 0:
                break
            if not request.prefill_done:
                continue
            if request.finished:
                continue

            tokens_after_step = request.total_tokens_in_cache + 1
            if not self.kv_cache.ensure_blocks(request, tokens_after_step):
                events.append(f"{request.request_id}: pause decode, no KV block")
                continue

            request.generated_tokens += 1
            budget -= 1
            events.append(f"{request.request_id}: decode 1")

            if request.finished:
                request.state = RequestState.FINISHED
                self.running.remove(request)
                self.finished.append(request)
                self.kv_cache.release(request)
                events.append(f"{request.request_id}: finished, release KV")

        self.print_step(events, budget)

    def done(self) -> bool:
        return not self.waiting and not self.running

    def print_step(self, events: list[str], remaining_budget: int) -> None:
        running_state = [
            (
                request.request_id,
                request.computed_prompt_tokens,
                request.generated_tokens,
                request.kv_blocks,
            )
            for request in self.running
        ]

        print(f"\nstep {self.step_id}")
        print("events:", "; ".join(events) if events else "none")
        print("remaining_token_budget:", remaining_budget)
        print("waiting:", [request.request_id for request in self.waiting])
        print("running:", running_state)
        print("finished:", [request.request_id for request in self.finished])
        print(
            "kv_blocks:",
            f"used={self.kv_cache.used_blocks}",
            f"free={len(self.kv_cache.free_blocks)}",
        )


def main() -> None:
    requests = [
        Request("req_A", prompt_tokens=10, max_new_tokens=4),
        Request("req_B", prompt_tokens=5, max_new_tokens=3),
        Request("req_C", prompt_tokens=12, max_new_tokens=2),
    ]

    scheduler = ToyScheduler(requests)
    while not scheduler.done():
        scheduler.step()


if __name__ == "__main__":
    main()

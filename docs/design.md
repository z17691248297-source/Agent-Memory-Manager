# AgentMem Design

AgentMem 是通用轻量 Agent Runtime + Memory Manager。它用于复现和评估智能体工作流中的上下文膨胀问题，并将 Event-Sourced Memory 作为 Agent 侧内存管理优化机制。

项目覆盖多轮会话、工具调用、分支推理、稳定 prefix、工具结果外置、Agent-aware `agent_meta` 传递和 vLLM cache_stats 观测。

## Architecture

核心模块：

- `AgentRuntime`：执行多轮输入、轻量 next_action loop、工具调用、LLM 调用和指标采集。
- `ToolExecutor` + `ToolResultStore`：执行工具，保存 raw output、chunk、index 和 artifact metadata。
- `EventSourcedMemoryAdapter`：optimized memory backend，记录事件并投影 Task State View。
- `MemoryDeltaParser`：解析模型输出协议，非法 JSON fallback 为普通 assistant response。
- `MemoryProjector` + `StateReducer`：将 memory_delta、tool_result artifact 和用户上下文合并为通用状态视图。
- `MemoryViewRenderer`：稳定渲染 Task State View、Artifact References、Recent Context 和 Current Query。
- `Evaluator`：读取 benchmark task 的显式规则，评估 success、score 和 failure reason。

## Baseline

baseline 用于复现未优化 Agent 的上下文膨胀：

- 工具 raw output 直接进入 prompt。
- 历史消息完整保留。
- 工具说明和动态上下文会反复注入。
- 分支推理按复制完整 shared context 估算成本。

baseline 是正式对照组。它的任务不是“更差实现”，而是代表常见的线性历史拼接方式。

## Optimized: Event-Sourced Agent Memory

AgentMem optimized 的核心是 Event-Sourced Agent Memory。

### Event Log

Agent 执行过程记录为事件：

- `user_message`
- `tool_call`
- `tool_result`
- `assistant_response`
- `memory_delta`
- `final_answer`
- `metric`

事件写入 `results/event_log/<run_id>.jsonl`，每行一个 JSON event。快照写入 `results/event_memory_snapshots/`，用于从最近状态恢复。

### Memory Delta

模型在同一次响应中输出：

```json
{
  "assistant_response": "...",
  "next_action": null,
  "memory_delta": {
    "goals": [],
    "constraints": [],
    "facts": [],
    "decisions": [],
    "open_questions": [],
    "todos": [],
    "artifact_refs": [],
    "tool_summaries": [],
    "warnings": []
  }
}
```

`memory_delta` 是 Agent 主动写入内存的协议。Memory 核心不使用第二个 LLM extractor，也不从自然语言中硬编码抽取 benchmark 关键词。

### Task State View

Memory Manager 将事件流投影为通用 Task State View：

- goals
- constraints
- facts
- decisions
- open_questions
- todos
- artifact_refs
- tool_summaries
- warnings

Reducer 只做通用合并、去重和容量控制：按 confidence、importance 和 recency 保留 top-k，不写死 OOM、timeout、KV cache、baseline、optimized 等任务关键词。

### Artifact References

所有工具结果统一 artifact 化：

```json
{
  "result_id": "...",
  "tool_name": "...",
  "summary": "...",
  "artifacts": [
    {
      "artifact_type": "text|table|log|json|code",
      "path": "...",
      "token_count": 0,
      "description": "..."
    }
  ],
  "metadata": {}
}
```

raw output 保存到 `results/tool_store/raw/`。Prompt 只注入 summary、result_id 和 artifact metadata，不渲染 raw content。`tools.max_output_chars` 只限制 prompt/display 注入，不影响 raw store 保存完整工具结果；只有显式配置 `raw_store_max_mb` 时才会限制 raw store。

### Stable Renderer

Renderer 使用稳定段落顺序：

1. Task State
2. Goals
3. Constraints
4. Facts
5. Decisions
6. Open Questions
7. Todos
8. Artifact References
9. Recent Context
10. Current Query

稳定结构让 system/project/tool/state 的前缀尽量保持一致，为 vLLM prefix cache 复用创造条件。

## Multi-step next_action Loop

optimized Runtime 支持轻量多步 Agent loop：

1. 构造 prompt。
2. 调用 LLM。
3. 解析 `assistant_response`、`next_action`、`memory_delta`。
4. 如果 `next_action.type == "tool_call"`，执行工具、保存 artifact、写入 tool_call/tool_result event，再进入下一 step。
5. 如果 `next_action` 为空或 `type == "final"`，返回 final answer。
6. 达到 `agent.max_steps` 后强制返回最新 assistant response。

默认配置：

```yaml
agent:
  max_steps: 3
  enable_next_action_loop: true
```

这个 loop 覆盖 planning、tool_calling、reflection、final_answer 等 benchmark 所需流程，但不实现完整 AutoGPT 的长期自主规划。

## Benchmark Boundary

Benchmark evaluator 可以是任务特定的。例如 task 文件可以要求答案包含某些 required facts，tool-heavy 可以检查日志相关事实，multi-stage 可以检查表格指标和优化建议。

这些任务关键词只允许出现在：

- `benchmarks/tasks/*.jsonl`
- evaluator
- 工具内部，例如 `log_analyzer`
- 测试数据

Memory 核心只理解通用 memory_delta 和 artifact_refs。

## Report Boundary

Report 会说明已配置模型 backend 的结果，包括 Qwen/MiniCPM 等开源模型服务的 latency、TTFT、tokens_per_second、peak_gpu_memory_mb 和 prefix cache metrics。

如果 `nvidia-smi` 或 vLLM `/metrics` 不可用，相关字段写为 `-1`，benchmark 不崩溃。

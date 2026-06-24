# AgentMem Design

AgentMem 定位为面向智能体推理的内存优化 Benchmark 系统。系统只实现 Agent 上下文层的内存管理，不修改 vLLM CUDA kernel，也不声称实现底层 KV block sharing。

## 轻量 Agent Runtime

`AgentRuntime` 的执行链路是：

1. 接收用户输入。
2. 在 `tool_calling` 阶段根据规则路由工具。
3. 执行安全工具并保存 `ToolResult`。
4. 由 memory backend 构造 prompt。
5. 调用 mock、vLLM 或 OpenAI-compatible backend。
6. 返回回答和 token、latency、TTFT、tool token 等指标。

这个 runtime 是 benchmark harness，不是完整 AutoGPT。它保留多轮、工具调用和分支实验所需的最小能力。

## Evaluator

主 benchmark 从 `benchmarks/tasks/` 读取固定 JSONL 任务。每条任务可以声明：

- `expected_tools`
- `answer_keywords`
- `expected_stages`
- `min_metrics`
- `max_metrics`

`agentmem.evaluation` 根据这些显式规则输出 `success`、`score` 和 `failure_reason`。runtime 只提供结构性执行状态，不把“完成一次调用”直接等同于任务成功。

## BaselineMemory

`BaselineMemory` 用作对照组：

- 所有工具完整 skill 文档进入 prompt。
- 工具 raw output 全文进入 prompt。
- 历史消息完整保留。
- 不做历史摘要、工具外置或 lazy loading。

它用于复现智能体推理中最直接的上下文膨胀。

## OptimizedMemory

`OptimizedMemory` 实现 AgentMem 的优化路径：

- 稳定 prompt 前缀。
- 工具 brief 默认注入。
- 命中工具后再加载对应 skill。
- 工具 raw output 外置。
- 旧历史压缩成 summary。

这些策略共同减少输入 token，降低 prefill 工作量，并间接降低 KV Cache 增长压力。

## Stable Prefix

optimized prompt 使用固定段落顺序：

1. `[system]`
2. `[project_rules]`
3. `[tool_briefs]`
4. `[loaded_skills]`
5. `[history_summary]`
6. `[recent_dialogue]`
7. `[tool_summaries]`

system、project rules 和 tool brief 的顺序稳定；动态历史、工具摘要和当前问题放在后部。prefix-cache benchmark 会对比 baseline 的动态前缀和 optimized 的稳定前缀。

## Tool Result Externalization

baseline 会把工具 raw output 全文放回 prompt。对于日志、文件和 repo scan，这会快速放大 prompt tokens。

optimized 会把 raw output 写入：

- `results/tool_store/raw/`
- `results/tool_store/index/`
- `results/tool_store/chunks/`

prompt 中只保留：

- `tool_name`
- `result_id`
- `raw_token_len`
- `summary_token_len`
- `summary`

benchmark 记录 `raw_tool_tokens`、`injected_tool_tokens` 和 `tool_compression_ratio`。

## Skill Lazy Loading

baseline 会注入所有工具完整说明。

optimized 默认只注入工具 brief 列表。工具路由命中特定工具后，只加载该工具的 `SKILL.md`。benchmark 记录：

- `tool_brief_tokens`
- `loaded_skill_tokens`

## History Summary

baseline 完整保留历史。

optimized 根据 `memory.recent_rounds` 保留最近几轮完整消息，更早历史由 `ContextCompressor` 压缩成 summary。long-session benchmark 记录：

- `history_tokens`
- `summary_tokens`
- `recent_turns`

## Branch Context Sharing

`BranchManager` 在 Agent 上下文层实现 shared context + delta 的 Copy-on-Write 模型。

baseline 估算每个分支复制完整 shared context 的 token 成本。optimized 只保存一份 shared context，每个分支保存自己的 delta。branching benchmark 记录：

- `shared_context_tokens`
- `branch_delta_tokens`
- `duplicated_context_tokens`
- `optimized_context_tokens`
- `branch_saving_ratio`

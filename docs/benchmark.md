# Benchmark

AgentMem benchmark 的目标是标准化复现智能体推理中的上下文膨胀问题，并对比 baseline 与 optimized 两种上下文管理策略。

## 命令

```bash
python -m agentmem benchmark --scenario tool-heavy --backend mock
python -m agentmem benchmark --scenario long-session --backend mock
python -m agentmem benchmark --scenario multi-stage --backend mock
python -m agentmem benchmark --scenario branching --backend mock
python -m agentmem benchmark --scenario prefix-cache --backend mock
python -m agentmem benchmark --scenario ablation --backend mock
python -m agentmem benchmark --all
python -m agentmem report
```

通用参数：

- `--mode baseline|optimized|both`
- `--backend mock|vllm|openai_compatible`
- `--repeat N`
- `--output results/`
- `--config configs/config.yaml`

## 固定任务与评估

主 benchmark 从 `benchmarks/tasks/` 读取固定 JSONL 任务：

- `tool_heavy.jsonl`
- `long_session.jsonl`
- `multi_stage.jsonl`
- `branching.jsonl`

每条任务声明 evaluator 条件，例如 `expected_tools`、`answer_keywords`、`expected_stages`、`min_metrics`。benchmark 不把流程可执行直接当作成功，CSV 中的 `success`、`score` 和 `failure_reason` 由 evaluator 生成。

各主场景统一输出以下基础字段：

- `scenario`
- `task_id`
- `workload_file`
- `mode`
- `backend`
- `prompt_tokens`
- `output_tokens`
- `total_tokens`
- `latency`
- `ttft`
- `peak_gpu_memory_mb`
- `success`
- `score`

## tool-heavy

目的：复现大规模工具输出导致 prompt tokens 和 KV Cache 压力膨胀。

baseline：

- `log_analyzer`、`file_reader` 等工具 raw output 全文进入 prompt。
- 所有工具完整说明进入 prompt。

optimized：

- raw output 保存到 `results/tool_store/`。
- prompt 只注入 summary、result_id 和 token 统计。
- 工具说明默认只注入 brief，命中后加载 skill。

输出：

- `results/tool_heavy_baseline.csv`
- `results/tool_heavy_optimized.csv`

核心指标：

- `prompt_tokens`
- `raw_tool_tokens`
- `injected_tool_tokens`
- `tool_compression_ratio`
- `tool_brief_tokens`
- `loaded_skill_tokens`
- `latency`
- `ttft`
- `peak_gpu_memory_mb`
- `success`
- `score`

## long-session

目的：复现多轮长生命周期会话导致历史上下文持续增长。

baseline 完整保留历史。optimized 保留最近 `recent_rounds` 轮，更早历史压缩成 summary。

输出：

- `results/long_session_baseline.csv`
- `results/long_session_optimized.csv`

核心指标：

- `round`
- `prompt_tokens`
- `history_tokens`
- `summary_tokens`
- `recent_turns`
- `latency`
- `ttft`
- `success`
- `score`

## multi-stage

目的：覆盖 planning -> tool_calling -> reflection -> final_answer 的多阶段智能体流程。

输出：

- `results/multi_stage_baseline.csv`
- `results/multi_stage_optimized.csv`

核心指标：

- `step`
- `stage`
- `completed_stages`
- `prompt_tokens`
- `raw_tool_tokens`
- `injected_tool_tokens`
- `history_tokens`
- `summary_tokens`
- `success`
- `score`

## branching

目的：复现分支推理中公共上下文重复复制，并生成多个方案文本供 evaluator 检查。

baseline 估算每个 branch 复制完整 shared context。optimized 只保存一份 shared context，每个 branch 保存 delta。

输出：

- `results/branching_baseline.csv`
- `results/branching_optimized.csv`
- `results/branch_benchmark.csv`

核心指标：

- `branch_count`
- `shared_context_tokens`
- `branch_delta_tokens`
- `duplicated_context_tokens`
- `optimized_context_tokens`
- `branch_saving_ratio`
- `branch_answer_tokens`
- `success`
- `score`

## prefix-cache

目的：验证稳定 prompt prefix 对 vLLM prefix cache、prefill 和 TTFT 的影响。

baseline：

- 动态字段放在 prompt 前部。
- 工具顺序随机。
- 每轮 prefix hash 不稳定。

optimized：

- system、project rules、tool brief 固定顺序。
- 动态 history summary 和 current query 后置。
- prefix hash 跨轮保持稳定。

输出：

- `results/prefix_cache_baseline.csv`
- `results/prefix_cache_optimized.csv`
- `results/vllm_benchmark.csv`，仅 vLLM backend 生成。

核心指标：

- `stable_prefix_hash`
- `stable_prefix_tokens`
- `prompt_tokens`
- `latency`
- `ttft`
- `prefix_cache_hit_rate`
- `cached_prompt_tokens`
- `kv_cache_usage`
- `success`
- `score`

## ablation

目的：对比单项优化的贡献。

变体：

1. `baseline`
2. `stable_prefix_only`
3. `skill_lazy_loading_only`
4. `tool_externalization_only`
5. `history_summary_only`
6. `full_optimized`

输出：

- `results/ablation.csv`

核心指标：

- `variant`
- `prompt_tokens`
- `latency`
- `raw_tool_tokens`
- `injected_tool_tokens`
- `tool_compression_ratio`
- `history_tokens`
- `summary_tokens`
- `loaded_skill_tokens`
- `unique_prefix_hashes`
- `prefix_reuse_score`
- `success`
- `score`

`stable_prefix_only` 会单独体现 prefix hash 稳定性；`tool_externalization_only`、`history_summary_only`、`skill_lazy_loading_only` 分别体现工具注入、历史 token 和加载 skill token 的变化。

## 报告

```bash
python -m agentmem report
```

报告生成：

- `results/summary.csv`
- `results/report.md`

`report.md` 包含项目目标、实验设置、固定 workload、硬件环境、success/score、各场景结果、ablation 和自动结论。

旧 `benchmarks/run_*.py` 脚本保留为 legacy 调试入口；正式 benchmark 以 `python -m agentmem benchmark` 为准。

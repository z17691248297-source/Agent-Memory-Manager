# Benchmark

AgentMem benchmark 用固定任务集评估 baseline 与 optimized Agent 内存路径。目标是在相同硬件配置、相同模型服务、相同 workload 下比较 prompt tokens、质量指标和 vLLM 真实推理指标。

Benchmark 覆盖工具密集、长会话、多阶段、分支、prefix-cache、ablation、cache-pressure 和 ttl-priority 场景，用于展示 AgentMem 在上下文构造和 vLLM Agent-aware cache 管理观测上的效果。

## Backend

Benchmark 使用 `configs/config.yaml` 中配置的模型 backend。当前正式路径是 vLLM OpenAI-compatible API，可连接 Qwen、MiniCPM 等开源模型，并支持 streaming TTFT 和 best-effort `/metrics` 采集。

## Commands

```bash
python -m agentmem benchmark --scenario tool-heavy
python -m agentmem benchmark --scenario long-session
python -m agentmem benchmark --scenario multi-stage
python -m agentmem benchmark --scenario branching
python -m agentmem benchmark --scenario prefix-cache
python -m agentmem report
```

全部场景：

```bash
bash scripts/run_all.sh
```

正式实验前先备份并重建结果目录，避免新旧结果混在一起：

```bash
mv results results_backup_$(date +%Y%m%d_%H%M%S)
mkdir results
```

通用参数：

- `--mode baseline|optimized|both|full_history|summary_memory|event_sourced_memory`
- `--backend vllm|openai_compatible`
- `--repeat N`
- `--output results/`
- `--config configs/config.yaml`

## Configuration

Benchmark 从 `configs/config.yaml` 读取：

- `llm.backend`
- `llm.model`
- `llm.base_url`
- `llm.temperature`
- `llm.max_tokens`
- `llm.timeout`
- `extractor.enabled`
- `extractor.backend`
- `extractor.base_url`
- `extractor.model`
- `vllm.metrics_url`

vLLM backend 会启用 streaming 以测量 TTFT。如果连接失败，CLI 输出：

```text
vLLM backend is unavailable. Please check llm.base_url in configs/config.yaml.
```

不会输出难懂 traceback。

## Output Fields

主 scenario CSV 至少记录：

- `scenario`
- `mode` / `memory_mode`
- `backend`
- `model`
- `round`
- `stage`
- `prompt_tokens`
- `output_tokens`
- `total_tokens`
- `latency`
- `ttft`
- `tokens_per_second`
- `peak_gpu_memory_mb`
- `success`
- `score`

long-session 和 multi-stage 额外记录：

- `full_history_tokens`
- `summary_tokens`
- `state_view_tokens`
- `event_count`
- `memory_delta_count`
- `fact_count`
- `decision_count`
- `artifact_ref_count`
- `early_fact_retention`

prefix-cache 额外记录：

- `prefix_cache_hit_rate`
- `cached_prompt_tokens`
- `kv_cache_usage`

如果 `nvidia-smi` 不可用，`peak_gpu_memory_mb` 为 `-1`。如果 vLLM `/metrics` 不可用，prefix cache 字段为 `-1`。

## Scenarios

### tool-heavy

覆盖工具调用和工具结果外置。baseline 注入 raw output，optimized 保存 artifact 并只渲染 summary/result_id/artifact metadata。

当前 `tool-heavy` 使用 16K 目标 workload：从原始 3000 行日志中保留 required_facts 命中行、前后 3 行上下文，并采样普通日志作为 filler。scenario 名仍是 `tool-heavy`，没有新增 `tool-heavy-16k`。

如果主模型服务以 `--max-model-len 4096` 启动，baseline 超上下文属于部署限制，不应被解释为 16K 实验已通过。16K tool-heavy 需要主 Agent 的 8000 服务支持 16K 或更高上下文。

输出：

- `results/tool_heavy_baseline.csv`
- `results/tool_heavy_optimized.csv`

### long-session

覆盖长生命周期多轮会话。对比：

- `full_history`
- `summary_memory`
- `event_sourced_memory`

同时写出用户口径文件：

- `results/long_session_baseline.csv`
- `results/long_session_optimized.csv`

其中 optimized 对应 event-sourced memory。

### multi-stage

覆盖 planning -> tool_calling -> reflection -> final_answer。optimized 使用多步 next_action loop，在 tool_calling 阶段允许模型触发工具调用、写入 memory_delta、再进入下一 step。

输出：

- `results/multi_stage_full_history.csv`
- `results/multi_stage_summary_memory.csv`
- `results/multi_stage_event_sourced_memory.csv`
- `results/multi_stage_baseline.csv`
- `results/multi_stage_optimized.csv`

### branching

覆盖分支推理。baseline 按每个分支复制 shared context 估算成本，optimized 按 shared context + branch delta 估算 Agent 上下文层节省。

输出：

- `results/branching_baseline.csv`
- `results/branching_optimized.csv`
- `results/branch_benchmark.csv`

### prefix-cache

覆盖稳定 prompt prefix。vLLM 会真实调用模型并 best-effort 读取 `/metrics`。

输出：

- `results/prefix_cache_baseline.csv`
- `results/prefix_cache_optimized.csv`

### vLLM aggregate

运行 vLLM scenario 后会额外生成：

- `results/vllm_benchmark.csv`

该文件聚合各 scenario 中 backend 为 `vllm` 的行，便于单独查看真实模型性能。

## Evaluation

Benchmark task 位于：

- `benchmarks/tasks/tool_heavy.jsonl`
- `benchmarks/tasks/long_session.jsonl`
- `benchmarks/tasks/multi_stage.jsonl`
- `benchmarks/tasks/branching.jsonl`

每条 task 可以声明 `required_facts`、`answer_keywords`、`expected_tools`、`expected_stages`、`min_metrics` 和 `max_metrics`。Evaluator 根据这些显式规则输出 `success`、`score`、`failure_reason`。

Memory 核心不写死 benchmark 关键词。任务特定关键词只属于 task/evaluator/tool/test 数据。

## Report

```bash
python -m agentmem report
```

生成：

- `results/summary.csv`
- `results/report.md`

报告包含：

- 项目目标
- 系统架构
- Event-Sourced Memory 机制说明
- extractor backend/model/base_url
- client OS / client environment / model server OS
- Benchmark 数据和任务说明
- baseline vs optimized 对比
- full_history / summary_memory / event_sourced_memory 对比
- 已配置模型 backend 结果
- success rate / score
- 指标说明

# AgentMem

AgentMem 是一个面向智能体推理过程的轻量 Agent Runtime + Memory Manager，并提供可复现 Benchmark 来评估优化前后的上下文、质量和真实性能指标。

项目实现了典型智能体工作流所需的多轮会话、工具调用、分支推理、Event-Sourced Memory、Agent-aware `agent_meta` 传递和 vLLM cache_stats 观测能力。

核心目标是：在相同硬件配置和相同开源模型服务下，对比 baseline 和 optimized Agent 内存路径，评估 prompt tokens、latency、TTFT、吞吐、显存、success rate 和 score。

## Optimized 主线

AgentMem optimized 的核心是 Event-Sourced Agent Memory：

1. Agent 执行过程记录为事件：`user_message`、`tool_call`、`tool_result`、`assistant_response`、`memory_delta`、`final_answer`、`metric`。
2. Agent 每轮通过 `memory_delta` 主动写入结构化记忆：`goals`、`constraints`、`facts`、`decisions`、`open_questions`、`todos`、`artifact_refs`、`tool_summaries`、`warnings`。
3. Memory Manager 将事件流投影为 Task State View。
4. Prompt 不再拼接完整长历史，而是渲染 Task State View、Artifact References、Recent Context 和 Current Query。
5. 工具结果以 artifact/result_id 形式外置保存到 `results/tool_store/`。
6. Stable Renderer 保证 prompt 结构稳定，为 vLLM prefix cache 复用创造条件。
7. History Summary 只作为对照组或 fallback，不再作为 optimized 的核心解释。

## 安装

```bash
cd /home/zb/vllm
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 配置模型

`configs/config.yaml` 已接入自有模型服务。核心配置：

```yaml
llm:
  backend: vllm
  model: /path/to/Qwen2.5-7B-Instruct
  base_url: http://<model-host>:8000/v1
  api_key: EMPTY
  temperature: 0
  max_tokens: 512
  timeout: 120

agent:
  max_steps: 3
  enable_next_action_loop: true

vllm:
  metrics_url: http://<model-host>:8000/metrics
```

`backend=vllm` 使用 OpenAI-compatible Chat Completions API，并通过 streaming 记录 TTFT。

## 常用命令

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

## Benchmark Scenarios

- `tool-heavy`：工具调用和工具结果外置。
- `long-session`：多轮长生命周期任务。
- `multi-stage`：planning -> tool_calling -> reflection -> final_answer。
- `branching`：分支推理和上下文复制成本。
- `prefix-cache`：稳定 prompt prefix 和 vLLM prefix cache 指标。

Benchmark task 位于 `benchmarks/tasks/*.jsonl`。Evaluator 可以按任务定义 `required_facts`、`answer_keywords`、`expected_tools` 和 `expected_stages`，但 Memory 核心不写死这些 benchmark 关键词。

## 结果文件

运行后主要输出：

- `results/tool_heavy_baseline.csv`
- `results/tool_heavy_optimized.csv`
- `results/long_session_baseline.csv`
- `results/long_session_optimized.csv`
- `results/multi_stage_baseline.csv`
- `results/multi_stage_optimized.csv`
- `results/branching_baseline.csv`
- `results/branching_optimized.csv`
- `results/prefix_cache_baseline.csv`
- `results/prefix_cache_optimized.csv`
- `results/vllm_benchmark.csv`
- `results/summary.csv`
- `results/report.md`
- `results/event_log/`
- `results/event_memory_snapshots/`
- `results/tool_store/`

long-session 和 multi-stage 还保留 `full_history`、`summary_memory`、`event_sourced_memory` 细分 CSV，用于报告中展示 full history、summary memory 与 event-sourced memory 的对比。

## vLLM 指标

CSV 会记录：

- `model`
- `prompt_tokens`
- `output_tokens`
- `total_tokens`
- `latency`
- `ttft`
- `tokens_per_second`
- `peak_gpu_memory_mb`
- `prefix_cache_hit_rate`
- `cached_prompt_tokens`
- `kv_cache_usage`

如果 `nvidia-smi` 不可用，`peak_gpu_memory_mb` 为 `-1`。如果 `/metrics` 不可用，prefix cache 相关字段为 `-1`。如果 vLLM 连接失败，CLI 会输出清晰错误：`vLLM backend is unavailable. Please check llm.base_url in configs/config.yaml.`

## openEuler / openKylin

部署说明见 [docs/openeuler_deployment.md](docs/openeuler_deployment.md)。如果模型机当前是 Ubuntu，也可以按同一流程启动 vLLM；正式文档以 openEuler 22.03 LTS / 24.03 LTS 和 openKylin 环境为目标。

## 测试

```bash
python -m pytest
bash scripts/run_all.sh
```

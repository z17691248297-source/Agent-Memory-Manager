# AgentMem

AgentMem 是一个面向智能体推理过程的内存优化 Benchmark 系统。

它的目标不是做一个完整 AutoGPT，也不是做 Web 诊断产品，而是复现智能体长生命周期推理中的上下文膨胀问题，并验证 Agent 层内存管理策略是否能降低 prompt tokens、工具注入 tokens、延迟和显存压力。

核心结论服务于一句话：

> AgentMem 通过 Agent 层内存管理减少输入 token 和上下文膨胀，从而间接降低 vLLM prefill 与 KV Cache 压力。

## 安装

```bash
cd /home/zb/vllm
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

默认配置使用项目组提供的远程 vLLM OpenAI-compatible API。离线 smoke test 可以在命令里加 `--backend mock`。

## 常用命令

```bash
python -m agentmem
python -m agentmem chat
python -m agentmem benchmark --scenario tool-heavy
python -m agentmem benchmark --scenario long-session
python -m agentmem benchmark --scenario multi-stage
python -m agentmem benchmark --scenario branching
python -m agentmem benchmark --scenario prefix-cache
python -m agentmem benchmark --scenario ablation
python -m agentmem benchmark --all
python -m agentmem report
python -m agentmem tools
python -m agentmem config show
python -m agentmem clean
```

旧入口 `run`、`ask`、`eval` 仍保留，用于单轮调试和固定 workload smoke test。`benchmarks/run_*.py` 属于 legacy 调试脚本，比赛主线以 `python -m agentmem benchmark` 和 `python -m agentmem report` 为准。

## Baseline vs Optimized

baseline 模式：

- 所有工具完整说明进入 prompt。
- 工具 raw output 全文进入 prompt。
- 多轮历史完整保留。
- 分支推理复制完整 shared context。
- prompt prefix 允许动态字段和工具顺序扰动。

optimized 模式：

- Stable Prefix Prompt：system、project rules、tool brief 固定排序，动态内容后置。
- Tool Result Externalization：raw output 保存到 `results/tool_store/`，prompt 只注入 summary、result_id 和 token 统计。
- Skill Lazy Loading：默认只注入工具 brief，命中工具后加载对应 skill。
- History Summary：旧历史压缩成 summary，只保留最近 `recent_rounds` 轮完整上下文。
- Branch Context Sharing：Agent 上下文层共享 shared context，每个分支只保存 delta。

## Benchmark Scenarios

```bash
python -m agentmem benchmark --scenario tool-heavy --backend mock
python -m agentmem benchmark --scenario long-session --backend mock
python -m agentmem benchmark --scenario multi-stage --backend mock
python -m agentmem benchmark --scenario branching --backend mock
python -m agentmem benchmark --scenario prefix-cache --backend mock
python -m agentmem benchmark --scenario ablation --backend mock
```

主 benchmark 读取固定任务文件：

- `benchmarks/tasks/tool_heavy.jsonl`
- `benchmarks/tasks/long_session.jsonl`
- `benchmarks/tasks/multi_stage.jsonl`
- `benchmarks/tasks/branching.jsonl`

每条任务声明 evaluator 规则，CSV 会输出 `success`、`score` 和 `failure_reason`。

也可以一次运行全部：

```bash
bash scripts/run_all.sh
```

主要输出：

- `results/tool_heavy_baseline.csv`
- `results/tool_heavy_optimized.csv`
- `results/long_session_baseline.csv`
- `results/long_session_optimized.csv`
- `results/multi_stage_baseline.csv`
- `results/multi_stage_optimized.csv`
- `results/branch_benchmark.csv`
- `results/prefix_cache_baseline.csv`
- `results/prefix_cache_optimized.csv`
- `results/ablation.csv`
- `results/summary.csv`
- `results/report.md`

## vLLM 模式

当前项目组 vLLM API 已写入 `configs/config.yaml`：

```yaml
llm:
  backend: vllm
  model: /home/vip/.cache/huggingface/hub/models--Qwen--Qwen2.5-7B-Instruct/snapshots/a09a35458c702b33eeacc393d103063234e8bc28
  base_url: http://47.108.145.21/v1
  api_key: EMPTY
  temperature: 0
  max_tokens: 512
  timeout: 120
```

运行：

```bash
python -m agentmem run "用一句话解释 KV Cache。"
python -m agentmem benchmark --scenario prefix-cache --backend vllm
python -m agentmem report
```

如果 `/metrics` 或 `nvidia-smi` 不可用，相关字段写为 `-1`，benchmark 不会因为这些增强指标缺失而崩溃。

## 查看报告

```bash
python -m agentmem report
less results/report.md
```

报告包含项目目标、实验设置、固定 workload、硬件环境、success/score、各场景结果、ablation 和自动结论。

## 测试

```bash
python -m pytest
bash scripts/run_all.sh
```

mock backend 是默认测试路径，用来保证无 GPU、无模型服务的环境也能复现实验流程。

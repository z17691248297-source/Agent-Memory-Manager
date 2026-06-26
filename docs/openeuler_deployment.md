# openEuler / openKylin Deployment

本文档说明如何在 openEuler / openKylin 环境中部署 AgentMem benchmark，并连接本地或远程 vLLM OpenAI-compatible 模型服务。

如果当前模型机暂时是 Ubuntu，也可以按相同 vLLM 启动和 AgentMem 配置方式运行；赛题交付文档以 openEuler 22.03 LTS / 24.03 LTS 和 openKylin 环境为目标。

## 1. 系统环境

推荐环境：

- OS：openEuler 22.03 LTS 或 openEuler 24.03 LTS；openKylin 也可按相同步骤部署。
- Python：3.10 或 3.11。
- CUDA：建议 CUDA 12.x；AgentMem 可以运行在无 GPU 的控制机上，但必须连接可访问的 vLLM 模型服务。
- vLLM：建议 0.5.x 或更新版本，具体命令可能随 vLLM 版本变化。
- 模型：Qwen2.5-7B-Instruct、Qwen2-7B-Instruct、MiniCPM 等开源 instruct 模型。

基础检查：

```bash
python3 --version
nvidia-smi
```

如果 `nvidia-smi` 不存在，AgentMem benchmark 不会崩溃，`peak_gpu_memory_mb` 会记录为 `-1`。

## 2. 安装 AgentMem

```bash
cd /path/to/Agent-Memory-Manager
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

如需在同一环境安装 vLLM：

```bash
pip install vllm
```

不同 CUDA、PyTorch 和 vLLM 版本可能需要使用对应 wheel。若 vLLM 安装失败，请以 vLLM 官方文档和当前机器 CUDA 版本为准。

## 3. 启动 vLLM

示例：

```bash
python -m vllm.entrypoints.openai.api_server \
  --model /path/to/Qwen2.5-7B-Instruct \
  --host 0.0.0.0 \
  --port 8000 \
  --enable-prefix-caching
```

部分 vLLM 版本可能改用：

```bash
vllm serve /path/to/Qwen2.5-7B-Instruct \
  --host 0.0.0.0 \
  --port 8000 \
  --enable-prefix-caching
```

如果 `--enable-prefix-caching` 在当前版本不可用，请先移除该参数运行基础 benchmark；此时 `/metrics` 中 prefix cache 字段可能为 `-1`。

## 4. 配置 AgentMem

编辑 `configs/config.yaml`：

```yaml
llm:
  backend: vllm
  model: /path/to/Qwen2.5-7B-Instruct
  base_url: http://127.0.0.1:8000/v1
  api_key: EMPTY
  temperature: 0
  max_tokens: 512
  timeout: 120

agent:
  max_steps: 3
  enable_next_action_loop: true

vllm:
  metrics_url: http://127.0.0.1:8000/metrics
  enable_prefix_caching: true
```

如果 AgentMem 和 vLLM 不在同一台机器，将 `base_url` 和 `metrics_url` 改成模型机地址，例如：

```yaml
llm:
  base_url: http://10.195.21.2:8000/v1
vllm:
  metrics_url: http://10.195.21.2:8000/metrics
```

SSH 连接只用于登录和运维，不是 benchmark API 地址。模型服务端口应以实际 vLLM `--port` 为准。

## 5. 运行 Benchmark

```bash
python -m agentmem benchmark --scenario tool-heavy
python -m agentmem benchmark --scenario long-session
python -m agentmem benchmark --scenario multi-stage
python -m agentmem benchmark --scenario branching
python -m agentmem benchmark --scenario prefix-cache
python -m agentmem report
```

## 6. 输出位置

主要输出：

- `results/*.csv`
- `results/vllm_benchmark.csv`
- `results/summary.csv`
- `results/report.md`
- `results/event_log/`
- `results/event_memory_snapshots/`
- `results/tool_store/`

其中 `vllm_benchmark.csv` 只在运行过 `--backend vllm` 后生成。

## 7. 常见问题

### vLLM 连接失败

现象：

```text
vLLM backend is unavailable. Please check llm.base_url in configs/config.yaml.
```

处理：

- 确认 vLLM 服务正在运行。
- 确认 `llm.base_url` 以 `/v1` 结尾。
- 确认防火墙和端口可访问。
- 确认 `llm.model` 与 vLLM 启动时加载的模型一致。

### nvidia-smi 不存在

AgentMem 会将 `peak_gpu_memory_mb` 写为 `-1`，benchmark 不会崩溃。真实 GPU 性能结论需要在可访问 GPU 指标的机器上运行。

### /metrics 不可用

AgentMem 会将 `prefix_cache_hit_rate`、`cached_prompt_tokens`、`kv_cache_usage` 写为 `-1`。这不影响主 benchmark，但 prefix cache 结论需要可用 metrics 才完整。

### 模型路径错误

vLLM 启动阶段通常会报模型路径不存在或 config 加载失败。请确认本地路径、Hugging Face cache 路径或模型名称可访问。

### 显存不足

可以尝试：

- 换用更小模型，例如 MiniCPM 或 Qwen 1.5B/3B。
- 降低 `--max-model-len`。
- 降低并发和 batch 参数。
- 使用量化模型。
- 减小 AgentMem `llm.max_tokens`。

AgentMem 本身只优化 Agent prompt 构造，不修改 vLLM CUDA kernel 或底层 KV cache manager。

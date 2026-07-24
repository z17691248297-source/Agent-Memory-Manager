# openEuler / openKylin Deployment

本文档说明如何在 openEuler / openKylin 环境中部署 AgentMem benchmark，并连接本地或远程 vLLM OpenAI-compatible 模型服务。

AgentMem 与 vLLM 支持客户端/服务端分离部署：AgentMem 客户端负责 Agent 侧上下文生命周期、工具结果外置和 benchmark 调度；vLLM 模型服务负责 GPU 推理。国产 OS 验证可以先覆盖 AgentMem 客户端的 openEuler 用户态容器运行，再连接统一远程 vLLM 服务进行 smoke。

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

如果 `nvidia-smi` 不存在，AgentMem benchmark 不会崩溃，`peak_gpu_memory_mb` 会记录为 unavailable。

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
  --model <served-model-name-or-model-path> \
  --host 0.0.0.0 \
  --port <model-port> \
  --enable-prefix-caching
```

部分 vLLM 版本可能改用：

```bash
vllm serve <served-model-name-or-model-path> \
  --host 0.0.0.0 \
  --port <model-port> \
  --enable-prefix-caching
```

如果 `--enable-prefix-caching` 在当前版本不可用，请先移除该参数运行基础 benchmark；此时 `/metrics` 中 prefix cache 字段可能为 unavailable。

## 4. 配置 AgentMem

编辑 `configs/config.yaml`：

```yaml
llm:
  backend: vllm
  model: <served-model-name>
  base_url: http://<model-host>:<model-port>/v1
  api_key_env: AGENTMEM_API_KEY
  temperature: 0
  max_tokens: 512
  timeout: 120

agent:
  max_steps: 3
  enable_next_action_loop: true

vllm:
  metrics_url: http://<model-host>:<model-port>/metrics
  enable_prefix_caching: true
```

如果 AgentMem 和 vLLM 不在同一台机器，将 `base_url` 和 `metrics_url` 改成模型机地址，例如：

```yaml
llm:
  base_url: http://<remote-model-host>:<model-port>/v1
vllm:
  metrics_url: http://<remote-model-host>:<model-port>/metrics
```

SSH 连接只用于登录和运维，不是 benchmark API 地址。模型服务端口应以实际 vLLM `--port` 为准。

## 5. openEuler 容器 Smoke

最小国产 OS 适配证据使用 openEuler 用户态容器，不要求容器内有 GPU。该 smoke 会验证：

- 容器内 `/etc/os-release` 为 openEuler。
- AgentMem CLI 可启动。
- AgentMem 可连接远程 OpenAI-compatible vLLM 服务。
- `tool-heavy` 场景可生成 `summary.csv`、`report.md` 和 `validation.json`。

运行：

```bash
DOCKER_CMD='sudo docker' bash scripts/run_openeuler_smoke.sh
```

默认连接：

```bash
AGENTMEM_LLM_BASE_URL=http://47.108.145.21/v1
AGENTMEM_MODEL=Qwen2.5-7B-Instruct
```

如需改成其他模型服务：

```bash
AGENTMEM_LLM_BASE_URL=http://<model-host>:<model-port>/v1 \
AGENTMEM_VLLM_METRICS_URL=http://<model-host>:<model-port>/metrics \
AGENTMEM_CACHE_STATS_URL=http://<model-host>:<model-port>/v1/agentmem/cache_stats \
AGENTMEM_MODEL=<served-model-name> \
DOCKER_CMD='sudo docker' bash scripts/run_openeuler_smoke.sh
```

输出：

- `results/openeuler-smoke/environment.json`
- `results/openeuler-smoke/summary.csv`
- `results/openeuler-smoke/report.md`
- `results/openeuler-smoke/validation.json`

通过标准：

- `environment.json` 中 `openEuler_userspace_container_verified` 为 `true`。
- `validation.json` 中 `valid` 为 `true`。
- `report.md` 中能看到真实 vLLM backend、模型名、`tool-heavy` 结果。

说明：该 smoke 只作为国产 OS 兼容性证据；完整性能对比仍使用统一最终 release benchmark 结果。由于 AgentMem 客户端不直接执行 GPU 推理，openEuler 容器 smoke 不作为显存或吞吐性能对比口径。

## 6. 运行 Benchmark

```bash
python -m agentmem benchmark --scenario tool-heavy
python -m agentmem benchmark --scenario long-session
python -m agentmem benchmark --scenario multi-stage
python -m agentmem benchmark --scenario branching
python -m agentmem benchmark --scenario prefix-cache
python -m agentmem report
```

## 7. 输出位置

主要输出：

- `results/*.csv`
- `results/vllm_benchmark.csv`
- `results/summary.csv`
- `results/report.md`
- `results/event_log/`
- `results/event_memory_snapshots/`
- `results/tool_store/`

其中 `vllm_benchmark.csv` 只在运行过 `--backend vllm` 后生成。

## 8. 常见问题

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

### Docker Hub 拉取超时

`scripts/run_openeuler_smoke.sh` 默认使用国内 openEuler 镜像源：

```bash
hub.oepkgs.net/openeuler/openeuler:24.03
```

如需手动切换镜像：

```bash
OPENEULER_IMAGE=hub.oepkgs.net/openeuler/openeuler:latest \
DOCKER_CMD='sudo docker' bash scripts/run_openeuler_smoke.sh
```

### 容器写 results 权限失败

脚本会在宿主机预创建 `results/openeuler-smoke/` 并放宽该目录权限。如果手动运行 Docker，请确保挂载目录允许容器内 `agentmem` 用户写入。

### nvidia-smi 不存在

AgentMem 会将 `peak_gpu_memory_mb` 标记为 unavailable，benchmark 不会崩溃。真实 GPU 性能结论需要在可访问 GPU 指标的机器上运行。

### /metrics 不可用

AgentMem 会将 `prefix_cache_hit_rate`、`cached_prompt_tokens`、`kv_cache_usage` 标记为 unavailable。这不影响主 benchmark，但 prefix cache 结论需要可用 metrics 才完整。

### 模型路径错误

vLLM 启动阶段通常会报模型路径不存在或 config 加载失败。请确认本地路径、Hugging Face cache 路径或模型名称可访问。

### 显存不足

可以尝试：

- 换用更小模型，例如 MiniCPM 或 Qwen 1.5B/3B。
- 降低 `--max-model-len`。
- 降低并发和 batch 参数。
- 使用量化模型。
- 减小 AgentMem `llm.max_tokens`。

AgentMem 负责 Agent prompt 构造、MemoryPlan 记录和 `agent_meta` 传递，vLLM 服务端根据这些元信息维护 Agent-aware KV cache 统计。

## Verification Flags

AgentMem records separate compatibility flags in `environment.json`:

- `openEuler_userspace_container_verified`: openEuler userspace container run succeeded; host kernel may be non-openEuler.
- `openEuler_native_host_verified`: native openEuler VM/host run succeeded.
- `Ubuntu_model_server_verified`: remote Ubuntu GPU model server was verified.
- `full_openEuler_gpu_deployment_verified`: full Agent plus GPU model server deployment on openEuler was verified.

A Dockerfile or image build alone never sets `official_os_compatibility_run=true` or any native-host/full-GPU flag.

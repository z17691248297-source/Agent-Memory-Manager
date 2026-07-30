# openEuler Container Client Run

本文件说明如何用 openEuler 容器运行 AgentMem client 和 benchmark。该流程证明 client、依赖安装、benchmark 脚本和远程 vLLM API 可在 openEuler 用户态环境中运行。

## 启动容器

```bash
docker run -it --name agentmem-openeuler \
  -v <repo-root>:/workspace/vllm \
  -w /workspace/vllm \
  openeuler/openeuler:22.03-lts bash
```

## 容器内安装依赖

```bash
cat /etc/os-release
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

如果镜像内缺少 `python3`、`pip` 或 `curl`，先用 openEuler 包管理器安装：

```bash
dnf install -y python3 python3-pip curl
```

## 检查远程模型服务

AgentMem 使用 `configs/config.yaml` 中配置的 Qwen2.5-7B-Instruct vLLM OpenAI-compatible 服务：

```bash
curl http://47.108.145.21/v1/models
```

metrics 和 cache_stats 端点：

```bash
curl http://47.108.145.21/metrics
curl http://47.108.145.21/v1/agentmem/cache_stats
```

## 正式实验前清理结果

正式实验前不要把新旧结果混在一起：

```bash
mv results results_backup_$(date +%Y%m%d_%H%M%S)
mkdir results
```

## 运行 benchmark

```bash
source .venv/bin/activate
python -m agentmem benchmark --scenario tool-heavy --backend vllm --repeat 3
python -m agentmem benchmark --scenario long-session --backend vllm --repeat 3
python -m agentmem benchmark --scenario multi-stage --backend vllm --repeat 3
python -m agentmem benchmark --scenario branching --backend vllm --repeat 3
python -m agentmem benchmark --scenario prefix-cache --backend vllm --repeat 3
python -m agentmem report
```

`report.md` 会记录：

- `client_os`
- `client_environment`
- `model_server_os`
- `main_llm_backend`
- `extractor_backend`
- `official_os_compatibility_run`

如果 client 在 openEuler 容器内运行，报告标注 `openEuler_userspace_container_verified: true`。

## 当前远程部署说明

推荐架构是 openEuler 容器运行 AgentMem client 和 benchmark，通过 `configs/config.yaml` 连接用户已有的 GPU vLLM 服务。

如果模型服务以较小 `max_model_len` 启动，tool-heavy 16K workload 的 baseline 超上下文是预期部署限制。要让 tool-heavy baseline 和 optimized 都在该 workload 上正常推理，模型服务需要以 16K 或更高 `max_model_len` 启动。

## 运行范围

- `openEuler_userspace_container_verified=true` 表示 AgentMem 已在 openEuler 用户态容器内完成运行验证。
- `openEuler_native_host_verified=true` 表示 AgentMem 已在 openEuler 虚拟机或物理机上完成运行验证。
- `Ubuntu_model_server_verified=true` 表示远程 GPU vLLM 模型服务已完成单独核验。
- `full_openEuler_gpu_deployment_verified=true` 表示 AgentMem 与 GPU 模型服务均在 openEuler 环境中完成运行验证。

本项目以 AgentMem client 的国产 OS 运行验证、远程 vLLM 服务调用和最终 benchmark 结果共同构成部署说明。

# openEuler Container Client Run

本文件说明如何用 openEuler 容器运行 AgentMem client 和 benchmark。该流程证明 client、依赖安装、benchmark 脚本和远程 vLLM API 在 openEuler 容器内兼容；它不等同于完整 openEuler 原生 GPU/vLLM 部署。

## 启动容器

```bash
docker run -it --name agentmem-openeuler \
  -v /home/zb/vllm:/workspace/vllm \
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

主 Agent 最终回答使用 8000 端口 Qwen2.5-7B-Instruct 服务：

```bash
curl http://47.108.145.21/v1/models
```

memory extraction 只用于生成结构化 `memory_delta` / state update。当前 9000 端口模型服务通过公网 2223 端口反向代理访问：

```bash
curl http://47.108.145.21:2223/v1/models
```

不要把 extractor 服务用于最终回答。最终回答仍由 `llm.base_url` 指向的 8000 服务生成。

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

如果 client 在 openEuler 容器内运行，报告标注 `official_os_compatibility_run: true`。如果是在 WSL2 或普通 Ubuntu 开发环境运行，报告标注为 development run。

## 当前远程部署说明

当前远程模型机为 Ubuntu 22.04.5 LTS，GPU 为 RTX 4090。8000 服务是主 Agent 推理服务，9000 服务是 extractor 服务。openEuler 容器运行 AgentMem client 和 benchmark，并在报告中标注 client 侧 openEuler 兼容性。

如果 8000 主模型服务仍以 `--max-model-len 4096` 启动，tool-heavy 16K workload 的 baseline 超上下文是预期部署限制。要让 tool-heavy baseline 和 optimized 都在该 workload 上正常推理，主 Agent 的 8000 服务需要以 16K 或更高 `max_model_len` 启动。

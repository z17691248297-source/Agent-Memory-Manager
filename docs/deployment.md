# Deployment

## 安装依赖

```bash
cd /home/zb/vllm
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 配置文件

主配置文件是 `configs/config.yaml`。默认 backend 是项目组提供的远程 `vllm`：

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

内存优化开关：

```yaml
memory:
  recent_rounds: 6
  enable_tool_externalization: true
  enable_skill_lazy_loading: true
  enable_history_summary: true
  enable_branch_sharing: true
  enable_stable_prefix: true
```

## Benchmark 运行

使用 `configs/config.yaml` 中配置的模型服务运行：

```bash
bash scripts/run_all.sh
```

vLLM backend 使用 OpenAI-compatible `/v1/chat/completions`。streaming 模式用于估算 TTFT。`/metrics` 会按 best-effort 读取 prefix cache、cached prompt tokens 和 KV cache usage；不可用时写 `-1`。

## 常见问题

### 没有 GPU 能运行吗？

正式 benchmark 需要可访问的模型服务。AgentMem 可以部署在无 GPU 的控制机上，但 `llm.base_url` 必须指向远程 vLLM 服务。

### vLLM 不可用会怎样？

CLI 会输出清晰错误：`vLLM backend is unavailable. Please check llm.base_url in configs/config.yaml.`，不会打印大段 traceback。

### Agent Runtime 覆盖哪些能力？

赛题核心是智能体推理过程中的内存管理优化。AgentMem runtime 覆盖多轮、工具调用、分支、prompt 构造、MemoryPlan 日志和 `agent_meta` 传递，用于复现实验问题和生成证据链。

### 如何观测 Agent-aware KV Cache 管理？

AgentMem 通过 OpenAI-compatible `extra_body.agent_meta` 传递 session、context、segment、priority 和 ttl，并通过 `/v1/agentmem/cache_stats` 采集服务端 KV cache 统计。

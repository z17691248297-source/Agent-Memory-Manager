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

## Mock 运行

mock 模式不需要 GPU 或模型服务：

```bash
python -m agentmem benchmark --scenario tool-heavy --backend mock
python -m agentmem benchmark --scenario long-session --backend mock
python -m agentmem benchmark --scenario multi-stage --backend mock
python -m agentmem benchmark --scenario branching --backend mock
python -m agentmem benchmark --scenario prefix-cache --backend mock
python -m agentmem benchmark --scenario ablation --backend mock
python -m agentmem report
```

一键运行：

```bash
bash scripts/run_all.sh
```

## vLLM 运行

运行 benchmark：

```bash
python -m agentmem run "用一句话解释 KV Cache。"
python -m agentmem benchmark --scenario prefix-cache --backend vllm
python -m agentmem benchmark --scenario tool-heavy --backend vllm
python -m agentmem report
```

vLLM backend 使用 OpenAI-compatible `/v1/chat/completions`。streaming 模式用于估算 TTFT。`/metrics` 会按 best-effort 读取 prefix cache、cached prompt tokens 和 KV cache usage；不可用时写 `-1`。

## 常见问题

### 没有 GPU 能运行吗？

可以。默认 mock backend 会生成可复现的 token、latency 和 CSV 结果。

### vLLM 不可用会怎样？

CLI 会输出清晰错误，例如 `vllm backend unavailable: ...`，不会打印大段 traceback。

### 为什么不是完整 Agent？

赛题核心是智能体推理过程中的内存管理优化。AgentMem 的 runtime 只保留多轮、工具调用、分支和 prompt 构造能力，用于复现实验问题和生成证据链。

### 是否实现了底层 KV Cache 管理？

没有。当前实现是 Agent 上下文层优化：减少进入 vLLM 的输入 token，提升 prefix 稳定性，从而间接降低 prefill 和 KV Cache 压力。

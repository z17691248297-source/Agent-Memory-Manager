# Agent Memory Manager

面向 vLLM Agent 工作负载的上下文编译与记忆管理实验项目。

## 项目目标

本项目不是普通聊天 Agent，而是希望解决 Agent 场景里常见的上下文膨胀问题：

- 多轮历史越来越长；
- system prompt 和工具 schema 反复出现；
- 工具返回结果很长；
- 分支规划会复制大量父上下文；
- 这些内容最终都会增加 prefill token 和 KV Cache 压力。

当前实现了一个第一版 **Agent Memory Compiler**：

```text
MemoryObject
  -> 稳定前缀布局
  -> token 成本估算
  -> 最近窗口和摘要记忆
  -> 长工具结果 artifact 外置
  -> 分支上下文过滤
  -> 编译后的 prompt 和 trace 指标
```

后续本地 vLLM 模型服务接入后，可以继续测量 TTFT、延迟、显存和 prefix cache 命中情况。

## 目录结构

```text
agent/
  memory_object.py        # 记忆对象抽象
  context_compiler.py     # 上下文编译器
  artifact_store.py       # 长工具结果外置存储
  policies.py             # 不同上下文策略

benchmarks/
  scenarios.py            # 可复现实验场景
  run_context_compiler_benchmark.py
                          # 策略对比脚本

docs/
  agent_memory_compiler_design.md
                          # 中文设计文档

experiments/
  toy_vllm_scheduler.py   # 用于理解 vLLM 调度/KV cache 的玩具代码
```

## 快速运行

```bash
cd /home/zb/vllm
PYTHONPATH=. python3 benchmarks/run_context_compiler_benchmark.py
```

运行后会输出类似：

```text
scenario | policy | tokens | stable | dynamic | artifact_refs | saved | dropped | artifacts
long_tool_result | baseline | 4076 | 0 | 4076 | 0 | 0 | 0 | 0
long_tool_result | context_compiler | 283 | 144 | 57 | 82 | 3793 | 0 | 1
branch_planning | baseline | 2140 | 0 | 2140 | 0 | 0 | 0 | 0
branch_planning | context_compiler | 305 | 144 | 91 | 70 | 1835 | 0 | 1
```

详细结果会写入：

```text
benchmarks/results/
```

该目录是运行产物，默认不会提交到 Git。

## 当前创新点

1. **稳定前缀区**
   将 system prompt、工具 schema、输出协议等固定在前缀区，便于后续和 vLLM prefix caching 对齐。

2. **工具结果外置**
   长工具结果不直接进入 prompt，只保留 artifact id、摘要、页数和原始 token 数。

3. **预算感知上下文编译**
   根据 token budget、重要性和最近性选择上下文，避免无控制地塞入全部历史。

4. **分支上下文过滤**
   分支规划任务只编译当前活跃分支和公共根上下文，避免重复发送无关分支内容。

## 后续计划

- 接入本地 vLLM OpenAI-compatible 服务；
- 使用真实模型 tokenizer 统计 token；
- 增加真实 Agent loop 和工具调用协议；
- 采集 vLLM `/metrics`；
- 将 Agent 侧 trace 与 vLLM 侧 TTFT、显存、prefix cache 指标关联。

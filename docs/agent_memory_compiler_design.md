# Agent 记忆编译器设计说明

## 项目定位

这个项目不是一个普通聊天机器人，而是一个面向 vLLM 推理服务场景的 Agent
记忆管理实验系统。

核心思想是：

> 把 Agent 运行过程中的历史消息、工具结果、摘要记忆和分支状态，编译成一个
> 更适合 vLLM prefix caching 和 KV Cache 管理的上下文。

换句话说，我们不只关心 Agent 能不能回答问题，还关心：

- 它发给模型的上下文有多少 token；
- 哪些内容属于稳定前缀，适合被 prefix cache 复用；
- 哪些工具结果不应该直接进入 prompt；
- 老历史应该保留原文、摘要，还是直接丢弃；
- 分支规划时是否重复发送了大量父上下文。

## 为什么这比简单 Agent 更深

普通 Agent 往往直接这样拼上下文：

```text
system prompt + 全部历史消息 + 原始工具结果 + 当前用户问题
```

这个项目在中间加了一层“上下文编译器”：

```text
MemoryObject
  -> token 成本估算
  -> 稳定前缀布局
  -> 工具结果外置
  -> 摘要与最近窗口选择
  -> 分支状态过滤
  -> 编译后的 prompt 和 trace 指标
```

这样 Agent 侧可以产生可量化的实验数据，后续本地 vLLM 服务接入后，就能继续
关联推理侧指标。

## Agent 侧指标

当前版本已经记录：

- `total_input_tokens`：最终输入 token 估算；
- `stable_prefix_tokens`：稳定前缀 token；
- `dynamic_context_tokens`：动态上下文 token；
- `inline_tool_result_tokens`：直接塞进 prompt 的工具结果 token；
- `artifact_ref_tokens`：artifact 引用 token；
- `artifact_saved_tokens`：通过工具结果外置节省的 token；
- `dropped_tokens`：因预算限制被丢弃的 token；
- `artifact_count`：生成的外置工具结果数量。

## vLLM 侧后续指标

模型部署同学接入本地 vLLM 后，可以继续采集：

- TTFT；
- 端到端延迟；
- 峰值 GPU 显存；
- 吞吐；
- prefix cache 命中情况；
- KV cache 使用情况。

## 核心模块

```text
agent/memory_object.py
  定义 MemoryObject、MemoryType 和轻量 token 估算。

agent/context_compiler.py
  根据 ContextPolicy 把 MemoryObject 列表编译成 prompt。

agent/artifact_store.py
  把长工具结果保存到 prompt 外部，并生成短引用。

agent/policies.py
  定义 baseline、recent_window、summary_artifact、context_compiler 等策略。

benchmarks/scenarios.py
  构造可复现的 Agent 记忆压力场景。

benchmarks/run_context_compiler_benchmark.py
  对所有场景运行多种策略，并写出 prompt 和 trace。
```

## 策略说明

### baseline

最朴素的上下文构造方式：

```text
全部历史 + 全部原始工具结果
```

它用于模拟“简单 Agent”容易出现的上下文膨胀问题。

### recent_window

保留稳定前缀和最近消息，但仍然内联工具结果。

### summary_artifact

加入摘要记忆，并把长工具结果外置成 artifact。

### context_compiler

第一版完整编译策略：

```text
稳定前缀
+ summary memory
+ 最近窗口
+ 重要性排序的旧记忆
+ artifact 引用
+ token budget 控制
```

## 运行方式

在仓库根目录运行：

```bash
cd /home/zb/vllm
PYTHONPATH=. python3 benchmarks/run_context_compiler_benchmark.py
```

输出文件：

```text
benchmarks/results/context_compiler_summary.json
benchmarks/results/*.prompt.txt
benchmarks/results/*.trace.json
benchmarks/results/artifacts/*
```

这些结果文件是运行产物，默认不提交到 Git。

## 当前示例结果

在合成 benchmark 上，当前结果大致如下：

```text
long_tool_result:
  baseline:          4076 tokens
  context_compiler:   283 tokens

branch_planning:
  baseline:          2140 tokens
  context_compiler:   305 tokens
```

这还不是最终 vLLM serving benchmark，而是 Agent 侧证据：

> 优化策略能把长工具结果和分支上下文压缩成更短、更结构化、更适合 vLLM 复用的 prompt。

## 下一步扩展

建议按下面顺序继续：

1. 接入本地 vLLM 模型 tokenizer，替换当前轻量 token 估算；
2. 增加 OpenAI-compatible vLLM client；
3. 把编译后的 prompt 发送到本地模型服务；
4. 同步采集 vLLM `/metrics`；
5. 增加稳定前缀 fingerprint，用于分析 prefix cache 友好性；
6. 构造更真实的分支规划 benchmark，对比“复制父上下文”和“只发送分支增量”。

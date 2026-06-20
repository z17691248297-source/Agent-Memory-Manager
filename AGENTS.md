# 仓库协作说明

## 项目目标

本仓库用于比赛项目“面向 Agent 的记忆管理系统设计与实现”。

当前目标不是做一个普通聊天机器人，而是构建一个可复现、可评测、面向 vLLM
推理服务场景的 Agent 记忆管理系统。

项目重点：

- 学习 vLLM 推理链路中的 `prefill`、`decode`、`KV Cache` 和 prefix caching；
- 构建 Agent 工作负载；
- 设计上下文编译和记忆管理策略；
- 通过 benchmark 证明优化前后的 token、延迟、显存和成功率变化。

## 当前阶段

当前优先级如下：

1. 理解模型权重、推理、`prefill`、`decode`、`KV Cache`；
2. 本地模型服务由其他同学负责，用 vLLM 暴露 OpenAI-compatible API；
3. 本仓库先实现 Agent 侧的 memory compiler 和 benchmark；
4. 后续接入本地 vLLM 服务，采集 TTFT、显存、延迟和 prefix cache 相关指标；
5. 最后再考虑是否修改 vLLM scheduler 或更底层的引擎逻辑。

不要一开始就跳到 CUDA kernel 或复杂 scheduler 改造。先把 Agent 侧 workload、
trace 和可复现实验跑通。

## 技术方向

Agent 侧优先做：

- 稳定前缀布局；
- 工具描述和 system prompt 去重；
- 长工具结果外置；
- summary memory；
- token budget 感知的上下文选择；
- 分支任务中的上下文复用；
- benchmark 和 trace。

vLLM 侧后续关注：

- OpenAI-compatible serving；
- prefix caching；
- KV Cache 使用情况；
- TTFT；
- 端到端延迟；
- 峰值 GPU 显存。

## Benchmark 要求

所有优化前后对比都应保持相同硬件、相同模型、相同 workload。

至少记录：

- 输入 token 数；
- 工具结果内联 token；
- artifact 节省 token；
- 端到端延迟；
- 任务成功率；
- 峰值 GPU 显存；
- prefix cache 相关指标。

Benchmark 场景至少覆盖：

- 多轮对话；
- 工具调用；
- 长工具结果；
- 分支规划。

## 目录约定

```text
docs/
  学习笔记、设计文档、报告

agent/
  Agent 运行时和记忆编译器

benchmarks/
  场景构造和评测脚本

experiments/
  原型实验和教学代码

scripts/
  环境准备、服务启动、指标采集脚本
```

## 开发风格

- 文档使用中文；
- 代码注释尽量使用中文；
- Python 标识符可以使用英文，便于和 vLLM、OpenAI-compatible API 生态对接；
- 每次新增优化都要有 baseline 对照；
- 不要只写理论说明，尽量配套可运行脚本和 trace 输出。

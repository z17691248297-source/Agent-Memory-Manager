# AgentMem Benchmark Report

## 1. 项目目标

AgentMem 是通用轻量 Agent Runtime + Memory Manager，用于让 Agent 通过 memory_delta 主动维护结构化任务状态，并通过 artifact_refs 管理工具结果。Benchmark 只用于评估不同任务场景下的上下文、质量和可追溯性表现；Memory 核心不依赖具体 benchmark 关键词。

## 2. 实验设置

| item | value |
| --- | --- |
| backend | vllm |
| model | /home/vip/.cache/huggingface/hub/models--Qwen--Qwen2.5-7B-Instruct/snapshots/a09a35458c702b33eeacc393d103063234e8bc28 |
| client_os | Ubuntu 24.04.4 LTS |
| client_environment | WSL2 |
| model_server_os | Ubuntu 22.04.5 LTS |
| official_os_compatibility_run | False |
| note | development run only |
| main_llm_backend | vllm |
| main_llm_base_url | http://47.108.145.21/v1 |
| main_llm_max_model_len | 16384 |
| agent_meta_enabled | True |
| cache_stats_available | True |
| cache_stats_unavailable_reason |  |
| extractor_backend | vllm |
| extractor_model | Qwen3.5-9B |
| extractor_base_url | http://47.108.145.21:2223/v1 |
| extractor_enabled | True |
| extractor_effective | False |
| extractor_status | fallback |
| extractor_success_count | 0 |
| extractor_failure_count | 2 |
| scenarios | tool_heavy |
| mode | baseline, optimized |
| repeat | 1 |
| recent_rounds | 6 |
| enabled_optimizations | event_sourced_memory, memory_delta, artifact_refs, stable_renderer, tool_externalization |

## 3. 系统架构

本项目不是完整 AutoGPT，也不是通用 Web Agent。本项目实现的是支持典型智能体工作流的轻量 Agent Runtime，并将 Event-Sourced Memory 作为 Agent 侧内存管理优化机制。

- AgentRuntime：负责多轮输入、轻量 next_action loop、工具执行、LLM 调用和指标采集。
- Event-Sourced Memory：记录 user_message、tool_call、tool_result、assistant_response、memory_delta、final_answer、metric 等事件。
- memory_delta：主模型响应中可主动写入 goals、constraints、facts、decisions、open_questions、todos、artifact_refs、tool_summaries 和 warnings；未稳定输出时，可选 extractor 只生成同一结构化状态更新，不生成最终回答。
- Task State View：Memory Manager 从事件流投影出的结构化状态，prompt 渲染 Task State View、Artifact References、Recent Context 和 Current Query。
- Tool Store：工具 raw output 保存在 results/tool_store/raw/，prompt 只引用 result_id、summary 和 artifact metadata。
- Stable Renderer：保持 prompt 结构稳定，为 vLLM prefix cache 复用创造条件。

## 4. Workloads

| scenario | workload_file | tasks |
| --- | --- | --- |
| tool-heavy | benchmarks/tasks/tool_heavy.jsonl | 1 |
| long-session | benchmarks/tasks/long_session.jsonl | 50 |
| multi-stage | benchmarks/tasks/multi_stage.jsonl | 4 |
| branching | benchmarks/tasks/branching.jsonl | 1 |
| prefix-cache | metric:prefix-cache | 0 |
| ablation | metric:ablation | 0 |

## 5. Hardware

| item | value |
| --- | --- |
| platform | Linux-6.6.87.2-microsoft-standard-WSL2-x86_64-with-glibc2.39 |
| python | 3.12.3 |
| gpu | unavailable |
| gpu_memory_mb | unavailable |
| driver | unavailable |

## 6. Success / Score

| scenario | mode | rows | success_rate | avg_score |
| --- | --- | --- | --- | --- |
| tool_heavy | baseline | 1 | 100.0000 | 1.0000 |
| tool_heavy | optimized | 1 | 100.0000 | 1.0000 |

## Configured Model Backend Results

说明：本节使用 configs/config.yaml 中配置的模型 backend；latency、TTFT、tokens_per_second 和显存字段用于真实性能分析。cache_stats 不可用时 cache 字段为 -1，并记录 unavailable_reason。agent_meta 不进入 prompt，只通过 OpenAI-compatible extra_body 发送。

| scenario | mode | prompt_tokens | state_view_tokens | latency | ttft | tokens_per_second | peak_gpu_memory_mb | prefix_cache_hit_rate | cached_prompt_tokens | kv_cache_usage | cache_total_blocks | cache_agent_sessions | cache_tool_result_blocks | cache_shared_prefix_blocks | cache_scratchpad_blocks | cache_expired_branch_blocks | success_rate | score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tool-heavy | baseline | 13697.0000 | 0.0000 | 4.8889 | 2.8027 | 31.9600 | -1.0000 | 0.0000 | 0.0000 | 0.0000 | 1024.0000 | 9.0000 | 1060.0000 | -1.0000 | -1.0000 | -1.0000 | 100.0000 | 1.0000 |
| tool-heavy | optimized | 1568.0000 | 0.0000 | 9.4988 | 1.2900 | 37.0517 | -1.0000 | 0.0000 | 0.0000 | 0.0000 | 1068.0000 | 10.0000 | 1091.0000 | -1.0000 | -1.0000 | -1.0000 | 100.0000 | 1.0000 |

## 7. Tool-heavy 结果

该场景复现大规模工具输出直接进入 prompt 后造成的上下文膨胀。

| mode | prompt_tokens | raw_tool_tokens | injected_tool_tokens | tool_compression_ratio | latency | ttft | peak_gpu_memory_mb | score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 13697.0000 | 6112.0000 | 6112.0000 | 1.0000 | 4.8889 | 2.8027 | -1.0000 | 1.0000 |
| optimized | 1568.0000 | 6112.0000 | 375.0000 | 0.0614 | 9.4988 | 1.2900 | -1.0000 | 1.0000 |

Prompt token reduction: 88.55%.

## 8. Long-session 结果

该场景复现多轮长生命周期会话中历史上下文持续增长的问题。

暂无 long-session 数据。

## 9. Multi-stage 结果

该场景覆盖 planning -> tool_calling -> reflection -> final_answer 的多阶段智能体流程。

暂无 multi-stage 数据。

## Event-Sourced Agent Memory

暂无 event-sourced memory 数据。

## 10. Branching 结果

该场景复现分支推理中公共上下文重复复制的问题。这里实现的是 Agent 上下文层共享，不是 vLLM 底层 KV block sharing。

暂无 branching 数据。

## 11. Prefix-cache 结果

该场景验证稳定 prompt prefix 对 prefix cache 复用、prefill 和 TTFT 的影响。vLLM 后端会尽力读取 /metrics。

暂无 prefix-cache 数据。

## 12. Ablation 结果

暂无 ablation 数据。

## 13. 当前局限性

- vLLM 指标依赖服务端版本和 /v1/agentmem/cache_stats 暴露情况；缺失时报告为 -1，并在 summary/report 中保留 unavailable_reason。
- 当前记录的 8000 主模型服务 max_model_len 可能为 4096；tool-heavy 16K workload 需要 16K 主模型服务才能让 baseline 正常推理。
- 当前 next_action loop 是轻量实现，覆盖工具调用和有限多步决策，不是完整 AutoGPT。
- Event-Sourced Memory 优先使用主模型按协议输出的 memory_delta；extractor 失败或非法 JSON 时 fallback 到空 memory_delta / 既有 rule-based path，benchmark 不崩溃。
- 本项目不修改 vLLM kernel，不声称实现底层 KV block sharing。

## 14. 结论

- Token 降低最明显的场景：tool_heavy，prompt token reduction 约 88.55%。
- 工具上下文膨胀来源：tool-heavy 场景最大 raw_tool_tokens 为 6112。
- 当前报告聚合任务成功率：100.00%。
- Ablation 中 prompt_tokens 最低的配置：暂无。
- 真实 vLLM prefix 指标：当前结果未包含可用兼容指标，相关字段保持 -1。
- Agent-aware cache_stats：已读取到 /v1/agentmem/cache_stats。
- 当前局限性：AgentMem 优化的是 Agent 上下文构造与外置存储路径，尚未修改 vLLM CUDA kernel 或底层 KV block manager。

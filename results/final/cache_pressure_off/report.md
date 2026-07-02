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
| agent_meta_enabled | False |
| cache_stats_available | True |
| cache_stats_unavailable_reason |  |
| extractor_backend | vllm |
| extractor_model | Qwen3.5-9B |
| extractor_base_url | http://47.108.145.21:2223/v1 |
| extractor_enabled | True |
| extractor_effective | False |
| extractor_status | unavailable |
| extractor_success_count | -20 |
| extractor_failure_count | -20 |
| scenarios | cache_pressure |
| mode | sessions_4 |
| repeat | 1 |
| recent_rounds | 6 |
| enabled_optimizations | event_sourced_memory, memory_delta, artifact_refs, stable_renderer, tool_externalization |

## 3. 系统架构

AgentMem 实现了支持典型智能体工作流的轻量 Agent Runtime，并将 Event-Sourced Memory 作为 Agent 侧内存管理优化机制。

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
| cache-pressure | metric:cache-pressure | 20 |
| ttl-priority | metric:ttl-priority | 0 |

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
| cache_pressure | sessions_4 | 20 | 100.0000 | 1.0000 |

## Configured Model Backend Results

说明：本节使用 configs/config.yaml 中配置的模型 backend；latency、TTFT、tokens_per_second 和显存字段用于真实性能分析。cache_stats 不可用时 cache 字段为 -1，并记录 unavailable_reason。agent_meta 不进入 prompt，只通过 OpenAI-compatible extra_body 发送。

| scenario | mode | prompt_tokens | state_view_tokens | latency | ttft | tokens_per_second | peak_gpu_memory_mb | prefix_cache_hit_rate | cached_prompt_tokens | kv_cache_usage | cache_total_blocks | cache_agent_sessions | cache_tool_result_blocks | cache_shared_prefix_blocks | cache_scratchpad_blocks | cache_expired_branch_blocks | success_rate | score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cache-pressure | sessions_4 | 5483.8000 | 0.0000 | 2.4380 | 0.4175 | 41.9676 | -1.0000 | 0.0000 | 0.0000 | 0.0000 | 7999.0000 | 14.0000 | 2483.0000 | 1388.0000 | 1384.0000 | 1381.0000 | 100.0000 | 1.0000 |

## AgentMeta on/off 对比

| agent_meta_enabled | scenario | prompt_tokens | latency | ttft | tokens_per_second | cache_total_blocks | cache_agent_sessions | cache_tool_result_blocks | cache_shared_prefix_blocks | cache_scratchpad_blocks | cache_expired_branch_blocks | success_rate | score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| False | cache-pressure | 5483.8000 | 2.4380 | 0.4175 | 41.9676 | 7999.0000 | 14.0000 | 2483.0000 | 1388.0000 | 1384.0000 | 1381.0000 | 100.0000 | 1.0000 |

## Cache pressure benchmark

| segment_type | sessions | prompt_tokens | latency | ttft | tokens_per_second | cache_total_blocks | cache_agent_sessions | cache_tool_result_blocks | cache_shared_prefix_blocks | cache_scratchpad_blocks | cache_expired_branch_blocks | success_rate | score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| shared_prefix | 4 | 5483.0000 | 2.7578 | 0.5710 | 40.3445 | 7999.0000 | 14.0000 | 2483.0000 | 1388.0000 | 1384.0000 | 1381.0000 | 100.0000 | 1.0000 |
| tool_schema | 4 | 5484.0000 | 2.4276 | 0.3341 | 43.2887 | 7999.0000 | 14.0000 | 2483.0000 | 1388.0000 | 1384.0000 | 1381.0000 | 100.0000 | 1.0000 |
| tool_result | 4 | 5486.0000 | 2.5504 | 0.4190 | 43.2848 | 7999.0000 | 14.0000 | 2483.0000 | 1388.0000 | 1384.0000 | 1381.0000 | 100.0000 | 1.0000 |
| scratchpad | 4 | 5485.0000 | 2.3625 | 0.3886 | 41.7092 | 7999.0000 | 14.0000 | 2483.0000 | 1388.0000 | 1384.0000 | 1381.0000 | 100.0000 | 1.0000 |
| expired_branch | 4 | 5481.0000 | 2.0916 | 0.3748 | 41.2110 | 7999.0000 | 14.0000 | 2483.0000 | 1388.0000 | 1384.0000 | 1381.0000 | 100.0000 | 1.0000 |

## TTL/Priority benchmark

暂无 ttl-priority 数据。

## cache_stats 可用性

| scenario | cache_stats_available | cache_stats_unavailable_reason | rows | cache_total_blocks | cache_agent_sessions | cache_tool_result_blocks | cache_shared_prefix_blocks | cache_scratchpad_blocks | cache_expired_branch_blocks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cache-pressure | True |  | 20 | 7999.0000 | 14.0000 | 2483.0000 | 1388.0000 | 1384.0000 | 1381.0000 |

## agent_meta segment 映射

| segment_type | agent_meta_usage | priority | cache_behavior |
| --- | --- | --- | --- |
| system | 系统指令和稳定角色约束 | high | 跨轮保留 |
| tool_schema | 工具说明、工具参数协议和调用边界 | high | 跨请求复用 |
| shared_prefix | 稳定 prefix、分支基座和公共项目规则 | high | 优先保留 |
| tool_result | 工具摘要、artifact ref 和大型结果索引 | normal/low | 显存压力下按优先级管理 |
| scratchpad | planning/reflection 中间状态 | low | 短生命周期管理 |
| expired_branch | 过期分支和被替代候选路径 | drop | 优先释放 |

## 7. Tool-heavy 结果

该场景复现大规模工具输出直接进入 prompt 后造成的上下文膨胀。

暂无 tool-heavy 数据。

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

## 13. 指标说明

- vLLM 指标依赖服务端版本和 /v1/agentmem/cache_stats 暴露情况；缺失时报告为 -1，并在 summary/report 中保留 unavailable_reason。
- 远程 vLLM 主模型服务通过 OpenAI-compatible API 提供推理能力，Agent-aware cache_stats 用于观察服务端 KV block 旁路元信息。
- Event-Sourced Memory 使用主模型按协议输出的 memory_delta；extractor 负责将不稳定输出规整为同一结构化状态更新。
- MemoryPlan JSONL 记录每次 LLM 请求前的 run_id、stage、context_id、segment_type、priority、ttl、included/excluded items 和 agent_meta。

## 14. 结论

- Token 降低最明显的场景：暂无，prompt token reduction 约 0.00%。
- 工具上下文膨胀来源：tool-heavy 场景最大 raw_tool_tokens 为 0。
- 当前报告聚合任务成功率：100.00%。
- Ablation 中 prompt_tokens 最低的配置：暂无。
- 真实 vLLM prefix 指标：当前结果未包含可用兼容指标，相关字段保持 -1。
- Agent-aware cache_stats：已读取到 /v1/agentmem/cache_stats。
- Agent-aware 实验通过 agent_meta 将 session、context、segment、priority 和 ttl 显式传递给 vLLM 服务端，支持长生命周期、多工具、多 session 的 cache 管理观测。

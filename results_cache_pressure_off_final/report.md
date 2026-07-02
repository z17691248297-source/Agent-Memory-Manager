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
| agent_meta_enabled |  |
| cache_stats_available |  |
| cache_stats_unavailable_reason |  |
| extractor_backend | vllm |
| extractor_model | Qwen3.5-9B |
| extractor_base_url | http://47.108.145.21:2223/v1 |
| extractor_enabled | True |
| extractor_effective | True |
| extractor_status | active |
| extractor_success_count | 10 |
| extractor_failure_count | 15 |
| scenarios | tool_heavy, long_session, multi_stage, branching, prefix_cache, ablation |
| mode | baseline, event_sourced_memory, full_history, optimized, summary_memory |
| repeat | 1 |
| recent_rounds | 6 |
| enabled_optimizations | event_sourced_memory, memory_delta, artifact_refs, stable_renderer, tool_externalization |

## 3. 系统架构

AgentMem 实现了支持典型智能体工作流的轻量 Agent Runtime，并将 Event-Sourced Memory 与 vLLM Agent-aware KV cache 元信息对接为端到端实验路径。

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
| prefix-cache | metric:prefix-cache | 12 |
| ablation | metric:ablation | 6 |
| cache-pressure | metric:cache-pressure | 0 |
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
| tool_heavy | baseline | 1 | 100.0000 | 1.0000 |
| tool_heavy | optimized | 1 | 100.0000 | 1.0000 |
| long_session | full_history | 50 | 98.0000 | 0.9950 |
| long_session | summary_memory | 50 | 98.0000 | 0.9917 |
| long_session | event_sourced_memory | 50 | 98.0000 | 0.9933 |
| multi_stage | full_history | 4 | 50.0000 | 0.8917 |
| multi_stage | summary_memory | 4 | 75.0000 | 0.9750 |
| multi_stage | event_sourced_memory | 4 | 100.0000 | 1.0000 |
| branching | baseline | 3 | 100.0000 | 1.0000 |
| branching | optimized | 3 | 100.0000 | 1.0000 |
| prefix_cache | baseline | 6 | 100.0000 | 1.0000 |
| prefix_cache | optimized | 6 | 100.0000 | 1.0000 |
| ablation | baseline | 1 | 100.0000 | 1.0000 |
| ablation | stable_prefix_only | 1 | 100.0000 | 1.0000 |
| ablation | skill_lazy_loading_only | 1 | 100.0000 | 1.0000 |
| ablation | tool_externalization_only | 1 | 100.0000 | 1.0000 |
| ablation | history_summary_only | 1 | 100.0000 | 1.0000 |
| ablation | full_optimized | 1 | 100.0000 | 1.0000 |

## Configured Model Backend Results

说明：本节使用 configs/config.yaml 中配置的模型 backend；latency、TTFT、tokens_per_second 和显存字段用于真实性能分析。cache_stats 不可用时 cache 字段为 -1，并记录 unavailable_reason。agent_meta 不进入 prompt，只通过 OpenAI-compatible extra_body 发送。

| scenario | mode | prompt_tokens | state_view_tokens | latency | ttft | tokens_per_second | peak_gpu_memory_mb | prefix_cache_hit_rate | cached_prompt_tokens | kv_cache_usage | cache_total_blocks | cache_agent_sessions | cache_tool_result_blocks | cache_shared_prefix_blocks | cache_scratchpad_blocks | cache_expired_branch_blocks | success_rate | score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tool-heavy | baseline | 13697.0000 | 0.0000 | 4.1937 | 1.6769 | 37.2935 | -1.0000 | 0.0000 | 0.0000 | 0.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | 100.0000 | 1.0000 |
| tool-heavy | optimized | 2086.0000 | 0.0000 | 11.7396 | 0.2962 | 61.4341 | -1.0000 | 0.0000 | 0.0000 | 0.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | 100.0000 | 1.0000 |
| long-session | full_history | 2322.3400 | 0.0000 | 0.8237 | 0.3195 | 39.3515 | -1.0000 | 0.0000 | 0.0000 | 0.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | 98.0000 | 0.9950 |
| long-session | summary_memory | 1665.9400 | 0.0000 | 1.3753 | 0.5063 | 41.2346 | -1.0000 | 0.0000 | 0.0000 | 0.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | 98.0000 | 0.9917 |
| long-session | event_sourced_memory | 2503.6000 | 1028.8400 | 3.4042 | 0.4822 | 51.6763 | -1.0000 | 0.0000 | 0.0000 | 0.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | 98.0000 | 0.9933 |
| multi-stage | full_history | 10845.2500 | 0.0000 | 4.8258 | 1.1154 | 47.9610 | -1.0000 | 0.0000 | 0.0000 | 0.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | 50.0000 | 0.8917 |
| multi-stage | summary_memory | 1550.2500 | 0.0000 | 5.4768 | 0.4411 | 48.3196 | -1.0000 | 0.0000 | 0.0000 | 0.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | 75.0000 | 0.9750 |
| multi-stage | event_sourced_memory | 1198.7500 | 398.2500 | 7.7163 | 0.3518 | 54.8612 | -1.0000 | 0.0000 | 0.0000 | 0.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | 100.0000 | 1.0000 |
| branching | baseline | 9585.3333 | 0.0000 | 10.8154 | 0.7685 | 48.8364 | -1.0000 | 0.0000 | 0.0000 | 0.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | 100.0000 | 1.0000 |
| branching | optimized | 2912.0000 | 0.0000 | 14.2270 | 0.2961 | 35.9898 | -1.0000 | 0.0000 | 0.0000 | 0.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | 100.0000 | 1.0000 |
| prefix-cache | baseline | 324.1667 | 0.0000 | 3.1623 | 0.6283 | 47.4520 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | 100.0000 | 1.0000 |
| prefix-cache | optimized | 358.0000 | 0.0000 | 4.1252 | 0.3076 | 40.4341 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | 100.0000 | 1.0000 |
| ablation | baseline | 6737.0000 | 0.0000 | 4.1131 | 2.5488 | 0.0000 | -1.0000 | 0.0000 | 0.0000 | 0.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | 100.0000 | 1.0000 |
| ablation | stable_prefix_only | 6737.0000 | 0.0000 | 1.9154 | 0.3481 | 0.0000 | -1.0000 | 0.0000 | 0.0000 | 0.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | 100.0000 | 1.0000 |
| ablation | skill_lazy_loading_only | 6627.0000 | 0.0000 | 4.1613 | 2.0001 | 0.0000 | -1.0000 | 0.0000 | 0.0000 | 0.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | 100.0000 | 1.0000 |
| ablation | tool_externalization_only | 1026.0000 | 0.0000 | 4.4873 | 0.4158 | 0.0000 | -1.0000 | 0.0000 | 0.0000 | 0.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | 100.0000 | 1.0000 |
| ablation | history_summary_only | 6568.0000 | 0.0000 | 2.8381 | 1.8770 | 0.0000 | -1.0000 | 0.0000 | 0.0000 | 0.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | 100.0000 | 1.0000 |
| ablation | full_optimized | 748.0000 | 0.0000 | 2.9360 | 0.4438 | 0.0000 | -1.0000 | 0.0000 | 0.0000 | 0.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | 100.0000 | 1.0000 |

## AgentMeta on/off 对比

暂无 agent_meta 实验数据。

## Cache pressure benchmark

暂无 cache-pressure 数据。

## TTL/Priority benchmark

暂无 ttl-priority 数据。

## cache_stats scope

- cache_stats_scope: unavailable. 当前 `/v1/agentmem/cache_stats` 采集的是服务端全局 cache 视图；若服务端未来支持 by_agent/by_session 过滤，可用 summary.csv 中记录的 agent_id 过滤本次实验。
- off 结果中如出现 expired_branch/tool_result/shared_prefix blocks，含义是全局历史缓存中已有这些 segment 的 block；off 请求本身没有携带 agent_meta，具体以 agent_meta_sent 和 audit_agent_meta.py 审计结果为准。

## cache_stats 可用性

| scenario | cache_stats_available | cache_stats_unavailable_reason | rows | cache_total_blocks | cache_agent_sessions | cache_tool_result_blocks | cache_shared_prefix_blocks | cache_scratchpad_blocks | cache_expired_branch_blocks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tool-heavy |  |  | 0 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 |
| long-session |  |  | 0 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 |
| multi-stage |  |  | 0 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 |
| branching |  |  | 0 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 |
| prefix-cache |  |  | 0 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 |
| ablation |  |  | 0 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 | -1.0000 |

## audit_agent_meta.py 审计摘要

暂无可审计的 agent_meta 行。

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

| mode | prompt_tokens | raw_tool_tokens | injected_tool_tokens | tool_compression_ratio | latency | ttft | peak_gpu_memory_mb | score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 13697.0000 | 6112.0000 | 6112.0000 | 1.0000 | 4.1937 | 1.6769 | -1.0000 | 1.0000 |
| optimized | 2086.0000 | 6112.0000 | 375.0000 | 0.0614 | 11.7396 | 0.2962 | -1.0000 | 1.0000 |

Prompt token reduction: 84.77%.

## 8. Long-session 结果

该场景复现多轮长生命周期会话中历史上下文持续增长的问题。

| mode | first_round_prompt_tokens | round_10_prompt_tokens | round_20_prompt_tokens | round_50_prompt_tokens | max_history_tokens | max_summary_tokens | max_state_view_tokens | avg_event_count | max_snapshot_count | early_fact_retention | success_rate | avg_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| full_history | 708.0000 | 1392.0000 | 2016.0000 | 3824.0000 | 1526.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.9093 | 98.0000 | 0.9950 |
| summary_memory | 359.0000 | 1424.0000 | 1972.0000 | 1967.0000 | 308.0000 | 383.0000 | 0.0000 | 0.0000 | 0.0000 | 0.9093 | 98.0000 | 0.9917 |
| event_sourced_memory | 499.0000 | 3469.0000 | 4631.0000 | 2461.0000 | 534.0000 | 0.0000 | 1329.0000 | 105.1600 | 19.0000 | 0.6633 | 98.0000 | 0.9933 |

## 9. Multi-stage 结果

该场景覆盖 planning -> tool_calling -> reflection -> final_answer 的多阶段智能体流程。

| mode | stage | prompt_tokens | state_view_tokens | event_count | snapshot_count | raw_tool_tokens | injected_tool_tokens | latency | early_fact_retention | score | success_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| full_history | planning | 705.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 6.3206 | 1.0000 | 1.0000 | 100.0000 |
| full_history | tool_calling | 14010.0000 | 0.0000 | 0.0000 | 0.0000 | 6112.0000 | 6112.0000 | 4.0166 | 1.0000 | 1.0000 | 100.0000 |
| full_history | reflection | 14179.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 4.8804 | 1.0000 | 0.6667 | 0.0000 |
| full_history | final_answer | 14487.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 4.0858 | 1.0000 | 0.9000 | 0.0000 |
| summary_memory | planning | 356.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 2.9645 | 1.0000 | 1.0000 | 100.0000 |
| summary_memory | tool_calling | 1762.0000 | 0.0000 | 0.0000 | 0.0000 | 6112.0000 | 375.0000 | 4.4081 | 1.0000 | 1.0000 | 100.0000 |
| summary_memory | reflection | 1910.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 5.8232 | 1.0000 | 1.0000 | 100.0000 |
| summary_memory | final_answer | 2173.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 8.7116 | 1.0000 | 0.9000 | 0.0000 |
| event_sourced_memory | planning | 510.0000 | 130.0000 | 4.0000 | 0.0000 | 0.0000 | 0.0000 | 7.9130 | 1.0000 | 1.0000 | 100.0000 |
| event_sourced_memory | tool_calling | 2007.0000 | 453.0000 | 9.0000 | 0.0000 | 6112.0000 | 375.0000 | 10.3357 | 1.0000 | 1.0000 | 100.0000 |
| event_sourced_memory | reflection | 1197.0000 | 546.0000 | 12.0000 | 1.0000 | 0.0000 | 0.0000 | 7.4858 | 1.0000 | 1.0000 | 100.0000 |
| event_sourced_memory | final_answer | 1081.0000 | 464.0000 | 15.0000 | 1.0000 | 0.0000 | 0.0000 | 5.1307 | 1.0000 | 1.0000 | 100.0000 |

## Event-Sourced Agent Memory

方法说明：Event Log 记录 Agent 执行事件；主模型响应可输出 memory_delta；当主模型未稳定输出时，可选 extractor 只生成同 schema 的结构化 memory_delta。Memory Manager 将 goals、constraints、facts、decisions、todos 和 artifact_refs 合并为 Task State View；Renderer 只渲染状态视图、artifact metadata 和最近上下文。

对比口径：full_history 注入完整历史和工具结果；summary_memory 使用工具外置和历史摘要；event_sourced_memory 使用模型产生的 memory_delta、artifact_refs 和 Task State View。Benchmark evaluator 可以按任务检查 required_facts，但 Memory 核心不写死任务关键词。

| scenario | memory_mode | prompt_tokens | state_view_tokens | success_rate | score | early_fact_retention | snapshot_count | memory_delta_count | fact_count | artifact_ref_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| long-session | full_history | 2322.3400 | 0.0000 | 98.0000 | 0.9950 | 0.9093 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| long-session | summary_memory | 1665.9400 | 0.0000 | 98.0000 | 0.9917 | 0.9093 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| long-session | event_sourced_memory | 2503.6000 | 1028.8400 | 98.0000 | 0.9933 | 0.6633 | 10.0000 | 19.3000 | 17.8000 | 4.6800 |
| multi-stage | full_history | 10845.2500 | 0.0000 | 50.0000 | 0.8917 | 1.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| multi-stage | summary_memory | 1550.2500 | 0.0000 | 75.0000 | 0.9750 | 1.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| multi-stage | event_sourced_memory | 1198.7500 | 398.2500 | 100.0000 | 1.0000 | 1.0000 | 0.5000 | 1.0000 | 0.0000 | 0.7500 |

结论：event_sourced_memory 相比 full_history 平均 prompt_tokens 降低约 18.51%。

早期事实保留：event_sourced_memory 相比 summary_memory 平均 early_fact_retention 更低 0.2278。

## 10. Branching 结果

该场景复现分支推理中公共上下文重复复制的问题，并通过 shared_prefix / expired_branch 等 segment_type 将分支基座与过期分支传递给 vLLM cache 管理原型。

| mode | branch_count | shared_context_tokens | branch_delta_tokens | duplicated_context_tokens | optimized_context_tokens | branch_saving_ratio | latency | score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 2 | 1820.0000 | 468.0000 | 4108.0000 | 4108.0000 | 0.0000 | 9.6744 | 1.0000 |
| baseline | 4 | 1820.0000 | 936.0000 | 8216.0000 | 8216.0000 | 0.0000 | 9.1372 | 1.0000 |
| baseline | 8 | 1820.0000 | 1872.0000 | 16432.0000 | 16432.0000 | 0.0000 | 13.6346 | 1.0000 |
| optimized | 2 | 1820.0000 | 468.0000 | 4108.0000 | 2288.0000 | 0.4430 | 14.3682 | 1.0000 |
| optimized | 4 | 1820.0000 | 936.0000 | 8216.0000 | 2756.0000 | 0.6646 | 14.1825 | 1.0000 |
| optimized | 8 | 1820.0000 | 1872.0000 | 16432.0000 | 3692.0000 | 0.7753 | 14.1302 | 1.0000 |

## 11. Prefix-cache 结果

该场景验证稳定 prompt prefix 对 prefix cache 复用、prefill 和 TTFT 的影响。vLLM 后端会尽力读取 /metrics。

| mode | unique_prefix_hashes | stable_prefix_tokens | prompt_tokens | latency | ttft | success_rate | avg_score | prefix_cache_hit_rate | cached_prompt_tokens | kv_cache_usage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 6 | 178.0000 | 324.1667 | 3.1623 | 0.6283 | 100.0000 | 1.0000 | -1.0000 | -1.0000 | -1.0000 |
| optimized | 1 | 175.0000 | 358.0000 | 4.1252 | 0.3076 | 100.0000 | 1.0000 | -1.0000 | -1.0000 | -1.0000 |

## 12. Ablation 结果

| variant | prompt_tokens | latency | raw_tool_tokens | injected_tool_tokens | tool_compression_ratio | history_tokens | summary_tokens | loaded_skill_tokens | unique_prefix_hashes | prefix_reuse_score | success | score | failure_reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 6737 | 4.1131138450000435 | 6112 | 6112 | 1.0 | 283 | 0 | 323 | 3 | 0.3333333333333333 | True | 1.0 |  |
| stable_prefix_only | 6737 | 1.9154216060005638 | 6112 | 6112 | 1.0 | 283 | 0 | 323 | 1 | 1.0 | True | 1.0 |  |
| skill_lazy_loading_only | 6627 | 4.161323500000435 | 6112 | 6112 | 1.0 | 283 | 0 | 80 | 3 | 0.3333333333333333 | True | 1.0 |  |
| tool_externalization_only | 1026 | 4.487253975000385 | 6112 | 375 | 0.061354712041884814 | 283 | 0 | 323 | 3 | 0.3333333333333333 | True | 1.0 |  |
| history_summary_only | 6568 | 2.838071955000487 | 6112 | 6112 | 1.0 | 101 | 13 | 323 | 3 | 0.3333333333333333 | True | 1.0 |  |
| full_optimized | 748 | 2.9359672649998174 | 6112 | 375 | 0.061354712041884814 | 101 | 13 | 80 | 1 | 1.0 | True | 1.0 |  |

## 13. 指标说明

- vLLM 指标依赖服务端版本和 /v1/agentmem/cache_stats 暴露情况；缺失时报告为 -1，并在 summary/report 中保留 unavailable_reason。
- 远程 vLLM 主模型服务通过 OpenAI-compatible API 提供推理能力，Agent-aware cache_stats 用于观察服务端 KV block 旁路元信息。
- Event-Sourced Memory 使用主模型按协议输出的 memory_delta；extractor 负责将不稳定输出规整为同一结构化状态更新。
- MemoryPlan JSONL 记录每次 LLM 请求前的 run_id、stage、context_id、segment_type、priority、ttl、included/excluded items 和 agent_meta。
- Agent-aware cache 实验关注 Agent 侧阶段、session、context、priority、ttl 与服务端 cache_stats 的关联观测。

## 14. 结论

- Token 降低最明显的场景：tool_heavy，prompt token reduction 约 84.77%。
- 工具上下文膨胀来源：tool-heavy 场景最大 raw_tool_tokens 为 6112。
- 当前报告聚合任务成功率：96.81%。
- Ablation 中 prompt_tokens 最低的配置：full_optimized。
- 真实 vLLM prefix 指标：当前结果未包含可用兼容指标，相关字段保持 -1。
- Agent-aware cache_stats：当前不可用或未返回目标字段，相关字段保持 -1。
- Agent-aware 实验通过 agent_meta 将 session、context、segment、priority 和 ttl 显式传递给 vLLM 服务端，支持长生命周期、多工具、多 session 的 cache 管理观测。

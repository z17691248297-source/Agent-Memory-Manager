# AgentMem Benchmark Report

## 1. 项目目标

AgentMem 是通用轻量 Agent Runtime + Memory Manager，用于让 Agent 通过 memory_delta 主动维护结构化任务状态，并通过 artifact_refs 管理工具结果。Benchmark 只用于评估不同任务场景下的上下文、质量和可追溯性表现；Memory 核心不依赖具体 benchmark 关键词。

## 2. 实验设置

| item | value |
| --- | --- |
| backend | vllm |
| model | Qwen2.5-7B-Instruct |
| client_os | Ubuntu 24.04.4 LTS |
| client_environment | WSL2 |
| model_server_os | unknown |
| official_os_compatibility_run | False |
| note | development run only |
| main_llm_backend | vllm |
| main_llm_base_url | http://47.108.145.21/v1 |
| main_llm_max_model_len | unknown |
| agent_meta_enabled | True |
| cache_stats_available | True |
| cache_stats_unavailable_reason | concurrent_agent_per_request_cache_not_collected |
| extractor_backend | vllm |
| extractor_model | Qwen2.5-7B-Instruct |
| extractor_base_url | http://47.108.145.21/v1 |
| extractor_enabled | True |
| extractor_effective | True |
| extractor_status | active |
| extractor_success_count | 48 |
| extractor_failure_count | 2 |
| scenarios | tool_heavy, multi_stage, branching, prefix_cache, cache_pressure, ttl_priority, concurrent_agents |
| mode | baseline, event_sourced_memory, full_history, optimized, summary_memory |
| repeat | 5 |
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
| prefix-cache | metric:prefix-cache | 120 |
| ablation | metric:ablation | 0 |
| cache-pressure | metric:cache-pressure | 40 |
| ttl-priority | metric:ttl-priority | 10 |

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
| tool_heavy | baseline | 10 | 50.0000 | 0.6154 |
| tool_heavy | optimized | 10 | 100.0000 | 1.0000 |
| multi_stage | full_history | 40 | 52.5000 | 0.7629 |
| multi_stage | summary_memory | 40 | 80.0000 | 0.9683 |
| multi_stage | event_sourced_memory | 40 | 50.0000 | 0.8167 |
| branching | baseline | 30 | 100.0000 | 1.0000 |
| branching | optimized | 30 | 100.0000 | 1.0000 |
| prefix_cache | baseline | 60 | 100.0000 | 1.0000 |
| prefix_cache | optimized | 60 | 100.0000 | 1.0000 |
| cache_pressure | sessions_4 | 40 | 100.0000 | 1.0000 |
| ttl_priority | ttl_priority | 10 | 100.0000 | 1.0000 |
| concurrent_agents | optimized | 30 | 100.0000 | 1.0000 |

## 实验有效性检查

- validation_status: PASS
- invalid_trials: none

## 正式统计

| metric | valid_n | total_n | mean | median | std | min | max | p50 | p95 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| prompt_tokens | 400 | 400 | 2920.7525 | 1694.0000 | 3697.6919 | 49.0000 | 16432.0000 | 1694.0000 | 11771.0000 |
| output_tokens | 400 | 400 | 266.5225 | 211.5000 | 182.3659 | 0.0000 | 696.0000 | 211.5000 | 512.0000 |
| total_tokens | 400 | 400 | 2615.6250 | 1985.0000 | 2849.1461 | 334.0000 | 12985.0000 | 1985.0000 | 6031.8000 |
| total_latency | 400 | 400 | 3.6524 | 2.9026 | 2.9171 | 0.1006 | 16.6390 | 2.9026 | 8.7967 |
| latency | 400 | 400 | 3.6524 | 2.9026 | 2.9171 | 0.1006 | 16.6390 | 2.9026 | 8.7967 |
| ttft | 380 | 400 | 0.4001 | 0.1591 | 0.8363 | 0.1183 | 8.5876 | 0.1591 | 1.1624 |
| tokens_per_second | 400 | 400 | 78.9529 | 61.9394 | 37.0721 | 0.0000 | 136.4286 | 61.9394 | 133.5827 |
| peak_gpu_memory_mb | 0 | 400 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| kv_cache_usage | 0 | 400 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| prefix_cache_hit_rate | 0 | 400 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| cached_prompt_tokens | 0 | 400 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| score | 400 | 400 | 0.9452 | 1.0000 | 0.1656 | 0.2308 | 1.0000 | 1.0000 | 1.0000 |

## Configured Model Backend Results

说明：本节使用配置文件中的模型 backend。不可用指标显示为 `unavailable`，并通过 *_status/*_reason 字段记录原因；服务级全局 cache 指标不能解释为单 Agent 指标。agent_meta 不进入 prompt，只通过 OpenAI-compatible extra_body 发送。

| scenario | mode | prompt_tokens | state_view_tokens | latency | ttft | tokens_per_second | peak_gpu_memory_mb | prefix_cache_hit_rate | cached_prompt_tokens | kv_cache_usage | cache_total_blocks | cache_agent_sessions | cache_tool_result_blocks | cache_shared_prefix_blocks | cache_scratchpad_blocks | cache_expired_branch_blocks | success_rate | score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tool-heavy | baseline | 8490.3000 | unavailable | 1.9826 | 0.2826 | 27.4682 | unavailable | unavailable | unavailable | unavailable | 6579.0000 | 298.0000 | unavailable | unavailable | unavailable | unavailable | 50.0000 | 0.6154 |
| tool-heavy | optimized | 1811.9000 | unavailable | 7.4004 | 0.1867 | 88.5534 | unavailable | unavailable | unavailable | unavailable | 6579.0000 | 303.0000 | unavailable | unavailable | unavailable | unavailable | 100.0000 | 1.0000 |
| multi-stage | full_history | 6791.3750 | 0.0000 | 3.0876 | 0.2817 | 36.4020 | unavailable | unavailable | unavailable | unavailable | 6579.0000 | 307.0000 | unavailable | unavailable | unavailable | unavailable | 52.5000 | 0.7629 |
| multi-stage | summary_memory | 1601.3000 | 0.0000 | 3.3131 | 0.2649 | 92.6331 | unavailable | unavailable | unavailable | unavailable | 6579.0000 | 313.0000 | unavailable | unavailable | unavailable | unavailable | 80.0000 | 0.9683 |
| multi-stage | event_sourced_memory | 1327.8500 | 497.9750 | 4.2381 | 0.2356 | 91.1623 | unavailable | unavailable | unavailable | unavailable | 6579.0000 | 318.0000 | unavailable | unavailable | unavailable | unavailable | 50.0000 | 0.8167 |
| branching | baseline | 9585.3333 | unavailable | 6.1032 | 0.2404 | 94.7345 | unavailable | unavailable | unavailable | unavailable | 6579.0000 | 318.0000 | unavailable | unavailable | unavailable | unavailable | 100.0000 | 1.0000 |
| branching | optimized | 2912.0000 | unavailable | 6.1116 | 0.2549 | 96.8279 | unavailable | unavailable | unavailable | unavailable | 6579.0000 | 318.0000 | unavailable | unavailable | unavailable | unavailable | 100.0000 | 1.0000 |
| prefix-cache | baseline | 326.2333 | unavailable | 2.0045 | 0.2030 | 88.9487 | unavailable | unavailable | unavailable | unavailable | 6579.0000 | 318.0000 | unavailable | unavailable | unavailable | unavailable | 100.0000 | 1.0000 |
| prefix-cache | optimized | 359.3667 | unavailable | 1.7690 | 0.3659 | 73.8445 | unavailable | unavailable | unavailable | unavailable | 6579.0000 | 318.0000 | unavailable | unavailable | unavailable | unavailable | 100.0000 | 1.0000 |
| cache-pressure | sessions_4 | 5483.8000 | unavailable | 2.1775 | 0.5458 | 67.3364 | unavailable | unavailable | unavailable | unavailable | 6587.0000 | 318.0000 | unavailable | unavailable | unavailable | unavailable | 100.0000 | 1.0000 |
| ttl-priority | ttl_priority | 3958.0000 | unavailable | 6.2581 | 0.6082 | 88.9898 | unavailable | unavailable | unavailable | unavailable | 6579.0000 | 318.0000 | unavailable | unavailable | unavailable | unavailable | 100.0000 | 1.0000 |
| concurrent-agents | optimized | 49.0000 | unavailable | 6.6350 | 1.4929 | 83.8410 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 100.0000 | 1.0000 |

## AgentMeta on/off 对比

| agent_meta_enabled | scenario | prompt_tokens | latency | ttft | tokens_per_second | cache_total_blocks | cache_agent_sessions | cache_tool_result_blocks | cache_shared_prefix_blocks | cache_scratchpad_blocks | cache_expired_branch_blocks | success_rate | score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| True | tool-heavy | 5151.1000 | 4.6915 | 0.2187 | 58.0108 | 6579.0000 | 303.0000 | unavailable | unavailable | unavailable | unavailable | 75.0000 | 0.8077 |
| True | multi-stage | 3240.1750 | 3.5463 | 0.2577 | 73.3991 | 6579.0000 | 318.0000 | unavailable | unavailable | unavailable | unavailable | 60.8333 | 0.8493 |
| True | branching | 6248.6667 | 6.1074 | 0.2476 | 95.7812 | 6579.0000 | 318.0000 | unavailable | unavailable | unavailable | unavailable | 100.0000 | 1.0000 |
| True | prefix-cache | 342.8000 | 1.8868 | 0.2844 | 81.3966 | 6579.0000 | 318.0000 | unavailable | unavailable | unavailable | unavailable | 100.0000 | 1.0000 |
| True | cache-pressure | 5483.8000 | 2.1775 | 0.5458 | 67.3364 | 6587.0000 | 318.0000 | unavailable | unavailable | unavailable | unavailable | 100.0000 | 1.0000 |
| True | ttl-priority | 3958.0000 | 6.2581 | 0.6082 | 88.9898 | 6579.0000 | 318.0000 | unavailable | unavailable | unavailable | unavailable | 100.0000 | 1.0000 |
| False | concurrent-agents | 49.0000 | 6.6350 | 1.4929 | 83.8410 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | 100.0000 | 1.0000 |

## Cache pressure benchmark

| segment_type | sessions | prompt_tokens | latency | ttft | tokens_per_second | cache_total_blocks | cache_agent_sessions | cache_tool_result_blocks | cache_shared_prefix_blocks | cache_scratchpad_blocks | cache_expired_branch_blocks | success_rate | score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| shared_prefix | 4 | 5483.0000 | 2.1654 | 0.5581 | 65.4753 | 6587.0000 | 318.0000 | unavailable | unavailable | unavailable | unavailable | 100.0000 | 1.0000 |
| tool_schema | 4 | 5484.0000 | 1.9816 | 0.5658 | 65.9655 | 6587.0000 | 318.0000 | unavailable | unavailable | unavailable | unavailable | 100.0000 | 1.0000 |
| tool_result | 4 | 5486.0000 | 2.6620 | 0.6461 | 70.7066 | 6587.0000 | 318.0000 | unavailable | unavailable | unavailable | unavailable | 100.0000 | 1.0000 |
| scratchpad | 4 | 5485.0000 | 2.1637 | 0.4651 | 72.0703 | 6587.0000 | 318.0000 | unavailable | unavailable | unavailable | unavailable | 100.0000 | 1.0000 |
| expired_branch | 4 | 5481.0000 | 1.9150 | 0.4942 | 62.4641 | 6587.0000 | 318.0000 | unavailable | unavailable | unavailable | unavailable | 100.0000 | 1.0000 |

## TTL/Priority benchmark

| segment_type | priority | ttl | prompt_tokens | latency | ttft | cache_total_blocks | cache_tool_result_blocks | cache_shared_prefix_blocks | cache_scratchpad_blocks | cache_expired_branch_blocks | success_rate | score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| shared_prefix | high | 3600 | 4054.0000 | 6.6754 | 0.9387 | 6579.0000 | unavailable | unavailable | unavailable | unavailable | 100.0000 | 1.0000 |
| tool_schema | high | 1800 | 4054.0000 | 5.8057 | 0.3632 | 6579.0000 | unavailable | unavailable | unavailable | unavailable | 100.0000 | 1.0000 |
| tool_result | low | 120 | 3974.0000 | 6.4825 | 1.0089 | 6579.0000 | unavailable | unavailable | unavailable | unavailable | 100.0000 | 1.0000 |
| scratchpad | low | 60 | 3894.0000 | 5.9811 | 0.3651 | 6579.0000 | unavailable | unavailable | unavailable | unavailable | 100.0000 | 1.0000 |
| expired_branch | drop | 1 | 3814.0000 | 6.3457 | 0.3651 | 6579.0000 | unavailable | unavailable | unavailable | unavailable | 100.0000 | 1.0000 |

## cache_stats scope

- cache_stats_scope: global cache view. 当前 `/v1/agentmem/cache_stats` 采集的是服务端全局 cache 视图；若服务端未来支持 by_agent/by_session 过滤，可用 summary.csv 中记录的 agent_id 过滤本次实验。
- off 结果中如出现 expired_branch/tool_result/shared_prefix blocks，含义是全局历史缓存中已有这些 segment 的 block；off 请求本身没有携带 agent_meta，具体以 agent_meta_sent 和 audit_agent_meta.py 审计结果为准。

## cache_stats 可用性

| scenario | cache_stats_available | cache_stats_unavailable_reason | rows | cache_total_blocks | cache_agent_sessions | cache_tool_result_blocks | cache_shared_prefix_blocks | cache_scratchpad_blocks | cache_expired_branch_blocks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tool-heavy | True | unavailable | 20 | 6579.0000 | 303.0000 | unavailable | unavailable | unavailable | unavailable |
| multi-stage | True | unavailable | 120 | 6579.0000 | 318.0000 | unavailable | unavailable | unavailable | unavailable |
| branching | True | unavailable | 60 | 6579.0000 | 318.0000 | unavailable | unavailable | unavailable | unavailable |
| prefix-cache | True | unavailable | 120 | 6579.0000 | 318.0000 | unavailable | unavailable | unavailable | unavailable |
| cache-pressure | True | unavailable | 40 | 6587.0000 | 318.0000 | unavailable | unavailable | unavailable | unavailable |
| ttl-priority | True | unavailable | 10 | 6579.0000 | 318.0000 | unavailable | unavailable | unavailable | unavailable |
| concurrent-agents | False | concurrent_agent_per_request_cache_not_collected | 30 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |

## audit_agent_meta.py 审计摘要

| agent_meta_enabled | rows | agent_meta_sent_true | agent_meta_sent_false | empty_segment_rows | segment_type_distribution |
| --- | --- | --- | --- | --- | --- |
| True | 370 | 190 | 180 | 180 | <empty>:180; assistant_message:30; expired_branch:10; scratchpad:70; shared_prefix:10; tool_result:60; tool_schema:10 |
| False | 30 | 30 | 0 | 0 | scratchpad:30 |

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
| baseline | 8490.3000 | 6112.0000 | 5058.0000 | 1.0000 | 1.9826 | 0.2826 | unavailable | 0.6154 |
| optimized | 1811.9000 | 6112.0000 | 375.0000 | 0.0614 | 7.4004 | 0.1867 | unavailable | 1.0000 |

Prompt token reduction: 78.66%.

## 8. Long-session 结果

该场景复现多轮长生命周期会话中历史上下文持续增长的问题。

暂无 long-session 数据。

## 9. Multi-stage 结果

该场景覆盖 planning -> tool_calling -> reflection -> final_answer 的多阶段智能体流程。

| mode | stage | prompt_tokens | state_view_tokens | event_count | snapshot_count | raw_tool_tokens | injected_tool_tokens | latency | early_fact_retention | score | success_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| full_history | planning | 705.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 2.6739 | 1.0000 | 1.0000 | 100.0000 |
| full_history | tool_calling | 8668.3000 | 0.0000 | 0.0000 | 0.0000 | 6112.0000 | 5058.0000 | 1.5600 | 1.0000 | 0.7083 | 50.0000 |
| full_history | reflection | 8762.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 4.1716 | 1.0000 | 0.7083 | 50.0000 |
| full_history | final_answer | 9030.2000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 3.9451 | 1.0000 | 0.6350 | 10.0000 |
| summary_memory | planning | 399.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 1.7119 | 1.0000 | 1.0000 | 100.0000 |
| summary_memory | tool_calling | 1769.6000 | 0.0000 | 0.0000 | 0.0000 | 6112.0000 | 375.0000 | 3.3059 | 1.0000 | 1.0000 | 100.0000 |
| summary_memory | reflection | 1944.3000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 3.7869 | 1.0000 | 0.9833 | 90.0000 |
| summary_memory | final_answer | 2292.3000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 4.4478 | 1.0000 | 0.8900 | 30.0000 |
| event_sourced_memory | planning | 525.0000 | 103.0000 | 4.0000 | 0.0000 | 0.0000 | 0.0000 | 1.9583 | 1.0000 | 1.0000 | 100.0000 |
| event_sourced_memory | tool_calling | 2081.1000 | 540.2000 | 9.8000 | 0.8000 | 6112.0000 | 375.0000 | 6.4471 | 1.0000 | 0.7500 | 50.0000 |
| event_sourced_memory | reflection | 1345.0000 | 657.9000 | 13.8000 | 1.0000 | 0.0000 | 0.0000 | 4.2199 | 1.0000 | 0.7667 | 40.0000 |
| event_sourced_memory | final_answer | 1360.3000 | 690.8000 | 17.8000 | 1.0000 | 0.0000 | 0.0000 | 4.3271 | 1.0000 | 0.7500 | 10.0000 |

## Event-Sourced Agent Memory

方法说明：Event Log 记录 Agent 执行事件；主模型响应可输出 memory_delta；当主模型未稳定输出时，可选 extractor 只生成同 schema 的结构化 memory_delta。Memory Manager 将 goals、constraints、facts、decisions、todos 和 artifact_refs 合并为 Task State View；Renderer 只渲染状态视图、artifact metadata 和最近上下文。

对比口径：full_history 注入完整历史和工具结果；summary_memory 使用工具外置和历史摘要；event_sourced_memory 使用模型产生的 memory_delta、artifact_refs 和 Task State View。Benchmark evaluator 可以按任务检查 required_facts，但 Memory 核心不写死任务关键词。

| scenario | memory_mode | prompt_tokens | state_view_tokens | success_rate | score | early_fact_retention | snapshot_count | memory_delta_count | fact_count | artifact_ref_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| multi-stage | full_history | 6791.3750 | 0.0000 | 52.5000 | 0.7629 | 1.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| multi-stage | summary_memory | 1601.3000 | 0.0000 | 80.0000 | 0.9683 | 1.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| multi-stage | event_sourced_memory | 1327.8500 | 497.9750 | 50.0000 | 0.8167 | 1.0000 | 0.7000 | 2.3500 | 0.4750 | 0.8000 |

结论：event_sourced_memory 相比 full_history 平均 prompt_tokens 降低约 80.45%。

早期事实保留：event_sourced_memory 相比 summary_memory 平均 early_fact_retention 更高 0.0000。

## 10. Branching 结果

该场景复现分支推理中公共上下文重复复制的问题，并通过 shared_prefix / expired_branch 等 segment_type 将分支基座与过期分支传递给 vLLM cache 管理原型。

| mode | branch_count | shared_context_tokens | branch_delta_tokens | duplicated_context_tokens | optimized_context_tokens | branch_saving_ratio | latency | score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 2 | 1820.0000 | 468.0000 | 4108.0000 | 4108.0000 | 0.0000 | 6.0575 | 1.0000 |
| baseline | 4 | 1820.0000 | 936.0000 | 8216.0000 | 8216.0000 | 0.0000 | 6.1569 | 1.0000 |
| baseline | 8 | 1820.0000 | 1872.0000 | 16432.0000 | 16432.0000 | 0.0000 | 6.0951 | 1.0000 |
| optimized | 2 | 1820.0000 | 468.0000 | 4108.0000 | 2288.0000 | 0.4430 | 6.0034 | 1.0000 |
| optimized | 4 | 1820.0000 | 936.0000 | 8216.0000 | 2756.0000 | 0.6646 | 6.1911 | 1.0000 |
| optimized | 8 | 1820.0000 | 1872.0000 | 16432.0000 | 3692.0000 | 0.7753 | 6.1402 | 1.0000 |

## 11. Prefix-cache 结果

该场景验证稳定 prompt prefix 对 prefix cache 复用、prefill 和 TTFT 的影响。vLLM 后端会尽力读取 /metrics。

| mode | unique_prefix_hashes | stable_prefix_tokens | prompt_tokens | latency | ttft | success_rate | avg_score | prefix_cache_hit_rate | cached_prompt_tokens | kv_cache_usage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 30 | 178.0000 | 326.2333 | 2.0045 | 0.2030 | 100.0000 | 1.0000 | unavailable | unavailable | unavailable |
| optimized | 1 | 175.0000 | 359.3667 | 1.7690 | 0.3659 | 100.0000 | 1.0000 | unavailable | unavailable | unavailable |

## 12. Ablation 结果

暂无 ablation 数据。

## 13. 并发结果

| concurrency | agents | latency | ttft | throughput_tasks_per_second | peak_gpu_memory_mb | kv_cache_usage | prefix_cache_hit_rate | success_rate | score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 5.5881 | 0.9845 | 0.1646 | unavailable | unavailable | unavailable | 100.0000 | 1.0000 |
| 2 | 2 | 5.1305 | 0.1710 | 0.2139 | unavailable | unavailable | unavailable | 100.0000 | 1.0000 |
| 4 | 4 | 5.8297 | 0.3189 | 0.1972 | unavailable | unavailable | unavailable | 100.0000 | 1.0000 |
| 8 | 8 | 7.5447 | 2.4740 | 0.2013 | unavailable | unavailable | unavailable | 100.0000 | 1.0000 |

## 14. 指标说明

- vLLM 指标依赖服务端版本、Prometheus /metrics 和 /v1/agentmem/cache_stats 暴露情况；缺失时显示 unavailable，并保留 status/reason。
- 远程 vLLM 主模型服务通过 OpenAI-compatible API 提供推理能力，Agent-aware cache_stats 用于观察服务端 KV block 旁路元信息。
- Event-Sourced Memory 使用主模型按协议输出的 memory_delta；extractor 负责将不稳定输出规整为同一结构化状态更新。
- MemoryPlan JSONL 记录每次 LLM 请求前的 run_id、stage、context_id、segment_type、priority、ttl、included/excluded items 和 agent_meta。
- Agent-aware cache 实验关注 Agent 侧阶段、session、context、priority、ttl 与服务端 cache_stats 的关联观测。
- P95 使用 inclusive linear interpolation：rank=(n-1)*0.95，在相邻排序样本之间线性插值。

## 15. 结论

- Token 降低最明显的场景：tool_heavy，prompt token reduction 约 78.66%。
- 工具上下文膨胀来源：tool-heavy 场景最大 raw_tool_tokens 为 6112.0000。
- 当前报告聚合任务成功率：87.00%。
- Ablation 中 prompt_tokens 最低的配置：暂无。
- 真实 vLLM prefix 指标：当前结果未包含可用兼容指标，相关字段为 unavailable。
- Agent-aware cache_stats：已读取到 /v1/agentmem/cache_stats。
- Agent-aware 实验通过 agent_meta 将 session、context、segment、priority 和 ttl 显式传递给 vLLM 服务端，支持长生命周期、多工具、多 session 的 cache 管理观测。

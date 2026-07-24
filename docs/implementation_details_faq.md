# AgentMem 关键实现细节说明

本文基于当前仓库源码整理，重点覆盖答辩时容易被追问的日志工具、评分、token、性能指标和 CSV 结果生成逻辑。结论里凡是说“启发式”或“简化版”的地方，都是源码中实际看到的实现。

## 1. 日志分析工具 log_analyzer 的实现

### 1.1 代码位置和入口

- 工具入口在 `agentmem/tools/log_analyzer.py`，函数是 `analyze_logs(input_text: str, context: dict | None = None) -> str`。
- 工具注册在 `agentmem/tools/tool_registry.py` 的 `build_default_registry()`：`registry.register_handler("log_analyzer", analyze_logs)`。
- 路由入口在 `agentmem/tools/router.py` 的 `ToolRouter.route()`，这是规则版路由器，不调用 LLM。
- 执行入口在 `agentmem/tools/executor.py` 的 `ToolExecutor.execute()`。
- 摘要逻辑不在 `log_analyzer.py` 本身，而在 `agentmem/memory/tool_result_store.py` 的 `ToolResultStore.summarize()` 和 `agentmem/tools/log_summary.py` 的 `analyze_log_text()` / `format_log_summary()`。

### 1.2 输入是什么

`analyze_logs()` 接受两类输入：

- `input_text`：用户 query 或工具调用入参。它会从文本行中匹配 `dataset: ...`、`optional_log_path: ...`、`log_path: ...`。
- `context`：benchmark 会通过 `_task_tool_context()` 把 task JSONL 中的 `dataset` / `optional_log_path` / `log_path` 传入工具上下文。

路径解析逻辑在 `agentmem/tools/log_analyzer.py::_dataset_path()`：

1. 优先读 `context["optional_log_path"]`；
2. 其次读 `context["dataset"]`；
3. 再从 `input_text` 中匹配 `dataset:` / `optional_log_path:` / `log_path:`；
4. 相对路径会拼到 `PROJECT_ROOT` 下；
5. 如果目标文件存在且是文件，就直接 `read_text(encoding="utf-8")`。

如果没有传入有效路径，则回退到 `DEFAULT_TOOL_HEAVY_DATASET = benchmarks/fixtures/tool_heavy_scaled.log`。如果该 fixture 也不存在，则调用 `generate_original_tool_heavy_log(line_count=3000)` 生成可复现的模拟大日志。

### 1.3 如何读取日志，是否限制 workspace

`log_analyzer.py` 目前没有像 `file_reader.py` / `csv_analyzer.py` 那样做严格的 allowed-root 校验。

- `file_reader.py` 只允许 `benchmarks/fixtures` 或 `examples`。
- `csv_analyzer.py` 只允许 `benchmarks/fixtures`。
- `log_analyzer.py` 只是把相对路径解析到 `PROJECT_ROOT` 下，并检查文件存在，不做 `relative_to(allowed_root)` 之类的限制。

因此答辩时要如实说明：日志工具当前是 benchmark-oriented 的简化实现，默认读取固定 fixture；路径安全边界比 `file_reader` / `csv_analyzer` 弱，当前没有单独限制到 `benchmarks/fixtures`。

### 1.4 工具本体是否分析日志

严格说，`log_analyzer.py::analyze_logs()` 本体并不分析日志，它只返回原始日志文本。

真正的“日志分析”发生在工具执行器保存结果时：

1. `ToolExecutor.execute()` 调用 handler 得到 `raw_result`；
2. `ToolExecutor.execute()` 调用 `self.result_store.summarize(raw_result, tool_name)`；
3. `ToolResultStore.summarize()` 发现 `tool_name == "log_analyzer"` 后调用 `_summarize_log()`；
4. `_summarize_log()` 调用 `format_log_summary(text)`；
5. `format_log_summary()` 调用 `analyze_log_text(text)`，并把结果 JSON pretty-print 成字符串。

### 1.5 识别哪些错误模式

日志摘要规则在 `agentmem/tools/log_summary.py`：

- `LOG_KEYWORDS` 包含：
  - `KV cache allocation failed`
  - `CUDA OOM`
  - `timeout`
  - `KV cache`
  - `OOM`
  - `exception`
  - `failed`
- `SEVERITIES` 包含：
  - `ERROR`
  - `WARNING`
  - `WARN`
  - `INFO`
  - `DEBUG`
  - `TRACE`

`analyze_log_text()` 对每一行做两件事：

- 用 `_severity()` 通过正则 `\b{severity}\b` 判断 severity；
- 用 `matched_keywords()` 做大小写不敏感的关键词包含匹配。

如果一行既没有命中关键词，也不是 `ERROR` / `WARN` / `WARNING`，就跳过，不进入 error group。

注意几个边界：

- `ERROR` 是 severity，不是 `LOG_KEYWORDS`，所以能进入分组，但如果没有其他关键词，signature 会用正则清洗后的日志行。
- `Exception` 如果写成 `exception` / `Exception`，会命中 `exception` 关键词，因为匹配前统一 lower。
- `Traceback` 不在 `LOG_KEYWORDS`，也不是 severity；单独一行 `Traceback ...` 没有 `ERROR/WARN` 时不会被当作关键错误分组。
- `CUDA out of memory` 不在关键词列表里；只有包含 `OOM` 或 `CUDA OOM` 才会被稳定识别。
- `Connection error` 不在关键词列表里；除非该行带 `ERROR` severity 或 `failed` / `exception` 等关键词，否则不会作为重点错误模式。

### 1.6 是正则、关键词，还是 LLM 总结

当前是规则/关键词实现，不调用 LLM。

- severity 识别使用正则：`re.search(rf"\b{severity}\b", line, flags=re.IGNORECASE)`。
- 错误关键词使用字符串包含匹配：`keyword.lower() in lowered`。
- signature 生成使用正则做数字和十六进制地址归一化，然后按关键词或清洗后的行聚合。
- root cause candidates 是按固定优先级遍历关键词和 error groups 得到，不是模型推理。

所以答辩时不要把它描述成智能日志诊断器。它是 deterministic log summarizer：按规则抽取 severity、关键词、样例行和根因候选。

### 1.7 输出结构是什么

`analyze_log_text()` 返回 dict，`format_log_summary()` 输出 JSON 字符串，主要字段是：

- `total_lines`：日志总行数；
- `severity_counts`：按 severity 计数，例如 `INFO`、`ERROR`、`WARN`；
- `error_groups`：错误分组列表，每组包含：
  - `signature`
  - `count`
  - `first_line`
  - `last_line`
  - `sample`
  - `keywords`
  - `severity`
- `root_cause_candidates`：最多 6 条根因候选，按 `KV cache allocation failed`、`CUDA OOM`、`OOM`、`timeout`、`KV cache`、`exception`、`failed` 的优先级生成。

当前输出没有单独命名为 `summary`、`error_count`、`warning_count` 的字段；对应信息在 `severity_counts` 和 JSON 摘要里体现。它会保留关键行样例，但不是完整上下文窗口，只保留每个分组前 `max_samples_per_group=3` 条 sample，且每条 sample 截断到 500 字符。

### 1.8 ToolResult / tool_store 流程

工具结果进入 `ToolResult` 和 `ToolResultStore` 的流程如下：

```text
user query
-> AgentRuntime.run()
-> ToolRouter.route()
   - 仅 stage == "tool_calling" 才路由工具
   - log_analyzer 命中关键词：日志、log、error、oom、timeout、kv cache、failed
-> AgentRuntime._execute_tool()
-> ToolExecutor.execute("log_analyzer", input_text, context)
   - 查 ToolSpec
   - 检查 enabled / permission
   - 用 ThreadPoolExecutor 执行 handler，并按 timeout_seconds 超时
-> analyze_logs()
   - 读取 task/context 指定日志，或默认 tool_heavy_scaled.log，或生成模拟日志
   - 返回原始日志文本 raw_result
-> ToolResultStore.summarize(raw_result, "log_analyzer")
   - 调用 log_summary.analyze_log_text()
   - 返回结构化 JSON 摘要 summary
-> ToolResult(...)
   - raw_result = 完整日志
   - summary = JSON 摘要
   - raw_token_len = estimate_tokens(raw_result)
   - summary_token_len = estimate_tokens(summary)
-> ToolResultStore.save()
   - 写 results/tool_store/raw/{result_id}.txt
   - 写 results/tool_store/chunks/{result_id}_chunk_N.txt
   - 写 results/tool_store/index/{result_id}.json，index 不内联 raw_result
   - artifacts 记录 result_id、tool_name、artifact_type、path、token_count、description
-> memory.add_tool_result(result)
   - baseline 把 prompt_display_text(result) 放进消息
   - optimized / event_sourced_memory 只把 result_id、raw_token_len、summary_token_len、summary 放进 prompt/state
```

### 1.9 raw_tool_tokens 和 injected_tool_tokens 是否在这里统计

不是在 `log_analyzer.py` 里统计，而是在执行器、存储和 runtime 中统计：

- `ToolExecutor.execute()` 初次构造 `ToolResult` 时：
  - `raw_token_len = estimate_tokens(raw_result)`
  - `summary_token_len = estimate_tokens(summary)`
- `ToolResultStore.save()` 写 raw 文件后，会用实际存储的 `raw_text` 重新计算 `tool_result.raw_token_len = estimate_tokens(raw_text)`。如果配置了 `raw_store_max_mb` 并截断，最终 raw token 以截断后的存储文本为准。
- `AgentRuntime.run()` 汇总本轮工具 token：
  - `raw_tool_tokens = sum(result.raw_token_len for result in tool_results)`
  - optimized/event-sourced memory 下 `injected_tool_tokens = sum(result.summary_token_len for result in tool_results)`
  - baseline/full_history 下 `injected_tool_tokens = sum(prompt_display_tokens(result, estimate_tokens) for result in tool_results)`

`ToolResult.compression_ratio` 的公式是 `summary_token_len / raw_token_len`，但只有启用工具结果外置时，runtime 的 `tool_compression_ratio` 才采用各工具 ratio 的平均值；baseline 下强制为 `1.0`。

## 2. success_rate 是怎么判断的

### 2.1 success 字段在哪里产生

有两层 success：

1. runtime 结构性成功：`agentmem/runtime/agent.py::AgentRuntime.run()` 生成 `metrics["success"]`。
2. benchmark evaluator 成功：`agentmem/evaluation.py::evaluate_task()` / `evaluate_metric_checks()` 生成最终写入 CSV 的 `success`。

对 benchmark CSV 来说，关键是第二层。`agentmem/benchmark.py` 中各场景在生成 row 后都会 `row.update(evaluation_fields(result))`，因此 evaluator 的 `success` / `score` 会覆盖或补充 runtime metrics 中的 `success`。

### 2.2 runtime 的 structural_success

`AgentRuntime.run()` 中的结构性成功定义为：

```python
structural_success = bool(assistant_response.strip()) and not llm_error and all(
    result.status not in {"failed", "timeout", "permission_denied"} for result in tool_results
)
```

这只说明流程可执行：有非空回答、LLM 没报错、工具没有 failed/timeout/permission_denied。源码注释和 evaluator 设计都表明，它不等同于任务质量成功。

### 2.3 benchmark evaluator 的 success

`agentmem/evaluation.py::evaluate_task()` 是 deterministic evaluator。它根据 task JSONL 中显式声明的条件构造 checks：

- `expect_answer`：回答非空；
- `expected_tools`：`metrics["tool_names"]` 中必须包含指定工具；
- `answer_keywords`：回答文本中必须包含关键词；
- `required_answer_points`：回答文本中必须包含要求点；
- `required_facts`：回答、retention_text、metrics 拼成的 haystack 中必须包含事实；
- `branch_keywords`：分支文本中必须包含关键词；
- `min_branch_count`：branch_count 达标；
- `expected_stages`：已完成 stage 列表必须完全匹配；
- `min_metrics` / `max_metrics`：指定指标必须满足上下限。

公式是：

```text
score = passed_checks / total_checks
success = score >= success_threshold
```

`success_threshold` 默认是 `1.0`，即所有 checks 都通过才成功。`evaluation_fields()` 输出的是 bool `success`、float `score`、失败项字符串和通过/总检查数。

### 2.4 success_rate 公式

`success_rate` 在 `agentmem/metrics/summarizer.py::_success_rate()` 计算：

```text
success_rate = success 为 True 的 row 数 / 有 success 字段的 row 数 * 100
```

实现细节：

- `_to_bool()` 把字符串 `true`、`1`、`yes`、`on` 识别为 True；
- 空值或缺失 success 不计入分母；
- 没有有效 success 时返回 `0.0`；
- 输出单位是百分比，所以成功率 100% 写成 `100.0`，不是 `1.0`。

### 2.5 各 scenario 的 success 判断

#### tool-heavy

入口：`agentmem/benchmark.py::_run_tool_heavy()`。

任务定义：`benchmarks/tasks/tool_heavy.jsonl`。

主要检查：

- `expect_answer: true`，回答必须非空；
- `expected_tools: ["log_analyzer"]`，必须实际调用 log_analyzer；
- `answer_keywords: ["oom", "timeout", "kv cache"]`，回答必须覆盖这些关键词；
- `required_facts: ["OOM", "timeout", "KV cache"]`，回答、metrics 或 retention 中必须保留这些事实；
- `required_answer_points: ["oom", "timeout", "kv cache"]`；
- `min_metrics: {"raw_tool_tokens": 1000, "injected_tool_tokens": 1}`；
- `success_threshold: 1.0`。

optimized 模式下如果首次 `result.success == False`，`_run_tool_heavy()` 会调用 `_refill_missing_evidence()` 尝试从 artifact/retention 中补证据并重新评价。

#### long-session

入口：`agentmem/benchmark.py::_run_long_session()`。

任务定义：`benchmarks/tasks/long_session.jsonl`。多数轮次只有 `expect_answer: true`，因此只要求非空回答。第 5/10/15/... 轮有 `expected_tools: ["calculator"]`，要求调用计算器。第 50 轮是最终保留测试，要求：

- 回答包含 `constraint_alpha_001`、`工具结果外置`、`任务成功率`；
- required facts 中还包括 `AgentMem` 和 `Event-Sourced Memory`；
- required answer points 也要求覆盖关键点。

`_evaluate_agent_task()` 会把 `_agent_retention_text(agent)` 放进 evaluator context，因此 long-session 可以检查早期事实是否还在 memory/retention 中，而不只看最终回答。

#### multi-stage

入口：`agentmem/benchmark.py::_run_multi_stage()`。

任务定义：`benchmarks/tasks/multi_stage.jsonl`，四步分别是 planning、tool_calling、reflection、final_answer。

主要检查：

- planning：回答非空，required_facts 包含 AgentMem、CUDA OOM、timeout、KV cache、任务成功率；
- tool_calling：必须调用 log_analyzer，回答和事实覆盖 OOM/timeout/KV cache，`raw_tool_tokens >= 1000`；
- reflection：回答覆盖 baseline、optimized、工具结果外置等；
- final_answer：回答覆盖 baseline、optimized、OOM、timeout、KV cache、success rate，且 `expected_stages` 必须等于 `["planning", "tool_calling", "reflection", "final_answer"]`。

#### branching

入口：`agentmem/benchmark.py::_run_branching()` 和 `_branch_row()`。

任务定义：`benchmarks/tasks/branching.jsonl`。

评价方式不是直接评价 LLM 输出，而是评价 `_branch_row()` 构造的 `branch_text`：

- `expect_answer: true`；
- `min_branch_count: 2`；
- `branch_keywords: ["方案", "优点", "风险"]`；
- context 中传入 `branch_text` 和 `branch_count`。

因此 branching 评分偏工程模拟：重点看分支上下文共享的 token 计算和结构，而不是自由文本生成质量。

#### prefix-cache

入口：`agentmem/benchmark.py::_run_prefix_cache()`。

不是 task JSONL evaluator，而是 `evaluate_metric_checks()`，检查：

- `llm_call_success`：没有 failure_reason；
- `prompt_tokens_positive`：prompt_tokens > 0；
- `stable_prefix_hash_present`：有 stable prefix hash；
- `expected_prefix_pattern`：
  - optimized 要求 `unique_hashes == 1`；
  - baseline 要求 `unique_hashes > 1`。

success 是所有 metric checks 都为 True。

#### ablation

入口：`agentmem/benchmark.py::_run_ablation()` 和 `_evaluate_ablation_row()`。

基础检查：

- `prompt_tokens_positive`；
- `tool_tokens_bounded`：`injected_tool_tokens <= raw_tool_tokens`。

不同 variant 追加检查：

- `stable_prefix_only`：prefix hash 数小于 baseline；
- `skill_lazy_loading_only`：loaded_skill_tokens 小于 baseline；
- `tool_externalization_only`：injected_tool_tokens 小于 baseline；
- `history_summary_only`：history_tokens 小于 baseline，且 summary_tokens > 0；
- `full_optimized`：prompt_tokens、injected_tool_tokens、history_tokens、loaded_skill_tokens、unique_prefix_hashes 都相对 baseline 降低。

#### cache-pressure

入口：`agentmem/benchmark.py::_run_cache_pressure()` 和 `_cache_experiment_row()`。

这里没有调用 `evaluate_task()`，而是在 `_cache_experiment_row()` 里直接：

```python
success = not bool(response.get("error")) and prompt_tokens > 0
score = 1.0 if success else 0.0
passed_checks = 1 if success else 0
total_checks = 1
```

也就是说 cache-pressure 的 success 是“LLM 调用没失败且 prompt_tokens > 0”的单项检查。

#### ttl-priority

入口：`agentmem/benchmark.py::_run_ttl_priority()` 和 `_cache_experiment_row()`。

与 cache-pressure 相同，success 是单项运行成功检查：没有 error 且 prompt_tokens > 0。

### 2.6 失败请求如何处理 success

- Agent runtime 层：LLM RuntimeError 会设置 `llm_error`，回答变成 `LLM call failed: ...`，`structural_success` 为 False；工具 failed/timeout/permission_denied 也导致 structural_success 为 False。
- `evaluate_task()` 层：如果 answer 为空、工具没调用、关键词缺失、metrics 阈值没达标，相关 check 为 False，score 降低，低于 threshold 则 success False。
- `_safe_call_prompt()` 层：LLM 调用失败时返回 `content=""`、`latency=0.0`、`ttft=None`、`completion_tokens=0`、`total_tokens=prompt_tokens`、`tokens_per_second=None`、`error=str(exc)`。cache-pressure/ttl-priority 会因此 success False。

### 2.7 success_rate 和 avg_score 的区别

- `success_rate` 是二值成功率：看每条 row 的 `success` bool，统计成功占比，单位是百分比。
- `avg_score` 是平均得分：对每条 row 的 `score` 做均值，范围通常是 0 到 1。
- 如果每条 row 都通过 threshold，success_rate 可以是 100%，但 avg_score 未必一定是 1.0。例如某个 task 设置 `success_threshold=0.8`，score=0.8 也算成功，那么 success_rate=100%，avg_score=0.8。当前主线 task 多数 threshold 是 1.0，所以常见结果里二者都满分，但机制上并不强绑定。

## 3. avg_score 是怎么计算的

### 3.1 score 字段在哪里生成

`score` 主要来自两个 evaluator：

- `agentmem/evaluation.py::evaluate_task()`：针对 JSONL task 的规则评价；
- `agentmem/evaluation.py::evaluate_metric_checks()`：针对 prefix-cache、ablation 等非自然任务的 metric check 评价。

缓存实验 cache-pressure / ttl-priority 在 `_cache_experiment_row()` 里直接把 `score` 写成 `1.0 if success else 0.0`。

### 3.2 score 规则

`evaluate_task()` 的 score 是：

```text
score = passed_checks / total_checks
```

每个 check 都是确定性的 bool 规则，来源包括：

- 回答是否非空；
- 指定工具是否调用；
- 回答关键词是否出现；
- required facts 是否出现在回答、retention_text 或 metrics；
- branch keywords 是否出现在 branch_text；
- branch_count 是否达标；
- stage 顺序是否匹配；
- metrics 的 min/max 阈值是否满足。

这不是 LLM judge，也不是语义相似度评分；它是关键词/结构化字段/指标阈值的启发式 deterministic evaluator。

### 3.3 各场景 score 规则概览

- tool-heavy：工具调用 + 回答关键词 + required facts + required answer points + raw/injected token 阈值。
- long-session：大部分轮次只要求非空回答；工具轮要求 calculator；最终第 50 轮要求早期约束和关键概念保留。
- multi-stage：每步按 JSONL 检查对应 facts/answer points/tool/stage sequence。
- branching：检查分支数量和 `方案/优点/风险` 等 branch keywords。
- prefix-cache：检查 LLM 调用成功、prompt_tokens > 0、prefix hash 存在、optimized/baseline 的 prefix hash 模式符合预期。
- ablation：检查每个优化项是否相对 baseline 降低对应 token 或 prefix hash。
- cache-pressure / ttl-priority：单项运行成功检查，score 只有 0 或 1。

### 3.4 avg_score 公式

`avg_score` 在 `agentmem/metrics/summarizer.py::_build_summary_rows()` 中来自：

```text
avg_score = _mean(frame, "score")
```

`_mean()` 会把每条 row 的 `score` 转成 float，忽略空值/不可转数字值，然后做算术平均。报告中的 `Success / Score`、tool-heavy、多阶段、prefix-cache 等章节也都用同样的 `_mean(..., "score")` 或 `_group(... {"score": "mean"})` 思路。

### 3.5 score 和 success 是否强绑定

不强绑定。

- `score` 是连续比例；
- `success` 是 `score >= success_threshold` 的 bool；
- `success_threshold` 默认 1.0，但 task 可以自定义。

因此理论上 success_rate 100% 不必然代表 avg_score 1.0。当前主线 workload 多数要求 threshold=1.0 或所有 metric checks 全通过，所以结果里经常同时出现 `success=True` 和 `score=1.0`。

## 4. token 是怎么计算的

### 4.1 本地 token 估算函数

统一 fallback 在 `agentmem/memory/memory_object.py::estimate_tokens()`：

```python
def estimate_tokens(text: str) -> int:
    clean = text.strip()
    if not clean:
        return 0
    return max(1, (len(clean) + 3) // 4)
```

也就是近似 `ceil(len(text) / 4)`。它不使用 tiktoken，不使用 transformers tokenizer，也不绑定 Qwen tokenizer。因此对中英文混合、Qwen 系列模型都只是粗略估算，不是精确 tokenizer 计数。

### 4.2 prompt_tokens

`agentmem/runtime/llm_client.py::OpenAICompatibleClient.chat()`：

- 非 streaming：
  - 优先读 `response.usage.prompt_tokens`；
  - 如果没有 usage，则 fallback 到 `estimate_tokens(str(messages))`。
- streaming：
  - 请求设置 `stream_options={"include_usage": True}`；
  - 遍历 chunk 时如果 chunk 有 `usage.prompt_tokens` 就记录；
  - 如果没有 usage，则 fallback 到 `estimate_tokens(str(messages))`。

`AgentRuntime.run()` 会把每次 LLM response 的 `prompt_tokens` 累加到本轮 metrics。

注意：ablation 和 branching 等部分 benchmark 会自己构造 prompt token。比如 `_run_ablation()` 先用 `estimate_tokens(prompt)` 作为 `prompt_tokens` 写入 row，而 response 里的 `total_tokens` 可能来自真实 API usage。这也是某些 CSV 中 `total_tokens` 可能和 `prompt_tokens + output_tokens` 不一致的原因之一。

### 4.3 output_tokens

源码里 LLM client 返回字段叫 `completion_tokens`，benchmark row 字段叫 `output_tokens`。

- 非 streaming：
  - 优先读 `response.usage.completion_tokens`；
  - 没有 usage 时 fallback 到 `estimate_tokens(content)`。
- streaming：
  - 优先读 streaming usage 的 `completion_tokens`；
  - 没有 usage 时 fallback 到拼接后的 content 的 `estimate_tokens(content)`。

`AgentRuntime.run()` 把 response 的 `completion_tokens` 累加成 metrics 的 `output_tokens`。

### 4.4 total_tokens

LLM client 中：

```text
total_tokens = prompt_tokens + completion_tokens
```

runtime 中：

```text
metrics["total_tokens"] = total_tokens or (prompt_tokens + output_tokens)
```

但某些 benchmark row 会优先使用 response 中的 `total_tokens`，而 prompt_tokens 可能是 benchmark 自己估算的值。例如 `_run_ablation()`：

- `prompt_tokens = estimate_tokens(prompt)`；
- `output_tokens = response.get("completion_tokens", 0)`；
- `total_tokens = response.get("total_tokens", prompt_tokens + output_tokens)`。

如果真实 vLLM/OpenAI usage 的 prompt token 与本地 `estimate_tokens(prompt)` 不同，就会出现 CSV 中 `total_tokens != prompt_tokens + output_tokens`。现有 `results/final/main/vllm_benchmark.csv` 里 ablation baseline 就是这种旧/混合口径示例：row 的 `prompt_tokens` 是本地估算，`total_tokens` 可能来自模型服务 usage。

### 4.5 raw_tool_tokens

含义：工具原始输出的 token 数。

来源：

- `ToolExecutor.execute()` 对 `raw_result` 计算 `estimate_tokens(raw_result)`；
- `ToolResultStore.save()` 将 raw 写入 `results/tool_store/raw/{result_id}.txt`，然后按实际存储文本重新计算 `raw_token_len`；
- `AgentRuntime.run()` 汇总 `raw_tool_tokens = sum(result.raw_token_len for result in tool_results)`。

对 log_analyzer 来说，raw_tool_tokens 不是对“文件路径”或“摘要”计数，而是对完整日志 raw 文本计数。tool-heavy 中的 `raw_tool_tokens=6112` 来自 `benchmarks/fixtures/tool_heavy_scaled.log` 的完整文本按 `ceil(len(text)/4)` 估算。测试 `tests/test_tool_heavy_scaled.py` 也验证该 fixture 的 token 估算在 5800 到 6400 之间。

### 4.6 injected_tool_tokens

含义：实际进入 prompt/display 表面的工具结果 token。

baseline/full_history：

- `BaselineMemory.add_tool_result()` 把 `prompt_display_text(result)` 作为 tool 消息放入历史；
- `AgentRuntime.run()` 在未启用 tool externalization 时用 `prompt_display_tokens(result, estimate_tokens)` 计数；
- 如果 raw 长度没有超过 `ToolSpec.max_output_chars`，`prompt_display_text(result)` 就是完整 raw；
- 因此 tool-heavy baseline 里 `injected_tool_tokens = raw_tool_tokens = 6112`。

optimized/summary_memory/event_sourced_memory：

- `OptimizedMemory._tool_prompt_record()` 只注入：
  - `tool_name`
  - `result_id`
  - `status`
  - `raw_token_len`
  - `summary_token_len`
  - `summary`
- `EventSourcedMemoryAdapter.add_tool_result()` 把 summary 和 artifact metadata 写入事件，prompt 中渲染状态视图和 artifact references；
- `AgentRuntime.run()` 在启用 tool externalization 时用 `sum(result.summary_token_len)` 作为 injected_tool_tokens；
- tool-heavy optimized 的 `injected_tool_tokens=375` 就是 log summary JSON 的 `summary_token_len`，而不是完整日志。

这体现了 tool result offloading：原始工具结果留在 `results/tool_store/raw/` 和 chunks/index，prompt 只携带摘要、result_id 和 artifact metadata。

### 4.7 tool_compression_ratio

`agentmem/tools/result.py::ToolResult.compression_ratio`：

```text
compression_ratio = summary_token_len / raw_token_len
```

`AgentRuntime.run()` 中：

- optimized/event-sourced memory：对本轮工具结果的 compression_ratio 取平均；
- baseline/full_history：强制写成 `1.0`。

所以它不是 `1 - injected/raw`，而是 `injected/raw` 口径。tool-heavy optimized 中：

```text
375 / 6112 = 0.061354712...
```

这就是现有 CSV 中大约 `0.0614` 的来源。值越小，代表注入 prompt 的工具摘要相对原始工具结果越短，工具结果外置带来的 prompt token 降低越明显。

## 5. TTFT、latency、tokens_per_second 怎么统计

### 5.1 LLM client 层

`agentmem/runtime/llm_client.py::OpenAICompatibleClient.chat()` 在函数开始处记录：

```python
start = time.perf_counter()
```

非 streaming：

- `latency = time.perf_counter() - start`，从进入 `chat()` 到 API 返回并解析内容结束；
- `ttft = unavailable`，因为非 streaming 无法观测首 token，并记录 `ttft_status/reason`；
- `tokens_per_second = completion_tokens / latency`，latency <= 0 时标记为 unavailable。

streaming：

- `_chat_streaming()` 遍历 chunks；
- 第一次收到非空 `delta.content` 时记录 `first_token_time = time.perf_counter()`；
- 最后 `latency = time.perf_counter() - start`；
- `ttft = first_token_time - start`，如果没有任何文本 chunk 则标记为 unavailable；
- `tokens_per_second = completion_tokens / latency`。

`build_llm_client()` 中如果 backend 是 `vllm`，会设置 `stream=True`，所以真实 vLLM 路径会尝试统计 TTFT。openai/openai_compatible 非 vLLM 默认不 streaming，TTFT 标记为 unavailable。

### 5.2 AgentRuntime 层

`AgentRuntime.run()`：

- 多步 agent loop 中会累加 LLM response 的 `latency`；
- 第一轮 LLM response 的 `ttft` 作为本轮 ttft；
- `tokens_per_second` 取最后一次 response 的值；
- 最终 metrics 的 `latency` 还会加上所有工具执行耗时：`latency + sum(result.latency for result in tool_results)`。

所以 agent row 中的 latency 是“LLM 调用耗时 + 工具耗时”的总耗时；TTFT 和 tokens_per_second 只来自 LLM client，不包含工具首包概念。

### 5.3 失败请求如何处理

`_safe_call_prompt()` 捕获 RuntimeError 后返回：

- `latency = 0.0`
- `ttft = unavailable`
- `prompt_tokens = estimate_tokens(prompt)`
- `completion_tokens = 0`
- `total_tokens = prompt_tokens`
- `tokens_per_second = unavailable`
- `error = str(exc)`

cache-pressure / ttl-priority 看到 `error` 后 success False。其他 task evaluator 如果 answer 为空或 check 不满足，也会失败。

### 5.4 字段在哪里写入 vllm_benchmark.csv

各 scenario 先写自己的 CSV，例如 `tool_heavy_*.csv`、`long_session_*.csv`、`branch_benchmark.csv`、`prefix_cache_*.csv`、`cache_pressure.csv`、`ttl_priority.csv`。

当 backend 是 `vllm` 时，`agentmem/benchmark.py::run_benchmark()` 调用 `_write_vllm_benchmark(output_dir)`：

1. 遍历 `output_dir.glob("*.csv")`；
2. 跳过 `summary.csv` 和 `vllm_benchmark.csv`；
3. 只保留 `row["backend"] == "vllm"` 的行；
4. 用 `VLLM_BENCHMARK_FIELDS` 选择字段；
5. 写入 `output_dir / "vllm_benchmark.csv"`。

因此 `vllm_benchmark.csv` 是逐请求/逐 row 明细的合并视图，不是聚合汇总。

## 6. summary.csv / vllm_benchmark.csv / final_summary.csv 是怎么生成的

### 6.1 vllm_benchmark.csv

生成函数：`agentmem/benchmark.py::_write_vllm_benchmark()`。

性质：逐请求明细合并表。

来源：

- 当前输出目录下所有 scenario CSV；
- 排除 `summary.csv` 和 `vllm_benchmark.csv`；
- 只收集 `backend == "vllm"` 的 row；
- 字段由 `VLLM_BENCHMARK_FIELDS` 定义，包括：
  - scenario/mode/memory_mode/backend/model/round/stage；
  - prompt_tokens/output_tokens/total_tokens；
  - latency/ttft/tokens_per_second/peak_gpu_memory_mb；
  - success/score；
  - prefix_cache_hit_rate/cached_prompt_tokens/kv_cache_usage；
  - agent_meta_enabled/agent_id/agent_meta_sent/agent_meta_*；
  - cache_stats_available/cache_stats_unavailable_reason/cache_*。

注意：仓库里已有历史结果文件可能是旧 schema。例如当前 `results/final/main/vllm_benchmark.csv` 样例字段没有 agent_meta/cache_stats 后续列，但源码当前的 `VLLM_BENCHMARK_FIELDS` 已经包含这些字段。解释时应以源码为准，同时说明结果文件可能来自旧版本运行。

### 6.2 summary.csv

生成函数：`agentmem/metrics/summarizer.py::summarize_results()`。

流程：

1. `_load_frames(results)` 读取各类场景 CSV，用于生成 report.md；
2. `_build_summary_rows(results)` 遍历 `results.glob("*.csv")`；
3. 跳过 `summary.csv`；
4. 对每个 CSV 文件分别做聚合；
5. `_write_csv(summary_path, summary, _summary_fields())` 写 `summary.csv`。

性质：按“每个 CSV 文件”聚合的汇总表，而不是全局按 scenario 合并后聚合。

主要字段来源：

- `file`：CSV 文件名；
- `scenario`：该文件第一条非空 row 的 scenario，缺失时用 path stem；
- `mode`：如果文件内只有一个 mode，取该 mode；多个 mode 写 `both`；
- `rows`：行数；
- `avg_prompt_tokens` / `avg_output_tokens` / `avg_total_tokens`：对应列均值；
- `avg_latency` / `avg_ttft` / `tokens_per_second`：对应列均值；
- `peak_gpu_memory_mb`：对应列最大值；
- `success_rate`：`_success_rate(frame)`；
- `avg_score`：`_mean(frame, "score")`；
- `avg_raw_tool_tokens` / `avg_injected_tool_tokens` / `avg_tool_compression_ratio`：对应列均值；
- `avg_state_view_tokens` / `avg_event_count` / `avg_snapshot_count` / `avg_branch_saving_ratio`：对应列均值；
- `agent_meta_enabled` / `agent_id` / `cache_stats_available` / `cache_stats_unavailable_reason`：第一条非空值；
- `cache_total_blocks` / `cache_agent_sessions` / `cache_tool_result_blocks` / `cache_shared_prefix_blocks` / `cache_scratchpad_blocks` / `cache_expired_branch_blocks`：最后一个可转数字值。

缺失字段处理：

- `_mean()` 对缺失/空/不可转数字值返回 0.0 或忽略；
- `_max()` 没有数值时返回 -1.0；
- `_last_numeric()` 没找到时返回默认 -1；
- `_write_csv()` 对缺失字段写空字符串。

### 6.3 final_summary.csv

生成脚本：`scripts/collect_final_results.py`。

性质：把多个 results 目录里的 `summary.csv` 收集成一个跨实验总表。

流程：

1. `collect_final_results(results_dirs)` 遍历输入目录；
2. 对每个目录找 `summary.csv`；
3. 不存在就跳过；
4. `_read_summary_rows()` 用 `csv.DictReader` 读取；
5. `_normalize_row()` 增加 `results_dir` 字段，并只保留 `OUTPUT_FIELDS`；
6. `_dedupe_rows()` 按完整输出字段 tuple 去重；
7. `write_summary()` 写 `final_summary.csv`。

`OUTPUT_FIELDS` 包括：

- `results_dir`
- `scenario`
- `mode`
- `agent_meta_enabled`
- `avg_prompt_tokens`
- `avg_latency`
- `avg_ttft`
- `success_rate`
- `avg_score`
- `avg_raw_tool_tokens`
- `avg_injected_tool_tokens`
- `avg_tool_compression_ratio`
- `avg_branch_saving_ratio`
- `cache_stats_available`
- `agent_id`

缺失字段填空字符串，不补 0。

### 6.4 agent_meta_enabled、agent_id、cache_stats_available、cache_* 来自哪里

agent_meta：

- 配置读取在 `agentmem/runtime/llm_factory.py::build_llm_client()`；
- backend 为 `vllm` 且 `AGENTMEM_ENABLE_AGENT_META` 或 config 的 `vllm.enable_agent_meta` 为真时，构造 `AgentMetaBuilder`；
- `OpenAICompatibleClient._request_extra_body()` 把 `agent_meta` 放进 OpenAI-compatible 请求的 `extra_body`；
- `AgentRuntime.run()` 从 response 返回的 `agent_meta` 写入 metrics：`agent_meta_enabled`、`agent_id`、`agent_meta_sent`、`agent_meta_agent_id`、`agent_meta_session_id`、`agent_meta_context_id`、`agent_meta_segment_type`、`agent_meta_priority`。

cache stats：

- 采集函数是 `agentmem/benchmark.py::_capture_cache_stats()`；
- 只有 backend 是 `vllm` 才尝试采集，否则 `_unavailable_cache_stats("backend_not_vllm")`；
- 使用 `agentmem/vllm/cache_stats.py::CacheStatsCollector.fetch()` 请求配置中的 `metrics_url`；
- 成功后 `flatten()` 提取：
  - `cache_total_blocks`
  - `cache_agent_sessions`
  - `cache_tool_result_blocks`
  - `cache_shared_prefix_blocks`
  - `cache_scratchpad_blocks`
  - `cache_expired_branch_blocks`
- 失败或字段缺失时相关字段为 unavailable，并保留 `unavailable_reason`。

### 6.5 final_summary、summary、vllm_benchmark 的字段关系

- scenario CSV 是源数据，每个场景写自己的字段集合。
- `vllm_benchmark.csv` 从场景 CSV 中抽取 backend=vllm 的逐 row 明细字段。
- `summary.csv` 从当前结果目录下每个 CSV 文件按文件聚合均值、最大值、成功率等。
- `final_summary.csv` 从多个结果目录的 `summary.csv` 中复制并规范化选定字段，便于横向比较。

## 7. benchmark 每个场景的 evaluator 是怎么写的

### 7.1 统一 task evaluator

统一函数是 `agentmem/evaluation.py::evaluate_task()`。它只看 task JSONL 显式写出来的条件，不继承 runtime success。测试 `tests/test_evaluation.py` 明确验证：

- 没有任何 criteria 的 task 会抛 `ValueError`；
- expected_tools + answer_keywords 满足时 success True、score 1.0；
- metric check 部分通过时 success False、score 可以是 0.5。

### 7.2 tool-heavy evaluator

`benchmarks/tasks/tool_heavy.jsonl` 定义一条任务：日志 triage。核心 evaluator criteria 是：

- expect answer；
- expected log_analyzer；
- answer keywords：oom、timeout、kv cache；
- required facts：OOM、timeout、KV cache；
- required answer points：oom、timeout、kv cache；
- raw_tool_tokens 和 injected_tool_tokens 下限；
- threshold 1.0。

### 7.3 long-session evaluator

`benchmarks/tasks/long_session.jsonl` 定义 50 轮。大部分轮次只要求回答非空，工具轮要求 calculator，最终第 50 轮要求复述早期约束 `constraint_alpha_001` 并覆盖工具结果外置、任务成功率、AgentMem、Event-Sourced Memory。

这里 evaluator 会结合 `_agent_retention_text(agent)`，所以它检查的是“长期记忆是否还能提供必要事实”，不只是当前回答文本。

### 7.4 multi-stage evaluator

`benchmarks/tasks/multi_stage.jsonl` 定义四步：

- plan：要求输出计划并包含关键事实；
- tool：要求 log_analyzer、日志关键词、raw_tool_tokens；
- reflect：要求 baseline/optimized/工具外置/历史摘要/stable prefix；
- final：要求最终回答覆盖所有关键点，并且 completed_stages 严格等于四步顺序。

### 7.5 branching evaluator

`benchmarks/tasks/branching.jsonl` 定义 branch_counts `[2, 4, 8]`。`_branch_row()` 构造 shared context 和 branch deltas，然后用 evaluate_task 检查：

- answer present；
- branch_count >= 2；
- branch_text 中包含 `方案`、`优点`、`风险`。

这是结构化 benchmark，不是复杂语义 judge。

### 7.6 prefix-cache evaluator

`_run_prefix_cache()` 使用 `evaluate_metric_checks()`：

- LLM 调用成功；
- prompt_tokens > 0；
- stable_prefix_hash 存在；
- optimized 下 unique hash 必须为 1，baseline 下必须大于 1。

### 7.7 ablation evaluator

`_evaluate_ablation_row()` 使用 `evaluate_metric_checks()`，以 baseline 为参照，检查单项优化是否产生预期 token/hash 变化。score 是通过检查比例，success 要求全部检查通过。

### 7.8 cache-pressure / ttl-priority evaluator

这两个场景没有复杂 task evaluator。`_cache_experiment_row()` 直接用：

```text
success = no error and prompt_tokens > 0
score = 1.0 if success else 0.0
```

它们主要用于观测 agent_meta/cache_stats，而不是自然语言答案质量。

## 8. 用答辩语言解释这些实现

### 日志分析工具

AgentMem 的 `log_analyzer` 当前是一个确定性、规则版工具，不是 LLM judge。工具本体负责读取 benchmark 指定的大日志，真正摘要在 ToolResultStore 保存结果时完成：按 severity 和关键词把 CUDA OOM、timeout、KV cache allocation failed、exception、failed 等模式聚合成 JSON 摘要。原始日志会落盘到 tool_store/raw 和 chunks，prompt 里只注入 result_id、summary 和 artifact metadata。这个实现适合可复现实验，但不是完整生产级日志诊断器，像 Traceback、CUDA out of memory、Connection error 这类没命中当前关键词或 severity 的形式需要后续扩展规则。

### success_rate

benchmark 的 success 不直接等于 runtime 是否跑通，而是由 deterministic evaluator 根据 workload JSONL 里的显式条件判断。每条 row 先得到 score，也就是通过检查数除以总检查数；再用 `score >= success_threshold` 得到 bool success。summary.csv 里的 success_rate 是成功 row 数除以有效 row 数再乘 100。不同场景的检查项不同：tool-heavy 看工具调用和日志关键词，multi-stage 看阶段顺序和必需事实，prefix-cache/ablation/cache 实验看结构化 metric checks。

### token 统计

模型调用的 prompt/output token 优先使用 OpenAI-compatible response usage；如果 usage 不存在，就回退到本地 `estimate_tokens()`，也就是按字符数除以 4 的轻量估算。这个 fallback 不依赖 tiktoken 或 Qwen tokenizer，所以不是精确模型 token。工具 token 单独统计：raw_tool_tokens 是完整工具输出落盘文本的估算 token，injected_tool_tokens 是实际注入 prompt 的文本 token。某些 CSV 中 total_tokens 和 prompt/output 相加不完全一致，主要是因为 prompt_tokens 可能来自本地估算，而 total_tokens 来自模型服务 usage 或旧字段兼容。

### 工具结果外置为什么能降低 token

baseline 会把工具结果的可显示文本直接放回上下文，所以大型日志会导致 injected_tool_tokens 接近 raw_tool_tokens。optimized/event-sourced memory 把完整 raw output 存到 tool_store，只把摘要、result_id、token_len 和 artifact metadata 注入 prompt。tool-heavy 的例子里 raw_tool_tokens 是 6112，而 optimized 注入摘要只有 375，因此 compression ratio 是 375/6112，约 0.0614。这个值越小，说明 prompt 中承载的工具结果越少，vLLM prefill 压力越低，同时仍可通过 result_id/chunk 回查原文证据。


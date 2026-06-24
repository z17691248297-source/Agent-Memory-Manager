# log_analyzer

用途：分析大段日志并定位关键故障信号。

能力边界：

- 识别 CUDA OOM、KV cache allocation failed、timeout、exception、failed 等行。
- MVP 默认生成可复现的模拟大日志，用于 benchmark 工具结果外置。
- 不联网，不执行 shell，不修改文件。

推荐输入：包含“日志”“log”“OOM”“timeout”“KV cache”等关键词的问题。

输出说明：原始日志可能很长，optimized prompt 只应注入 `result_id`、摘要、原始 token 数和摘要 token 数。

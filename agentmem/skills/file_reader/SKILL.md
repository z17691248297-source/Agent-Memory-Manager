# file_reader

用途：读取受控目录下的文本文件，并将大结果交给 ToolResultStore 外置。

安全限制：

- 只允许 `benchmarks/fixtures/` 和 `examples/`。
- 不支持写文件，不读取系统敏感路径。
- 没有路径时返回模拟大文件，便于 benchmark 对比 baseline 和 optimized。

输出说明：baseline 会把全文放入 prompt；AgentMem 只注入摘要和 `result_id`。

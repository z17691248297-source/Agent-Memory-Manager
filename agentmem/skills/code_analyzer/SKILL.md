# code_analyzer

用途：对 Python 文件做静态、只读、轻量分析。

能力：

- 统计 class、function、import、TODO、FIXME。
- 标记疑似过长函数名等简单问题。
- 不执行代码，不导入目标模块。

限制：只允许当前项目目录内的 `.py` 文件；没有路径时返回可复现模拟分析结果。

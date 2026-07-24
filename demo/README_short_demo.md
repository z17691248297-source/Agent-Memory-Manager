# AgentMem 3 分钟精简 Demo

推荐视频时长：3 分钟以内。

视频只现场运行 4 段内容：

1. 连接自部署 vLLM/Qwen 模型。
2. 运行 3 轮真实多轮对话，展示 AgentMem 记忆能力和 agent_meta 字段。
3. 展示 MemoryPlan；如果没有 MemoryPlan，则展示 agent_meta 审计。
4. 展示从最终 `summary.csv` 提取的精选 benchmark 摘要，不展示完整原表。

全量 benchmark 不适合视频现场跑，因为耗时长；提交用脱敏结果保存在 `results/final-release-sanitized/exp_20260724T041247Z_ece79c19/summary.csv` 和 `report.md`。视频中的 benchmark 部分只展示精选摘要，避免直接展示包含多模型、多 mode 的完整原表。

`cache-pressure` 在视频中只作为 `agent_meta/cache_stats` 链路验证：展示 on/off 都可运行、success_rate 和 cache_stats 可用性，不宣称该场景一定带来 TTFT 或 latency 性能提升。

运行方式：

```bash
source .venv/bin/activate
export AGENTMEM_LLM_BASE_URL=http://<model-host>:8000/v1
export AGENTMEM_MODEL=Qwen2.5-7B-Instruct
bash demo/demo_short.sh
```

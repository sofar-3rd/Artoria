# 工具执行中宕机后的恢复

工具开始后用 `SIGKILL` 杀死子进程, 再从同一 SQLite checkpoint 的两个独立副本比较:

- **新输入**: `invoke({"messages": [HumanMessage("重试")]}, config)`, 先调用模型, 历史缺少旧工具结果。
- **恢复**: `invoke(None, config)`, 先执行原工具, 补齐结果后调用模型。

在项目根目录运行:

```bash
uv sync --project backend --dev
backend/.venv/bin/python backend/tests/exception/reproduce_checkpoint_crash.py

# 真实接口, 使用 backend/.env; 不修改配置, 可能消耗额度。
backend/.venv/bin/python backend/tests/exception/reproduce_checkpoint_crash.py \
  --live --model gpt-6.1-sol
```

模拟测试也已纳入后端 pytest。历史实测见 [summary.json](summary.json): 两个 GPT 接口的新输入返回 400, 恢复返回 200; HY 接受新输入并生成新的工具调用, 没有补齐旧调用。

每轮 `results/` 保留 SQLite 副本、请求日志和结果。新运行每个分支只写一个 `result.json`, 旧原始记录迁移后保持不变。日志不记录 API Key。

边界: 使用 `durability="sync"`, 经项目代理访问, 不是 OpenAI 官方直连接口或生产 PostgreSQL 验证。400 原文未明确点名缺少 ToolMessage。新消息可能在报错前已持久化; 工具重跑仍需幂等。

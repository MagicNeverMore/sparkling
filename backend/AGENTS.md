# Backend Logging Standards

- 后端模块统一使用 `from app.logger import get_logger` 或相对导入 `from ..logger import get_logger`，并在模块顶层定义 `logger = get_logger(__name__)`。
- 日志必须使用参数化格式，例如 `logger.info("atom 已创建 id=%s", atom_id)`，不要使用 f-string 拼接动态内容。
- 日志级别约定：
  - `debug`：高频查询、过滤结果、队列领取、WebSocket 连接数等排查细节。
  - `info`：用户可见状态变化、任务入队/完成、数据库切换、外部 provider 测试成功等关键路径。
  - `warning`：可恢复失败、校验失败、provider 测试失败、认证失败、重试等需要关注但不影响进程继续运行的问题。
  - `exception`：捕获异常并继续处理或转换为 HTTP 错误时使用，保留 traceback。
  - `error`：不可恢复或会导致请求/任务失败的错误；优先使用 `exception`。
- 严禁写入敏感信息：密码、password hash、session token、API key、GitHub token、PostgreSQL URL 原文、完整 Authorization header。
- 可以记录脱敏或低敏字段：资源 id、任务 id、数量、状态、耗时、数据库 backend、是否配置了某项 secret、SQLite 文件路径。
- 外部调用必须记录开始/成功/失败中的关键结果：provider 类型、model、latency、数量、错误摘要；不要记录完整 prompt 或用户私密内容。
- 后台任务必须记录领取、跳过、完成、失败和重试；失败日志应包含任务类型、任务 id 和可定位 payload id。
- Router 层记录业务动作结果，Service 层记录核心状态流转；避免在循环中对每条普通数据打 `info`。
- 新增后端模块时，如果模块包含运行逻辑、I/O、状态变更或异常处理，必须加入 logger；纯 ORM model、类型定义和空 `__init__.py` 可不加。

# 测试体系文档

## 概览

本项目使用 **pytest + pytest-asyncio** 作为测试框架，共 189 个测试用例，覆盖从数据采集到 API 端点的完整链路。

运行全部测试：

```bash
python -m pytest tests/ -v
```

## 技术栈

| 组件 | 版本 | 用途 |
|------|------|------|
| pytest | 9.x | 测试运行器 |
| pytest-asyncio | 1.4+ | 异步测试支持（`asyncio_mode = auto`） |
| aiosqlite | - | 内存 SQLite 测试数据库 |
| httpx | - | ASGI 测试客户端 |
| unittest.mock | 标准库 | Mock/Patch 外部依赖 |

## 配置

`pytest.ini` 核心配置：

```ini
[pytest]
asyncio_mode = auto          # 自动识别 async 测试函数
testpaths = tests            # 测试目录
addopts = -v --tb=short     # 详细输出 + 短格式错误回溯

markers =
    unit: Unit tests (no external dependencies, fast)
    integration: Integration tests (require DB or internal services)
    api: API endpoint tests (require ASGI test client)
    slow: Slow tests (LLM calls, network)
```

按标记运行：

```bash
python -m pytest -m unit          # 只跑单元测试
python -m pytest -m integration   # 只跑集成测试
python -m pytest -m api           # 只跑 API 测试
python -m pytest -m "not slow"    # 跳过慢速测试
```

## 公共 Fixtures

定义在 `tests/conftest.py`，所有测试文件共享：

### `setup_deps`（autouse）

每个测试自动执行，初始化 `deps` 模块的测试状态：

- `deps.settings` → `Settings(deepseek_api_key="test-key")`
- `deps.news_queue` / `scored_queue` / `alert_queue` → 空 asyncio.Queue
- `deps.dedup_cache` → 空 OrderedDict
- `deps.active_connections` / `active_subscriptions` / `sources` → 空字典

测试结束后自动清理。

### `db`

提供内存 SQLite 数据库，包含完整建表 schema：

```python
@pytest.fixture
async def db():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await conn.executescript(SCHEMA)
    await conn.commit()
    yield conn
    await conn.close()
```

### `seeded_db`

在 `db` 基础上预填充测试数据，返回 `(conn, ids)` 元组：

```python
db, ids = seeded_db
ids["n1"]  # 新闻 "央行宣布降息25个基点"
ids["n2"]  # 新闻 "Fed signals rate cut in September"
ids["n3"]  # 新闻 "股市大涨突破3500点"
ids["e1"]  # 实体 "央行"
ids["e2"]  # 实体 "LPR"
ids["e3"]  # 实体 "美联储"
```

预填充数据包括：3 条新闻、3 条情绪记录、3 个实体、2 条多维情绪、1 条订阅。

### `api_client`

httpx 异步测试客户端，直接调用 ASGI 应用，无需启动服务器：

```python
async def test_example(api_client):
    resp = await api_client.get("/api/health")
    assert resp.status_code == 200
```

### `sample_rss` / `sample_news_items`

提供样例 RSS XML 和 NewsItem 对象，用于爬虫和解析器测试。

## 测试文件索引

| 文件 | 测试类数 | 用例数 | 覆盖模块 |
|------|---------|--------|----------|
| `test_analysis.py` | 7 | 19 | 分析流程图、深度分析触发、风险评级 |
| `test_api.py` | 8 | 23 | 所有 API 端点（健康、订阅、来源、报告、情绪、实体、通知） |
| `test_crawler.py` | 8 | 25 | 爬虫解析器（新浪/财联社/东方财富/金十/36氪）、去重、源配置 |
| `test_entity_extractor.py` | 1 | 5 | 实体提取与持久化 |
| `test_event_cluster.py` | 3 | 8 | 事件聚类匹配、显著性计算 |
| `test_intent_report.py` | 3 | 7 | 意图搜索关键词提取、新闻搜索、实时爬取 |
| `test_knowledge_graph.py` | 4 | 11 | 知识图谱关系解析、因果链推理 |
| `test_multi_sentiment.py` | 1 | 5 | 多维情绪分析（fear/greed/optimism/uncertainty） |
| `test_notification.py` | 3 | 9 | 通知静默期、告警级别过滤 |
| `test_report_service.py` | 3 | 7 | 报告导出 Markdown、追问、多模型对比 |
| `test_repository.py` | 6 | 15 | 数据持久化（新闻/情绪/实体/报告/关系/订阅） |
| `test_sentiment.py` | 2 | 3 | FinBERT 模型推理、快速消费 |
| `test_slow_track.py` | 3 | 10 | 慢链路告警级别、深度分析触发与执行 |
| `test_sources.py` | 2 | 12 | 默认源配置、RSS 解析器 |
| `test_subscription.py` | 1 | 7 | 订阅关键词匹配逻辑 |
| `test_subscription_manager.py` | 1 | 5 | 订阅管理器增删查持久化 |
| `test_ws.py` | 1 | 6 | WebSocket 连接管理、广播 |

## Mock 策略

本项目大量使用 mock 来隔离外部依赖，关键模式：

### DeepSeek LLM Client

所有分析模块（entity_extractor、multi_sentiment、report_service 等）在函数内部 import DeepSeekClient，因此 patch 路径为原始模块：

```python
mock_client = AsyncMock()
mock_client.analyze.return_value = '{"fear":0.1,"greed":0.5}'

with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client), \
     patch("app.analysis.xxx.deps") as mock_deps:
    mock_deps.settings = MagicMock()
    # 调用被测函数
```

注意：`multi_model_compare` 内部会从 `deps.settings` 读取 `deepseek_api_key` 等属性创建新的 `Settings` 对象，此时必须 mock 为有效字符串：

```python
mock_settings = MagicMock()
mock_settings.deepseek_api_key = "test-key"
mock_settings.deepseek_model = "deepseek-chat"
mock_deps.settings = mock_settings
```

### 数据库

使用 `patch("app.repository.get_db", return_value=db)` 将应用数据库指向内存测试库：

```python
with patch("app.repository.get_db", return_value=db):
    # 所有数据库操作都在内存 SQLite 中执行
```

### 爬虫源

`fetch_all_sources` 在 `intent_report` 内部 import，patch 原始模块：

```python
with patch("app.crawler.sources.fetch_all_sources", return_value=mock_items):
    # fetch_all_sources 被替换为返回固定数据
```

## 添加新测试指南

### 1. 纯逻辑测试（无外部依赖）

```python
class TestMyFunction:
    def test_basic(self):
        from app.xxx import my_function
        result = my_function("input")
        assert result == expected
```

### 2. 需要数据库的测试

```python
class TestMyDbFeature:
    @pytest.mark.asyncio
    async def test_with_empty_db(self, db):
        with patch("app.repository.get_db", return_value=db):
            # 操作空数据库
            pass

    @pytest.mark.asyncio
    async def test_with_seed_data(self, seeded_db):
        db, ids = seeded_db
        with patch("app.repository.get_db", return_value=db):
            # 操作预填充数据
            pass
```

### 3. 需要 LLM 的测试

```python
class TestMyLlmFeature:
    @pytest.mark.asyncio
    async def test_success(self, seeded_db):
        db, ids = seeded_db
        mock_client = AsyncMock()
        mock_client.analyze.return_value = "预期LLM输出"

        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client), \
             patch("app.analysis.xxx.deps") as mock_deps, \
             patch("app.repository.get_db", return_value=db):
            mock_deps.settings = MagicMock()
            result = await my_function(...)
            assert result is not None

    @pytest.mark.asyncio
    async def test_llm_failure(self, seeded_db):
        mock_client = AsyncMock()
        mock_client.analyze.side_effect = Exception("API error")
        # ... 验证降级处理
```

### 4. API 端点测试

```python
class TestMyEndpoint:
    @pytest.mark.asyncio
    async def test_get(self, api_client):
        resp = await api_client.get("/api/my-endpoint")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_post_validation(self, api_client):
        resp = await api_client.post("/api/my-endpoint", json={})
        assert resp.status_code == 422
```

## 常见问题

### Q: patch 路径怎么确定？

被测函数如果在**函数内部** import（如 `from app.xxx import Yyy`），则 patch 原始模块路径 `app.xxx.Yyy`，而非被测模块路径。如果被测模块在**顶层** import，则 patch 被测模块路径 `app.my_module.Yyy`。

### Q: 异步测试怎么写？

确保函数是 `async def`，pytest-asyncio 的 `auto` 模式会自动处理。异步 fixture 同样用 `async def` 定义。

### Q: 测试间状态会泄漏吗？

不会。`setup_deps` fixture 是 `autouse`，每个测试前后自动初始化和清理 `deps` 状态。`db` fixture 每次创建新的内存数据库。

### Q: 如何跳过需要网络的测试？

使用 `@pytest.mark.slow` 标记，运行时加 `-m "not slow"` 过滤。

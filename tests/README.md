# 测试体系文档

## 概览

本项目使用 **pytest + pytest-asyncio** 作为测试框架，共 **~350+** 个测试用例，覆盖从数据采集到 API 端点的完整链路，以及边界条件、错误处理、安全、并发、性能等专项测试。

运行全部测试：

```bash
# 运行所有测试
python -m pytest tests/ -v

# 按标记运行
python -m pytest -m unit          # 只跑单元测试
python -m pytest -m integration   # 只跑集成测试
python -m pytest -m api           # 只跑 API 测试
python -m pytest -m edge          # 只跑边界条件测试
python -m pytest -m security      # 只跑安全测试
python -m pytest -m concurrency   # 只跑并发测试
python -m pytest -m performance   # 只跑性能测试
python -m pytest -m e2e           # 只跑端到端测试
python -m pytest -m "not slow"   # 跳过慢速测试

# 组合过滤
python -m pytest -m "unit and not slow"
python -m pytest -m "(unit or integration) and not slow"

# 覆盖率报告
python -m pytest tests/ --cov=app --cov-report=term-missing
python -m pytest tests/ --cov=app --cov-report=html
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

`pyproject.toml` 核心配置：

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "-v --tb=short"

markers = [
    "unit: Unit tests (no external dependencies, fast)",
    "integration: Integration tests (require DB or internal services)",
    "api: API endpoint tests (require ASGI test client)",
    "slow: Slow tests (LLM calls, network)",
    "edge: Edge case and boundary condition tests",
    "security: Security and input validation tests",
    "concurrency: Concurrency and race condition tests",
    "performance: Performance and load tests",
    "e2e: End-to-end pipeline tests",
]
```

按标记运行：

```bash
python -m pytest -m unit          # 只跑单元测试
python -m pytest -m integration     # 只跑集成测试
python -m pytest -m api             # 只跑 API 测试
python -m pytest -m "not slow"      # 跳过慢速测试
```

## 公共 Fixtures

定义在 `tests/conftest.py`，所有测试文件共享：

### `setup_deps`（autouse）

每个测试自动执行，初始化 `deps` 模块的测试状态：

- `deps.settings` -> `Settings(deepseek_api_key="test-key")`
- `deps.news_queue` / `scored_queue` / `alert_queue` -> 空 asyncio.Queue
- `deps.dedup_cache` -> 空 OrderedDict
- `deps.active_connections` / `active_subscriptions` / `sources` -> 空字典

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

### 原有测试文件（189 个用例）

| 文件 | 测试类数 | 用例数 | 覆盖模块 | 主要标记 |
|------|---------|--------|----------|----------|
| `test_analysis.py` | 7 | 19 | 分析流程图、深度分析触发、风险评级 | unit, integration |
| `test_api.py` | 8 | 23 | 所有 API 端点（健康、订阅、来源、报告、情绪、实体、通知） | api |
| `test_crawler.py` | 8 | 25 | 爬虫解析器（新浪/财联社/东方财富/金十/36氪）、去重、源配置 | unit |
| `test_entity_extractor.py` | 1 | 5 | 实体提取与持久化 | integration |
| `test_event_cluster.py` | 3 | 8 | 事件聚类匹配、显著性计算 | unit, integration |
| `test_intent_report.py` | 3 | 7 | 意图搜索关键词提取、新闻搜索、实时爬取 | integration, slow |
| `test_knowledge_graph.py` | 4 | 11 | 知识图谱关系解析、因果链推理 | unit, integration |
| `test_multi_sentiment.py` | 1 | 5 | 多维情绪分析（fear/greed/optimism/uncertainty） | integration, slow |
| `test_notification.py` | 3 | 9 | 通知静默期、告警级别过滤 | unit |
| `test_report_service.py` | 3 | 7 | 报告导出 Markdown、追问、多模型对比 | unit, integration, slow |
| `test_repository.py` | 6 | 15 | 数据持久化（新闻/情绪/实体/报告/关系/订阅） | integration |
| `test_sentiment.py` | 2 | 3 | FinBERT 模型推理、快速消费 | unit |
| `test_slow_track.py` | 3 | 10 | 慢链路告警级别、深度分析触发与执行 | unit, integration |
| `test_sources.py` | 2 | 12 | 默认源配置、RSS 解析器 | unit |
| `test_subscription.py` | 1 | 7 | 订阅关键词匹配逻辑 | unit |
| `test_subscription_manager.py` | 1 | 5 | 订阅管理器增删查持久化 | integration |
| `test_ws.py` | 1 | 6 | WebSocket 连接管理、广播 | unit |
| `test_fed_policy.py` | 4 | 11 | 美联储政策追踪、缓存、新闻搜索 | integration, slow |

### 新增测试文件（~160+ 个用例）

| 文件 | 测试类数 | 用例数 | 覆盖内容 | 主要标记 |
|------|---------|--------|----------|----------|
| `test_edge_cases.py` | 10 | ~45 | 边界值、空输入、极端值、特殊字符、超长数据 | edge, unit |
| `test_error_handling.py` | 8 | ~40 | LLM/API 失败、超时、异常降级、部分失败恢复 | unit, integration |
| `test_security.py` | 6 | ~35 | SQL 注入、XSS、输入验证、恶意数据过滤 | security, api |
| `test_concurrency.py` | 8 | ~30 | 并发队列、WebSocket 广播、竞态条件、任务取消 | concurrency, unit |
| `test_performance.py` | 7 | ~25 | 大数据集、响应时间、内存效率、压力测试 | performance |
| `test_e2e.py` | 5 | ~20 | 完整数据流、生命周期管理、端到端管道 | e2e, integration |
| `test_models.py` | 10 | ~35 | Pydantic 模型验证、序列化、数据库 schema、配置 | unit |

## 测试分类体系

### 1. 单元测试（Unit Tests）

**目标**：验证单个函数/类的正确性，无外部依赖，运行速度快（<100ms）。

**覆盖模块**：
- 数据模型验证（`test_models.py`）
- 爬虫解析器（`test_crawler.py`, `test_sources.py`）
- 去重逻辑（`test_crawler.py`）
- 标题哈希计算（`test_crawler.py`）
- HTML 清理（`test_crawler.py`）
- 订阅匹配（`test_subscription.py`）
- 通知过滤（`test_notification.py`）
- WebSocket 连接管理（`test_ws.py`）
- 知识图谱解析（`test_knowledge_graph.py`）
- 事件聚类计算（`test_event_cluster.py`）

**运行命令**：
```bash
python -m pytest -m unit
```

### 2. 集成测试（Integration Tests）

**目标**：验证模块间的协作，需要数据库或内部服务。

**覆盖模块**：
- Repository 层 CRUD（`test_repository.py`）
- 实体提取与持久化（`test_entity_extractor.py`）
- 多维情绪分析（`test_multi_sentiment.py`）
- 事件聚类与存储（`test_event_cluster.py`）
- 报告服务（`test_report_service.py`）
- 订阅管理器（`test_subscription_manager.py`）
- 慢链路分析（`test_slow_track.py`, `test_analysis.py`）
- 美联储政策（`test_fed_policy.py`）
- 意图报告（`test_intent_report.py`）

**运行命令**：
```bash
python -m pytest -m integration
```

### 3. API 测试（API Tests）

**目标**：验证 HTTP 端点的正确性、响应格式、状态码。

**覆盖端点**：
- `/health`, `/status`
- `/subscriptions` (GET/POST/DELETE)
- `/sources` (GET/POST/PATCH/DELETE)
- `/reports` (GET/POST)
- `/sentiment/*`
- `/entities/*`, `/events/*`
- `/knowledge/*`
- `/notifications/*`
- `/fed-policy/*`

**运行命令**：
```bash
python -m pytest -m api
```

### 4. 边界条件测试（Edge Case Tests）

**目标**：验证系统在边界值和极端条件下的行为。

**测试场景**：
- 空字符串/空列表/空字典输入
- 超长数据（10000+ 字符标题）
- 特殊字符（HTML、脚本、Unicode emoji）
- 混合语言（中英日混杂）
- 分数边界值（-1.0, 0.0, 1.0, 刚好越过阈值）
- 缓存大小为 0 或 1
- 数据库偏移量超出范围
- 重复数据插入

**运行命令**：
```bash
python -m pytest -m edge
```

### 5. 错误处理测试（Error Handling Tests）

**目标**：验证系统在外部服务失败时的降级和恢复能力。

**测试场景**：
- DeepSeek API 连接被拒绝
- 请求超时（TimeoutError）
- 返回畸形 JSON
- 返回空字符串
- 返回不完整的 JSON
- LLM 返回错误的数据结构
- 超出范围的数值
- 数据库外键约束失败
- 图执行超时/异常
- 所有重试耗尽

**运行命令**：
```bash
python -m pytest -m "error or error_handling"
# 或使用文件名
python -m pytest tests/test_error_handling.py
```

### 6. 安全测试（Security Tests）

**目标**：验证系统对恶意输入的防护能力。

**测试场景**：
- SQL 注入（标题、用户 ID、报告 ID、来源名）
- XSS（脚本标签、事件处理器、HTML 实体）
- 无效输入验证（负数限制、空意图、超长输入）
- 畸形 URL
- XML 实体扩展（Billion Laughs）
- 队列溢出
- 大负载处理

**运行命令**：
```bash
python -m pytest -m security
```

### 7. 并发测试（Concurrency Tests）

**目标**：验证系统在并发访问下的正确性和稳定性。

**测试场景**：
- 多生产者/单消费者队列
- 队列满时的阻塞行为
- 并发去重缓存访问
- 100 个并发 WebSocket 连接
- 广播时连接断开
- 快速连接/断开循环
- 并发订阅修改
- 并发数据库实体保存
- 任务取消处理
- 内存压力下的缓存行为

**运行命令**：
```bash
python -m pytest -m concurrency
```

### 8. 性能测试（Performance Tests）

**目标**：验证系统在高负载下的响应时间和资源使用。

**测试场景**：
- 100 条新闻顺序保存（<5s）
- 100 个实体批量保存（<3s）
- 空数据库趋势查询（<1s）
- 大数据标题哈希计算（<100ms）
- 大 HTML 清理（<1s）
- API 端点响应时间（<1s）
- 50 并发 API 请求（<5s）
- 100 个 WebSocket 连接广播（<1s）
- 100 条 RSS 解析（<2s）
- 10000 次去重缓存操作（<2s）

**运行命令**：
```bash
python -m pytest -m performance
```

### 9. 端到端测试（E2E Tests）

**目标**：验证完整数据流从输入到输出的正确性。

**测试场景**：
- 爬取 -> 去重 -> 情感分析 -> 订阅匹配 -> 通知 -> 广播
- 实体提取 -> 关系提取 -> 因果链推理
- 事件聚类 -> 显著性计算 -> 存储
- 美联储新闻爬取 -> 政策摘要生成 -> 缓存
- 意图提取 -> 新闻搜索 -> 报告生成
- 报告保存 -> 追问 -> 多模型对比
- 数据生命周期：创建 -> 查询 -> 清理
- 来源生命周期：添加 -> 更新 -> 删除
- 订阅生命周期：创建 -> 查询 -> 删除

**运行命令**：
```bash
python -m pytest -m e2e
```

### 10. 慢速测试（Slow Tests）

**目标**：需要真实网络或 LLM 调用的测试。

**标记文件**：
- `test_multi_sentiment.py`
- `test_intent_report.py`
- `test_report_service.py`
- `test_fed_policy.py`

**运行命令**：
```bash
# 跳过慢速测试
python -m pytest -m "not slow"

# 只跑慢速测试
python -m pytest -m slow
```

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
mock_settings.deepseek_temperature = 0.7
mock_settings.deepseek_max_tokens = 2048
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

### 5. 边界条件测试

```python
class TestMyFeatureEdgeCases:
    def test_empty_input(self):
        result = my_function("")
        assert result == expected_for_empty

    def test_very_long_input(self):
        result = my_function("x" * 10000)
        assert result is not None

    def test_special_characters(self):
        result = my_function("<script>alert('xss')</script>")
        assert "<script>" not in result  # 或验证正确存储
```

### 6. 并发测试

```python
class TestMyFeatureConcurrency:
    @pytest.mark.asyncio
    async def test_concurrent_access(self):
        async def worker(i):
            return await my_async_function(i)

        tasks = [asyncio.create_task(worker(i)) for i in range(10)]
        results = await asyncio.gather(*tasks)
        assert len(results) == 10
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

### Q: 如何只运行特定类型的测试？

```bash
# 只运行单元测试
python -m pytest -m unit

# 只运行安全测试
python -m pytest -m security

# 只运行性能测试
python -m pytest -m performance

# 运行单元测试和集成测试，但跳过慢速测试
python -m pytest -m "(unit or integration) and not slow"

# 运行特定文件
python -m pytest tests/test_edge_cases.py

# 运行特定类
python -m pytest tests/test_edge_cases.py::TestNewsItemEdgeCases

# 运行特定方法
python -m pytest tests/test_edge_cases.py::TestNewsItemEdgeCases::test_empty_title
```

### Q: 测试覆盖率怎么看？

```bash
# 终端输出
python -m pytest tests/ --cov=app --cov-report=term-missing

# HTML 报告（生成 htmlcov/index.html）
python -m pytest tests/ --cov=app --cov-report=html

# 只看未覆盖的行
python -m pytest tests/ --cov=app --cov-report=term-missing:skip-covered
```

### Q: 如何调试失败的测试？

```bash
# 在失败处暂停（PDB）
python -m pytest tests/ --pdb

# 只运行上次失败的测试
python -m pytest tests/ --lf

# 显示最详细的输出
python -m pytest tests/ -vvv --tb=long

# 捕获输出
python -m pytest tests/ -s
```

## 测试策略

### 分层测试金字塔

```
        /\
       /  \     E2E Tests (~20)      - 完整用户场景
      /____\    
     /      \   Integration Tests (~80) - 模块协作
    /________\  
   /          \ Unit Tests (~250)       - 函数/类逻辑
  /____________\
```

### 测试优先级

1. **P0 - 核心流程**：新闻爬取 -> 去重 -> 情感分析 -> 告警 -> 通知
2. **P1 - 数据持久化**：所有 Repository CRUD 操作
3. **P2 - API 端点**：所有外部接口
4. **P3 - 边界条件**：空输入、超长数据、特殊字符
5. **P4 - 错误恢复**：外部服务失败、超时、降级
6. **P5 - 安全**：SQL 注入、XSS、输入验证
7. **P6 - 并发**：多线程/多协程场景
8. **P7 - 性能**：大数据集、响应时间

### CI/CD 建议

```yaml
# .github/workflows/test.yml 建议配置
steps:
  - name: Run Unit Tests
    run: python -m pytest -m "unit and not slow" -v

  - name: Run Integration Tests
    run: python -m pytest -m "integration and not slow" -v

  - name: Run API Tests
    run: python -m pytest -m api -v

  - name: Run Security Tests
    run: python -m pytest -m security -v

  - name: Run Edge Case Tests
    run: python -m pytest -m edge -v

  - name: Coverage Report
    run: python -m pytest --cov=app --cov-report=xml
```

## 维护指南

### 添加新模块的测试

1. 确定模块类型（纯逻辑 / 需要 DB / 需要 LLM / API 端点）
2. 在对应测试文件中添加测试类，或创建新文件
3. 使用适当的 pytest 标记（`unit`, `integration`, `api`, `slow`）
4. 如有需要，在 `conftest.py` 中添加新的 fixture
5. 更新本文档的测试文件索引

### 测试文件命名规范

- `test_<module>.py` - 对应模块的测试
- `test_<category>.py` - 专项测试（edge, security, concurrency 等）

### 测试类命名规范

- `Test<Feature>` - 功能测试
- `Test<Feature>EdgeCases` - 边界条件
- `Test<Feature>Failures` - 错误处理
- `Test<Feature>Concurrency` - 并发测试
- `Test<Feature>Performance` - 性能测试

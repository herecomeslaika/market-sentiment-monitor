# Market Sentiment Monitor — 项目介绍与敏捷开发流程

---

## Slide 1: 封面

**Market Sentiment Monitor**
实时金融舆情监控与智能分析平台

- 日期：2026年6月
- 技术栈：Python + FastAPI + Vue 3 + FinBERT + DeepSeek LLM

---

## Slide 2: 项目概述

### 一句话定位

> 从 13 个财经新闻源实时采集新闻，经过 FinBERT 情绪评分和 DeepSeek 深度分析，将市场情绪、关键实体、事件聚合、政策追踪等信息通过 WebSocket 推送到前端仪表盘。

### 核心价值

- **实时性**：30 秒轮询 + WebSocket 推送，从新闻发布到仪表盘展示 < 1 分钟
- **智能化**：双轨分析架构（快速 FinBERT + 深度 LLM），自动实体提取与事件聚类
- **全景式**：情绪趋势、多维情绪雷达、知识图谱、美联储政策追踪，多维度呈现市场状态
- **可交互**：订阅关键词、意图搜索生成报告、追问、多模型对比

---

## Slide 3: 系统架构

```
┌─────────────────┐    ┌──────────────────────────────┐    ┌──────────────────────┐
│  News Sources    │    │     Backend (FastAPI)         │    │  Frontend (Vue 3)    │
│                 │    │                              │    │                      │
│ • 新浪财经 x3   │───▶│  Crawler → Dedup → Queue     │    │  SentimentChart      │
│ • 东方财富       │    │      ↓                       │    │  NewsFeed / AlertFeed│
│ • 财联社         │    │  Fast Track (FinBERT)        │    │  EntityCloud         │
│ • 金十数据       │    │      ↓ (score < threshold)   │    │  MultiSentimentRadar │
│ • 36氪          │    │  Slow Track (DeepSeek)       │    │  EventTimeline       │
│ • CNBC x2       │    │    ├ Entity Extraction       │    │  KnowledgeGraph      │
│ • MarketWatch   │    │    ├ Multi-Sentiment Analysis │    │  FedPolicy           │
│ • Yahoo Finance │    │    ├ Event Clustering        │────▶│  IntentSearch        │
│ • BBC Business  │    │    ├ Knowledge Graph         │ WS │  ReportBrowser       │
│ • Investing     │    │    └ Report Generation       │    │  SubscriptionManager │
└─────────────────┘    │      ↓                       │    │  KeywordStats        │
                       │  Alert → WebSocket Push      │    └──────────────────────┘
                       └──────────────────────────────┘
```

---

## Slide 4: 技术选型

| 层级 | 技术 | 选型理由 |
|------|------|---------|
| 后端框架 | FastAPI | 原生异步、自动 OpenAPI 文档、高性能 |
| 情绪模型 | FinBERT (DistilBERT) | 金融领域预训练、多语言支持、CPU 可推理 |
| 深度分析 | DeepSeek Chat | 中文理解能力强、成本低、支持长上下文 |
| 数据库 | SQLite + aiosqlite | 轻量、零配置、单机部署够用 |
| 实时通信 | WebSocket | 双向推送、低延迟 |
| 前端框架 | Vue 3 + Composition API | 轻量、响应式、组件化 |
| 图表 | Chart.js + 自定义 Canvas | 灵活绘制趋势图/雷达图/知识图谱 |
| 部署 | Docker Compose | 一键启动、环境隔离 |

---

## Slide 5: 数据管线详解

```
新闻采集 → 去重 → 情绪评分 → 告警判断 → 深度分析 → 前端推送

1. [Crawler] 每 30 秒轮询 13 个源，解析 RSS/HTML
2. [Dedup]   MD5 标题哈希去重，避免重复处理
3. [Fast Track] FinBERT 评分：score ∈ [-1, +1]，label: positive/negative/neutral
4. [Threshold] |score| > 0.5 → 进入 Slow Track
5. [Slow Track] 并行执行 5 项深度分析：
   • 实体提取 → 持久化到 entities/news_entities 表
   • 多维情绪 → fear/greed/optimism/uncertainty + momentum_shift
   • 事件聚类 → 按 entity overlap 匹配已有事件或创建新事件
   • 知识图谱 → 实体关系抽取 + 因果链推理
   • 深度研报 → LangGraph 流程生成结构化报告
6. [Alert] 告警级别分配 (info/warning/critical)，WebSocket 推送
```

---

## Slide 6: 核心功能展示

### 6.1 情绪趋势图

- 小时级聚合，5 点移动平均线平滑噪声
- 波动带（min/max）+ 区域填充（正=绿，负=红）
- 情绪分布条（positive/neutral/negative 比例）
- 动量拐点标记（momentum_shift 事件）

### 6.2 热门实体云

- 按出现频率和情绪着色的词云
- 点击实体查看时间线

### 6.3 多维情绪雷达

- fear / greed / optimism / uncertainty 四维雷达图
- 动量拐点检测与标注

### 6.4 事件聚合时间线

- 按实体重叠自动聚类
- 显著性评分 (news_count × |sentiment_avg|)

### 6.5 美联储政策追踪

- 优先英文信息源 (CNBC/MarketWatch/Yahoo/Reuters)
- LLM 提炼：利率趋势 / 政策立场 / QE-QT 状态
- 折叠式 UI，点击展开

### 6.6 意图搜索 & 报告

- 输入自然语言意图，自动提取关键词 → 搜索 → 爬取 → 生成报告
- 支持追问 (follow-up) 和多模型对比 (contrarian view)

---

## Slide 7: API 设计

RESTful + WebSocket 混合架构，30+ 端点

| 类别 | 端点数 | 关键端点 |
|------|--------|---------|
| 健康与状态 | 2 | `/health`, `/status` |
| 美联储政策 | 2 | `/fed-policy`, `/fed-policy/news` |
| 订阅管理 | 4 | CRUD on `/subscriptions` |
| 新闻与情绪 | 7 | `/news/history`, `/sentiment/trend`, `/sentiment/multi` |
| 报告 | 6 | 生成/列表/详情/追问/导出/对比 |
| 实体与事件 | 4 | `/entities`, `/events`, `/knowledge/relations` |
| 告警与通知 | 4 | `/alerts/history`, `/notifications/{uid}` |
| 清理 | 1 | `/cleanup` |
| WebSocket | 1 | `/ws/dashboard` |

---

## Slide 8: 测试体系

### 覆盖范围

| 维度 | 数据 |
|------|------|
| 测试文件 | 17 个 |
| 测试用例 | 203 个 |
| 覆盖模块 | 后端全模块 + 全 API 端点 |

### 测试分层

```
┌──────────────────────────────────┐
│  API Tests (httpx ASGI Client)   │  ← 端到端，覆盖路由层
├──────────────────────────────────┤
│  Integration Tests (SQLite 内存)  │  ← 数据库 CRUD + 逻辑组合
├──────────────────────────────────┤
│  Unit Tests (Mock LLM/DB)        │  ← 纯逻辑，隔离外部依赖
└──────────────────────────────────┘
```

### 关键设计

- `autouse` fixture 自动初始化全局状态，测试间零泄漏
- 内存 SQLite + `seeded_db` fixture，每测试独立数据
- DeepSeekClient 统一 mock 路径，LLM 调用零成本
- pytest markers: `unit` / `integration` / `api` / `slow`

---

## Slide 9: 敏捷开发流程

### 开发节奏

```
Week 1        Week 2          Week 3          Week 4
┌──────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│ MVP       │ │ 深度分析     │ │ 前端可视化   │ │ 优化与扩展   │
│           │ │             │ │             │ │             │
│ • 爬虫     │ │ • Slow Track│ │ • 情绪趋势图 │ │ • Fed Policy│
│ • FinBERT  │ │ • 实体提取   │ │ • 实体云     │ │ • 意图搜索   │
│ • WebSocket│ │ • 事件聚类   │ │ • 雷达图     │ │ • 测试体系   │
│ • 基础告警 │ │ • 知识图谱   │ │ • 时间线     │ │ • 项目文档   │
└──────────┘ └─────────────┘ └─────────────┘ └─────────────┘
 交付: 可运行    交付: 5项分析   交付: 6个组件   交付: 生产就绪
```

### 核心原则

1. **MVP First** — 第一周交付最小可用产品（采集→评分→推送）
2. **Incremental Delivery** — 每周交付可演示的增量功能
3. **Vertical Slicing** — 每个功能从后端到前端完整实现
4. **Test-Driven** — 先写测试框架，后写业务代码（203 测试先行验证）

---

## Slide 10: 敏捷实践详解

### 1. 用户故事驱动

每个功能从一个用户故事开始：

```
作为交易员，
我想实时看到市场情绪变化，
以便在情绪拐点时调整仓位。

→ 拆解为：爬虫采集 + 情绪评分 + 趋势图 + WebSocket 推送
```

### 2. 迭代式开发 (Sprint)

| Sprint | 目标 | 交付物 |
|--------|------|--------|
| Sprint 1 | 数据管线打通 | 爬虫→去重→评分→推送，可用 CLI 验证 |
| Sprint 2 | 智能分析上线 | Slow Track 5 项分析，DB 持久化 |
| Sprint 3 | 可视化仪表盘 | 6 个 Vue 组件，WebSocket 实时更新 |
| Sprint 4 | 增值功能 | Fed 政策追踪、意图搜索、测试与文档 |

### 3. 持续集成

- **每次提交自动验证**：`pytest tests/` 全量回归
- **前后端分离构建**：`npm run build` + `pip install -e .`
- **Docker 一键部署**：`docker compose up -d`

### 4. 快速反馈循环

```
写代码 → 跑测试 → 看前端效果 → 收集反馈 → 下一轮
   ↑                                        │
   └────────────────────────────────────────┘
```

- 测试 < 30 秒完成，快速验证逻辑正确性
- 前端 dev server HMR，修改即见效果
- WebSocket 实时推送，端到端验证 < 1 分钟

---

## Slide 11: AI 辅助开发实践

### 人机协作模式

本项目的开发全程使用 **Claude Code (CLI)** 作为 AI 结对编程伙伴：

```
用户描述需求 / 发现问题
        ↓
Claude Code 理解上下文 → 探索代码库 → 制定方案 → 实现 → 测试
        ↓
用户 Review → 确认 / 修正方向 → 继续迭代
```

### 典型场景

| 场景 | AI 贡献 | 人工决策 |
|------|---------|---------|
| 新增 Fed Policy 栏目 | 自动创建模块/路由/组件/测试/文档 | 定义需求、审核架构方案 |
| 修复"暂无数据"问题 | 定位 API 路径不匹配，修复 4 个组件 | 确认修复方向 |
| 优化情绪趋势图 | 重写后端聚合+前端图表，一次到位 | 确认小时级聚合方案 |
| 重构测试体系 | 统一 conftest、重写 10 个测试文件 | 确认测试分层策略 |

### 效率提升

- **代码生成**：从描述到可运行代码，平均 < 5 分钟
- **Bug 定位**：跨模块问题追踪，从报错到根因 < 3 分钟
- **测试编写**：每个模块 5-11 个测试用例，一次生成通过
- **文档撰写**：README + 测试文档 + PPT 大纲，自动从代码生成

---

## Slide 12: 项目统计

| 指标 | 数值 |
|------|------|
| 后端模块 | 24 个 Python 文件 |
| 前端组件 | 12 个 Vue 组件 |
| API 端点 | 30+ |
| 新闻源 | 13 个（国内 7 + 海外 6） |
| 测试用例 | 203 个 |
| 代码行数 | ~5,000 行后端 + ~3,000 行前端 |
| 开发周期 | 4 周 |
| Git 提交 | 7 次 feature commit |

---

## Slide 13: 演示 / Live Demo

### 演示流程

1. 启动服务 → 打开仪表盘
2. 实时新闻采集 → 情绪评分推送到前端
3. 点击热门实体 → 查看实体情绪时间线
4. 展开美联储政策追踪 → 查看 LLM 生成的政策摘要
5. 意图搜索 → 输入"降息对银行股影响" → 生成完整报告
6. 报告追问 → 多模型对比

---

## Slide 14: 未来展望

| 方向 | 具体计划 |
|------|---------|
| 数据库升级 | SQLite → PostgreSQL，支持并发与连接池 |
| 用户认证 | JWT + 角色权限，多用户隔离 |
| 告警渠道 | 邮件 / 钉钉 / 企业微信 / Telegram |
| 历史回测 | 基于历史情绪数据回测交易策略 |
| 多市场支持 | A股 / 港股 / 美股 / 加密货币 独立看板 |
| 模型优化 | 接入 GPT-4 / Claude 做多模型交叉验证 |
| 部署优化 | Kubernetes 编排 + Prometheus 监控 |

---

## Slide 15: Q&A

**感谢聆听**

- 项目仓库：`D:\trading`
- 文档：`README.md` + `tests/README.md`
- API 文档：`http://localhost:8000/docs`（Swagger UI 自动生成）

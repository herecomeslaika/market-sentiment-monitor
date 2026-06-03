# Market Sentiment Monitor

Real-time financial news sentiment monitoring and analysis platform. Collects news from 13 domestic and overseas sources, runs FinBERT sentiment scoring, performs deep LLM analysis on high-impact events, and presents everything through a Vue 3 dashboard with WebSocket live updates.

## Architecture

```
News Sources (13)          Backend (FastAPI)              Frontend (Vue 3)
┌──────────────┐     ┌─────────────────────────┐     ┌───────────────────┐
│ Sina/CLS/Jin10│     │ Crawler ──→ Dedup       │     │ SentimentChart    │
│ EastMoney/36Kr│────▶│   │                     │     │ NewsFeed/AlertFeed│
│ CNBC/MW/Yahoo│     │   ▼                     │     │ EntityCloud       │
│ BBC/Investing │     │ Fast Track (FinBERT)    │     │ MultiSentimentRadar│
└──────────────┘     │   │                     │     │ EventTimeline     │
                     │   ▼                     │     │ KnowledgeGraph    │
                     │ Slow Track (DeepSeek)   │     │ FedPolicy         │
                     │   ├─ Entity Extract     │     │ ReportBrowser     │
                     │   ├─ Multi-Sentiment    │     │ IntentSearch      │
                     │   ├─ Event Cluster      │────▶│ SubscriptionMgr   │
                     │   ├─ Knowledge Graph    │ WS  │ KeywordStats      │
                     │   └─ Report Generate    │     └───────────────────┘
                     │   │                     │
                     │   ▼                     │
                     │ Alert → WebSocket Push  │
                     └─────────────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 18+
- DeepSeek API key

### Install & Run

```bash
# Backend
pip install -e ".[dev]"
cp .env.example .env
# Edit .env: set SENTIMENT_DEEPSEEK_API_KEY

# Frontend
cd frontend && npm install && npm run build && cd ..

# Start server
python -m app.main
# Or: serve  (via pyproject.toml entry point)
```

Open http://localhost:8000

### Development

```bash
# Backend (hot reload)
uvicorn app.main:app --reload

# Frontend (dev server)
cd frontend && npm run dev
# Opens at http://localhost:5174, proxies API to :8000
```

### Docker

```bash
docker compose up -d
```

## Configuration

All settings via environment variables (prefix `SENTIMENT_`) or `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `DEEPSEEK_API_KEY` | *required* | DeepSeek LLM API key |
| `DEEPSEEK_MODEL` | `deepseek-chat` | LLM model name |
| `RSS_POLL_INTERVAL_SECONDS` | `30` | Crawler poll interval |
| `MODEL_NAME` | `distilbert-base-multilingual-...` | FinBERT model |
| `PROCESS_POOL_SIZE` | `2` | FinBERT worker processes |
| `DEFAULT_ALERT_THRESHOLD` | `-0.5` | Alert trigger threshold |
| `HOST` / `PORT` | `0.0.0.0` / `8000` | Server bind address |

## News Sources

### Domestic (7)
| Source | Key | Parser |
|--------|-----|--------|
| 新浪财经-A股 | `sina_stock` | sina |
| 新浪财经-港股 | `sina_hk` | sina |
| 新浪财经-美股 | `sina_us` | sina |
| 东方财富 | `eastmoney` | eastmoney |
| 财联社 | `cls` | cls |
| 金十数据 | `jin10` | jin10 |
| 36氪 | `kr36` | kr36 |

### Overseas (6)
| Source | Key | Parser |
|--------|-----|--------|
| CNBC | `cnbc_top` | rss |
| CNBC Asia | `cnbc_asia` | rss |
| MarketWatch | `marketwatch` | rss |
| Yahoo Finance | `yahoo_finance` | rss |
| BBC Business | `bbc_business` | rss |
| Investing Crypto | `investing_crypto` | rss |

## API Reference

### Health & Status
| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Queue sizes, connection count |
| GET | `/status` | Full system status |

### Fed Policy
| Method | Path | Description |
|--------|------|-------------|
| GET | `/fed-policy` | Current policy summary (cached 1h) |
| GET | `/fed-policy?refresh=true` | Force regenerate summary |
| GET | `/fed-policy/news` | Fed-related news list |

### Subscriptions
| Method | Path | Description |
|--------|------|-------------|
| POST | `/subscriptions` | Create subscription |
| GET | `/subscriptions` | List all subscriptions |
| GET | `/subscriptions/{user_id}` | Get specific subscription |
| DELETE | `/subscriptions/{user_id}` | Remove subscription |

### Sources
| Method | Path | Description |
|--------|------|-------------|
| GET | `/sources` | List all sources |
| POST | `/sources` | Add new source |
| PATCH | `/sources/{key}` | Update source (enable/disable) |
| DELETE | `/sources/{key}` | Remove source |

### News & Sentiment
| Method | Path | Description |
|--------|------|-------------|
| GET | `/news/history` | News list (paginated) |
| GET | `/sentiment/trend` | Hourly trend with MA + momentum shifts |
| GET | `/sentiment/history` | Recent sentiment records |
| GET | `/sentiment/multi` | Multi-dimensional sentiment |
| GET | `/sentiment/momentum` | Momentum shift events |
| GET | `/sentiment/entity/{name}` | Entity-specific sentiment |

### Reports
| Method | Path | Description |
|--------|------|-------------|
| POST | `/reports/generate` | Generate intent-based report |
| GET | `/reports` | List reports |
| GET | `/reports/{id}` | Get report detail |
| POST | `/reports/{id}/followup` | Ask follow-up question |
| GET | `/reports/{id}/markdown` | Export as Markdown |
| POST | `/reports/{id}/compare` | Multi-model contrarian view |

### Entities & Events
| Method | Path | Description |
|--------|------|-------------|
| GET | `/entities` | Hot entities |
| GET | `/entities/{name}/timeline` | Entity timeline |
| GET | `/events` | Event clusters |
| GET | `/events/{cluster_id}` | Event detail |

### Knowledge Graph
| Method | Path | Description |
|--------|------|-------------|
| GET | `/knowledge/relations` | Entity relations |
| GET | `/knowledge/relations/{name}` | Entity-specific relations |
| POST | `/knowledge/causal-chain` | Infer causal chain |

### Alerts & Notifications
| Method | Path | Description |
|--------|------|-------------|
| GET | `/alerts/history` | Alert history |
| GET | `/notifications/{user_id}` | Notification preferences |
| PUT | `/notifications/{user_id}` | Set notification preferences |
| POST | `/cleanup` | Clean old data |

### WebSocket

Connect to `/ws/dashboard` for real-time updates:

```json
{"type": "news", "payload": {...}}
{"type": "sentiment", "payload": {...}}
{"type": "alert", "payload": {...}}
{"type": "momentum_shift", "payload": {...}}
{"type": "entity_update", "payload": {...}}
{"type": "event_update", "payload": {...}}
```

## Backend Modules

| Module | Description |
|--------|-------------|
| `app/main.py` | FastAPI app, lifespan, background tasks |
| `app/deps.py` | Global state (queues, connections, settings) |
| `app/db.py` | SQLite schema, migration, connection management |
| `app/models.py` | Pydantic/dataclass models |
| `app/repository.py` | Database CRUD operations |
| `app/crawler/sources.py` | News source configs and parsers |
| `app/crawler/scheduler.py` | Periodic crawl scheduler |
| `app/crawler/dedup.py` | Title-hash deduplication |
| `app/sentiment/finbert_worker.py` | FinBERT process pool worker |
| `app/sentiment/fast_track.py` | Fast-track sentiment consumer |
| `app/analysis/slow_track.py` | Slow-track deep analysis pipeline |
| `app/analysis/deepseek_client.py` | DeepSeek LLM client (with retries) |
| `app/analysis/entity_extractor.py` | Named entity extraction |
| `app/analysis/multi_sentiment.py` | Fear/greed/optimism/uncertainty analysis |
| `app/analysis/event_cluster.py` | Event clustering by entity overlap |
| `app/analysis/knowledge_graph.py` | Entity relation & causal chain inference |
| `app/analysis/intent_report.py` | On-demand intent-based report generation |
| `app/analysis/fed_policy.py` | Fed monetary policy tracker |
| `app/analysis/report_service.py` | Report storage, follow-up, multi-model compare |
| `app/subscription/matcher.py` | Subscription keyword matching |
| `app/subscription/manager.py` | Subscription CRUD with DB persistence |
| `app/notification/dispatcher.py` | Alert dispatch with silence/level filtering |
| `app/ws/connection_manager.py` | WebSocket connection manager & alert pusher |

## Frontend Components

| Component | Description |
|-----------|-------------|
| `SentimentChart.vue` | Trend chart with MA line, volatility band, distribution bars, momentum markers |
| `NewsFeed.vue` | Real-time news list with sentiment scores |
| `AlertFeed.vue` | Alert notifications |
| `EntityCloud.vue` | Hot entity word cloud |
| `MultiSentimentRadar.vue` | Fear/greed/optimism radar chart |
| `EventTimeline.vue` | Event cluster timeline |
| `KnowledgeGraph.vue` | Entity relation graph |
| `FedPolicy.vue` | Fed policy tracker (collapsible, English-source prioritized) |
| `IntentSearch.vue` | On-demand report generation from intent |
| `ReportBrowser.vue` | Report list with follow-up & compare |
| `SubscriptionManager.vue` | Keyword subscription management |
| `KeywordStats.vue` | Triggered keyword statistics |

## Testing

See [tests/README.md](tests/README.md) for full documentation.

```bash
# Run all tests (203 tests)
python -m pytest tests/

# By marker
python -m pytest -m unit
python -m pytest -m integration
python -m pytest -m api
python -m pytest -m "not slow"

# With coverage
python -m pytest tests/ --cov=app --cov-report=term-missing
```

## Data Pipeline

```
1. Crawler polls sources every 30s
2. New items → dedup (MD5 title hash) → news_queue
3. Fast Track: FinBERT scores sentiment → scored_queue
4. Slow Track (if score crosses threshold):
   a. Entity extraction (DeepSeek)
   b. Multi-sentiment analysis (fear/greed/optimism/uncertainty)
   c. Event clustering (entity overlap matching)
   d. Knowledge graph relation extraction
   e. Deep analysis report (LangGraph flow)
5. Alert → WebSocket push to subscribed users
```

## Database Schema

SQLite at `data/sentiment.db` with tables:

- `news` — Raw news items with title hash dedup
- `sentiment` — FinBERT scores (score, label, confidence)
- `alerts` — Triggered alerts with deep analysis
- `reports` — Stored reports with referenced news
- `subscriptions` — User keyword subscriptions
- `entities` — Named entities with aliases
- `news_entities` — News-entity linkage
- `event_clusters` — Clustered events with significance
- `multi_sentiment` — Fear/greed/optimism/uncertainty + momentum
- `entity_relations` — Knowledge graph edges
- `fed_policy_summary` — Fed policy snapshots (1h cache)

## License

Private project.

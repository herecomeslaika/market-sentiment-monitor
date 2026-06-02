<template>
  <div class="dashboard">
    <header class="header">
      <h1>市场情绪监控</h1>
      <span class="status" :class="{ connected: wsConnected }">
        {{ wsConnected ? '已连接' : '未连接' }}
      </span>
    </header>
    <div class="intent-section">
      <IntentSearch @view-report="onViewReport" />
    </div>
    <div class="intelligence-row">
      <div class="intel-card">
        <EntityCloud @select="onEntitySelect" />
      </div>
      <div class="intel-card">
        <MultiSentimentRadar />
      </div>
      <div class="intel-card">
        <EventTimeline @select="onEventSelect" />
      </div>
    </div>
    <div class="grid">
      <div class="chart-area">
        <SentimentChart :trend="trend" />
      </div>
      <div class="sidebar">
        <KeywordStats :keywords="keywords" />
        <SubscriptionManager
          :subscription="subscription"
          @subscribe="handleSubscribe"
          @unsubscribe="handleUnsubscribe"
        />
      </div>
    </div>
    <div class="feeds">
      <NewsFeed :news="mergedNews" />
      <AlertFeed :alerts="alerts" />
    </div>
    <div class="reports-section">
      <ReportBrowser ref="reportBrowserRef" />
      <KnowledgeGraph @select="onEntitySelect" />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import SentimentChart from './components/SentimentChart.vue'
import NewsFeed from './components/NewsFeed.vue'
import AlertFeed from './components/AlertFeed.vue'
import KeywordStats from './components/KeywordStats.vue'
import SubscriptionManager from './components/SubscriptionManager.vue'
import ReportBrowser from './components/ReportBrowser.vue'
import IntentSearch from './components/IntentSearch.vue'
import EntityCloud from './components/EntityCloud.vue'
import EventTimeline from './components/EventTimeline.vue'
import MultiSentimentRadar from './components/MultiSentimentRadar.vue'
import KnowledgeGraph from './components/KnowledgeGraph.vue'

const news = ref([])
const sentiments = ref([])
const alerts = ref([])
const trend = ref([])
const keywords = ref([])
const subscription = ref(null)
const wsConnected = ref(false)
const reportBrowserRef = ref(null)
function onViewReport(report) {
  if (reportBrowserRef.value) {
    reportBrowserRef.value.openReport(report)
  }
  document.querySelector('.reports-section')?.scrollIntoView({ behavior: 'smooth' })
}

function onEntitySelect(entity) {
  // Scroll to intent search and populate with entity name
  const input = document.querySelector('.intent-search input')
  if (input) {
    input.value = entity.name + '的影响分析'
    input.dispatchEvent(new Event('input'))
  }
  document.querySelector('.intent-section')?.scrollIntoView({ behavior: 'smooth' })
}

function onEventSelect(event) {
  if (reportBrowserRef.value) {
    reportBrowserRef.value.openReport({
      id: event.id,
      alert_level: event.significance >= 0.5 ? 'warning' : 'info',
      triggered_keywords: (event.entities || []).map(e => e.name),
      deep_analysis: null,
      news_title: event.title,
      news_source: '事件聚合',
      created_at: event.last_seen,
      sentiment_score: event.sentiment_avg,
      sentiment_label: event.sentiment_avg < -0.3 ? 'negative' : event.sentiment_avg > 0.3 ? 'positive' : 'neutral',
    })
  }
  document.querySelector('.reports-section')?.scrollIntoView({ behavior: 'smooth' })
}

let ws = null
let wsReconnectTimer = null

// Merge news with sentiment scores
const mergedNews = computed(() => {
  const scoreMap = new Map()
  for (const s of sentiments.value) {
    if (s.title_hash) scoreMap.set(s.title_hash, s)
  }
  return news.value.map(item => {
    const scoreData = scoreMap.get(item.title_hash)
    if (scoreData) {
      return { ...item, score: scoreData.score, label: scoreData.label }
    }
    return item
  }).sort((a, b) => {
    // Items with scores first, then by recency
    if (a.score != null && b.score == null) return -1
    if (a.score == null && b.score != null) return 1
    return 0
  })
})

async function fetchData() {
  try {
    const [newsRes, sentRes, trendRes, kwRes] = await Promise.all([
      fetch('/news/history?limit=50').then(r => r.json()),
      fetch('/sentiment/history?hours=24').then(r => r.json()),
      fetch('/sentiment/trend').then(r => r.json()),
      fetch('/stats/keywords').then(r => r.json()),
    ])
    if (Array.isArray(newsRes)) news.value = newsRes
    if (Array.isArray(sentRes)) sentiments.value = sentRes
    if (Array.isArray(trendRes)) trend.value = trendRes
    if (Array.isArray(kwRes)) keywords.value = kwRes
  } catch (e) {
    console.error('Failed to fetch data:', e)
  }
}

function connectWS() {
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
  const url = `${protocol}://${location.host}/ws/dashboard`
  ws = new WebSocket(url)

  ws.onopen = () => {
    wsConnected.value = true
    // Send subscription if exists
    if (subscription.value) {
      ws.send(JSON.stringify({
        action: 'subscribe',
        keywords: subscription.value.keywords,
        threshold: subscription.value.threshold,
      }))
    }
  }

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.type === 'news') {
        news.value = [data.payload, ...news.value].slice(0, 100)
      } else if (data.type === 'sentiment') {
        sentiments.value = [data.payload, ...sentiments.value].slice(0, 100)
      } else if (data.type === 'alert') {
        alerts.value = [formatAlert(data.payload), ...alerts.value].slice(0, 50)
      } else if (data.type === 'entity_update') {
        // Entity updates — could trigger refresh of entity cloud
      } else if (data.type === 'event_update') {
        // Event cluster updates — could trigger refresh of event timeline
      } else if (data.type === 'momentum_shift') {
        // Momentum shift alerts
        const payload = data.payload || data
        alerts.value = [{
          alert_level: 'warning',
          title: `情绪拐点: ${payload.entity}`,
          score: null,
          label: payload.dominant,
          deep_analysis: null,
          keywords: [payload.entity],
          created_at: new Date().toLocaleString('zh-CN'),
          is_momentum_shift: true,
        }, ...alerts.value].slice(0, 50)
      }
    } catch (e) {
      console.error('WS message error:', e)
    }
  }

  ws.onclose = () => {
    wsConnected.value = false
    // Reconnect after 3s
    wsReconnectTimer = setTimeout(connectWS, 3000)
  }

  ws.onerror = () => {
    wsConnected.value = false
  }
}

function formatAlert(payload) {
  return {
    alert_level: payload.alert_level || 'warning',
    title: payload.news_item?.title || payload.title || '',
    score: payload.sentiment?.score ?? payload.score ?? null,
    label: payload.sentiment?.label || payload.label || '',
    deep_analysis: payload.deep_analysis || null,
    keywords: payload.triggered_keywords || [],
    created_at: new Date().toLocaleString('zh-CN'),
  }
}

function handleSubscribe(data) {
  subscription.value = data
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ action: 'subscribe', keywords: data.keywords, threshold: data.threshold }))
  }
}

function handleUnsubscribe() {
  subscription.value = null
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ action: 'unsubscribe' }))
  }
}

onMounted(() => {
  fetchData()
  connectWS()
  // Refresh data every 30s
  const interval = setInterval(fetchData, 30000)
  onUnmounted(() => {
    clearInterval(interval)
    if (ws) ws.close()
    if (wsReconnectTimer) clearTimeout(wsReconnectTimer)
  })
})
</script>

<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: #f0f2f5;
  color: #333;
}
.dashboard { max-width: 1200px; margin: 0 auto; padding: 16px; }
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.header h1 { font-size: 24px; }
.status {
  font-size: 13px;
  padding: 4px 12px;
  border-radius: 12px;
  background: #fee;
  color: #e74c3c;
}
.status.connected { background: #e8f8ef; color: #27ae60; }
.intelligence-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  padding: 0 16px;
  margin-bottom: 16px;
}
.intel-card {
  background: #fff;
  border-radius: 8px;
  border: 1px solid #e0e0e0;
  overflow: hidden;
}
.grid {
  display: grid;
  grid-template-columns: 1fr 320px;
  gap: 16px;
  margin-bottom: 16px;
}
.sidebar { display: flex; flex-direction: column; gap: 16px; }
.feeds {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.intent-section {
  margin-bottom: 16px;
}
.reports-section {
  margin-top: 16px;
}
@media (max-width: 768px) {
  .grid { grid-template-columns: 1fr; }
  .feeds { grid-template-columns: 1fr; }
}
</style>

<template>
  <div class="dashboard">
    <header class="header">
      <h1>市场情绪监控</h1>
      <div class="status-bar">
        <span :class="['status-dot', connected ? 'online' : 'offline']"></span>
        <span>{{ connected ? '已连接' : '未连接' }}</span>
        <span class="spacer"></span>
        <span>队列: {{ health.news_queue_size }}/{{ health.scored_queue_size }}/{{ health.alert_queue_size }}</span>
        <span>订阅: {{ health.active_subscriptions }}</span>
      </div>
    </header>

    <div class="grid">
      <!-- Sentiment Trend Chart -->
      <section class="card span-2">
        <h2>情绪趋势</h2>
        <SentimentChart :data="sentimentTrend" />
      </section>

      <!-- Alert Feed -->
      <section class="card">
        <h2>实时告警</h2>
        <AlertFeed :alerts="alerts" />
      </section>

      <!-- News Feed -->
      <section class="card">
        <h2>最新新闻</h2>
        <NewsFeed :news="newsList" />
      </section>

      <!-- Keyword Stats -->
      <section class="card">
        <h2>关键词统计</h2>
        <KeywordStats :stats="keywordStats" />
      </section>

      <!-- Subscription Manager -->
      <section class="card">
        <h2>订阅管理</h2>
        <SubscriptionManager />
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import SentimentChart from './components/SentimentChart.vue'
import AlertFeed from './components/AlertFeed.vue'
import NewsFeed from './components/NewsFeed.vue'
import KeywordStats from './components/KeywordStats.vue'
import SubscriptionManager from './components/SubscriptionManager.vue'
import { useApi } from './composables/useApi.js'

const health = ref({})
const sentimentTrend = ref([])
const alerts = ref([])
const newsList = ref([])
const keywordStats = ref([])
const connected = ref(false)

const api = useApi()

let ws = null
let pollTimer = null

async function fetchHealth() {
  try {
    health.value = await api.get('/health')
  } catch {}
}

async function fetchSentimentTrend() {
  try {
    sentimentTrend.value = await api.get('/sentiment/trend?hours=24')
  } catch {}
}

async function fetchNews() {
  try {
    newsList.value = await api.get('/news/history?limit=20')
  } catch {}
}

async function fetchAlerts() {
  try {
    const data = await api.get('/alerts/history?limit=20')
    alerts.value = data
  } catch {}
}

async function fetchKeywordStats() {
  try {
    keywordStats.value = await api.get('/stats/keywords?hours=24')
  } catch {}
}

async function pollData() {
  await Promise.all([
    fetchHealth(),
    fetchSentimentTrend(),
    fetchNews(),
    fetchAlerts(),
    fetchKeywordStats(),
  ])
}

function connectWebSocket() {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  ws = new WebSocket(`${protocol}//${location.host}/ws/dashboard`)

  ws.onopen = () => { connected.value = true }
  ws.onclose = () => { connected.value = false; setTimeout(connectWebSocket, 3000) }
  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data)
      if (msg.type === 'alert') {
        alerts.value.unshift(msg.payload)
        if (alerts.value.length > 50) alerts.value.pop()
      }
    } catch {}
  }
}

onMounted(() => {
  pollData()
  pollTimer = setInterval(pollData, 15000)
  connectWebSocket()
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (ws) ws.close()
})
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; }
.dashboard { max-width: 1400px; margin: 0 auto; padding: 20px; }
.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; padding: 16px 20px; background: #1e293b; border-radius: 12px; }
.header h1 { font-size: 20px; font-weight: 600; }
.status-bar { display: flex; align-items: center; gap: 12px; font-size: 13px; color: #94a3b8; }
.spacer { flex: 1; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; }
.status-dot.online { background: #22c55e; }
.status-dot.offline { background: #ef4444; }
.grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.card { background: #1e293b; border-radius: 12px; padding: 20px; }
.card.span-2 { grid-column: span 2; }
.card h2 { font-size: 15px; font-weight: 600; margin-bottom: 16px; color: #cbd5e1; }
@media (max-width: 900px) { .grid { grid-template-columns: 1fr; } .card.span-2 { grid-column: span 1; } }
</style>

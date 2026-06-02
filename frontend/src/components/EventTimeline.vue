<template>
  <div class="event-timeline">
    <h3>事件聚合</h3>
    <div v-if="loading" class="loading">加载中...</div>
    <div v-else-if="events.length === 0" class="empty">暂无事件数据</div>
    <div v-else class="timeline-list">
      <div
        v-for="event in events"
        :key="event.id"
        class="event-card"
        @click="$emit('select', event)"
      >
        <div class="event-header">
          <span class="event-badge" :class="significanceClass(event.significance)">
            {{ event.significance >= 0.5 ? '重要' : '一般' }}
          </span>
          <span class="event-time">{{ formatTime(event.last_seen) }}</span>
        </div>
        <div class="event-title">{{ event.title }}</div>
        <div class="event-meta">
          <span class="event-count">{{ event.news_ids?.length || 0 }} 条新闻</span>
          <span class="score-badge" :class="scoreClass(event.sentiment_avg)">
            {{ event.sentiment_avg?.toFixed(2) || '0.00' }}
          </span>
        </div>
        <div v-if="event.entities?.length" class="event-entities">
          <span v-for="e in event.entities.slice(0, 4)" :key="e.name" class="entity-chip">
            {{ e.name }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const props = defineProps({ apiBase: { type: String, default: '' } })
const emit = defineEmits(['select'])

const events = ref([])
const loading = ref(true)

function significanceClass(s) { return s >= 0.7 ? 'critical' : s >= 0.5 ? 'warning' : 'info' }
function scoreClass(s) { return s < -0.3 ? 'negative' : s > 0.3 ? 'positive' : 'neutral' }
function formatTime(t) { return t ? new Date(t).toLocaleString('zh-CN') : '' }

async function fetchEvents() {
  try {
    const resp = await fetch(`${props.apiBase}/events?limit=20`)
    if (resp.ok) events.value = await resp.json()
  } catch (e) {
    console.error('Failed to fetch events:', e)
  } finally {
    loading.value = false
  }
}

onMounted(fetchEvents)
</script>

<style scoped>
.timeline-list { display: flex; flex-direction: column; gap: 8px; }
.event-card {
  padding: 10px; border-radius: 6px; cursor: pointer;
  border-left: 3px solid #3498db; background: #f8f9fa;
  transition: all 0.15s;
}
.event-card:hover { background: #e9ecef; }
.event-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.event-badge { font-size: 11px; padding: 2px 8px; border-radius: 10px; font-weight: 600; }
.event-badge.critical { background: #f8d7da; color: #721c24; }
.event-badge.warning { background: #fef3cd; color: #856404; }
.event-badge.info { background: #d1ecf1; color: #0c5460; }
.event-time { font-size: 11px; color: #999; }
.event-title { font-size: 14px; font-weight: 500; color: #333; }
.event-meta { display: flex; justify-content: space-between; margin-top: 4px; font-size: 12px; }
.score-badge { padding: 2px 6px; border-radius: 8px; font-weight: 600; }
.score-badge.negative { background: #fde8e8; color: #e74c3c; }
.score-badge.positive { background: #e8f8ef; color: #27ae60; }
.score-badge.neutral { background: #fef9e7; color: #f39c12; }
.event-entities { margin-top: 4px; }
.entity-chip {
  font-size: 11px; background: #e8f4fd; color: #2980b9;
  padding: 1px 6px; border-radius: 8px; margin-right: 3px;
}
.loading, .empty { color: #999; text-align: center; padding: 20px; }
</style>
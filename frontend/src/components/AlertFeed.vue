<template>
  <div class="alert-feed">
    <div v-if="!alerts.length" class="empty">暂无告警</div>
    <div v-for="a in alerts" :key="a.id" :class="['alert-item', a.alert_level]">
      <div class="alert-header">
        <span :class="['badge', a.alert_level]">{{ levelText(a.alert_level) }}</span>
        <span class="time">{{ formatTime(a.created_at) }}</span>
      </div>
      <div class="title">{{ a.title }}</div>
      <div class="meta">
        <span>{{ a.source }}</span>
        <span>情绪: {{ a.score?.toFixed(3) }}</span>
        <span v-if="a.triggered_keywords?.length">关键词: {{ a.triggered_keywords?.join(', ') }}</span>
      </div>
      <div v-if="a.deep_analysis" class="analysis">{{ a.deep_analysis?.slice(0, 150) }}...</div>
    </div>
  </div>
</template>

<script setup>
defineProps({ alerts: { type: Array, default: () => [] } })

function levelText(level) {
  return { critical: '严重', warning: '警告', info: '信息' }[level] || level
}

function formatTime(t) {
  if (!t) return ''
  return new Date(t).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}
</script>

<style scoped>
.alert-feed { max-height: 400px; overflow-y: auto; }
.alert-item { padding: 10px 12px; border-radius: 8px; margin-bottom: 8px; background: #0f172a; border-left: 3px solid #64748b; }
.alert-item.critical { border-left-color: #ef4444; }
.alert-item.warning { border-left-color: #f59e0b; }
.alert-item.info { border-left-color: #3b82f6; }
.alert-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.badge { font-size: 11px; padding: 2px 8px; border-radius: 4px; font-weight: 600; }
.badge.critical { background: #7f1d1d; color: #fca5a5; }
.badge.warning { background: #78350f; color: #fcd34d; }
.badge.info { background: #1e3a5f; color: #93c5fd; }
.time { font-size: 11px; color: #64748b; }
.title { font-size: 13px; font-weight: 500; margin-bottom: 4px; }
.meta { font-size: 11px; color: #94a3b8; display: flex; gap: 12px; }
.analysis { font-size: 12px; color: #cbd5e1; margin-top: 6px; padding-top: 6px; border-top: 1px solid #334155; }
.empty { color: #64748b; font-size: 13px; text-align: center; padding: 40px 0; }
</style>

<template>
  <div class="alert-feed">
    <h2>预警通知</h2>
    <div class="alert-list">
      <div v-for="(alert, idx) in alerts" :key="idx" class="alert-item" :class="alertLevel(alert)">
        <div class="alert-header">
          <span class="alert-level">{{ alert.alert_level || 'warning' }}</span>
          <span class="alert-time">{{ alert.created_at || '' }}</span>
        </div>
        <div class="alert-title">{{ alert.title }}</div>
        <div v-if="alert.score != null" class="alert-score">
          情绪分数: <strong>{{ alert.score.toFixed(2) }}</strong>
        </div>
        <div v-if="alert.deep_analysis" class="alert-analysis">
          <details>
            <summary>深度分析</summary>
            <div class="analysis-content">{{ alert.deep_analysis }}</div>
          </details>
        </div>
        <div v-if="alert.keywords && alert.keywords.length" class="alert-keywords">
          触发关键词:
          <span v-for="kw in alert.keywords" :key="kw" class="keyword-tag">{{ kw }}</span>
        </div>
      </div>
    </div>
    <div v-if="!alerts.length" class="empty">暂无预警</div>
  </div>
</template>

<script setup>
const props = defineProps({
  alerts: { type: Array, default: () => [] }
})

function alertLevel(alert) {
  const level = alert.alert_level || 'warning'
  if (level === 'critical') return 'critical'
  if (level === 'info') return 'info'
  return 'warning'
}
</script>

<style scoped>
.alert-feed {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}
.alert-feed h2 {
  margin: 0 0 12px;
  font-size: 18px;
}
.alert-item {
  padding: 12px;
  border-radius: 6px;
  margin-bottom: 8px;
  border-left: 4px solid #f39c12;
  background: #fffbf0;
}
.alert-item.critical {
  border-left-color: #e74c3c;
  background: #fff5f5;
}
.alert-item.info {
  border-left-color: #3498db;
  background: #f0f8ff;
}
.alert-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 6px;
}
.alert-level {
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  padding: 2px 8px;
  border-radius: 10px;
  background: #fef3cd;
  color: #856404;
}
.alert-item.critical .alert-level { background: #f8d7da; color: #721c24; }
.alert-item.info .alert-level { background: #d1ecf1; color: #0c5460; }
.alert-time { font-size: 11px; color: #999; }
.alert-title { font-size: 14px; font-weight: 500; color: #333; }
.alert-score { font-size: 12px; color: #666; margin-top: 4px; }
.alert-analysis { margin-top: 8px; }
.analysis-content {
  font-size: 12px;
  color: #555;
  white-space: pre-wrap;
  padding: 8px;
  background: #f9f9f9;
  border-radius: 4px;
  margin-top: 4px;
  max-height: 200px;
  overflow-y: auto;
}
.keyword-tag {
  font-size: 11px;
  background: #e8f4fd;
  color: #2980b9;
  padding: 1px 6px;
  border-radius: 8px;
  margin-right: 4px;
}
.empty { text-align: center; color: #999; padding: 24px; }
</style>

<template>
  <div class="keyword-stats">
    <h2>关键词统计</h2>
    <div class="stats-list">
      <div v-for="(s, i) in keywords" :key="i" class="stat-row">
        <div class="stat-label">
          <span v-for="kw in keywordList(s)" :key="kw" class="kw-tag">{{ kw }}</span>
        </div>
        <div class="stat-bar">
          <div class="bar-fill" :style="{ width: barWidth(s.count) }"></div>
        </div>
        <span class="stat-count">{{ s.count }}</span>
        <span :class="['level-badge', s.alert_level]">{{ s.alert_level }}</span>
      </div>
    </div>
    <div v-if="!keywords.length" class="empty">暂无统计数据</div>
  </div>
</template>

<script setup>
const props = defineProps({
  keywords: { type: Array, default: () => [] }
})

function keywordList(s) {
  if (Array.isArray(s.triggered_keywords)) return s.triggered_keywords
  if (typeof s.triggered_keywords === 'string') return [s.triggered_keywords]
  return []
}

function barWidth(count) {
  const max = Math.max(...props.keywords.map(s => s.count || 0), 1)
  return Math.min(100, (count / max) * 100) + '%'
}
</script>

<style scoped>
.keyword-stats {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}
.keyword-stats h2 {
  margin: 0 0 12px;
  font-size: 18px;
}
.stat-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  border-bottom: 1px solid #f0f0f0;
}
.stat-label {
  min-width: 100px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.kw-tag {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 4px;
  background: #e8f4fd;
  color: #2980b9;
}
.stat-bar {
  flex: 1;
  height: 6px;
  background: #f0f0f0;
  border-radius: 3px;
}
.bar-fill {
  height: 100%;
  background: #3498db;
  border-radius: 3px;
}
.stat-count {
  font-size: 12px;
  color: #666;
  min-width: 20px;
  text-align: right;
}
.level-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
}
.level-badge.critical { background: #fde8e8; color: #e74c3c; }
.level-badge.warning { background: #fef3cd; color: #856404; }
.level-badge.info { background: #d1ecf1; color: #0c5460; }
.empty {
  text-align: center;
  color: #999;
  padding: 24px;
}
</style>

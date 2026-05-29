<template>
  <div class="keyword-stats">
    <div v-if="!stats.length" class="empty">暂无统计数据</div>
    <div v-for="s in stats" :key="s.triggered_keywords" class="stat-row">
      <div class="keywords">
        <span v-for="kw in (Array.isArray(s.triggered_keywords) ? s.triggered_keywords : [s.triggered_keywords])" :key="kw" class="kw-tag">{{ kw }}</span>
      </div>
      <div class="bar-container">
        <div class="bar" :style="{ width: barWidth(s.count) + '%' }"></div>
      </div>
      <span class="count">{{ s.count }}</span>
      <span :class="['level-tag', s.alert_level]">{{ s.alert_level }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
const props = defineProps({ stats: { type: Array, default: () => [] } })

const maxCount = computed(() => Math.max(...props.stats.map(s => s.count || 0), 1))
function barWidth(count) { return Math.min(100, (count / maxCount.value) * 100) }
</script>

<style scoped>
.keyword-stats { }
.stat-row { display: flex; align-items: center; gap: 10px; padding: 6px 0; border-bottom: 1px solid #1e293b; }
.keywords { display: flex; gap: 4px; min-width: 120px; }
.kw-tag { font-size: 11px; padding: 2px 6px; border-radius: 3px; background: #1e3a5f; color: #93c5fd; }
.bar-container { flex: 1; height: 6px; background: #0f172a; border-radius: 3px; }
.bar { height: 100%; background: #3b82f6; border-radius: 3px; transition: width 0.3s; }
.count { font-size: 12px; color: #94a3b8; min-width: 24px; text-align: right; }
.level-tag { font-size: 10px; padding: 1px 6px; border-radius: 3px; }
.level-tag.critical { background: #7f1d1d; color: #fca5a5; }
.level-tag.warning { background: #78350f; color: #fcd34d; }
.level-tag.info { background: #1e3a5f; color: #93c5fd; }
.empty { color: #64748b; font-size: 13px; text-align: center; padding: 40px 0; }
</style>

<template>
  <div class="chart-container">
    <h2>情绪趋势</h2>
    <div class="chart" ref="chartRef">
      <svg :width="width" :height="height">
        <!-- Grid lines -->
        <line v-for="y in gridY" :key="'g-'+y" x1="40" :y1="y" :x2="width-10" :y2="y" stroke="#eee" />
        <!-- Y-axis labels -->
        <text v-for="(label, i) in yLabels" :key="'yl-'+i" x="5" :y="gridY[i]+4" font-size="10" fill="#999">{{ label }}</text>
        <!-- Zero line -->
        <line :x1="40" :y1="zeroY" :x2="width-10" :y2="zeroY" stroke="#ccc" stroke-dasharray="4" />
        <!-- Data line -->
        <polyline
          v-if="points.length > 1"
          :points="pointsStr"
          fill="none"
          stroke="#3498db"
          stroke-width="2"
        />
        <!-- Data dots -->
        <circle v-for="(p, i) in points" :key="'d-'+i" :cx="p.x" :cy="p.y" r="3" :fill="dotColor(p.raw)" />
      </svg>
    </div>
    <div v-if="!trend.length" class="empty">暂无趋势数据</div>
  </div>
</template>

<script setup>
import { computed, ref, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  trend: { type: Array, default: () => [] }
})

const chartRef = ref(null)
const width = ref(600)
const height = ref(250)

const padding = { top: 20, right: 10, bottom: 30, left: 40 }

function resize() {
  if (chartRef.value) {
    width.value = Math.max(chartRef.value.clientWidth, 300)
  }
}

onMounted(() => {
  resize()
  window.addEventListener('resize', resize)
})
onUnmounted(() => window.removeEventListener('resize', resize))

const gridY = computed(() => {
  const ys = []
  for (let i = 0; i <= 4; i++) {
    ys.push(padding.top + (i * (height.value - padding.top - padding.bottom)) / 4)
  }
  return ys
})

const yLabels = computed(() => ['+1.0', '+0.5', '0.0', '-0.5', '-1.0'])

const zeroY = computed(() => {
  return padding.top + (height.value - padding.top - padding.bottom) * 0.5
})

const points = computed(() => {
  if (!props.trend.length) return []
  const chartW = width.value - padding.left - padding.right
  const chartH = height.value - padding.top - padding.bottom
  return props.trend.map((item, i) => {
    const score = item.avg_score ?? item.score ?? 0
    const x = padding.left + (i / Math.max(props.trend.length - 1, 1)) * chartW
    const y = padding.top + (1 - (score + 1) / 2) * chartH
    return { x, y, raw: score }
  })
})

const pointsStr = computed(() => points.value.map(p => `${p.x},${p.y}`).join(' '))

function dotColor(score) {
  if (score < -0.3) return '#e74c3c'
  if (score > 0.3) return '#27ae60'
  return '#f39c12'
}
</script>

<style scoped>
.chart-container {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}
.chart-container h2 {
  margin: 0 0 12px;
  font-size: 18px;
}
.chart {
  overflow-x: auto;
}
.empty {
  text-align: center;
  color: #999;
  padding: 24px;
}
</style>

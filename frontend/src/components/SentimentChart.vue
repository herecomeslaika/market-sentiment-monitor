<template>
  <div class="chart-container" ref="container">
    <svg :width="width" :height="height">
      <!-- Grid lines -->
      <line v-for="y in gridLines" :key="'g'+y" x1="40" :x2="width-10" :y1="y" :y2="y" stroke="#334155" stroke-dasharray="2" />
      <!-- Y axis labels -->
      <text v-for="(label, i) in yLabels" :key="'l'+i" x="35" :y="gridLines[i]+4" text-anchor="end" fill="#64748b" font-size="10">{{ label }}</text>
      <!-- Area -->
      <path v-if="points.length > 1" :d="areaPath" fill="url(#areaGrad)" opacity="0.3" />
      <!-- Line -->
      <path v-if="points.length > 1" :d="linePath" fill="none" stroke="#3b82f6" stroke-width="2" />
      <!-- Dots -->
      <circle v-for="(p, i) in points" :key="i" :cx="p.x" :cy="p.y" r="3" fill="#3b82f6" />
      <!-- X axis labels -->
      <text v-for="(p, i) in xLabels" :key="'x'+i" :x="p.x" :y="height-2" text-anchor="middle" fill="#64748b" font-size="9">{{ p.label }}</text>
      <!-- Gradient -->
      <defs>
        <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#3b82f6" stop-opacity="0.5" />
          <stop offset="100%" stop-color="#3b82f6" stop-opacity="0" />
        </linearGradient>
      </defs>
    </svg>
    <p v-if="!data.length" class="empty">暂无趋势数据</p>
  </div>
</template>

<script setup>
import { computed, ref, onMounted, onUnmounted } from 'vue'

const props = defineProps({ data: { type: Array, default: () => [] } })
const width = ref(600)
const height = ref(200)
const container = ref(null)

const margin = { top: 10, right: 10, bottom: 25, left: 40 }
const plotW = computed(() => width.value - margin.left - margin.right)
const plotH = computed(() => height.value - margin.top - margin.bottom)

const points = computed(() => {
  if (!props.data.length) return []
  return props.data.map((d, i) => ({
    x: margin.left + (i / Math.max(props.data.length - 1, 1)) * plotW.value,
    y: margin.top + (1 - (d.avg_score + 1) / 2) * plotH.value,
    ...d,
  }))
})

const linePath = computed(() => {
  if (points.value.length < 2) return ''
  return points.value.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ')
})

const areaPath = computed(() => {
  if (points.value.length < 2) return ''
  const base = margin.top + plotH.value
  return linePath.value + ` L ${points.value[points.value.length - 1].x} ${base} L ${points.value[0].x} ${base} Z`
})

const gridLines = computed(() => {
  const step = plotH.value / 4
  return [0, 1, 2, 3, 4].map(i => margin.top + i * step)
})

const yLabels = computed(() => ['+1.0', '+0.5', '0.0', '-0.5', '-1.0'])

const xLabels = computed(() => {
  if (!points.value.length) return []
  const step = Math.max(1, Math.floor(points.value.length / 6))
  return points.value.filter((_, i) => i % step === 0).map(p => ({
    x: p.x,
    label: (p.time_bucket || '').slice(5, 16),
  }))
})

let resizeObserver = null
onMounted(() => {
  if (container.value) {
    width.value = container.value.clientWidth
    resizeObserver = new ResizeObserver(entries => {
      width.value = entries[0].contentRect.width
    })
    resizeObserver.observe(container.value)
  }
})
onUnmounted(() => { if (resizeObserver) resizeObserver.disconnect() })
</script>

<style scoped>
.chart-container { width: 100%; }
.empty { color: #64748b; font-size: 13px; text-align: center; padding: 40px 0; }
</style>

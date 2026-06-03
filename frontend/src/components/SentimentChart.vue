<template>
  <div class="chart-container">
    <h2>情绪趋势</h2>
    <div class="chart" ref="chartRef">
      <svg :viewBox="`0 0 ${svgW} ${svgH}`" :width="svgW" :height="svgH" preserveAspectRatio="xMidYMid meet">
        <!-- Grid lines -->
        <line v-for="y in gridY" :key="'g-'+y" x1="50" :y1="y" :x2="svgW-10" :y2="y" stroke="#f0f0f0" />
        <!-- Y-axis labels -->
        <text v-for="(label, i) in yLabels" :key="'yl-'+i" x="5" :y="gridY[i]+4" font-size="10" fill="#999">{{ label }}</text>
        <!-- Zero line -->
        <line :x1="50" :y1="zeroY" :x2="svgW-10" :y2="zeroY" stroke="#ccc" stroke-dasharray="4" />

        <!-- Volatility band (min-max range) -->
        <polygon v-if="bandPoints.length" :points="bandPoints" fill="rgba(52,152,219,0.08)" stroke="none" />

        <!-- Area fill under MA line -->
        <polygon v-if="areaPoints.length" :points="areaPoints" :fill="areaColor" stroke="none" />

        <!-- Raw avg line (thin, faded) -->
        <polyline v-if="rawPoints.length > 1" :points="rawPointsStr" fill="none" stroke="#bdc3c7" stroke-width="1" opacity="0.5" />

        <!-- MA line (main) -->
        <polyline v-if="maPoints.length > 1" :points="maPointsStr" fill="none" :stroke="maColor" stroke-width="2.5" stroke-linejoin="round" />

        <!-- Sentiment distribution bars -->
        <g v-for="(d, i) in distBars" :key="'db-'+i">
          <rect :x="d.x - 6" :y="d.posY" :width="4" :height="d.posH" fill="#27ae60" opacity="0.5" rx="1" />
          <rect :x="d.x - 1" :y="d.neutralY" :width="4" :height="d.neutralH" fill="#f39c12" opacity="0.5" rx="1" />
          <rect :x="d.x + 4" :y="d.negY" :width="4" :height="d.negH" fill="#e74c3c" opacity="0.5" rx="1" />
        </g>

        <!-- Momentum shift markers -->
        <g v-for="(m, i) in momentumMarkers" :key="'ms-'+i">
          <polygon :points="m.triangle" fill="#e74c3c" />
          <text :x="m.x" :y="m.textY" font-size="9" fill="#e74c3c" text-anchor="middle" font-weight="600">{{ m.label }}</text>
        </g>

        <!-- Data dots on MA line -->
        <circle v-for="(p, i) in maPoints" :key="'d-'+i" :cx="p.x" :cy="p.y" r="2.5" :fill="dotColor(p.raw)" />

        <!-- X-axis time labels (rotated -45deg) -->
        <g v-for="(label, i) in xLabels" :key="'xl-'+i">
          <text
            :x="label.x"
            :y="svgH - 4"
            font-size="10"
            fill="#888"
            text-anchor="end"
            :transform="`rotate(-40, ${label.x}, ${svgH - 4})`"
          >{{ label.text }}</text>
        </g>
      </svg>

      <!-- Legend -->
      <div class="legend">
        <span class="legend-item"><span class="legend-line" style="background:#3498db"></span>MA趋势线</span>
        <span class="legend-item"><span class="legend-line" style="background:#bdc3c7"></span>原始均值</span>
        <span class="legend-item"><span class="legend-area" style="background:rgba(52,152,219,0.15)"></span>波动区间</span>
        <span class="legend-item"><span class="legend-dot" style="background:#27ae60"></span>积极</span>
        <span class="legend-item"><span class="legend-dot" style="background:#f39c12"></span>中性</span>
        <span class="legend-item"><span class="legend-dot" style="background:#e74c3c"></span>消极</span>
        <span class="legend-item"><span class="legend-triangle"></span>动量拐点</span>
      </div>
    </div>
    <div v-if="!trend.length" class="empty">暂无趋势数据</div>
  </div>
</template>

<script setup>
import { computed, ref, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  trend: { type: Array, default: () => [] },
  momentumShifts: { type: Array, default: () => [] }
})

const chartRef = ref(null)
const svgW = ref(640)
const svgH = ref(300)

const pad = { top: 24, right: 15, bottom: 50, left: 50 }

function resize() {
  if (chartRef.value) {
    svgW.value = Math.max(chartRef.value.clientWidth, 400)
  }
}

onMounted(() => { resize(); window.addEventListener('resize', resize) })
onUnmounted(() => window.removeEventListener('resize', resize))

const chartW = computed(() => svgW.value - pad.left - pad.right)
const chartH = computed(() => svgH.value - pad.top - pad.bottom)

const gridY = computed(() => {
  const ys = []
  for (let i = 0; i <= 4; i++) ys.push(pad.top + (i * chartH.value) / 4)
  return ys
})

const yLabels = ['+1.0', '+0.5', '0.0', '-0.5', '-1.0']
const zeroY = computed(() => pad.top + chartH.value * 0.5)

function scoreToY(score) { return pad.top + (1 - (score + 1) / 2) * chartH.value }
function idxToX(i) { return pad.left + (i / Math.max(props.trend.length - 1, 1)) * chartW.value }

// X-axis labels: auto spacing, rotated to avoid overlap
const xLabels = computed(() => {
  if (!props.trend.length) return []
  // Leave ~55px per label (rotated -40deg needs less horizontal space)
  const maxLabels = Math.max(2, Math.floor(chartW.value / 55))
  const step = Math.max(1, Math.ceil(props.trend.length / maxLabels))
  const labels = []
  for (let i = 0; i < props.trend.length; i++) {
    if (i % step !== 0 && i !== props.trend.length - 1) continue
    const bucket = props.trend[i].time_bucket || ''
    const parts = bucket.split(' ')
    let text = ''
    if (parts.length === 2) {
      const datePart = parts[0].slice(5)  // MM-DD
      const timePart = parts[1]            // HH:00
      // Show date on first or when day changes
      if (labels.length === 0) {
        text = datePart + ' ' + timePart
      } else {
        const prevDate = (labels[labels.length - 1]?.raw || '').split(' ')[0]
        text = (parts[0] !== prevDate) ? datePart + ' ' + timePart : timePart
      }
    } else {
      text = bucket.slice(5)  // fallback
    }
    labels.push({ x: idxToX(i), text, raw: bucket })
  }
  return labels
})

// MA line points
const maPoints = computed(() =>
  props.trend.map((item, i) => ({
    x: idxToX(i),
    y: scoreToY(item.ma_score ?? item.avg_score ?? 0),
    raw: item.ma_score ?? item.avg_score ?? 0
  }))
)
const maPointsStr = computed(() => maPoints.value.map(p => `${p.x},${p.y}`).join(' '))

// Raw avg score points
const rawPoints = computed(() =>
  props.trend.map((item, i) => ({
    x: idxToX(i),
    y: scoreToY(item.avg_score ?? 0),
    raw: item.avg_score ?? 0
  }))
)
const rawPointsStr = computed(() => rawPoints.value.map(p => `${p.x},${p.y}`).join(' '))

// MA color based on latest trend direction
const maColor = computed(() => {
  if (!props.trend.length) return '#3498db'
  const score = props.trend[props.trend.length - 1].ma_score ?? props.trend[props.trend.length - 1].avg_score ?? 0
  return score > 0.1 ? '#27ae60' : score < -0.1 ? '#e74c3c' : '#3498db'
})

// Area fill under MA line
const areaPoints = computed(() => {
  if (maPoints.value.length < 2) return ''
  const pts = maPoints.value.map(p => `${p.x},${p.y}`)
  pts.push(`${maPoints.value[maPoints.value.length - 1].x},${zeroY.value}`)
  pts.push(`${maPoints.value[0].x},${zeroY.value}`)
  return pts.join(' ')
})

const areaColor = computed(() => {
  if (!props.trend.length) return 'rgba(52,152,219,0.1)'
  const score = props.trend[props.trend.length - 1].ma_score ?? props.trend[props.trend.length - 1].avg_score ?? 0
  return score > 0.1 ? 'rgba(39,174,96,0.12)' : score < -0.1 ? 'rgba(231,76,60,0.12)' : 'rgba(52,152,219,0.1)'
})

// Volatility band
const bandPoints = computed(() => {
  if (props.trend.length < 2) return ''
  const top = props.trend.map((item, i) => `${idxToX(i)},${scoreToY(item.max_score ?? item.avg_score ?? 0)}`)
  const bottom = [...props.trend].reverse().map((item, ri) => {
    const i = props.trend.length - 1 - ri
    return `${idxToX(i)},${scoreToY(item.min_score ?? item.avg_score ?? 0)}`
  })
  return [...top, ...bottom].join(' ')
})

// Distribution bars
const distBars = computed(() => {
  const barMaxH = 16
  return props.trend.map((item, i) => {
    const total = Math.max(item.news_count || item.count || 1, 1)
    const pos = (item.pos_count || 0) / total
    const neg = (item.neg_count || 0) / total
    const neutral = (item.neutral_count || 0) / total
    const baseY = pad.top + chartH.value + 4
    return {
      x: idxToX(i),
      negY: baseY,
      negH: neg * barMaxH,
      neutralY: baseY + neg * barMaxH,
      neutralH: neutral * barMaxH,
      posY: baseY + (neg + neutral) * barMaxH,
      posH: pos * barMaxH,
    }
  })
})

// Momentum shift markers — group by trend bucket, avoid overlapping
const momentumMarkers = computed(() => {
  if (!props.momentumShifts.length || !props.trend.length) return []
  // Map each shift to a trend bucket index
  const bucketGroups = new Map() // bucketIdx -> list of shifts
  for (const m of props.momentumShifts) {
    const mTime = m.processed_at || ''
    let bestIdx = -1
    for (let i = 0; i < props.trend.length; i++) {
      if (mTime.startsWith((props.trend[i].time_bucket || '').slice(0, 13))) {
        bestIdx = i
        break
      }
    }
    if (bestIdx < 0) continue
    if (!bucketGroups.has(bestIdx)) bucketGroups.set(bestIdx, [])
    bucketGroups.get(bestIdx).push(m)
  }
  // Build one marker per group
  const markers = []
  for (const [idx, group] of bucketGroups) {
    const x = idxToX(idx)
    const y = pad.top + 2
    const size = 5
    const count = group.length
    // Show top entity name if 1-2, otherwise show count
    const label = count === 1
      ? (group[0].entity_name || group[0].dominant || '').slice(0, 8)
      : count <= 2
        ? (group[0].entity_name || group[0].dominant || '').slice(0, 6) + '...'
        : `${count}个拐点`
    markers.push({
      x,
      triangle: `${x},${y + size} ${x - size},${y - size} ${x + size},${y - size}`,
      textY: y - size - 3,
      label,
    })
  }
  return markers
})

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
.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 8px;
  padding-left: 50px;
}
.legend-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: #666;
}
.legend-line {
  display: inline-block;
  width: 16px;
  height: 2px;
  border-radius: 1px;
}
.legend-area {
  display: inline-block;
  width: 16px;
  height: 8px;
  border-radius: 2px;
}
.legend-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.legend-triangle {
  display: inline-block;
  width: 0;
  height: 0;
  border-left: 5px solid transparent;
  border-right: 5px solid transparent;
  border-bottom: 8px solid #e74c3c;
}
.empty {
  text-align: center;
  color: #999;
  padding: 24px;
}
</style>

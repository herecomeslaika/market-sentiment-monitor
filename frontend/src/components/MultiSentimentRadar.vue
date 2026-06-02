<template>
  <div class="multi-sentiment-radar">
    <h3>多维情绪分析</h3>
    <div v-if="loading" class="loading">加载中...</div>
    <div v-else-if="data.length === 0" class="empty">暂无情绪数据</div>
    <template v-else>
      <div class="radar-chart">
        <svg viewBox="0 0 200 200" class="radar-svg">
          <!-- Grid -->
          <polygon v-for="i in 4" :key="'grid-'+i"
            :points="radarGrid(i * 0.25)"
            fill="none" stroke="#e0e0e0" stroke-width="0.5"
          />
          <!-- Axis lines -->
          <line v-for="(_, i) in dims" :key="'axis-'+i"
            x1="100" y1="100" :x2="axisEnd(i).x" :y2="axisEnd(i).y"
            stroke="#ccc" stroke-width="0.5"
          />
          <!-- Data polygon -->
          <polygon v-if="currentData"
            :points="dataPolygon(currentData)"
            fill="rgba(52,152,219,0.25)" stroke="#3498db" stroke-width="1.5"
          />
          <!-- Data points -->
          <circle v-for="(dim, i) in dims" :key="'pt-'+i"
            :cx="dataPoint(currentData, i).x" :cy="dataPoint(currentData, i).y"
            r="3" fill="#3498db"
          />
          <!-- Labels -->
          <text v-for="(dim, i) in dims" :key="'label-'+i"
            :x="labelPos(i).x" :y="labelPos(i).y"
            text-anchor="middle" font-size="10" fill="#555"
          >{{ dim }}</text>
        </svg>
      </div>
      <div class="sentiment-list">
        <div v-for="item in data.slice(0, 8)" :key="item.id" class="sentiment-row">
          <span class="item-title">{{ item.title?.slice(0, 30) }}</span>
          <div class="dim-bars">
            <span v-for="dim in dims" :key="dim" class="dim-bar" :class="dim">
              <span class="bar-fill" :style="{ width: (item[dim] * 100) + '%' }"></span>
              <span class="bar-label">{{ item[dim]?.toFixed(1) }}</span>
            </span>
          </div>
          <span class="dominant-badge" :class="item.dominant">{{ item.dominant }}</span>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'

const props = defineProps({ apiBase: { type: String, default: '/api' } })
const dims = ['fear', 'greed', 'optimism', 'uncertainty']
const dimLabels = { fear: '恐惧', greed: '贪婪', optimism: '乐观', uncertainty: '不确定性' }

const data = ref([])
const loading = ref(true)
const currentData = computed(() => data.value[0] || null)

const center = 100
const radius = 70
const angles = dims.map((_, i) => (Math.PI * 2 * i) / dims.length - Math.PI / 2)

function radarGrid(level) {
  return dims.map((_, i) => {
    const a = angles[i]
    return `${center + radius * level * Math.cos(a)},${center + radius * level * Math.sin(a)}`
  }).join(' ')
}

function axisEnd(i) {
  return { x: center + radius * Math.cos(angles[i]), y: center + radius * Math.sin(angles[i]) }
}

function dataPoint(item, i) {
  if (!item) return { x: center, y: center }
  const val = item[dims[i]] || 0
  return {
    x: center + radius * val * Math.cos(angles[i]),
    y: center + radius * val * Math.sin(angles[i]),
  }
}

function dataPolygon(item) {
  return dims.map((_, i) => {
    const p = dataPoint(item, i)
    return `${p.x},${p.y}`
  }).join(' ')
}

function labelPos(i) {
  const r = radius + 18
  return { x: center + r * Math.cos(angles[i]), y: center + r * Math.sin(angles[i]) + 3 }
}

async function fetchData() {
  try {
    const resp = await fetch(`${props.apiBase}/sentiment/multi?hours=24&limit=10`)
    if (resp.ok) data.value = await resp.json()
  } catch (e) {
    console.error('Failed to fetch multi-sentiment:', e)
  } finally {
    loading.value = false
  }
}

onMounted(fetchData)
</script>

<style scoped>
.radar-chart { display: flex; justify-content: center; padding: 8px; }
.radar-svg { width: 200px; height: 200px; }
.sentiment-list { display: flex; flex-direction: column; gap: 6px; margin-top: 8px; }
.sentiment-row { display: flex; align-items: center; gap: 8px; padding: 4px 0; border-bottom: 1px solid #f0f0f0; }
.item-title { font-size: 12px; width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dim-bars { flex: 1; display: flex; flex-direction: column; gap: 1px; }
.dim-bar { display: flex; align-items: center; gap: 4px; font-size: 10px; }
.dim-bar .bar-fill { height: 4px; border-radius: 2px; transition: width 0.3s; }
.dim-bar.fear .bar-fill { background: #e74c3c; }
.dim-bar.greed .bar-fill { background: #f39c12; }
.dim-bar.optimism .bar-fill { background: #27ae60; }
.dim-bar.uncertainty .bar-fill { background: #8e44ad; }
.dim-bar .bar-label { width: 24px; text-align: right; color: #666; }
.dominant-badge { font-size: 10px; padding: 1px 6px; border-radius: 8px; font-weight: 600; }
.dominant-badge.fear { background: #fde8e8; color: #e74c3c; }
.dominant-badge.greed { background: #fef9e7; color: #f39c12; }
.dominant-badge.optimism { background: #e8f8ef; color: #27ae60; }
.dominant-badge.uncertainty { background: #f3e5f5; color: #8e44ad; }
.dominant-badge.neutral { background: #f5f5f5; color: #999; }
.loading, .empty { color: #999; text-align: center; padding: 20px; }
</style>
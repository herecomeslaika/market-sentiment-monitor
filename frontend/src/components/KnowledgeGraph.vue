<template>
  <div class="knowledge-graph">
    <h3>知识图谱</h3>
    <div v-if="loading" class="loading">加载中...</div>
    <div v-else-if="relations.length === 0" class="empty">暂无关系数据</div>
    <template v-else>
      <div class="graph-canvas">
        <svg :width="width" :height="height" class="graph-svg">
          <!-- Edges -->
          <line
            v-for="(edge, i) in edges" :key="'e-'+i"
            :x1="nodePos(edge.source).x" :y1="nodePos(edge.source).y"
            :x2="nodePos(edge.target).x" :y2="nodePos(edge.target).y"
            :class="'edge-' + edge.relation"
            stroke-width="1.5"
          />
          <!-- Edge labels -->
          <text
            v-for="(edge, i) in edges" :key="'el-'+i"
            :x="(nodePos(edge.source).x + nodePos(edge.target).x) / 2"
            :y="(nodePos(edge.source).y + nodePos(edge.target).y) / 2 - 4"
            text-anchor="middle" font-size="9" fill="#888"
          >{{ edgeLabel(edge.relation) }}</text>
          <!-- Nodes -->
          <g v-for="node in nodes" :key="node.name" class="graph-node" @click="$emit('select', node)">
            <circle :cx="node.x" :cy="node.y" r="16" :class="'node-' + (node.type || 'unknown')" />
            <text :x="node.x" :y="node.y + 4" text-anchor="middle" font-size="9" fill="white" font-weight="600">
              {{ node.name.slice(0, 4) }}
            </text>
            <text :x="node.x" :y="node.y + 28" text-anchor="middle" font-size="8" fill="#555">
              {{ node.name }}
            </text>
          </g>
        </svg>
      </div>
      <div class="relation-legend">
        <span class="legend-item"><span class="legend-line edge-affects"></span> 影响</span>
        <span class="legend-item"><span class="legend-line edge-belongs_to"></span> 属于</span>
        <span class="legend-item"><span class="legend-line edge-causes"></span> 导致</span>
        <span class="legend-item"><span class="legend-line edge-correlates"></span> 关联</span>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'

const props = defineProps({ apiBase: { type: String, default: '' } })
const emit = defineEmits(['select'])

const relations = ref([])
const loading = ref(true)
const width = 400
const height = 300

const nodes = computed(() => {
  const map = new Map()
  relations.value.forEach(r => {
    if (!map.has(r.source_entity)) map.set(r.source_entity, { name: r.source_entity, type: 'unknown', x: 0, y: 0 })
    if (!map.has(r.target_entity)) map.set(r.target_entity, { name: r.target_entity, type: 'unknown', x: 0, y: 0 })
  })
  const list = Array.from(map.values())
  // Simple circular layout
  const cx = width / 2, cy = height / 2, r = Math.min(cx, cy) - 40
  list.forEach((n, i) => {
    const angle = (2 * Math.PI * i) / list.length - Math.PI / 2
    n.x = cx + r * Math.cos(angle)
    n.y = cy + r * Math.sin(angle)
  })
  return list
})

const edges = computed(() => {
  return relations.value.slice(0, 20).map(r => ({
    source: r.source_entity,
    target: r.target_entity,
    relation: r.relation,
    confidence: r.confidence,
  }))
})

function nodePos(name) {
  const n = nodes.value.find(n => n.name === name)
  return n ? { x: n.x, y: n.y } : { x: width / 2, y: height / 2 }
}

function edgeLabel(relation) {
  const map = { affects: '影响', belongs_to: '属于', causes: '导致', correlates: '关联' }
  return map[relation] || relation
}

async function fetchRelations() {
  try {
    const resp = await fetch(`${props.apiBase}/knowledge/relations?limit=20`)
    if (resp.ok) relations.value = await resp.json()
  } catch (e) {
    console.error('Failed to fetch relations:', e)
  } finally {
    loading.value = false
  }
}

onMounted(fetchRelations)
</script>

<style scoped>
.graph-canvas { display: flex; justify-content: center; }
.graph-svg { background: #fafafa; border-radius: 8px; }
.graph-node { cursor: pointer; }
.graph-node:hover circle { filter: brightness(1.15); }
.node-company { fill: #1565c0; }
.node-industry { fill: #7b1fa2; }
.node-policy { fill: #e65100; }
.node-indicator { fill: #2e7d32; }
.node-person { fill: #c62828; }
.node-unknown { fill: #607d8b; }
.edge-affects { stroke: #3498db; }
.edge-belongs_to { stroke: #9b59b6; }
.edge-causes { stroke: #e74c3c; }
.edge-correlates { stroke: #f39c12; }
.relation-legend { display: flex; gap: 12px; justify-content: center; margin-top: 8px; }
.legend-item { font-size: 11px; color: #666; display: flex; align-items: center; gap: 4px; }
.legend-line { display: inline-block; width: 16px; height: 2px; }
.loading, .empty { color: #999; text-align: center; padding: 20px; }
</style>
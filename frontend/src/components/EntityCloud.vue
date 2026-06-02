<template>
  <div class="entity-cloud">
    <h3>热门实体</h3>
    <div v-if="loading" class="loading">加载中...</div>
    <div v-else-if="entities.length === 0" class="empty">暂无实体数据</div>
    <div v-else class="cloud-container">
      <span
        v-for="entity in entities"
        :key="entity.name"
        class="entity-tag"
        :class="entity.type"
        :style="{ fontSize: tagSize(entity.news_count) + 'px' }"
        @click="$emit('select', entity)"
      >
        {{ entity.name }}
        <small class="count">{{ entity.news_count }}</small>
      </span>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const props = defineProps({ apiBase: { type: String, default: '' } })
const emit = defineEmits(['select'])

const entities = ref([])
const loading = ref(true)

function tagSize(count) {
  return Math.min(14 + count * 2, 28)
}

async function fetchEntities() {
  try {
    const resp = await fetch(`${props.apiBase}/entities?limit=30`)
    if (resp.ok) entities.value = await resp.json()
  } catch (e) {
    console.error('Failed to fetch entities:', e)
  } finally {
    loading.value = false
  }
}

onMounted(fetchEntities)
</script>

<style scoped>
.entity-cloud { padding: 12px; }
.cloud-container { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.entity-tag {
  display: inline-block; padding: 4px 10px; border-radius: 14px;
  cursor: pointer; transition: all 0.2s; user-select: none;
}
.entity-tag:hover { transform: scale(1.1); filter: brightness(1.1); }
.entity-tag.company { background: #e3f2fd; color: #1565c0; }
.entity-tag.industry { background: #f3e5f5; color: #7b1fa2; }
.entity-tag.policy { background: #fff3e0; color: #e65100; }
.entity-tag.indicator { background: #e8f5e9; color: #2e7d32; }
.entity-tag.person { background: #fce4ec; color: #c62828; }
.count { opacity: 0.5; margin-left: 2px; font-size: 0.7em; }
.loading, .empty { color: #999; text-align: center; padding: 20px; }
</style>

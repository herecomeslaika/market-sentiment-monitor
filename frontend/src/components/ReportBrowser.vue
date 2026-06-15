<template>
  <div class="report-browser">
    <h2>历史报告</h2>

    <!-- Intent input -->
    <div class="intent-bar">
      <input
        v-model="intentText"
        placeholder="输入研究意图，如：降息对银行股的影响"
        @keyup.enter="generateReport"
        :disabled="generating"
      />
      <button class="btn-generate" @click="generateReport" :disabled="generating || !intentText.trim()">
        {{ generating ? '生成中...' : '生成研报' }}
      </button>
    </div>
    <div v-if="generateError" class="generate-error">{{ generateError }}</div>

    <div class="toolbar">
      <select v-model="levelFilter" @change="fetchReports">
        <option value="">全部级别</option>
        <option value="critical">Critical</option>
        <option value="warning">Warning</option>
        <option value="info">Info</option>
      </select>
      <button class="btn-refresh" @click="fetchReports">刷新</button>
    </div>

    <!-- Report list -->
    <div v-if="!selectedReport" class="report-list">
      <div v-for="r in reports" :key="r.id" class="report-card" :class="levelClass(r.alert_level)" @click="openReport(r)">
        <div class="report-header">
          <span class="level-badge" :class="levelClass(r.alert_level)">{{ r.alert_level }}</span>
          <span class="report-time">{{ r.created_at }}</span>
        </div>
        <div class="report-title">{{ r.news_title }}</div>
        <div class="report-meta">
          <span class="report-source">{{ r.news_source }}</span>
          <span v-if="r.sentiment_score != null" class="score-badge" :class="scoreClass(r.sentiment_score)">
            {{ r.sentiment_label }} {{ r.sentiment_score.toFixed(2) }}
          </span>
        </div>
        <div v-if="r.triggered_keywords && r.triggered_keywords.length" class="report-keywords">
          <span v-for="kw in r.triggered_keywords.slice(0, 3)" :key="kw" class="kw-tag">{{ kw }}</span>
        </div>
      </div>
      <div v-if="!reports.length" class="empty">暂无报告</div>
      <div v-if="reports.length" class="pagination">
        <button :disabled="offset === 0" @click="prevPage">上一页</button>
        <span>第 {{ offset / limit + 1 }} 页</span>
        <button :disabled="reports.length < limit" @click="nextPage">下一页</button>
      </div>
    </div>

    <!-- Report detail -->
    <div v-else class="report-detail">
      <button class="btn-back" @click="selectedReport = null">&larr; 返回列表</button>
      <div class="detail-header">
        <span class="level-badge" :class="levelClass(selectedReport.alert_level)">{{ selectedReport.alert_level }}</span>
        <span class="detail-time">{{ selectedReport.created_at }}</span>
      </div>
      <h3 class="detail-title">{{ selectedReport.news_title }}</h3>
      <div class="detail-meta">
        <span>来源: {{ selectedReport.news_source }}</span>
        <span>情绪: <strong :class="scoreClass(selectedReport.sentiment_score)">{{ selectedReport.sentiment_label }} {{ selectedReport.sentiment_score?.toFixed(2) }}</strong></span>
        <span>置信度: {{ selectedReport.sentiment_confidence?.toFixed(2) }}</span>
      </div>
      <div v-if="selectedReport.news_url" class="detail-link">
        <a :href="selectedReport.news_url" target="_blank">查看原文</a>
      </div>
      <div v-if="selectedReport.triggered_keywords?.length" class="detail-keywords">
        触发关键词:
        <span v-for="kw in selectedReport.triggered_keywords" :key="kw" class="kw-tag">{{ kw }}</span>
      </div>
      <div v-if="selectedReport.news_snippet" class="detail-snippet">
        <h4>新闻摘要</h4>
        <p>{{ selectedReport.news_snippet }}</p>
      </div>
      <div v-if="selectedReport.deep_analysis" class="detail-analysis">
        <h4>深度研报</h4>
        <div class="analysis-text">{{ selectedReport.deep_analysis }}</div>
      </div>
      <div v-if="selectedReport.referenced_news?.length" class="detail-references">
        <h4>参考来源</h4>
        <ul class="ref-list">
          <li v-for="(ref, idx) in selectedReport.referenced_news" :key="idx">
            <span class="ref-source">[{{ ref.source }}]</span>
            <span class="ref-title">{{ ref.title }}</span>
            <a v-if="ref.url" :href="ref.url" target="_blank" class="ref-link">查看原文</a>
          </li>
        </ul>
      </div>

      <!-- Action buttons -->
      <div class="detail-actions">
        <button class="btn-action" @click="exportMarkdown" :disabled="loading">导出 Markdown</button>
        <button class="btn-action" @click="compareModels" :disabled="loading">对比分析</button>
      </div>

      <!-- Follow-up question -->
      <div class="followup-section">
        <h4>追问</h4>
        <div class="followup-input">
          <input v-model="followupQuestion" placeholder="输入追问问题..." @keyup.enter="askFollowup" :disabled="loading || !selectedReport.deep_analysis" />
          <button @click="askFollowup" :disabled="loading || !selectedReport.deep_analysis">提问</button>
        </div>
        <div v-if="followupAnswer" class="followup-answer">
          <p>{{ followupAnswer }}</p>
        </div>
      </div>

      <!-- Contrarian view -->
      <div v-if="contrarianView" class="contrarian-section">
        <h4>相反视角分析</h4>
        <div class="analysis-text">{{ contrarianView }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const reports = ref([])
const selectedReport = ref(null)
const levelFilter = ref('')
const offset = ref(0)
const limit = 10
const loading = ref(false)
const followupQuestion = ref('')
const followupAnswer = ref('')
const contrarianView = ref('')
const intentText = ref('')
const generating = ref(false)
const generateError = ref('')

async function fetchReports() {
  try {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset.value) })
    if (levelFilter.value) params.set('level', levelFilter.value)
    const res = await fetch(`/reports?${params}`)
    reports.value = await res.json()
  } catch (e) {
    console.error('Failed to fetch reports:', e)
  }
}

function openReport(r) {
  selectedReport.value = r
  followupAnswer.value = ''
  contrarianView.value = ''
  followupQuestion.value = ''
}

function prevPage() {
  offset.value = Math.max(0, offset.value - limit)
  fetchReports()
}

function nextPage() {
  offset.value += limit
  fetchReports()
}

function levelClass(level) {
  if (level === 'critical') return 'critical'
  if (level === 'info') return 'info'
  return 'warning'
}

function scoreClass(score) {
  if (score == null) return ''
  if (score < -0.3) return 'score-negative'
  if (score > 0.3) return 'score-positive'
  return 'score-neutral'
}

async function exportMarkdown() {
  if (!selectedReport.value) return
  loading.value = true
  try {
    const res = await fetch(`/reports/${selectedReport.value.id}/markdown`)
    if (res.ok) {
      const text = await res.text()
      const blob = new Blob([text], { type: 'text/markdown' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `report_${selectedReport.value.id}.md`
      a.click()
      URL.revokeObjectURL(url)
    }
  } catch (e) {
    console.error('Export failed:', e)
  } finally {
    loading.value = false
  }
}

async function compareModels() {
  if (!selectedReport.value) return
  loading.value = true
  contrarianView.value = ''
  try {
    const res = await fetch(`/reports/${selectedReport.value.id}/compare`, { method: 'POST' })
    if (res.ok) {
      const data = await res.json()
      contrarianView.value = data.contrarian_view
    }
  } catch (e) {
    console.error('Compare failed:', e)
  } finally {
    loading.value = false
  }
}

async function askFollowup() {
  if (!selectedReport.value || !followupQuestion.value.trim()) return
  loading.value = true
  followupAnswer.value = ''
  try {
    const res = await fetch(`/reports/${selectedReport.value.id}/followup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: followupQuestion.value }),
    })
    if (res.ok) {
      const data = await res.json()
      followupAnswer.value = data.answer
    }
  } catch (e) {
    console.error('Followup failed:', e)
  } finally {
    loading.value = false
  }
}

async function generateReport() {
  if (!intentText.value.trim()) return
  generating.value = true
  generateError.value = ''
  try {
    const res = await fetch('/reports/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ intent: intentText.value }),
    })
    const data = await res.json()
    if (data.error) {
      generateError.value = data.error
      return
    }
    // Refresh list and open the new report
    await fetchReports()
    selectedReport.value = {
      id: data.report_id,
      alert_level: data.alert_level,
      triggered_keywords: data.keywords,
      deep_analysis: data.deep_analysis,
      news_title: data.news_title,
      news_source: data.news_source,
      news_url: data.news_url,
      news_snippet: data.news_snippet,
      sentiment_score: data.sentiment_score ?? 0,
      sentiment_label: data.sentiment_label ?? 'neutral',
      sentiment_confidence: data.sentiment_confidence ?? 0,
      referenced_news: data.referenced_news || [],
      created_at: data.created_at,
    }
    intentText.value = ''
  } catch (e) {
    generateError.value = '生成失败: ' + e.message
  } finally {
    generating.value = false
  }
}

onMounted(fetchReports)

defineExpose({ openReport })
</script>

<style scoped>
.report-browser {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}
.report-browser h2 {
  margin: 0 0 12px;
  font-size: 18px;
}
.intent-bar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.intent-bar input {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 14px;
}
.intent-bar input:focus {
  outline: none;
  border-color: #3498db;
  box-shadow: 0 0 0 2px rgba(52,152,219,0.15);
}
.btn-generate {
  padding: 8px 20px;
  border: none;
  border-radius: 6px;
  background: #3498db;
  color: #fff;
  font-size: 14px;
  cursor: pointer;
  white-space: nowrap;
}
.btn-generate:hover { background: #2980b9; }
.btn-generate:disabled { opacity: 0.5; cursor: default; }
.generate-error {
  color: #e74c3c;
  font-size: 13px;
  margin-bottom: 8px;
}
.toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.toolbar select {
  padding: 4px 8px;
  border-radius: 4px;
  border: 1px solid #ddd;
  font-size: 13px;
}
.btn-refresh {
  padding: 4px 12px;
  border-radius: 4px;
  border: 1px solid #ddd;
  background: #f8f8f8;
  cursor: pointer;
  font-size: 13px;
}
.btn-refresh:hover { background: #eee; }
.report-card {
  padding: 10px 12px;
  border-left: 4px solid #f39c12;
  border-radius: 4px;
  background: #fffbf0;
  margin-bottom: 8px;
  cursor: pointer;
  transition: box-shadow 0.15s;
}
.report-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
.report-card.critical { border-left-color: #e74c3c; background: #fff5f5; }
.report-card.info { border-left-color: #3498db; background: #f0f8ff; }
.report-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 4px;
}
.level-badge {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  padding: 1px 8px;
  border-radius: 10px;
  background: #fef3cd;
  color: #856404;
}
.level-badge.critical { background: #f8d7da; color: #721c24; }
.level-badge.info { background: #d1ecf1; color: #0c5460; }
.report-time { font-size: 11px; color: #999; }
.report-title { font-size: 14px; font-weight: 500; color: #333; }
.report-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 4px;
}
.report-source { font-size: 12px; color: #888; }
.score-badge {
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 10px;
  font-weight: 600;
}
.score-badge.score-negative { background: #fde8e8; color: #e74c3c; }
.score-badge.score-positive { background: #e8f8ef; color: #27ae60; }
.score-badge.score-neutral { background: #fef9e7; color: #f39c12; }
.report-keywords { margin-top: 4px; }
.kw-tag {
  font-size: 11px;
  background: #e8f4fd;
  color: #2980b9;
  padding: 1px 6px;
  border-radius: 8px;
  margin-right: 4px;
}
.pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
}
.pagination button {
  padding: 4px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  background: #f8f8f8;
  cursor: pointer;
  font-size: 13px;
}
.pagination button:disabled { opacity: 0.5; cursor: default; }
.empty { text-align: center; color: #999; padding: 24px; }

/* Detail view */
.btn-back {
  background: none;
  border: none;
  color: #3498db;
  cursor: pointer;
  font-size: 14px;
  padding: 0;
  margin-bottom: 12px;
}
.btn-back:hover { text-decoration: underline; }
.detail-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
}
.detail-title { font-size: 18px; margin: 0 0 8px; }
.detail-meta {
  display: flex;
  gap: 16px;
  font-size: 13px;
  color: #666;
  margin-bottom: 8px;
}
.detail-link { margin-bottom: 8px; }
.detail-link a { color: #3498db; font-size: 13px; }
.detail-keywords { margin-bottom: 8px; font-size: 13px; color: #666; }
.detail-snippet {
  background: #f9f9f9;
  padding: 12px;
  border-radius: 6px;
  margin-bottom: 12px;
}
.detail-snippet h4 { margin: 0 0 6px; font-size: 14px; }
.detail-snippet p { margin: 0; font-size: 13px; color: #555; line-height: 1.5; }
.detail-analysis {
  background: #f5f8ff;
  padding: 12px;
  border-radius: 6px;
  margin-bottom: 12px;
}
.detail-analysis h4 { margin: 0 0 6px; font-size: 14px; }
.analysis-text {
  font-size: 13px;
  color: #444;
  white-space: pre-wrap;
  line-height: 1.6;
  max-height: 400px;
  overflow-y: auto;
}
.detail-actions {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}
.btn-action {
  padding: 6px 14px;
  border: 1px solid #ddd;
  border-radius: 4px;
  background: #f8f8f8;
  cursor: pointer;
  font-size: 13px;
}
.btn-action:hover { background: #eee; }
.btn-action:disabled { opacity: 0.5; cursor: default; }
.followup-section {
  border-top: 1px solid #eee;
  padding-top: 12px;
  margin-bottom: 12px;
}
.followup-section h4 { margin: 0 0 8px; font-size: 14px; }
.followup-input {
  display: flex;
  gap: 8px;
}
.followup-input input {
  flex: 1;
  padding: 6px 10px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 13px;
}
.followup-input button {
  padding: 6px 14px;
  border: 1px solid #3498db;
  border-radius: 4px;
  background: #3498db;
  color: #fff;
  cursor: pointer;
  font-size: 13px;
}
.followup-input button:disabled { opacity: 0.5; cursor: default; }
.followup-answer {
  margin-top: 8px;
  padding: 10px;
  background: #f9f9f9;
  border-radius: 4px;
  font-size: 13px;
  color: #444;
  white-space: pre-wrap;
  line-height: 1.5;
}
.contrarian-section {
  border-top: 1px solid #eee;
  padding-top: 12px;
}
.contrarian-section h4 { margin: 0 0 8px; font-size: 14px; color: #e74c3c; }
</style>

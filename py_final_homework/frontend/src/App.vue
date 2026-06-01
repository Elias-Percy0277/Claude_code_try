<template>
  <div id="app" class="datavis-app">
    <!-- 背景装饰线条 -->
    <div class="bg-decoration">
      <div class="bg-line bg-line-1"></div>
      <div class="bg-line bg-line-2"></div>
      <div class="bg-line bg-line-3"></div>
    </div>

    <!-- 三栏布局：会话侧边栏 | 主区域 -->
    <div class="app-layout">
      <!-- 左侧：会话列表侧边栏 -->
      <SessionSidebar
        ref="sessionSidebar"
        @newSession="handleNewSessionFromSidebar"
        @sessionSwitched="handleSessionSwitched"
      />

      <!-- 右侧：主区域 -->
      <div class="main-area">
        <!-- 头部 -->
        <header class="app-header">
          <div class="header-left">
            <button class="btn-hamburger" @click="sessionSidebar?.toggleMobile()">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="3" y1="6" x2="21" y2="6"/>
                <line x1="3" y1="12" x2="21" y2="12"/>
                <line x1="3" y1="18" x2="21" y2="18"/>
              </svg>
            </button>
            <div class="header-brand">
              <span class="brand-dot"></span>
              <h1 class="brand-title">
                <span class="title-stroke">DATA</span><span class="title-solid">VIS</span>
              </h1>
            </div>
          </div>
          <div class="header-info" v-if="store.hasValidSession">
            <span class="filename">{{ store.datasetCount > 1 ? `${store.datasetCount} 个数据集` : (store.datasets?.[0]?.dataset_name || store.filename) }}</span>
            <span class="info-sep">//</span>
            <span class="info">{{ store.totalRows }} 行</span>
          </div>
        </header>

        <!-- 主内容 -->
        <main class="app-main">
          <!-- 无会话：欢迎视图 -->
          <div v-if="!store.hasValidSession" class="welcome-view">
            <div class="welcome-content">
              <div class="welcome-icon">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                  <polyline points="14 2 14 8 20 8"/>
                  <line x1="12" y1="18" x2="12" y2="12"/>
                  <line x1="9" y1="15" x2="15" y2="15"/>
                </svg>
              </div>
              <h2 class="welcome-title">上传数据，开始分析</h2>
              <p class="welcome-desc">支持 CSV / Excel / JSON 等格式，最大 60MB</p>
              <FileUpload @uploaded="handleFileUploaded" />
            </div>
          </div>

          <!-- 有会话：聊天优先布局 -->
          <div v-else class="session-view">
            <!-- 顶栏：数据集信息 + 添加数据 -->
            <div class="session-topbar">
              <div class="datasets-chips">
                <span
                  v-for="(ds, index) in store.datasets"
                  :key="ds.dataset_id"
                  class="dataset-chip"
                  :class="{ primary: index === 0 }"
                >
                  {{ ds.dataset_name }}
                  <span class="chip-meta">{{ ds.row_count }}行</span>
                  <button
                    v-if="store.datasetCount > 1"
                    class="btn-remove-chip"
                    @click="handleDeleteDataset(ds.dataset_id)"
                    title="删除数据集"
                  >×</button>
                </span>
              </div>
              <div class="topbar-actions">
                <button
                  @click="showAddFile = true"
                  class="btn-add-file"
                  v-if="store.datasetCount < 10"
                >
                  + 添加数据
                </button>
              </div>
            </div>

            <!-- 中部：聊天 + 图表（可滚动） -->
            <div class="session-content">
              <!-- 分析摘要面板 -->
              <div v-if="store.analysisSummary && !store.summaryCollapsed" class="summary-panel">
                <div class="summary-header">
                  <span class="summary-title">{{ store.analysisSummary.title }}</span>
                  <button class="btn-collapse" @click="store.toggleSummaryCollapsed()">收起</button>
                </div>
                <div class="summary-body">
                  <div
                    v-for="(section, si) in store.analysisSummary.sections"
                    :key="si"
                    class="summary-section"
                  >
                    <div class="summary-section-name">{{ section.name }}</div>
                    <div class="summary-items">
                      <div
                        v-for="(item, ii) in section.items"
                        :key="ii"
                        class="summary-card"
                        :class="{ highlight: item.highlight }"
                      >
                        <span class="summary-card-label">{{ item.label }}</span>
                        <span class="summary-card-value">{{ item.value }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              <!-- 折叠时的提示条 -->
              <div v-else-if="store.analysisSummary && store.summaryCollapsed" class="summary-collapsed-bar" @click="store.toggleSummaryCollapsed()">
                <span>{{ store.analysisSummary.title }}</span>
                <span class="expand-hint">展开查看</span>
              </div>

              <ChatPanel @viewCharts="handleViewCharts" @pinCharts="handlePinCharts" @adoptSuggestion="handleAdoptSuggestion" />

              <!-- 固定图表提示栏 -->
              <div v-if="store.pinnedCharts.length > 0" class="pinned-bar">
                <span>{{ store.pinnedCharts.length }} 个固定图表用于对比</span>
                <button @click="store.clearPinnedCharts()" class="btn-clear-pinned">清除固定</button>
              </div>

              <!-- 历史图表查看提示栏 -->
              <div v-if="store.viewingHistoryCharts && store.charts.length > 0" class="history-viewing-bar">
                <span>正在查看历史图表</span>
                <button @click="handleBackToCurrent" class="btn-back-current">返回最新</button>
              </div>

              <!-- 图表展示 -->
              <ChartViewer v-if="store.charts.length > 0 || store.pinnedCharts.length > 0" :history-mode="store.viewingHistoryCharts" />

              <!-- 错误提示 -->
              <ErrorMessage
                v-if="store.error"
                :message="store.error"
                @close="store.clearError()"
              />
            </div>

            <!-- 底栏：输入 + 示例 -->
            <div class="session-bottombar">
              <div class="input-row">
                <textarea
                  v-model="store.queryInput"
                  @keydown.enter.exact.prevent="handleSendMessage"
                  placeholder="输入分析请求..."
                  rows="2"
                  :disabled="store.isLoading"
                ></textarea>
                <button
                  v-if="store.isLoading"
                  @click="handleStopAnalysis"
                  class="btn-stop"
                >
                  停止
                </button>
                <button
                  v-else
                  @click="handleSendMessage"
                  :disabled="!store.queryInput.trim()"
                  class="btn-send"
                >
                  发送
                </button>
              </div>
              <div v-if="!store.isLoading" class="examples-row">
                <button
                  v-for="(example, i) in exampleQueries"
                  :key="i"
                  @click="store.queryInput = example"
                  class="btn-example"
                >
                  {{ example }}
                </button>
              </div>
            </div>
          </div>

          <!-- 添加文件对话框（覆盖层） -->
          <div v-if="showAddFile" class="add-file-overlay" @click.self="showAddFile = false">
            <div class="add-file-dialog">
              <div class="add-file-header">
                <h3>添加数据集</h3>
                <button class="btn-close-dialog" @click="showAddFile = false">×</button>
              </div>
              <FileUpload @uploaded="handleFileAdded" />
            </div>
          </div>
        </main>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useAppStore } from '@/stores/app'
import SessionSidebar from '@/components/SessionSidebar.vue'
import FileUpload from '@/components/FileUpload.vue'
import ChatPanel from '@/components/ChatPanel.vue'
import ChartViewer from '@/components/ChartViewer.vue'
import ErrorMessage from '@/components/ErrorMessage.vue'
import { analyzeStream, executeSuggestion, deleteDataset, getAnalysisHistory, checkSession } from '@/api/client'

const store = useAppStore()
const showAddFile = ref(false)
const sessionSidebar = ref(null)
const abortController = ref(null)

const defaultQueries = [
  '分析数据概览',
  '显示销售额趋势',
  '销售额和利润的相关性',
  '各地区的销售额对比'
]

const exampleQueries = computed(() => {
  return store.suggestedQueries.length > 0 ? store.suggestedQueries : defaultQueries
})

// 组件挂载时恢复状态
onMounted(async () => {
  store.$hydrate()

  // 如果有会话，验证有效性并恢复历史
  if (store.hasValidSession) {
    try {
      const sessionInfo = await checkSession(store.sessionId)
      if (!sessionInfo.valid) {
        store.clearSession()
        sessionSidebar.value?.fetchSessions()
      } else if (store.messages.length === 0) {
        // 从后端恢复聊天历史
        const result = await getAnalysisHistory(store.sessionId)
        if (result.success && result.history && result.history.length > 0) {
          store.messages = result.history
          store.$persist()
        }
      }
    } catch (e) {
      // 会话已过期
      store.clearSession()
    }
  }

  window.dispatchEvent(new Event('app-ready'))
})

// 新建会话（从侧边栏触发）
function handleNewSessionFromSidebar() {
  store.clearSession()
  store.setCharts([])
}

// 切换会话
async function handleSessionSwitched(sessionId) {
  if (store.isLoading) {
    if (!confirm('分析正在进行中，确定要切换吗？')) return
  }

  store.setLoading(true)
  try {
    // 验证会话并获取详情
    const sessionInfo = await checkSession(sessionId)
    if (!sessionInfo.valid) {
      store.clearSession()
      store.setError('会话已过期或不存在')
      sessionSidebar.value?.fetchSessions()
      return
    }

    // 获取聊天历史
    let messages = []
    try {
      const historyResult = await getAnalysisHistory(sessionId)
      if (historyResult.success && historyResult.history) {
        messages = historyResult.history
      }
    } catch (e) {
      // 无历史记录，正常
    }

    // 原子替换状态
    store.loadSession(sessionId, {
      filename: sessionInfo.filename,
      datasets: sessionInfo.datasets || []
    }, messages)
  } catch (e) {
    store.setError('加载会话失败: ' + e.message)
  } finally {
    store.setLoading(false)
  }
}

// 处理文件上传（新建会话）
async function handleFileUploaded(result) {
  store.setSession(
    result.session_id,
    result.datasets?.[0]?.dataset_name || result.filename,
    result.total_rows,
    result.datasets?.[0]?.columns || [],
    result.datasets || []
  )
  store.addMessage({
    role: 'system',
    content: result.message || `成功上传 ${result.dataset_count} 个数据集，总计 ${result.total_rows} 行数据。`
  })
  // 刷新侧边栏会话列表
  sessionSidebar.value?.fetchSessions()
}

// 处理添加文件到现有会话
async function handleFileAdded(result) {
  store.addDatasets(result.datasets)
  store.addMessage({
    role: 'system',
    content: result.message || `成功添加 ${result.dataset_count} 个数据集到当前会话。`
  })
  showAddFile.value = false
  sessionSidebar.value?.fetchSessions()
}

// 删除数据集
async function handleDeleteDataset(datasetId) {
  if (!confirm('确定要删除这个数据集吗？')) return

  try {
    await deleteDataset(store.sessionId, datasetId)
    store.removeDataset(datasetId)
    store.addMessage({
      role: 'system',
      content: '数据集已删除'
    })
  } catch (error) {
    store.setError(error.message)
  }
}

// 处理发送消息
async function handleSendMessage() {
  const query = store.queryInput.trim()
  if (!query || store.isLoading) return

  // 添加用户消息
  store.addMessage({
    role: 'user',
    content: query
  })

  // 添加助手消息占位
  store.addMessage({
    role: 'assistant',
    content: '',
    charts: null
  })

  store.queryInput = ''
  store.setLoading(true)
  store.setError(null)
  store.setCharts([])
  store.viewingHistoryCharts = false
  store.viewingMessageIndex = -1

  // 创建 AbortController 用于停止分析
  abortController.value = new AbortController()

  try {
    await analyzeStream(
      store.sessionId,
      query,
      // onData
      (data) => {
        if (data.type === 'charts') {
          store.setCharts(data.data)
        } else if (data.type === 'text') {
          store.updateLastMessageContent(data.content)
        } else if (data.type === 'suggestions') {
          store.setSuggestions(data.data, null)
          // 更新最后一条消息以包含建议
          const lastMsg = store.messages[store.messages.length - 1]
          if (lastMsg && lastMsg.role === 'assistant') {
            lastMsg.suggestions = data.data
          }
        } else if (data.type === 'warning') {
          // 将警告附加到消息
          store.updateLastMessageContent(
            (store.messages[store.messages.length - 1]?.content || '') + `\n\n> ⚠️ ${data.message}`
          )
        }
      },
      // onError
      (error) => {
        store.setError(error)
      },
      // onDone
      (result) => {
        // 如果已经被停止，不要覆盖状态
        if (!store.isLoading) return
        store.setLoading(false)
        abortController.value = null
        // 更新最终消息，包含图表信息
        const lastMsg = store.messages[store.messages.length - 1]
        if (lastMsg && lastMsg.role === 'assistant') {
          lastMsg.content = result.content
          if (result.hasCharts) {
            lastMsg.charts = store.charts
          }
        }
        // 提取分析摘要
        const summary = extractSummary(result.content)
        if (summary) {
          store.setAnalysisSummary(summary)
        }
        // 更新动态建议（从 Agent2 的 suggestions 生成，或 fallback）
        if (store.suggestions.length > 0) {
          store.setSuggestedQueries(store.suggestions.map(s => s.title))
        } else {
          store.setSuggestedQueries(generateSuggestions(result.content, query))
        }
        store.$persist()
      },
      abortController.value.signal
    )
  } catch (error) {
    if (error.name === 'AbortError') {
      // 用户主动停止，状态已由 handleStopAnalysis 更新
    } else {
      store.setError(error.message)
      store.updateLastMessageContent(`分析失败：${error.message}`)
      store.setLoading(false)
    }
    abortController.value = null
  }
}

// 停止分析
function handleStopAnalysis() {
  if (abortController.value) {
    abortController.value.abort()
    abortController.value = null
  }
  // 立即更新 UI 状态，不依赖 stream 错误传播
  store.setLoading(false)
  const lastMsg = store.messages[store.messages.length - 1]
  if (lastMsg && lastMsg.role === 'assistant' && !lastMsg.content.includes('[已停止]')) {
    lastMsg.content = (lastMsg.content || '') + '\n\n*[已停止]*'
    store.$persist()
  }
}

// 查看历史图表
function handleViewCharts(messageIndex) {
  store.viewHistoricalCharts(messageIndex)
}

// 执行采纳的建议
async function handleAdoptSuggestion(suggestion) {
  if (store.isLoading) return

  store.addMessage({
    role: 'user',
    content: `[执行建议] ${suggestion.title}`
  })

  store.addMessage({
    role: 'assistant',
    content: '',
    charts: null
  })

  store.clearSuggestions()
  store.setLoading(true)
  store.setError(null)
  store.setCharts([])
  store.viewingHistoryCharts = false
  store.viewingMessageIndex = -1

  abortController.value = new AbortController()

  try {
    await executeSuggestion(
      store.sessionId,
      suggestion.operation,
      suggestion.parameters,
      (data) => {
        if (data.type === 'charts') {
          store.setCharts(data.data)
        } else if (data.type === 'text') {
          store.updateLastMessageContent(data.content)
        }
      },
      (error) => { store.setError(error) },
      (result) => {
        if (!store.isLoading) return
        store.setLoading(false)
        abortController.value = null
        const lastMsg = store.messages[store.messages.length - 1]
        if (lastMsg && lastMsg.role === 'assistant') {
          lastMsg.content = result.content
          if (result.hasCharts) {
            lastMsg.charts = store.charts
          }
        }
        store.$persist()
      },
      abortController.value.signal
    )
  } catch (error) {
    store.setError(error.message)
    store.setLoading(false)
    abortController.value = null
  }
}

// 固定历史图表用于对比
function handlePinCharts(messageIndex) {
  const message = store.messages[messageIndex]
  if (message && message.charts) {
    message.charts.forEach(chart => {
      store.pinChart(chart)
    })
  }
}

// 返回当前最新图表
function handleBackToCurrent() {
  store.viewCurrentCharts()
}

// ---- 分析摘要提取 ----
function extractSummary(content) {
  if (!content || typeof content !== 'string') return null

  const sections = []
  const lines = content.split('\n')
  let currentSection = null

  for (const line of lines) {
    // 匹配 ### 标题
    const headingMatch = line.match(/^###\s+(.+)/)
    if (headingMatch) {
      currentSection = { name: headingMatch[1].trim(), items: [] }
      sections.push(currentSection)
      continue
    }

    if (!currentSection) {
      // 如果还没遇到标题，创建默认 section
      currentSection = { name: '分析结果', items: [] }
      sections.push(currentSection)
    }

    // 匹配 **标签**: 值 或 **标签**：值 或 - **标签**: 值
    const itemMatch = line.match(/[-*]?\s*\*\*(.+?)\*\*[\s]*[:：]\s*(.+)/)
    if (itemMatch) {
      const label = itemMatch[1].trim()
      const value = itemMatch[2].trim()
      // 过滤过长的值
      if (value.length <= 80) {
        currentSection.items.push({ label, value, highlight: false })
      }
      continue
    }

    // 匹配数字开头的洞察条目（如 "1. **xxx**：..."）
    const insightMatch = line.match(/^\d+\.\s*\*\*(.+?)\*\*[\s]*[:：]?\s*(.*)/)
    if (insightMatch && insightMatch[2]) {
      currentSection.items.push({
        label: insightMatch[1].trim(),
        value: insightMatch[2].trim().substring(0, 60),
        highlight: true
      })
    }
  }

  // 过滤空 section
  const filteredSections = sections.filter(s => s.items.length > 0)
  if (filteredSections.length === 0) return null

  // 提取标题（取第一个 ## 标题）
  const titleMatch = content.match(/^##\s+(.+)/m)
  const title = titleMatch ? titleMatch[1].trim() : '分析摘要'

  return { title, sections: filteredSections }
}

// ---- 动态建议查询 ----
function generateSuggestions(content, query) {
  const suggestions = []
  const cols = store.datasets?.[0]?.columns || []
  const numCols = cols.length > 0 ? cols.slice(0, 3) : []

  // 基于分析内容推荐
  if (/概览|overview|总览/i.test(content) || /概览/i.test(query)) {
    suggestions.push(
      `分析${numCols[0] || '数据'}的趋势变化`,
      `各分类列的数值对比分析`,
      `查看${numCols[0] || '数据'}的分布情况`,
      `综合以上数据进行深度分析`
    )
  } else if (/趋势|trend|变化/i.test(content) || /趋势/i.test(query)) {
    suggestions.push(
      `计算${numCols[0] || '数据'}的移动平均`,
      `${numCols[0] || '数据'}与其他列的相关性分析`,
      `按分组对比${numCols[0] || '数据'}的趋势`,
      `综合以上数据进行深度分析`
    )
  } else if (/相关|correlation/i.test(content) || /相关/i.test(query)) {
    suggestions.push(
      `${numCols[1] || '数据'}的趋势分析`,
      `各分组的${numCols[0] || '数据'}对比`,
      `查看${numCols[0] || '数据'}的分布情况`,
      `综合以上数据进行深度分析`
    )
  } else if (/对比|comparison|分组/i.test(content) || /对比|分组/i.test(query)) {
    suggestions.push(
      `${numCols[0] || '数据'}的趋势变化`,
      `${numCols[0] || '数据'}的分布分析`,
      `数据中有哪些异常值`,
      `综合以上数据进行深度分析`
    )
  } else if (/分布|distribution/i.test(content) || /分布/i.test(query)) {
    suggestions.push(
      `${numCols[0] || '数据'}的趋势分析`,
      `各分组间的${numCols[0] || '数据'}对比`,
      `分析${numCols[1] || '数据'}与${numCols[0] || '数据'}的相关性`,
      `综合以上数据进行深度分析`
    )
  } else if (/综合|总结/i.test(query)) {
    suggestions.push(
      `数据中有哪些异常值`,
      `分析${numCols[0] || '数据'}的趋势`,
      `各分组的对比分析`,
      `查看数据分布情况`
    )
  }

  // 默认 fallback
  if (suggestions.length === 0) {
    suggestions.push(
      '分析数据概览',
      `分析${numCols[0] || '数据'}趋势`,
      '数据分布分析',
      '综合以上数据进行深度分析'
    )
  }

  return suggestions.slice(0, 4)
}
</script>

<style scoped>
/* ============ 背景装饰 ============ */
.bg-decoration {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: 0;
  overflow: hidden;
}

.bg-line {
  position: absolute;
  width: 120vw;
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--theme-green), transparent);
  opacity: 0.3;
}

.bg-line-1 {
  top: 15%;
  transform: rotate(-15deg);
  animation: move-line 12s linear infinite;
}

.bg-line-2 {
  top: 60%;
  transform: rotate(8deg);
  animation: move-line 15s linear infinite reverse;
}

.bg-line-3 {
  top: 85%;
  transform: rotate(-5deg);
  animation: move-line 10s linear infinite;
  animation-delay: -3s;
}

@keyframes move-line {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* ============ 根布局 ============ */
.datavis-app {
  min-height: 100vh;
  background: var(--theme-black);
  position: relative;
  z-index: 1;
}

.app-layout {
  display: flex;
  min-height: 100vh;
  position: relative;
  z-index: 1;
}

/* ============ 主区域 ============ */
.main-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}

/* ============ Header ============ */
.app-header {
  background: var(--theme-dark);
  border-bottom: 1px solid var(--theme-border);
  padding: 1rem 2rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
  position: relative;
  z-index: 10;
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.btn-hamburger {
  display: none;
  width: 36px;
  height: 36px;
  border: 1px solid var(--theme-border);
  background: transparent;
  color: var(--theme-white);
  border-radius: 4px;
  cursor: pointer;
  align-items: center;
  justify-content: center;
  transition: var(--theme-transition);
}

.btn-hamburger:hover {
  border-color: var(--theme-green);
  color: var(--theme-green);
}

.header-brand {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.brand-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--theme-green);
  box-shadow: 0 0 10px var(--theme-green);
  animation: pulse-dot 2s ease-in-out infinite;
}

@keyframes pulse-dot {
  0%, 100% { box-shadow: 0 0 10px var(--theme-green); }
  50% { box-shadow: 0 0 20px var(--theme-green), 0 0 40px rgba(23, 247, 0, 0.3); }
}

.brand-title {
  margin: 0;
  font-size: 1.5rem;
  font-weight: 700;
  letter-spacing: 0.15em;
  display: flex;
  gap: 0.15em;
}

.title-stroke {
  color: transparent;
  -webkit-text-stroke: 1.5px var(--theme-white);
}

.title-solid {
  color: var(--theme-green);
}

.header-info {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.filename {
  font-weight: 500;
  color: var(--theme-white);
  font-size: 0.9rem;
}

.info-sep {
  color: var(--theme-green);
  font-weight: 300;
}

.info {
  color: var(--theme-white-dim);
  font-size: 0.9rem;
}

/* ============ 主内容 ============ */
.app-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 1.25rem;
  max-width: 1200px;
  width: 100%;
  margin: 0 auto;
  position: relative;
  z-index: 1;
  overflow: hidden;
}

/* ============ 欢迎视图 ============ */
.welcome-view {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.welcome-content {
  max-width: 500px;
  width: 100%;
  text-align: center;
}

.welcome-icon {
  color: var(--theme-green);
  margin-bottom: 1rem;
  opacity: 0.6;
}

.welcome-title {
  font-size: 1.5rem;
  color: var(--theme-white);
  margin: 0 0 0.5rem;
  font-weight: 600;
}

.welcome-desc {
  color: var(--theme-white-dim);
  margin: 0 0 1.5rem;
  font-size: 0.9rem;
}

/* ============ 会话视图 ============ */
.session-view {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  min-height: 0;
}

/* 顶栏 */
.session-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.6rem 1rem;
  background: var(--theme-dark);
  border: 1px solid var(--theme-border);
  border-radius: var(--theme-radius-sm);
  flex-shrink: 0;
}

.datasets-chips {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
  align-items: center;
}

.dataset-chip {
  padding: 0.25rem 0.75rem;
  background: var(--theme-dark-2);
  border: 1px solid var(--theme-border);
  border-radius: 20px;
  font-size: 0.8rem;
  color: var(--theme-white-dim);
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
}

.dataset-chip.primary {
  border-color: rgba(23, 247, 0, 0.3);
  color: var(--theme-green);
  background: var(--theme-green-dim);
}

.chip-meta {
  font-size: 0.7rem;
  opacity: 0.7;
}

.btn-remove-chip {
  background: none;
  border: none;
  color: var(--theme-red);
  cursor: pointer;
  font-size: 1rem;
  padding: 0;
  line-height: 1;
  margin-left: 0.25rem;
  opacity: 0.6;
  transition: var(--theme-transition);
}

.btn-remove-chip:hover {
  opacity: 1;
}

.topbar-actions {
  flex-shrink: 0;
}

.btn-add-file {
  padding: 0.4rem 1rem;
  border: 1px solid var(--theme-green);
  background: transparent;
  color: var(--theme-green);
  border-radius: var(--theme-radius-sm);
  cursor: pointer;
  font-size: 0.85rem;
  transition: var(--theme-transition);
  white-space: nowrap;
}

.btn-add-file:hover {
  background: var(--theme-green);
  color: var(--theme-black);
}

/* 中部内容（可滚动） */
.session-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  min-height: 0;
  overflow-y: auto;
}

.session-content::-webkit-scrollbar {
  width: 6px;
}

.session-content::-webkit-scrollbar-thumb {
  background: var(--theme-border);
  border-radius: 3px;
}

/* ============ 分析摘要面板 ============ */
.summary-panel {
  background: var(--theme-dark);
  border: 1px solid var(--theme-border);
  border-radius: var(--theme-radius);
  overflow: hidden;
  flex-shrink: 0;
}

.summary-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.6rem 1rem;
  border-bottom: 1px solid var(--theme-border);
  background: var(--theme-dark-2);
}

.summary-title {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--theme-green);
}

.btn-collapse {
  background: none;
  border: none;
  color: var(--theme-white-dim);
  cursor: pointer;
  font-size: 0.75rem;
  transition: var(--theme-transition);
}

.btn-collapse:hover {
  color: var(--theme-white);
}

.summary-body {
  padding: 0.75rem 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.summary-section-name {
  font-size: 0.75rem;
  color: var(--theme-white-dim);
  text-transform: uppercase;
  letter-spacing: 0.1em;
  margin-bottom: 0.4rem;
}

.summary-items {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 0.5rem;
}

.summary-card {
  background: var(--theme-dark-2);
  border: 1px solid var(--theme-border);
  border-radius: 6px;
  padding: 0.5rem 0.65rem;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.summary-card.highlight {
  border-left: 2px solid var(--theme-green);
}

.summary-card-label {
  font-size: 0.75rem;
  color: var(--theme-white-dim);
}

.summary-card-value {
  font-size: 0.8rem;
  color: var(--theme-white);
  font-weight: 500;
  word-break: break-all;
}

.summary-collapsed-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 1rem;
  background: var(--theme-dark);
  border: 1px solid var(--theme-border);
  border-radius: var(--theme-radius-sm);
  cursor: pointer;
  font-size: 0.85rem;
  color: var(--theme-white-dim);
  transition: var(--theme-transition);
  flex-shrink: 0;
}

.summary-collapsed-bar:hover {
  border-color: var(--theme-green);
  color: var(--theme-green);
}

.expand-hint {
  font-size: 0.75rem;
  opacity: 0.6;
}

/* 底栏 */
.session-bottombar {
  background: var(--theme-dark);
  border: 1px solid var(--theme-border);
  border-radius: var(--theme-radius);
  padding: 1rem;
  flex-shrink: 0;
}

.input-row {
  display: flex;
  gap: 0.75rem;
  align-items: flex-end;
}

.input-row textarea {
  flex: 1;
  background: var(--theme-dark-2);
  border: 1px solid var(--theme-border);
  border-radius: var(--theme-radius-sm);
  padding: 0.75rem;
  font-size: 0.95rem;
  color: var(--theme-white);
  resize: none;
  font-family: 'Inter', inherit;
  transition: border-color 0.3s ease;
  min-height: 44px;
  max-height: 120px;
}

.input-row textarea::placeholder {
  color: var(--theme-white-dim);
}

.input-row textarea:focus {
  outline: none;
  border-color: var(--theme-green);
  box-shadow: 0 0 0 2px var(--theme-green-dim);
}

.btn-send {
  padding: 0.6rem 1.5rem;
  background: var(--theme-green);
  color: var(--theme-black);
  border: none;
  border-radius: var(--theme-radius-sm);
  cursor: pointer;
  font-size: 0.9rem;
  font-weight: 600;
  letter-spacing: 0.05em;
  transition: var(--theme-transition);
  white-space: nowrap;
  flex-shrink: 0;
}

.btn-send:hover:not(:disabled) {
  box-shadow: 0 0 20px rgba(23, 247, 0, 0.4);
  transform: translateY(-1px);
}

.btn-send:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

.btn-stop {
  padding: 0.6rem 1.5rem;
  background: var(--theme-red);
  color: var(--theme-white);
  border: none;
  border-radius: var(--theme-radius-sm);
  cursor: pointer;
  font-size: 0.9rem;
  font-weight: 600;
  letter-spacing: 0.05em;
  transition: var(--theme-transition);
  white-space: nowrap;
  flex-shrink: 0;
}

.btn-stop:hover {
  box-shadow: 0 0 20px rgba(255, 68, 68, 0.4);
  transform: translateY(-1px);
}

.loading-text {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
}

.loading-text::before {
  content: '';
  width: 8px;
  height: 8px;
  border: 2px solid var(--theme-black);
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.examples-row {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.75rem;
  flex-wrap: wrap;
}

.btn-example {
  padding: 0.4rem 0.75rem;
  border: 1px solid var(--theme-border);
  background: transparent;
  border-radius: 20px;
  cursor: pointer;
  font-size: 0.8rem;
  color: var(--theme-white-dim);
  transition: var(--theme-transition);
  white-space: nowrap;
}

.btn-example:hover {
  border-color: var(--theme-green);
  color: var(--theme-green);
  background: var(--theme-green-dim);
}

/* ============ 添加文件覆盖层 ============ */
.add-file-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  z-index: 50;
  display: flex;
  align-items: center;
  justify-content: center;
}

.add-file-dialog {
  background: var(--theme-dark);
  border: 1px solid var(--theme-border);
  border-radius: var(--theme-radius);
  padding: 1.5rem;
  max-width: 500px;
  width: 90%;
}

.add-file-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.add-file-header h3 {
  margin: 0;
  font-size: 1rem;
  color: var(--theme-white);
  font-weight: 600;
}

.btn-close-dialog {
  width: 32px;
  height: 32px;
  border: 1px solid var(--theme-border);
  background: transparent;
  color: var(--theme-white-dim);
  border-radius: 4px;
  cursor: pointer;
  font-size: 1.2rem;
  line-height: 1;
  transition: var(--theme-transition);
}

.btn-close-dialog:hover {
  border-color: var(--theme-red);
  color: var(--theme-red);
}

/* ============ 历史图表栏 ============ */
.history-viewing-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: var(--theme-green-dim);
  border: 1px solid rgba(23, 247, 0, 0.3);
  border-radius: var(--theme-radius-sm);
  padding: 0.75rem 1rem;
  font-size: 0.9rem;
  color: var(--theme-green);
}

.btn-back-current {
  padding: 0.4rem 1rem;
  background: var(--theme-green);
  color: var(--theme-black);
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.85rem;
  font-weight: 500;
  transition: var(--theme-transition);
}

.btn-back-current:hover {
  box-shadow: 0 0 15px rgba(23, 247, 0, 0.4);
}

/* ============ 固定图表栏 ============ */
.pinned-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: rgba(255, 217, 61, 0.1);
  border: 1px solid rgba(255, 217, 61, 0.3);
  border-radius: var(--theme-radius-sm);
  padding: 0.75rem 1rem;
  font-size: 0.9rem;
  color: #ffd93d;
}

.btn-clear-pinned {
  padding: 0.4rem 1rem;
  background: transparent;
  color: #ffd93d;
  border: 1px solid #ffd93d;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.85rem;
  font-weight: 500;
  transition: all 0.2s;
}

.btn-clear-pinned:hover {
  background: #ffd93d;
  color: var(--theme-black);
}

/* ============ 响应式 ============ */
@media (max-width: 768px) {
  .app-header {
    padding: 0.75rem 1rem;
  }

  .btn-hamburger {
    display: flex;
  }

  .app-main {
    padding: 0.75rem;
  }

  .header-info {
    display: none;
  }

  .session-topbar {
    flex-direction: column;
    align-items: flex-start;
    gap: 0.5rem;
  }

  .examples-row {
    flex-direction: column;
  }

  .btn-example {
    width: 100%;
  }
}
</style>

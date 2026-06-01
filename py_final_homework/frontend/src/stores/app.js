/**
 * Pinia 状态管理
 * 管理会话、消息、图表、加载状态等
 */
import { defineStore } from 'pinia'

export const useAppStore = defineStore('app', {
  state: () => ({
    // 会话信息
    sessionId: null,
    filename: null,
    rowCount: null,
    columns: [],
    datasets: [],  // 多数据集支持

    // 消息
    messages: [],

    // 当前显示的图表
    charts: [],

    // 固定的历史图表（用于对比展示）
    pinnedCharts: [],

    // 历史图表查看状态
    viewingHistoryCharts: false,
    viewingMessageIndex: -1,

    // UI 状态
    isLoading: false,
    error: null,

    // 结构化分析摘要
    analysisSummary: null,    // { title, sections: [{ name, items: [{ label, value, highlight }] }] }
    summaryCollapsed: false,

    // Agent2 返回的分析建议
    suggestions: [],          // [{title, rationale, operation, parameters, expected_insight}]
    interpretation: null,     // Agent2 对当前结果的解读

    // 动态建议查询
    suggestedQueries: [],

    // 输入框
    queryInput: ''
  }),

  getters: {
    // 是否有有效会话
    hasValidSession: (state) => !!state.sessionId,

    // 数据集数量
    datasetCount: (state) => state.datasets?.length || 0,

    // 总行数
    totalRows: (state) => state.datasets?.reduce((sum, ds) => sum + (ds.row_count || 0), 0) || state.rowCount || 0,

    // 获取最新消息
    lastMessage: (state) => {
      return state.messages[state.messages.length - 1] || null
    },

    // 获取用户消息数量
    userMessageCount: (state) => {
      return state.messages.filter(m => m.role === 'user').length
    }
  },

  actions: {
    // 初始化时恢复状态
    $hydrate() {
      const saved = localStorage.getItem('datavis_state')
      if (saved) {
        try {
          const parsed = JSON.parse(saved)
          this.sessionId = parsed.sessionId
          this.messages = parsed.messages || []
          this.filename = parsed.filename
          this.datasets = parsed.datasets || []
          this.viewingHistoryCharts = parsed.viewingHistoryCharts || false
          this.viewingMessageIndex = parsed.viewingMessageIndex ?? -1
        } catch (e) {
          console.error('恢复状态失败:', e)
        }
      }
    },

    // 持久化状态
    $persist() {
      const toSave = {
        sessionId: this.sessionId,
        messages: this.messages,
        filename: this.filename,
        datasets: this.datasets,
        viewingHistoryCharts: this.viewingHistoryCharts,
        viewingMessageIndex: this.viewingMessageIndex
      }
      localStorage.setItem('datavis_state', JSON.stringify(toSave))
    },

    // 设置会话信息
    setSession(sessionId, filename, rowCount, columns, datasets = null) {
      this.sessionId = sessionId
      this.filename = filename
      this.rowCount = rowCount
      this.columns = columns
      this.datasets = datasets || [{
        dataset_id: sessionId,
        dataset_name: filename,
        original_filename: filename,
        row_count: rowCount,
        columns: columns
      }]
      this.messages = []
      this.charts = []
      this.error = null
      this.$persist()
    },

    // 添加数据集
    addDatasets(newDatasets) {
      this.datasets = [...this.datasets, ...newDatasets]
      this.$persist()
    },

    // 删除数据集
    removeDataset(datasetId) {
      this.datasets = this.datasets.filter(ds => ds.dataset_id !== datasetId)
      this.$persist()
    },

    // 清除会话
    clearSession() {
      this.sessionId = null
      this.filename = null
      this.rowCount = null
      this.columns = []
      this.datasets = []
      this.messages = []
      this.charts = []
      this.pinnedCharts = []
      this.error = null
      this.analysisSummary = null
      this.summaryCollapsed = false
      this.suggestedQueries = []
      this.suggestions = []
      this.interpretation = null
      localStorage.removeItem('datavis_state')
    },

    // 添加消息
    addMessage(message) {
      this.messages.push({
        ...message,
        timestamp: new Date().toISOString()
      })
      this.$persist()
    },

    // 更新最后一条消息的内容
    updateLastMessageContent(content) {
      if (this.messages.length > 0) {
        const lastMsg = this.messages[this.messages.length - 1]
        if (lastMsg.role === 'assistant') {
          lastMsg.content = content
        }
      }
    },

    // 设置图表
    setCharts(charts) {
      this.charts = charts || []
    },

    // 固定历史图表（用于对比）
    pinChart(chart) {
      this.pinnedCharts.push(JSON.parse(JSON.stringify(chart)))
    },

    // 取消固定所有图表
    clearPinnedCharts() {
      this.pinnedCharts = []
    },

    // 查看历史图表
    viewHistoricalCharts(messageIndex) {
      const message = this.messages[messageIndex]
      if (message && message.charts && message.charts.length > 0) {
        this.charts = [...message.charts]
        this.viewingHistoryCharts = true
        this.viewingMessageIndex = messageIndex
      }
    },

    // 返回当前最新图表
    viewCurrentCharts() {
      this.viewingHistoryCharts = false
      this.viewingMessageIndex = -1
    },

    // 设置加载状态
    setLoading(loading) {
      this.isLoading = loading
    },

    // 设置错误
    setError(error) {
      this.error = error
    },

    // 清除错误
    clearError() {
      this.error = null
    },

    // 设置查询输入
    setQueryInput(query) {
      this.queryInput = query
    },

    // 设置分析摘要
    setAnalysisSummary(data) {
      this.analysisSummary = data
    },

    // 切换摘要面板折叠
    toggleSummaryCollapsed() {
      this.summaryCollapsed = !this.summaryCollapsed
    },

    // 设置建议查询
    setSuggestedQueries(queries) {
      this.suggestedQueries = queries
    },

    // 设置 Agent2 建议
    setSuggestions(suggestions, interpretation) {
      this.suggestions = suggestions || []
      this.interpretation = interpretation || null
    },

    // 清除建议
    clearSuggestions() {
      this.suggestions = []
      this.interpretation = null
    },

    // 切换会话时加载（原子替换状态）
    loadSession(sessionId, sessionData, messages) {
      this.sessionId = sessionId
      this.filename = sessionData.filename || ''
      this.datasets = sessionData.datasets || []
      this.messages = messages || []
      this.charts = []
      this.pinnedCharts = []
      this.viewingHistoryCharts = false
      this.viewingMessageIndex = -1
      this.error = null
      this.$persist()
    }
  }
})

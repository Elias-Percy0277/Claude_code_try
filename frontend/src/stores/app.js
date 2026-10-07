/**
 * Pinia 状态管理
 * 管理会话、消息、图表、加载状态等
 * 职责：集中维护 DataVis 全局状态（会话/数据集/消息/图表/流式与 UI 状态），
 * 提供 getters 派生数据与 actions 变更状态，并负责 localStorage 的持久化与恢复。
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

    // 控制图表区域可见性（不销毁组件）
    chartsVisible: false,

    // 固定的历史图表（用于对比展示）
    pinnedCharts: [],

    // 历史图表查看状态
    viewingHistoryCharts: false,
    viewingMessageIndex: -1,

    // UI 状态
    isLoading: false,
    isStreaming: false,  // 是否正在接收流式数据
    error: null,

    // 结构化分析摘要
    analysisSummary: null,    // { title, sections: [{ name, items: [{ label, value, highlight }] }] }
    summaryCollapsed: false,

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
    // AI-assisted: 使用 Claude 实现 localStorage 状态恢复，手动调整了恢复字段范围（含 viewingHistory 等）
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

    // 持久化状态（安全化：永不向外抛出异常，charts 数据不存入 localStorage）
    // AI-assisted: 使用 Claude 生成 Pinia 状态管理，手动调整了持久化字段（剥离 charts 仅存消息元数据）
    $persist() {
      try {
        const toSave = {
          sessionId: this.sessionId,
          // 剥离 charts 数据：图表已保存在后端 meta.json，localStorage 仅存消息元数据
          messages: this.messages.map(msg => ({
            role: msg.role,
            content: msg.content,
            timestamp: msg.timestamp
          })),
          filename: this.filename,
          datasets: this.datasets,
          viewingHistoryCharts: false,
          viewingMessageIndex: -1
        }
        localStorage.setItem('datavis_state', JSON.stringify(toSave))
      } catch (e) {
        console.warn('[persist] 持久化失败:', e.message)
      }
    },

    // 设置会话信息
    // AI-assisted: 使用 Claude 实现会话信息初始化，手动调整了 datasets 默认结构兜底
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
    // AI-assisted: 使用 Claude 实现多数据集追加，未做大幅修改
    addDatasets(newDatasets) {
      this.datasets = [...this.datasets, ...newDatasets]
      this.$persist()
    },

    // 删除数据集
    // AI-assisted: 使用 Claude 实现数据集按 ID 过滤删除，未做大幅修改
    removeDataset(datasetId) {
      this.datasets = this.datasets.filter(ds => ds.dataset_id !== datasetId)
      this.$persist()
    },

    // 清除会话
    // AI-assisted: 使用 Claude 实现会话与相关状态清空，手动调整了清空字段范围及 localStorage 移除
    clearSession() {
      this.sessionId = null
      this.filename = null
      this.rowCount = null
      this.columns = []
      this.datasets = []
      this.messages = []
      this.charts = []
      this.chartsVisible = false
      this.pinnedCharts = []
      this.error = null
      this.isStreaming = false
      this.analysisSummary = null
      this.summaryCollapsed = false
      this.suggestedQueries = []
      localStorage.removeItem('datavis_state')
    },

    // 添加消息
    // AI-assisted: 使用 Claude 实现消息追加并打时间戳，未做大幅修改
    addMessage(message) {
      this.messages.push({
        ...message,
        timestamp: new Date().toISOString()
      })
      this.$persist()
    },

    // 更新最后一条消息的内容
    // AI-assisted: 使用 Claude 实现流式增量写入最新 assistant 消息，未做大幅修改
    updateLastMessageContent(content) {
      if (this.messages.length > 0) {
        const lastMsg = this.messages[this.messages.length - 1]
        if (lastMsg.role === 'assistant') {
          lastMsg.content = content
        }
      }
    },

    // 设置图表（有数据时自动显示图表区域）
    // AI-assisted: 使用 Claude 实现图表设置与可见性联动，未做大幅修改
    setCharts(charts) {
      this.charts = charts || []
      if (this.charts.length > 0) {
        this.chartsVisible = true
      }
    },

    // 固定历史图表（用于对比）
    // AI-assisted: 使用 Claude 实现图表深拷贝固定，人工校验后保留深拷贝防引用共享
    pinChart(chart) {
      this.pinnedCharts.push(JSON.parse(JSON.stringify(chart)))
    },

    // 取消固定所有图表
    // AI-assisted: 使用 Claude 实现清空固定图表，未做大幅修改
    clearPinnedCharts() {
      this.pinnedCharts = []
    },

    // 查看历史图表（深拷贝避免引用共享问题）
    // AI-assisted: 使用 Claude 实现历史图表回看，人工校验后保留深拷贝逻辑
    viewHistoricalCharts(messageIndex) {
      const message = this.messages[messageIndex]
      if (message && message.charts && message.charts.length > 0) {
        this.charts = JSON.parse(JSON.stringify(message.charts))
        this.chartsVisible = true
        this.viewingHistoryCharts = true
        this.viewingMessageIndex = messageIndex
      }
    },

    // 返回当前最新图表
    // AI-assisted: 使用 Claude 实现退出历史回看，未做大幅修改
    viewCurrentCharts() {
      this.viewingHistoryCharts = false
      this.viewingMessageIndex = -1
    },

    // 设置加载状态
    // AI-assisted: 使用 Claude 实现加载状态开关，未做大幅修改
    setLoading(loading) {
      this.isLoading = loading
    },

    // 设置流式状态
    // AI-assisted: 使用 Claude 实现流式状态开关，未做大幅修改
    setStreaming(value) {
      this.isStreaming = value
    },

    // 设置错误
    // AI-assisted: 使用 Claude 实现错误信息设置，未做大幅修改
    setError(error) {
      this.error = error
    },

    // 清除错误
    // AI-assisted: 使用 Claude 实现错误清除，未做大幅修改
    clearError() {
      this.error = null
    },

    // 设置查询输入
    // AI-assisted: 使用 Claude 实现查询输入同步，未做大幅修改
    setQueryInput(query) {
      this.queryInput = query
    },

    // 设置分析摘要
    // AI-assisted: 使用 Claude 实现结构化摘要存储，未做大幅修改
    setAnalysisSummary(data) {
      this.analysisSummary = data
    },

    // 切换摘要面板折叠
    // AI-assisted: 使用 Claude 实现摘要折叠切换，未做大幅修改
    toggleSummaryCollapsed() {
      this.summaryCollapsed = !this.summaryCollapsed
    },

    // 设置建议查询
    // AI-assisted: 使用 Claude 实现建议查询列表设置，未做大幅修改
    setSuggestedQueries(queries) {
      this.suggestedQueries = queries
    },

    // 切换会话时加载（原子替换状态）
    // AI-assisted: 使用 Claude 实现切换会话的原子状态替换，人工校验后保留字段重置范围
    loadSession(sessionId, sessionData, messages) {
      this.sessionId = sessionId
      this.filename = sessionData.filename || ''
      this.datasets = sessionData.datasets || []
      this.messages = messages || []
      this.charts = []
      this.chartsVisible = false
      this.pinnedCharts = []
      this.viewingHistoryCharts = false
      this.viewingMessageIndex = -1
      this.error = null
      this.$persist()
    }
  }
})

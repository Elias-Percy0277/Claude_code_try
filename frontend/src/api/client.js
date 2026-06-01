/**
 * API 客户端
 * 封装所有 API 请求
 */
import axios from 'axios'

const API_BASE = '/api'

// SSE 请求直连后端，绕过 Vite 代理缓冲
const API_DIRECT = 'http://localhost:8000/api'

const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器
api.interceptors.request.use(
  (config) => {
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器
api.interceptors.response.use(
  (response) => {
    return response.data
  },
  (error) => {
    const message = error.response?.data?.error?.message ||
                   error.response?.data?.detail ||
                   error.message ||
                   '请求失败'
    return Promise.reject(new Error(message))
  }
)

/**
 * 文件上传（单文件）
 */
export async function uploadFile(file) {
  return uploadFiles([file])
}

/**
 * 文件上传（多文件）
 */
export async function uploadFiles(files, sessionId = null) {
  const formData = new FormData()
  files.forEach(file => {
    formData.append('files', file)
  })

  const params = sessionId ? `?session_id=${sessionId}` : ''

  const response = await axios.post(`${API_BASE}/upload${params}`, formData, {
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  })

  return response.data
}

/**
 * 检查会话有效性
 */
export async function checkSession(sessionId) {
  return await api.get(`/session/${sessionId}`)
}

/**
 * 分析请求（同步）
 */
export async function analyzeSync(sessionId, query) {
  return await api.post('/analysis/sync', {
    session_id: sessionId,
    query: query
  })
}

/**
 * 分析请求（SSE 流式）
 */
export async function analyzeStream(sessionId, query, onData, onError, onDone, signal = null) {
  const response = await fetch(`${API_DIRECT}/analysis`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      session_id: sessionId,
      query: query
    }),
    signal
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.error?.message || '请求失败')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let chartsReceived = false
  let currentResponse = ''
  let aborted = false
  let doneCalled = false

  // 监听 abort 信号，主动取消 reader
  if (signal) {
    signal.addEventListener('abort', () => {
      aborted = true
      try { reader.cancel() } catch (e) { /* ignore */ }
    }, { once: true })
  }

  function processLine(line) {
    if (!line.trim() || !line.startsWith('data: ')) return
    const jsonStr = line.slice(6)
    if (jsonStr === '[DONE]') return

    try {
      const data = JSON.parse(jsonStr)

      if (data.type === 'charts') {
        onData({ type: 'charts', data: data.data })
        chartsReceived = true
      } else if (data.type === 'text') {
        currentResponse += data.delta
        onData({ type: 'text', delta: data.delta, content: currentResponse })
      } else if (data.type === 'done') {
        doneCalled = true
        onDone({ content: currentResponse, hasCharts: chartsReceived, warning: data.warning })
      } else if (data.type === 'error') {
        onError(data.message)
      }
    } catch (e) {
      console.error('解析 SSE 数据失败:', e)
    }
  }

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done || aborted) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        processLine(line)
      }
    }

    // 流结束后处理可能残留在 buffer 中的数据
    if (buffer.trim()) {
      const remainingLines = buffer.split('\n')
      for (const line of remainingLines) {
        processLine(line)
      }
      buffer = ''
    }

    // 兜底：如果流结束但从未收到 done 事件，手动触发
    if (!doneCalled && !aborted) {
      onDone({ content: currentResponse, hasCharts: chartsReceived, warning: null })
    }
  } catch (error) {
    if (error.name === 'AbortError') {
      // 用户主动取消，不视为错误
      onDone({ content: currentResponse, hasCharts: chartsReceived, warning: null })
    } else {
      onError(error.message)
      // 即使出错也要确保 onDone 被调用，避免前端卡死
      if (!doneCalled) {
        onDone({ content: currentResponse, hasCharts: chartsReceived, warning: null })
      }
    }
  }
}

/**
 * 列出会话
 */
export async function listSessions() {
  return await api.get('/sessions')
}

/**
 * 删除会话
 */
export async function deleteSession(sessionId) {
  return await api.delete(`/session/${sessionId}`)
}

/**
 * 重命名会话
 */
export async function renameSession(sessionId, name) {
  return await api.patch(`/session/${sessionId}`, { name })
}

/**
 * 从会话中删除数据集
 */
export async function deleteDataset(sessionId, datasetId) {
  return await api.delete(`/upload/session/${sessionId}/dataset/${datasetId}`)
}

/**
 * 清理过期会话
 */
export async function cleanupSessions() {
  return await api.post('/sessions/cleanup')
}

/**
 * 获取会话统计
 */
export async function getSessionStats() {
  return await api.get('/sessions/stats')
}

/**
 * 获取会话的分析历史
 */
export async function getAnalysisHistory(sessionId) {
  return await api.get(`/analysis/history/${sessionId}`)
}

/**
 * 图表类型切换（后端重绘）
 */
export async function rechart(sessionId, query, chartType) {
  return await api.post('/analysis/rechart', {
    session_id: sessionId,
    query: query,
    chart_type: chartType
  })
}

export default api

/**
 * API 客户端
 * 封装所有 API 请求
 * 职责：统一 axios 实例与拦截器，提供上传、会话、分析（含 SSE 流式）、
 * 数据集、统计与历史等接口；analyzeStream 负责解析 SSE 流并回调分发各事件。
 */
import axios from 'axios'

const API_BASE = '/api'

// SSE 请求 URL：开发模式直连后端绕过代理缓冲，生产模式用相对路径
const API_DIRECT = import.meta.env.VITE_SSE_URL ||
  (import.meta.env.DEV ? 'http://localhost:8000/api' : '/api')

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
 * AI-assisted: 使用 Claude 实现单文件上传转调，未做大幅修改
 */
export async function uploadFile(file) {
  return uploadFiles([file])
}

/**
 * 文件上传（多文件）
 * AI-assisted: 使用 Claude 实现 multipart 多文件上传与 session_id 拼接，人工校验后保留原逻辑
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
 * AI-assisted: 使用 Claude 实现会话有效性查询，未做大幅修改
 */
export async function checkSession(sessionId) {
  return await api.get(`/session/${sessionId}`)
}

/**
 * 分析请求（同步）
 * AI-assisted: 使用 Claude 实现同步分析请求封装，未做大幅修改
 */
export async function analyzeSync(sessionId, query) {
  return await api.post('/analysis/sync', {
    session_id: sessionId,
    query: query
  })
}

/**
 * 分析请求（SSE 流式）
 * AI-assisted: 使用 Claude 封装 SSE 流式请求解析（含超时/abort/兜底 done 处理），人工校验后保留原逻辑
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

  // SSE 流超时保护：180 秒内无数据则自动终止
  const STREAM_TIMEOUT = 180000
  let lastDataTime = Date.now()

  // 监听 abort 信号，主动取消 reader
  if (signal) {
    signal.addEventListener('abort', () => {
      aborted = true
      try { reader.cancel() } catch (e) { /* ignore */ }
    }, { once: true })
  }

  // 解析单行 SSE 数据并按 type 分发到 onData/onError/onDone 回调
  // AI-assisted: 使用 Claude 实现 SSE 行解析与事件分发，人工校验后保留原逻辑
  function processLine(line) {
    if (!line.trim() || !line.startsWith('data: ')) return
    const jsonStr = line.slice(6)
    if (jsonStr === '[DONE]') return

    try {
      const data = JSON.parse(jsonStr)

      // SSE 调试日志（验证通过后可移除）
      console.log(`[SSE] type=${data.type}`, data.type === 'charts'
        ? `charts=${data.data?.length}`
        : data.type === 'progress'
          ? data.message
          : data.type === 'done'
            ? 'done'
            : data.delta?.substring(0, 30))

      if (data.type === 'charts') {
        onData({ type: 'charts', data: data.data })
        chartsReceived = true
      } else if (data.type === 'text') {
        currentResponse += data.delta
        onData({ type: 'text', delta: data.delta, content: currentResponse })
      } else if (data.type === 'progress') {
        onData({ type: 'progress', message: data.message })
      } else if (data.type === 'done') {
        doneCalled = true
        try {
          onDone({ content: currentResponse, hasCharts: chartsReceived, warning: data.warning })
        } catch (e) {
          console.error('[SSE] onDone 回调异常:', e)
        }
      } else if (data.type === 'error') {
        onError(data.message)
      }
    } catch (e) {
      console.error('解析 SSE 数据失败:', e)
    }
  }

  try {
    while (true) {
      // 超时检查：防止后端僵死导致前端无限等待
      if (Date.now() - lastDataTime > STREAM_TIMEOUT) {
        console.warn('[SSE] 流超时（180s 无数据），自动终止')
        try { reader.cancel() } catch (e) { /* ignore */ }
        break
      }

      const { done, value } = await reader.read()
      if (done || aborted) break

      lastDataTime = Date.now()
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
 * AI-assisted: 使用 Claude 实现会话列表拉取，未做大幅修改
 */
export async function listSessions() {
  return await api.get('/sessions')
}

/**
 * 删除会话
 * AI-assisted: 使用 Claude 实现会话删除请求，未做大幅修改
 */
export async function deleteSession(sessionId) {
  return await api.delete(`/session/${sessionId}`)
}

/**
 * 重命名会话
 * AI-assisted: 使用 Claude 实现会话重命名请求，未做大幅修改
 */
export async function renameSession(sessionId, name) {
  return await api.patch(`/session/${sessionId}`, { name })
}

/**
 * 从会话中删除数据集
 * AI-assisted: 使用 Claude 实现数据集删除请求，未做大幅修改
 */
export async function deleteDataset(sessionId, datasetId) {
  return await api.delete(`/upload/session/${sessionId}/dataset/${datasetId}`)
}

/**
 * 清理过期会话
 * AI-assisted: 使用 Claude 实现过期会话清理请求，未做大幅修改
 */
export async function cleanupSessions() {
  return await api.post('/sessions/cleanup')
}

/**
 * 获取会话统计
 * AI-assisted: 使用 Claude 实现会话统计拉取，未做大幅修改
 */
export async function getSessionStats() {
  return await api.get('/sessions/stats')
}

/**
 * 获取会话的分析历史
 * AI-assisted: 使用 Claude 实现分析历史拉取，未做大幅修改
 */
export async function getAnalysisHistory(sessionId) {
  return await api.get(`/analysis/history/${sessionId}`)
}

/**
 * 图表类型切换（后端重绘）
 * AI-assisted: 使用 Claude 实现图表重绘请求，未做大幅修改
 */
export async function rechart(sessionId, query, chartType) {
  return await api.post('/analysis/rechart', {
    session_id: sessionId,
    query: query,
    chart_type: chartType
  })
}

export default api

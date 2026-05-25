# DataVis 项目实现计划

## Context

本项目是一个交互式数据分析平台，核心特色是**自然语言驱动数据分析**。用户上传数据集后，可通过自然语言描述分析需求，系统自动拆解需求、执行数据处理与可视化，并生成智能回复。

### 核心交互流程（含性能优化）
```
用户上传数据
    ↓
用户自然语言提问
    ↓
[缓存检查] 相同查询? → 是: 直接返回缓存
    ↓ 否
DEEPSEEK API 解析意图 → 返回结构化分析任务
    ↓
数据处理 + 可视化（pyecharts）
    ↓
[结果润色] 简单统计? → 模板生成 → 返回
         复杂分析? → LLM 润色 → 返回
    ↓
[异步返回] 先返回图表，文本补齐
```

#### 性能优化策略
1. **缓存机制**：相同查询 + 相同文件（file_hash）→ 直接返回缓存结果
2. **结果润色短路**：简单统计用模板生成，不调用 LLM
3. **异步返回**：POST + fetch 流式处理，图表优先返回，文本流式补齐

---

## 项目架构

```
py_final_homework/
├── backend/
│   ├── main.py                 # FastAPI 入口
│   ├── api/
│   │   ├── __init__.py
│   │   ├── upload.py          # 文件上传 API
│   │   ├── analysis.py        # 分析请求 API
│   │   └── export.py          # PDF 导出 API
│   ├── core/
│   │   ├── __init__.py
│   │   ├── data_loader.py     # 数据加载器（CSV/JSON/Excel/SQL）
│   │   ├── preprocessor.py    # 数据预处理
│   │   ├── analyzer.py        # 统计分析引擎
│   │   ├── intent_parser.py   # 自然语言意图解析（规则引擎）
│   │   └── visualizer.py      # 图表生成器
│   ├── agent/
│   │   ├── __init__.py
│   │   └── llm_client.py      # DEEPSEEK API 客户端
│   ├── session/
│   │   ├── __init__.py
│   │   └── manager.py         # 会话管理器
│   ├── cache/
│   │   ├── __init__.py
│   │   └── cache.py           # 请求缓存
│   └── models/
│       └── schemas.py          # Pydantic 数据模型
│
├── frontend/
│   ├── index.html              # 入口 HTML
│   ├── src/
│   │   ├── main.js            # Vue 入口
│   │   ├── App.vue            # 根组件
│   │   ├── components/
│   │   │   ├── FileUpload.vue # 文件上传组件
│   │   │   ├── ChatPanel.vue  # 对话面板组件
│   │   │   ├── ChartViewer.vue # ECharts 图表组件
│   │   │   └── ErrorMessage.vue # 错误提示组件
│   │   ├── api/
│   │   │   └── client.js      # API 客户端
│   │   └── stores/
│   │       └── app.js         # Pinia 状态管理
│   ├── package.json
│   └── vite.config.js         # Vite 构建配置
│
├── data/                       # 临时数据存储
├── output/                     # 导出文件存储
├── sessions/                   # 会话隔离目录（按 session_id 分目录）
├── requirements.txt
└── README.md
```

---

## 安全设计

### 文件上传安全
```python
# 大小限制
MAX_FILE_SIZE = 60 * 1024 * 1024  # 60MB

# 扩展名白名单
ALLOWED_EXTENSIONS = {'.csv', '.xlsx', '.json', '.xls'}

# 文件类型校验
def validate_file(filename: str, content_type: str) -> bool:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"不支持的文件类型: {ext}")
    return True
```

### SQL 连接安全
- **仅内部配置**：SQL 连接字符串通过环境变量配置，不开放用户输入
- **只读权限**：数据库连接使用只读账号
- **查询限制**：禁止 DROP/ALTER/UPDATE 等写操作

### API 安全
```python
# 请求频率限制
from slowapi import Limiter
limiter = Limiter(key_func=get_remote_address)

@app.post("/api/analysis")
@limiter.limit("10/minute")  # 每分钟最多 10 次
async def analyze(...):
    ...
```

### 数据隔离
- 会话目录权限隔离
- 定期清理过期会话文件

---

## 错误处理与健壮性设计

### 统一错误响应格式
```python
{
    "success": false,
    "error": {
        "code": "INVALID_FILE_FORMAT",
        "message": "不支持的文件格式，请上传 CSV、Excel 或 JSON 文件",
        "detail": {...}
    }
}
```

### 错误码定义
| 错误码 | 说明 | 处理策略 |
|-------|------|---------|
| `INVALID_FILE_FORMAT` | 不支持的文件格式 | 返回提示，拒绝上传 |
| `FILE_TOO_LARGE` | 文件超过 60MB | 返回提示，拒绝上传 |
| `FILE_PARSE_FAILED` | 文件解析失败 | 返回具体错误原因 |
| `NO_ANALYZABLE_COLUMNS` | 无可分析的数值列 | 提示用户上传有效数据 |
| `LLM_PARSE_ERROR` | LLM 返回非 JSON | 重试 1 次，失败则降级为 overview |
| `ANALYSIS_FAILED` | 分析计算异常 | 返回友好错误提示 |
| `SESSION_NOT_FOUND` | 会话不存在或过期 | 提示用户重新上传 |
| `API_RATE_LIMIT` | API 调用超限 | 返回等待时间 |

### 降级策略
```python
# LLM 解析失败时的完整处理流程
def safe_parse_intent(query: str, df: pd.DataFrame) -> dict:
    try:
        result = llm_parse(query, df)

        # 1. 检查置信度
        if result.get('confidence', 1.0) < 0.7:
            return {
                "confidence": 0.5,
                "tasks": [{"intent": "overview"}],
                "warning": "意图识别置信度较低，已自动切换为数据概览"
            }

        # 2. 校验列名
        actual_columns = df.columns.tolist()
        result['tasks'] = validate_and_fix_columns(result['tasks'], actual_columns)

        return result

    except JSONDecodeError:
        # JSON 解析失败，降级到概览
        return {"tasks": [{"intent": "overview"}]}
    except ColumnMatchError as e:
        # 列名无法匹配，降级到概览
        return {
            "tasks": [{"intent": "overview"}],
            "warning": f"无法识别目标列：{e}"
        }
    except APIError:
        # API 调用失败，返回友好错误
        raise AnalysisError("AI 服务暂时不可用，请稍后重试")
```

### 数据校验
```python
def validate_dataframe(df: pd.DataFrame) -> None:
    if df.empty:
        raise ValidationError("数据集为空")
    if len(get_numeric_columns(df)) == 0:
        raise ValidationError("数据集中没有数值列可供分析")
```

---

## 核心模块设计

### 1. 后端 - FastAPI (`backend/main.py`)
- 提供 RESTful API
- CORS 配置支持前端调用
- 静态文件服务

### 2. 数据加载器 (`backend/core/data_loader.py`)
- 支持 CSV、JSON、Excel (.xlsx) 文件
- 支持 SQL 数据库连接
- 统一返回 pandas DataFrame

### 3. 意图解析器 (`backend/core/intent_parser.py`)
**纯 LLM 方案**：所有意图识别由 DEEPSEEK API 完成

#### Prompt 模板
```
你是数据分析意图识别专家。根据用户问题和数据集信息，返回结构化的分析任务。

用户问题：{user_query}
数据集列名：{columns}
列的数据类型：{dtypes}

支持的意图类型：
- overview: 数据概览（统计摘要、缺失值、数据类型）
- trend: 趋势分析（折线图、趋势方向）
- correlation: 相关性分析（相关系数矩阵、热力图）
- seasonality: 季节性分解（周期性模式）
- moving_avg: 移动平均（平滑趋势，**必须包含 window 参数**）
- distribution: 分布分析（直方图、箱线图）
- comparison: 分组对比（多组数据对比）

返回 JSON 格式：
{
  "confidence": 0.95,
  "tasks": [
    {
      "intent": "moving_avg",
      "target_columns": ["列名1"],
      "groupby": "分组列名（可选）",
      "params": {"window": 7}
    }
  ]
}

**重要约束**：
1. target_columns 中的列名必须精确匹配数据集列名，不能编造
2. moving_avg 意图的 params 必须包含 window（建议值：3/7/14/30）
3. confidence 表示解析置信度（0-1），低于 0.7 时系统将降级到 overview

只返回 JSON，不要其他文字。
```

#### 输出格式
```json
{
  "confidence": 0.9,
  "tasks": [
    {
      "intent": "trend",
      "target_columns": ["销售额", "利润"],
      "params": {}
    },
    {
      "intent": "moving_avg",
      "target_columns": ["销售额"],
      "params": {"window": 7}
    }
  ]
}
```

#### 列名校验与模糊匹配
```python
def validate_and_fix_columns(tasks: list, actual_columns: list) -> list:
    """校验并修复 LLM 返回的列名"""
    from Levenshtein import distance

    for task in tasks:
        for col in task.get('target_columns', []):
            # 精确匹配
            if col in actual_columns:
                continue

            # 模糊匹配（Levenshtein 距离）
            best_match = min(actual_columns, key=lambda c: distance(col, c))
            if distance(col, best_match) <= 2:  # 允许最多 2 个字符差异
                # 替换为最佳匹配
                task['target_columns'].remove(col)
                task['target_columns'].append(best_match)
            else:
                # 无法匹配，降级到 overview
                raise ColumnMatchError(f"无法匹配列名: {col}")

    return tasks
```

### 4. 分析引擎 (`backend/core/analyzer.py`)
- 统计分析：均值、中位数、标准差、分位数
- 相关性分析：Pearson/Spearman 相关系数矩阵
- 时序分析：趋势检测、季节性分解（STL）
- 移动平均：简单移动平均、指数移动平均

#### 时序分析预处理（STL 分解要求）
```python
from statsmodels.tsa.seasonal import STL
import pandas as pd

def prepare_timeseries(df: pd.DataFrame, date_column: str, value_column: str):
    """
    预处理时间序列数据以满足 STL 分解要求：
    1. 等间隔时间戳
    2. 无缺失值
    """
    # 1. 确保日期列是 datetime 类型
    df = df.copy()
    df[date_column] = pd.to_datetime(df[date_column])

    # 2. 按日期排序
    df = df.sort_values(date_column)

    # 3. 设置日期为索引
    df = df.set_index(date_column)

    # 4. 检查时间间隔
    if len(df) < 2:
        raise ValueError("数据点太少，无法进行时序分析")

    # 计算最常见的时间间隔
    intervals = df.index.to_series().diff().dropna()
    most_common_interval = intervals.mode()[0]

    # 5. 重采样到规则频率
    try:
        # 推断频率（D=日, W=周, M=月, Q=季, Y=年）
        inferred_freq = pd.infer_freq(df.index)
        if inferred_freq is None:
            # 无法推断，使用最常见间隔
            df = df.asfreq(most_common_interval)
        else:
            df = df.asfreq(inferred_freq)

        # 6. 前向填充缺失值
        df[value_column] = df[value_column].ffill()

        # 7. 检查是否还有缺失值
        if df[value_column].isna().any():
            # ffill 仍有缺失，用均值填充
            df[value_column] = df[value_column].fillna(df[value_column].mean())

        return df, most_common_interval

    except Exception as e:
        raise AnalysisError(f"时序数据预处理失败: {e}")

def safe_seasonal_decompose(df: pd.DataFrame, date_column: str, value_column: str):
    """
    安全的季节性分解，失败时降级为简单趋势
    """
    try:
        # 预处理
        ts_df, interval = prepare_timeseries(df, date_column, value_column)

        # STL 分解要求至少 2 个完整周期
        if len(ts_df) < 24:  # 至少 24 个数据点
            return {
                "success": False,
                "reason": "数据点不足（需要至少 24 个）",
                "fallback": "trend_only"
            }

        # 执行 STL 分解
        stl = STL(ts_df[value_column], period=12)  # 假设月度数据
        result = stl.fit()

        return {
            "success": True,
            "trend": result.trend.tolist(),
            "seasonal": result.seasonal.tolist(),
            "residual": result.resid.tolist()
        }

    except Exception as e:
        # 降级：返回简单趋势
        return {
            "success": False,
            "reason": str(e),
            "fallback": "trend_only",
            "message": "数据不满足季节性分解要求，已降级为趋势分析"
        }
```

### 5. 可视化生成器 (`backend/core/visualizer.py`)
**统一方案**：使用 pyecharts 生成 ECharts JSON 配置

#### 工作流程
```
analyzer 分析结果 → pyecharts 生成图表 → dump_as_dict() → 返回 JSON
```

#### 返回格式
```python
{
    "chart_type": "line",
    "option": {  # ECharts option JSON
        "title": {...},
        "xAxis": {...},
        "yAxis": {...},
        "series": [...]
    }
}
```

#### 支持的图表类型
- 折线图（趋势、时序）
- 热力图（相关性矩阵）
- 柱状图（分组对比）
- 散点图（相关性）
- 箱线图（分布）
- 饼图（占比）

#### PDF 导出
仅在导出功能中渲染为图片（使用 snapshot-pyecharts 或 phantomjs）

### 6. 流式响应设计 (`backend/api/analysis.py`)
使用 **POST + StreamingResponse** 实现 SSE 格式流式响应

#### 技术方案
```python
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json

class AnalysisRequest(BaseModel):
    session_id: str
    query: str

async def analyze_stream(request: AnalysisRequest):
    """生成 SSE 格式的流式响应"""
    try:
        # 获取会话数据
        session = session_manager.get(request.session_id)
        df = session.dataframe

        # 1. 意图解析
        intent = await intent_parser.parse(request.query, df)

        # 2. 数据分析（同步，快速）
        charts_data = await analyzer.analyze_and_visualize(intent, df)

        # 3. 先发送图表数据
        yield f"data: {json.dumps({'type': 'charts', 'data': charts_data}, ensure_ascii=False)}\n\n"

        # 4. LLM 润色（异步，慢速），流式发送
        if needs_llm_polish(request.query):
            async for text_chunk in llm_client.polish_stream(request.query, charts_data):
                yield f"data: {json.dumps({'type': 'text', 'delta': text_chunk}, ensure_ascii=False)}\n\n"

        # 5. 结束标记
        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    except Exception as e:
        # 错误处理
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

@app.post("/api/analysis")
async def analyze(request: AnalysisRequest):
    """POST 接口，返回 SSE 流式响应"""
    return StreamingResponse(
        analyze_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # 禁用 Nginx 缓冲
        }
    )
```

#### 前端对接（fetch + ReadableStream）
前端使用 `fetch` POST 请求，通过 `response.body.getReader()` 读取流。见前端部分的 `ChatPanel.vue` 实现。

### 9. LLM 客户端 (`backend/agent/llm_client.py`)
调用 DEEPSEEK API，支持三种功能：

#### 功能 1：意图解析
将用户自然语言转换为结构化的分析任务 JSON

#### 功能 2：结果润色（带短路机制）
```python
def polish_result(query: str, result: dict) -> str:
    # 简单情况：模板化生成，不调用 LLM
    if is_simple_stats(result):
        return template_polish(result)

    # 复杂情况：调用 LLM 润色
    return llm_polish(query, result)
```

**模板化示例**：
```python
# 输入: {"mean": 1000, "max": 5000}
# 输出: "数据的平均值为 1000，最大值为 5000。"
```

#### 功能 3：流式文本生成（用于 SSE）
```python
import httpx
import json

async def llm_polish_stream(query: str, result: dict):
    """流式调用 DEEPSEEK API，逐块返回文本"""
    async with httpx.AsyncClient() as client:
        async with client.stream(
            'POST',
            'https://api.deepseek.com/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {DEEPSEEK_API_KEY}',
                'Content-Type': 'application/json'
            },
            json={
                'model': 'deepseek-chat',
                'messages': [
                    {'role': 'system', 'content': '你是数据分析助手...'},
                    {'role': 'user', 'content': f'分析结果：{result}'}
                ],
                'stream': True  # 启用流式
            }
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith('data: '):
                    data = line[6:]
                    if data == '[DONE]':
                        break
                    chunk = json.loads(data)
                    delta = chunk['choices'][0]['delta'].get('content', '')
                    if delta:
                        yield delta
```

### 10. 前端架构 (Vue 3 + Vite)

#### 技术栈
- **Vue 3** - 渐进式框架
- **Vite** - 构建工具
- **Pinia** - 状态管理
- **vue-echarts** - ECharts Vue 组件
- **axios** - HTTP 客户端

#### 目录结构
```
frontend/src/
├── main.js           # Vue 入口
├── App.vue           # 根组件
├── components/
│   ├── FileUpload.vue    # 文件上传
│   ├── ChatPanel.vue     # 对话面板
│   ├── ChartViewer.vue   # 图表展示（使用 vue-echarts）
│   └── ErrorMessage.vue  # 错误提示
├── api/
│   └── client.js      # API 封装
└── stores/
    └── app.js         # Pinia store（状态管理）
```

#### 状态管理（Pinia）+ localStorage 持久化
```javascript
// stores/app.js
import { defineStore } from 'pinia'

export const useAppStore = defineStore('app', {
  state: () => ({
    sessionId: null,      // 从 localStorage 恢复
    messages: [],         // 从 localStorage 恢复
    charts: [],           // 不持久化（刷新后重新渲染）
    isLoading: false,
    error: null
  }),

  actions: {
    // 初始化时恢复状态
    $hydrate() {
      const saved = localStorage.getItem('datavis_state')
      if (saved) {
        const parsed = JSON.parse(saved)
        this.sessionId = parsed.sessionId
        this.messages = parsed.messages || []
      }
    },

    // 每次状态变更时持久化
    $persist() {
      const toSave = {
        sessionId: this.sessionId,
        messages: this.messages
      }
      localStorage.setItem('datavis_state', JSON.stringify(toSave))
    },

    async sendMessage(query) {
      // 发送前检查会话是否有效
      if (this.sessionId) {
        try {
          await api.get(`/api/session/${this.sessionId}`)
        } catch (e) {
          // 会话过期，清除状态
          this.$reset()
          localStorage.removeItem('datavis_state')
          throw new Error('会话已过期，请重新上传数据')
        }
      }
      // ... 发送消息逻辑
    },

    setSessionId(id) {
      this.sessionId = id
      this.$persist()
    },

    addMessage(msg) {
      this.messages.push(msg)
      this.$persist()
    },

    clearError() {
      this.error = null
    }
  }
})

// 应用初始化时恢复状态
// main.js
const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.mount('#app')

// 恢复状态
const store = useAppStore()
store.$hydrate()
```

#### 流式客户端集成（fetch + ReadableStream）
```vue
<!-- ChatPanel.vue -->
<script setup>
import { ref } from 'vue'
import { useAppStore } from '@/stores/app'

const store = useAppStore()
const currentResponse = ref('')
let abortController = null

async function sendMessage(query) {
  // 取消之前的请求
  if (abortController) {
    abortController.abort()
  }
  abortController = new AbortController()

  currentResponse.value = ''
  const chartsReceived = ref(false)

  try {
    const response = await fetch('/api/analysis', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        session_id: store.sessionId,
        query: query
      }),
      signal: abortController.signal
    })

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.error?.message || '请求失败')
    }

    // 读取流式响应
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      // 解码并按行分割（SSE 格式）
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''  // 保留不完整的行

      for (const line of lines) {
        if (!line.trim() || !line.startsWith('data: ')) continue

        const jsonStr = line.slice(6)  // 去掉 "data: " 前缀
        if (jsonStr === '[DONE]') break

        try {
          const data = JSON.parse(jsonStr)

          if (data.type === 'charts') {
            // 图表优先渲染
            store.setCharts(data.data)
            chartsReceived.value = true
          } else if (data.type === 'text') {
            // 文本流式补齐
            currentResponse.value += data.delta
          } else if (data.type === 'done') {
            // 完成，保存消息
            store.addMessage({
              role: 'assistant',
              content: currentResponse.value,
              charts: chartsReceived.value ? store.charts : null
            })
          } else if (data.type === 'error') {
            store.setError(data.message)
          }
        } catch (e) {
          console.error('解析 SSE 数据失败:', e)
        }
      }
    }
  } catch (error) {
    if (error.name === 'AbortError') {
      console.log('请求已取消')
    } else {
      store.setError(error.message || '连接中断，请重试')
    }
  } finally {
    abortController = null
  }
}
</script>
```

### 7. 缓存管理器 (`backend/cache/cache.py`)
减少重复 LLM 调用，提升响应速度

#### 缓存键设计
```python
# 缓存键 = session_id + query + file_hash
# file_hash 在会话创建时计算一次，避免重复序列化 DataFrame
cache_key = f"{session_id}:{query}:{file_hash}"

# file_hash 来源：原始文件的 MD5（前 8 位）
file_hash = hashlib.md5(upload_file.read()).hexdigest()[:8]
```

#### 缓存结构
```python
{
    "result": {...},      # 完整响应
    "created_at": timestamp,
    "hit_count": 1
}
```

#### 淘汰策略
- LRU（最近最少使用）
- 最大缓存 100 条
- 过期时间 1 小时

### 8. 会话管理器 (`backend/session/manager.py`)
管理用户会话和数据隔离，支持服务重启恢复

#### 会话目录结构
```
sessions/
├── {session_id}/
│   ├── meta.json           # 会话元信息
│   ├── data.parquet        # 数据持久化（高性能二进制格式）
│   └── cache.json          # 可选：分析结果缓存
```

#### meta.json 结构（优化版）
```json
{
  "session_id": "abc-123",
  "created_at": "2024-01-01 12:00:00",
  "last_accessed": "2024-01-01 12:30:00",
  "file_hash": "abc12345",
  "original_filename": "data.csv",
  "columns_info": {
    "销售额": {"dtype": "float64", "nullable": false, "nunique": 1000},
    "地区": {"dtype": "object", "nullable": true, "nunique": 5}
  },
  "row_count": 10000,
  "chat_history": []
}
```

**说明**：
- `nunique`: 唯一值数量（不存储实际值列表）
- `nullable`: 是否包含空值
- `dtype`: pandas 数据类型
- `row_count`: 总行数

#### 内存会话结构
```python
Session = {
    "session_id": "uuid",
    "created_at": timestamp,
    "last_accessed": timestamp,
    "file_hash": "abc12345",
    "dataframe": pd.DataFrame,   # 可选内存缓存（LRU 淘汰）
    "disk_path": "sessions/{id}/",  # 磁盘持久化路径
    "columns_info": {...},
    "chat_history": []
}
```

#### 持久化策略
```python
def create_session(upload_file) -> Session:
    session_id = uuid4()
    session_dir = f"sessions/{session_id}"
    os.makedirs(session_dir, exist_ok=True)

    # 1. 保存数据到磁盘（parquet 格式，高性能）
    df = pd.read_csv(upload_file)
    df.to_parquet(f"{session_dir}/data.parquet")

    # 2. 保存元信息（高效计算列统计）
    meta = {
        "session_id": session_id,
        "created_at": now(),
        "file_hash": hashlib.md5(upload_file.read()).hexdigest()[:8],
        "columns_info": analyze_columns(df),
        "row_count": len(df),
        "chat_history": []
    }
    json_dump(meta, f"{session_dir}/meta.json")

    # 3. 内存缓存（可选）
    return Session(
        session_id=session_id,
        dataframe=df,  # 内存缓存
        disk_path=session_dir,
        ...
    )

def get_session(session_id: str) -> Session:
    # 1. 先查内存缓存
    if session_id in memory_cache:
        session = memory_cache[session_id]
        session.last_accessed = now()
        return session

    # 2. 内存未命中，从磁盘加载
    meta_path = f"sessions/{session_id}/meta.json"
    if not os.path.exists(meta_path):
        raise SessionNotFoundError()

    meta = json_load(meta_path)
    df = pd.read_parquet(f"sessions/{session_id}/data.parquet")

    # 3. 加载回内存
    session = Session(
        session_id=session_id,
        dataframe=df,
        **meta
    )
    memory_cache[session_id] = session
    return session
```

#### API 设计
- `create_session(upload_file)` → 创建并持久化，返回 session_id
- `get_session(session_id)` → 优先内存，未命中则加载磁盘
- `update_session(session_id)` → 更新 meta.json 和内存
- `cleanup_expired_sessions()` → 清理过期会话（30 分钟）+ 磁盘文件

#### 会话清理机制（后台任务）
```python
import time
import shutil
from datetime import datetime, timedelta
import asyncio

# 方案 A：后台定时任务（推荐用于生产环境）
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

SESSION_EXPIRE_MINUTES = 30  # 会话过期时间

async def cleanup_expired_sessions():
    """定时清理过期会话"""
    now = datetime.now()
    expire_threshold = now - timedelta(minutes=SESSION_EXPIRE_MINUTES)

    sessions_dir = Path("sessions")
    if not sessions_dir.exists():
        return

    for session_dir in sessions_dir.iterdir():
        if not session_dir.is_dir():
            continue

        meta_path = session_dir / "meta.json"
        if not meta_path.exists():
            # 元文件损坏，直接删除目录
            shutil.rmtree(session_dir)
            continue

        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)

            last_accessed = datetime.fromisoformat(meta['last_accessed'])

            if last_accessed < expire_threshold:
                # 过期，删除会话
                shutil.rmtree(session_dir)

                # 同时清除内存缓存
                if meta['session_id'] in memory_cache:
                    del memory_cache[meta['session_id']]

                print(f"清理过期会话: {meta['session_id']}")
        except Exception as e:
            print(f"清理会话失败 {session_dir}: {e}")

# 启动定时任务（每小时执行一次）
scheduler.add_job(cleanup_expired_sessions, 'interval', hours=1)
scheduler.start()

# 方案 B：创建会话时触发轻量清理（适合开发/小规模）
def create_session(upload_file) -> Session:
    # 创建新会话前，随机触发一次清理（10% 概率）
    if random.random() < 0.1:
        cleanup_expired_sessions()

    # ... 创建会话逻辑
```

#### 列信息分析（高效）
```python
def analyze_columns(df: pd.DataFrame) -> dict:
    """高效分析列信息，避免高基数列的性能问题"""
    result = {}

    for col in df.columns:
        info = {
            "dtype": str(df[col].dtype),
            "nullable": df[col].isna().any()
        }

        # 对于低基数列（分类列），计算唯一值数量
        if df[col].nunique() < 100:  # 阈值可调
            info["nunique"] = df[col].nunique()
        else:
            # 高基数列，使用估算或标记
            info["nunique"] = "high"

        result[col] = info

    return result
```

#### LRU 内存管理
```python
from functools import lru_cache

# 限制内存中最多缓存 10 个 DataFrame
@lru_cache(maxsize=10)
def get_dataframe(session_id: str) -> pd.DataFrame:
    return pd.read_parquet(f"sessions/{session_id}/data.parquet")
```

### 8. 前端 (`frontend/`)
- **布局**：左侧上传/数据预览，右侧对话交互 + 可视化展示
- **ECharts 集成**：动态渲染后端返回的图表配置
- **对话界面**：类似 ChatGPT 的对话流，支持历史记录

---

## 模块化开发策略

### 开发原则
每个模块可独立开发、测试、验证，模块间通过清晰接口交互。

### 模块验证顺序
```
Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 6 → Phase 7 → Phase 8 → Phase 9 → Phase 10
   ↓        ↓        ↓        ↓        ↓        ↓        ↓        ↓        ↓        ↓
骨架     数据      意图      分析      可视      LLM      会话      API      前端    联调
```

### 每个模块的验证方式

#### Phase 1: 项目骨架
```bash
# 验证方式：启动服务器
uvicorn backend.main:app --reload
curl http://localhost:8000/health  # 应返回 {"status": "ok"}
```

#### Phase 2: 数据加载
```python
# test_data_loader.py
from backend.core.data_loader import load_data

df = load_data("test.csv")
assert not df.empty
assert len(df.columns) > 0
print("✓ 数据加载模块验证通过")
```

#### Phase 3: 意图解析
```python
# test_intent_parser.py
from backend.core.intent_parser import parse_intent

result = parse_intent("分析销售额趋势", df)
assert result["confidence"] > 0.7
assert result["tasks"][0]["intent"] == "trend"
print("✓ 意图解析模块验证通过")
```

#### Phase 4: 分析引擎
```python
# test_analyzer.py
from backend.core.analyzer import analyze_trend

result = analyze_trend(df, "销售额")
assert "trend_direction" in result
print("✓ 分析引擎模块验证通过")
```

#### Phase 5: 可视化
```python
# test_visualizer.py
from backend.core.visualizer import create_line_chart

option = create_line_chart(df, "销售额")
assert "title" in option
assert "xAxis" in option
print("✓ 可视化模块验证通过")
```

#### Phase 6: LLM 客户端
```python
# test_llm_client.py
from backend.agent.llm_client import polish_result

text = polish_result("分析销售额", {"mean": 1000})
assert isinstance(text, str)
print("✓ LLM 客户端模块验证通过")
```

#### Phase 7: 会话管理
```python
# test_session.py
from backend.session.manager import create_session, get_session

session = create_session(upload_file)
assert session.session_id is not None

retrieved = get_session(session.session_id)
assert retrieved.session_id == session.session_id
print("✓ 会话管理模块验证通过")
```

#### Phase 8: API 路由
```bash
# 验证方式：API 测试
curl -X POST http://localhost:8000/api/upload -F "file=@test.csv"
# 应返回 {"session_id": "...", "filename": "test.csv"}

curl -X GET http://localhost:8000/api/session/{session_id}
# 应返回会话信息
```

#### Phase 9: 前端开发
```bash
# 验证方式：启动前端开发服务器
cd frontend
npm run dev
# 访问 http://localhost:5173
# 测试文件上传、对话、图表渲染
```

### 模块间接口定义

| 模块 | 输入 | 输出 |
|-----|------|------|
| `data_loader` | 文件路径 | `pd.DataFrame` |
| `intent_parser` | query + DataFrame | `{"tasks": [...], "confidence": 0.9}` |
| `analyzer` | task + DataFrame | `{"result": {...}, "stats": {...}}` |
| `visualizer` | result + DataFrame | `{"chart_type": "line", "option": {...}}` |
| `llm_client` | query + result | `str` (润色后的文本) |
| `session_manager` | session_id | `Session` 对象 |

### 测试文件结构
```
tests/
├── test_data_loader.py
├── test_intent_parser.py
├── test_analyzer.py
├── test_visualizer.py
├── test_llm_client.py
├── test_session.py
└── fixtures/
    └── sample_data.csv
```

---

## 实现步骤

### Phase 1: 项目骨架搭建
1. 创建目录结构
2. 配置 `requirements.txt` 依赖（含 statsmodels）
3. 初始化 FastAPI 入口
4. **定义 Pydantic 数据模型**（统一错误响应格式）
   ```python
   # models/schemas.py
   from pydantic import BaseModel

   class ErrorResponse(BaseModel):
       success: bool = False
       error: ErrorDetail

   class ErrorDetail(BaseModel):
       code: str
       message: str
       detail: dict = {}

   # 定义所有错误码常量
   class ErrorCode:
       INVALID_FILE_FORMAT = "INVALID_FILE_FORMAT"
       FILE_TOO_LARGE = "FILE_TOO_LARGE"
       FILE_PARSE_FAILED = "FILE_PARSE_FAILED"
       NO_ANALYZABLE_COLUMNS = "NO_ANALYZABLE_COLUMNS"
       LLM_PARSE_ERROR = "LLM_PARSE_ERROR"
       ANALYSIS_FAILED = "ANALYSIS_FAILED"
       SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
       API_RATE_LIMIT = "API_RATE_LIMIT"
   ```

### Phase 2: 数据加载与预处理
1. 实现 `data_loader.py` - 支持 CSV/JSON/Excel/SQL
2. 实现 `preprocessor.py` - 缺失值处理、类型推断
3. 添加数据校验逻辑

### Phase 3: 意图解析（LLM）
1. 实现 `intent_parser.py` - LLM 意图识别
2. 设计 Prompt 模板
3. 添加 JSON 解析错误处理与降级策略

### Phase 4: 分析引擎
1. 实现 `analyzer.py` - 统计分析函数
2. 时序分析功能（依赖 statsmodels，需先验证安装）
3. 添加异常处理与友好错误提示

### Phase 5: 可视化模块
1. 实现 `visualizer.py` - 使用 pyecharts 生成 ECharts JSON
2. 测试各图表类型输出格式

### Phase 6: LLM 集成与缓存
1. 实现 `llm_client.py` - DEEPSEEK API 调用
2. 实现结果润色短路机制（模板化）
3. 实现 `cache.py` - 请求缓存管理

### Phase 7: 会话管理
1. 实现 `session/manager.py` - 会话隔离
2. 添加会话过期清理机制

### Phase 8: API 路由与错误处理
1. 实现 `api/upload.py` - 文件上传
2. 实现 `api/analysis.py` - 分析请求（SSE 流式响应）
3. 实现 `api/session.py` - 会话检查端点（前端恢复时验证）
   ```python
   @app.get("/api/session/{session_id}")
   async def check_session(session_id: str):
       session = session_manager.get(session_id)
       if not session:
           raise HTTPException(404, "SESSION_NOT_FOUND")
       return {
           "valid": True,
           "filename": session.original_filename,
           "created_at": session.created_at
       }
   ```
4. 添加统一错误处理中间件

### Phase 9: 前端开发（Vue 3）
1. 初始化 Vite + Vue 3 项目
2. 配置 vue-echarts 和 Pinia
3. 实现核心组件（FileUpload、ChatPanel、ChartViewer）
4. 实现状态管理（Pinia store）
5. 实现流式返回处理
6. 错误处理与提示组件

### Phase 10: 联调与测试
1. 端到端测试
2. 示例数据集测试
3. 错误场景测试

### Phase 11: PDF 导出（可选）
1. 使用 reportlab 或 weasyprint
2. 生成包含图表的分析报告

---

## 关键依赖

### 后端（Python）
```txt
fastapi
uvicorn
python-multipart
pandas
numpy
openpyxl
sqlalchemy
statsmodels
pyecharts
httpx          # DEEPSEEK API 调用
pydantic
reportlab      # PDF 导出（可选）
snapshot-pyecharts  # 图表截图（可选）
slowapi        # API 速率限制
python-Levenshtein  # 列名模糊匹配
APScheduler    # 后台定时任务（会话清理）
```

### 前端（Node.js）
```txt
vue
vite
pinia
vue-echarts
echarts
axios
```

---

## 验证计划

1. **数据加载测试**：用不同格式的测试数据验证加载功能
2. **意图解析测试**：测试各种自然语言查询的识别准确率
3. **分析功能测试**：验证各类统计分析和时序分析的输出正确性
4. **端到端测试**：完整走通 "上传-查询-分析-展示" 流程
5. **可视化测试**：验证图表正确渲染且数据准确

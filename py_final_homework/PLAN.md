# DataVis 双 Agent 架构设计文档

## 项目概述

DataVis 是一个交互式数据分析平台，采用双 Agent 架构，将"调度"与"顾问"职责分离，解决单 Agent 架构下的模糊请求超时和角色混淆问题。

## 架构设计

### 双 Agent 流程

```
用户请求 → Agent1（规划调度器）
           ↓ 输出 JSON 任务计划
  ┌─────────────────────────────────────┐
  │ type: operation                     │
  │   → executor.py 执行分析            │
  │   → 返回统计结果 + ECharts 图表     │
  │   → 更新 session context            │
  ├─────────────────────────────────────┤
  │ type: consultation                  │
  │   → Agent2（分析顾问）              │
  │   → 返回结构化建议列表              │
  │   → 前端渲染为一键执行按钮          │
  ├─────────────────────────────────────┤
  │ type: error                         │
  │   → 返回错误提示                    │
  └─────────────────────────────────────┘
           ↓ SSE 流式响应
       前端渲染结果
```

### 核心组件

| 组件 | 文件 | 职责 |
|------|------|------|
| Agent1 | `backend/agent/planner.py` | 规划调度，分类 operation/consultation/error |
| Agent2 | `backend/agent/advisor.py` | 分析顾问，生成结构化可执行建议 |
| 操作注册表 | `backend/core/operations.py` | 7 个操作的元信息，Agent 共享 |
| 操作执行器 | `backend/core/executor.py` | 执行操作，返回 OperationResult |
| 会话上下文 | `backend/models/session_context.py` | 数据画像、分析历史、最近结果 |
| 分析引擎 | `backend/core/analyzer.py` | 统计计算函数 |
| 可视化 | `backend/core/visualizer.py` | ECharts JSON 生成 |

### 会话上下文结构

```python
SessionContext = {
    "data_id": "dataset_xxx",
    "data_profile": {
        "columns": [...],
        "numeric_columns": [...],
        "categorical_columns": [...],
        "unique_values_preview": {"分类列": ["值1", "值2"]},
        "row_count": 1000
    },
    "available_operations": [...],          # 操作注册表
    "analysis_history": [                   # 已完成的分析
        {"step": 1, "operation": "trend", "summary": "..."}
    ],
    "last_operation_result": OperationResult | None
}
```

### SSE 消息类型

| 类型 | 方向 | 数据 |
|------|------|------|
| `charts` | 后端→前端 | ECharts 配置列表 |
| `text` | 后端→前端 | 文本增量 delta |
| `suggestions` | 后端→前端 | Agent2 建议列表 |
| `warning` | 后端→前端 | 非致命警告 |
| `error` | 后端→前端 | 错误信息 |
| `done` | 后端→前端 | 流结束信号 |

### 超时与降级策略

| 场景 | 策略 |
|------|------|
| Agent1 LLM 超时 (30s) | 本地关键词预检测 fallback |
| Agent2 LLM 超时 (45s) | 基于数据画像的模板建议 |
| 纯模糊需求 | 快速路径直接路由到 consultation，跳过 LLM |
| 操作执行失败 | 发送 warning，继续后续步骤 |

## 操作注册表

| 操作 | 说明 | 参数 |
|------|------|------|
| `overview` | 数据概览 | 无 |
| `trend` | 趋势分析 | columns, chart_type |
| `distribution` | 分布分析 | column, chart_type |
| `comparison` | 分组对比 | target_columns, groupby, groupby2, chart_type |
| `correlation` | 相关性 | columns, chart_type |
| `moving_avg` | 移动平均 | column, window, chart_type |
| `seasonality` | 季节性分解 | column, chart_type |

## 前端交互

### 建议采纳流程

1. 用户发送模糊请求 → Agent1 路由到 consultation
2. Agent2 返回建议列表 → 前端渲染建议卡片
3. 用户点击"一键执行" → `POST /api/analysis/execute`
4. 跳过 Agent1，直接执行操作 → 返回结果

### 状态管理

```javascript
// Pinia store 新增状态
suggestions: [],          // Agent2 建议列表
interpretation: null,     // Agent2 对结果的解读
```

## 已完成里程碑

### v1.0 — 基础功能（main 分支）
- 单 Agent 架构
- 7 种分析操作
- SSE 流式响应
- ECharts 交互式图表
- 会话管理

### v2.0 — 双 Agent 架构（feature/dual-agent-architecture 分支）
- Agent1 规划调度器 + Agent2 分析顾问
- 操作注册表
- 会话上下文（数据画像 + 分析历史）
- 建议采纳（一键执行）
- 模糊请求快速路由
- LLM 降级容错

## 已知限制

1. `intent_parser.py` 已被 `planner.py` 替代但未删除，可在清理阶段移除
2. 会话上下文持久化使用 JSON 文件读写，无文件锁，不适合高并发
3. 前端 `analyzeSync` 函数为死代码，可移除
4. 测试文件 `test_intent_parser.py` 需要重写为 `test_planner.py`

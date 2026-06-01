# DataVis - 交互式数据分析平台

基于双 Agent 架构的自然语言数据分析平台。用户上传数据集后，通过自然语言描述分析需求，系统由 Agent1（规划调度器）自动识别意图，调度后端执行数据分析，或由 Agent2（分析顾问）提供结构化分析建议。

## 功能特性

- **双 Agent 架构** — Agent1 调度操作/咨询，Agent2 生成可执行分析建议
- **自然语言交互** — 用自然语言描述分析需求，系统自动路由到对应处理流程
- **7 种分析操作** — 概览、趋势、分布、分组对比、相关性、移动平均、季节性分解
- **交互式图表** — 自动生成 ECharts 交互式图表（折线/柱状/散点/热力/饼图等）
- **一键执行建议** — Agent2 建议可直接点击执行，无需重新输入
- **流式响应** — SSE 实时推送图表和文本
- **会话上下文** — 维护数据画像、分析历史，支撑多轮对话
- **降级容错** — LLM 失败时自动降级为本地关键词匹配或模板建议

## 系统架构

```
用户请求 → Agent1（规划调度器）→ JSON 任务计划
  ├─ type: operation  → 后端执行器 → 统计结果 + ECharts 图表
  └─ type: consultation → Agent2（分析顾问）→ 结构化建议列表
→ SSE 流式响应 → 前端渲染
```

**核心原则**：
- Agent1 只负责调度，不生成分析结论
- Agent2 是纯顾问，不调用数据操作，只提供建议
- 所有分析能力预先注册在操作注册表中，两个 Agent 共享

## 技术栈

### 后端
- **FastAPI** — 高性能 Web 框架
- **Pandas / NumPy / SciPy** — 数据处理与统计分析
- **DEEPSEEK API** — LLM 驱动 Agent
- **ECharts** — 图表生成（JSON 配置）

### 前端
- **Vue 3** + **Vite** — 渐进式框架 + 构建工具
- **Pinia** — 状态管理
- **vue-echarts** — 图表渲染

## 项目结构

```
py_final_homework/
├── backend/
│   ├── main.py                     # FastAPI 入口
│   ├── api/
│   │   ├── upload.py               # 文件上传 API
│   │   ├── analysis.py             # 分析 API（双 Agent 流程）
│   │   └── session.py              # 会话管理 API
│   ├── agent/
│   │   ├── llm_client.py           # DEEPSEEK API 客户端
│   │   ├── planner.py              # Agent1 — 规划调度器
│   │   └── advisor.py              # Agent2 — 分析顾问
│   ├── core/
│   │   ├── operations.py           # 操作注册表（7 个操作）
│   │   ├── executor.py             # 操作执行器
│   │   ├── analyzer.py             # 统计分析引擎
│   │   ├── visualizer.py           # 图表生成器
│   │   ├── data_loader.py          # 数据加载器
│   │   └── preprocessor.py         # 数据预处理
│   ├── models/
│   │   ├── schemas.py              # API 数据模型
│   │   └── session_context.py      # 会话上下文模型
│   ├── session/
│   │   └── manager.py              # 会话管理器（含上下文持久化）
│   └── cache/
│       └── cache.py                # 缓存管理器
├── frontend/
│   └── src/
│       ├── App.vue                 # 根组件
│       ├── components/
│       │   ├── ChatPanel.vue       # 对话面板（含建议卡片）
│       │   ├── ChartViewer.vue     # 图表展示
│       │   ├── FileUpload.vue      # 文件上传
│       │   └── ...
│       ├── stores/app.js           # Pinia 状态管理
│       └── api/client.js           # API 客户端（SSE）
├── tests/                          # 测试文件
├── requirements.txt
└── .env                            # 环境变量
```

## 快速开始

### 1. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
cd frontend && npm install
```

### 3. 启动服务

```bash
# 后端
uvicorn backend.main:app --reload

# 前端（新终端）
cd frontend && npm run dev
```

### 4. 访问

- 前端界面: http://localhost:5173
- API 文档: http://localhost:8000/docs

## API 端点

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/upload` | POST | 上传数据文件 |
| `/api/analysis` | POST | 分析请求（SSE，双 Agent 流程） |
| `/api/analysis/execute` | POST | 执行采纳的建议（SSE） |
| `/api/analysis/rechart` | POST | 图表类型切换 |
| `/api/analysis/history/{id}` | GET | 获取聊天历史 |
| `/api/session/{id}` | GET | 检查会话有效性 |
| `/api/sessions` | GET | 列出所有会话 |

## 使用示例

| 场景 | 查询示例 | 路由 |
|------|---------|------|
| 具体分析 | "分析 age 和 fnlwgt 的相关性" | Agent1 → operation |
| 具体分析 | "按 workclass 对比 age，用柱状图" | Agent1 → operation |
| 模糊建议 | "下一步怎么分析" | Agent1 → consultation → Agent2 |
| 混合需求 | "分析趋势，然后建议下一步" | Agent1 → operation + consultation |

## 支持的操作

| 操作 | 说明 | 所需列 |
|------|------|--------|
| `overview` | 数据概览 | 无 |
| `trend` | 趋势分析（线性回归） | 至少 1 个数值列 |
| `distribution` | 分布分析（直方图/箱线图/异常值） | 1 个数值列 |
| `comparison` | 分组对比（含交叉表/ANOVA） | 1 个数值列 + 1 个分类列 |
| `correlation` | 相关性分析（Pearson/Spearman） | 至少 2 个数值列 |
| `moving_avg` | 移动平均（SMA/EMA） | 1 个数值列 |
| `seasonality` | 季节性分解（STL） | 1 个数值列 + 1 个日期列 |

## Git 分支管理

| 分支 | 说明 |
|------|------|
| `main` | 升级前的稳定版本（备份） |
| `feature/dual-agent-architecture` | 双 Agent 架构（当前开发分支） |

## 配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DEEPSEEK_API_KEY` | DEEPSEEK API 密钥（Agent1 规划调度器） | 必填 |
| `DEEPSEEK_API_KEY_2` | DEEPSEEK API 密钥（Agent2 分析顾问） | 可选，未设置时回退使用 `DEEPSEEK_API_KEY` |
| `HOST` | 服务器地址 | 0.0.0.0 |
| `PORT` | 服务器端口 | 8000 |
| `SESSION_EXPIRE_MINUTES` | 会话过期时间 | 30 |

## 开发

```bash
python -m pytest tests/
```

## 许可证

MIT License

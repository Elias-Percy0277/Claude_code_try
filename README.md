# DataVis - 交互式数据分析平台

一个基于自然语言驱动的数据分析平台，用户上传数据集后，可通过自然语言描述分析需求，系统自动拆解需求、执行数据处理与可视化，并生成智能回复。

## 功能特性

- **🗣️ 自然语言交互** - 用自然语言描述分析需求，系统自动识别意图
- **📊 多种分析类型** - 支持趋势分析、相关性分析、分布分析、分组对比等
- **📈 可视化图表** - 自动生成 ECharts 交互式图表
- **🤖 AI 驱动** - 集成 DEEPSEEK API 进行智能意图识别
- **🔄 流式响应** - SSE 流式返回，先展示图表，文本流式补齐
- **💾 智能缓存** - 相同查询直接返回缓存结果
- **📁 会话管理** - 数据隔离，支持多会话并发

## 技术栈

### 后端
- **FastAPI** - 高性能 Web 框架
- **Pandas** - 数据处理
- **Pyecharts** - 图表生成（ECharts JSON）
- **DEEPSEEK API** - LLM 意图识别
- **Pinia** - 状态管理（会话、缓存）

### 前端
- **Vue 3** - 渐进式框架
- **Vite** - 构建工具
- **Pinia** - 状态管理
- **vue-echarts** - 图表渲染
- **Axios** - HTTP 客户端

## 项目结构

```
py_final_homework/
├── backend/
│   ├── main.py                 # FastAPI 入口
│   ├── api/
│   │   ├── upload.py           # 文件上传 API
│   │   ├── analysis.py         # 分析请求 API (SSE)
│   │   └── session.py          # 会话管理 API
│   ├── core/
│   │   ├── data_loader.py      # 数据加载器
│   │   ├── preprocessor.py     # 数据预处理
│   │   ├── analyzer.py         # 分析引擎
│   │   ├── intent_parser.py    # 意图解析 (LLM + 规则)
│   │   └── visualizer.py       # 可视化生成器
│   ├── agent/
│   │   └── llm_client.py       # DEEPSEEK API 客户端
│   ├── session/
│   │   └── manager.py          # 会话管理器
│   ├── cache/
│   │   └── cache.py            # 缓存管理器
│   └── models/
│       └── schemas.py          # Pydantic 数据模型
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── main.js
│       ├── App.vue
│       ├── stores/app.js
│       ├── api/client.js
│       └── components/
│           ├── FileUpload.vue
│           ├── ChatPanel.vue
│           ├── ChartViewer.vue
│           └── ErrorMessage.vue
├── sessions/                   # 会话存储目录
├── tests/                      # 测试文件
├── .env                        # 环境变量配置
├── requirements.txt            # Python 依赖
└── README.md
```

## 快速开始

### 1. 克隆项目

```bash
git clone <repository-url>
cd py_final_homework
```

### 2. 配置环境变量

```bash
# 复制配置模板
cp .env.example .env

# 编辑 .env，填入你的 DEEPSEEK API Key
# 获取 API Key: https://platform.deepseek.com/
```

### 3. 安装依赖

```bash
# 安装 Python 依赖
pip install -r requirements.txt

# 安装前端依赖
cd frontend
npm install
```

### 4. 启动服务

**启动后端服务器：**
```bash
uvicorn backend.main:app --reload
```

**启动前端服务器（新终端）：**
```bash
cd frontend
npm run dev
```

### 5. 访问应用

- **前端界面**: http://localhost:5173
- **API 文档**: http://localhost:8000/docs

## 使用示例

### 1. 上传数据

支持 CSV、Excel (.xlsx, .xls)、JSON 格式文件，最大 60MB。

### 2. 自然语言查询

支持的查询示例：

| 查询类型 | 示例 |
|----------|------|
| 数据概览 | "看看数据概览"、"数据有什么" |
| 趋势分析 | "分析销售额趋势"、"利润变化趋势" |
| 相关性 | "销售额和利润的相关性" |
| 分组对比 | "各地区的销售额对比" |
| 分布分析 | "销售额的分布情况" |
| 移动平均 | "计算销售额的7天移动平均" |

## API 端点

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/upload` | POST | 上传数据文件 |
| `/api/analysis` | POST | 分析请求（SSE 流式） |
| `/api/session/{id}` | GET | 检查会话有效性 |
| `/api/sessions` | GET | 列出所有会话 |
| `/api/sessions/cleanup` | POST | 清理过期会话 |

## 配置说明

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DEEPSEEK_API_KEY` | DEEPSEEK API 密钥 | 必填 |
| `HOST` | 服务器地址 | 0.0.0.0 |
| `PORT` | 服务器端口 | 8000 |
| `SESSION_EXPIRE_MINUTES` | 会话过期时间 | 30 |
| `MAX_CACHE_SIZE` | 最大缓存数 | 100 |

### 文件上传限制

- 文件大小：最大 60MB
- 支持格式：`.csv`, `.xlsx`, `.json`, `.xls`

## 开发

### 运行测试

```bash
# 运行所有测试
python -m pytest tests/

# 运行特定模块测试
python tests/test_data_loader.py
python tests/test_analyzer.py
python tests/test_cache.py
python tests/test_session.py
```

### 代码规范

- Python: 遵循 PEP 8
- JavaScript: 遵循 ESLint 默认规则
- 提交信息: 遵循 Conventional Commits

## 注意事项

1. **DEEPSEEK API Key** - 请妥善保管，不要提交到版本控制
2. **会话数据** - 存储在 `sessions/` 目录，会自动清理过期会话
3. **CORS 配置** - 生产环境需修改 `ALLOWED_ORIGINS`

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！

# DataVis - 交互式数据分析平台

一个基于自然语言驱动的数据分析平台，用户上传数据集后，可通过自然语言描述分析需求，系统自动拆解需求、执行数据处理与可视化，并生成智能回复。同时集成了机器学习建模、公平性审计和微信 AI 托管功能。

## 功能特性

### 数据分析
- **🗣️ 自然语言交互** - 用自然语言描述分析需求，系统自动识别意图
- **📊 多种分析类型** - 支持趋势分析、相关性分析、分布分析、分组对比、移动平均、季节性分解、分类关联分析
- **📈 可视化图表** - 自动生成 ECharts 交互式图表（折线、柱状、散点、饼图、热力图、雷达图、箱线图等）
- **🔄 图表切换** - 支持运行时切换图表类型（bar/line/pie/scatter/area/radar/boxplot/histogram）
- **🤖 AI 驱动** - 集成 DEEPSEEK API 进行智能意图识别和分析解读
- **🔄 流式响应** - SSE 流式返回，先展示图表，文本流式补齐
- **💬 聊天历史** - 持久化聊天记录，支持多轮对话上下文
- **💾 智能缓存** - 相同查询直接返回缓存结果
- **📁 多数据集管理** - 支持一个会话中添加多个数据集（最多 10 个）
- **📂 会话管理** - 数据隔离，支持多会话并发、会话切换、重命名

### 机器学习（Adult Income 数据集）
- **🔧 模型训练** - 支持逻辑回归和随机森林，自动特征工程
- **📊 模型评估** - 准确率、精确率、召回率、F1、ROC-AUC、PR-AUC、混淆矩阵
- **🔍 特征重要性** - 自动排序并可视化 Top-N 特征
- **⚖️ 公平性审计** - 按敏感属性（性别、种族等）分组评估 TPR/FPR 差异
- **📉 交叉验证** - 5 折交叉验证，多模型对比并推荐最优

### 微信 AI 托管（wechat_agent）
- **📱 自动回复** - 基于白名单自动回复微信私聊消息
- **🧠 本地 AI** - 使用 Ollama + qwen2.5 模型
- **🎭 风格学习** - 支持从聊天记录学习个人说话风格
- **🖥️ 网页后台** - Flask 管理后台（端口 5001）
- **📌 系统托盘** - 支持暂停/恢复，最小化到托盘
- **🎯 模板检测** - 坐标模板快速检测（低 CPU 占用），OCR 作为补充

## 技术栈

### 后端
- **FastAPI** - 高性能 Web 框架
- **Pandas / NumPy** - 数据处理
- **Pyecharts** - 图表生成（ECharts JSON）
- **scikit-learn** - 机器学习（模型训练、评估、公平性审计）
- **statsmodels / SciPy** - 统计分析、季节性分解
- **DEEPSEEK API** - LLM 意图识别与智能分析
- **Pydantic** - 数据模型验证
- **httpx** - 异步 HTTP 客户端
- **SQLAlchemy** - 数据库（wechat_agent）
- **APScheduler** - 定时任务调度
- **colorama** - Windows 终端彩色输出

### 前端
- **Vue 3** - 渐进式框架
- **Vite** - 构建工具
- **Pinia** - 状态管理（会话、缓存、聊天历史）
- **vue-echarts / ECharts** - 图表渲染
- **Axios** - HTTP 客户端
- **Marked** - Markdown 渲染

## 项目结构

```
py_final_homework/
├── backend/
│   ├── main.py                    # FastAPI 入口，应用配置
│   ├── api/
│   │   ├── upload.py              # 文件上传 API（多文件、多数据集）
│   │   ├── analysis.py            # 分析请求 API（SSE 流式 + 同步）
│   │   └── session.py             # 会话管理 API（CRUD + 统计）
│   ├── core/
│   │   ├── data_loader.py         # 数据加载器（CSV/Excel/JSON/.data/.names/.index）
│   │   ├── preprocessor.py        # 数据预处理
│   │   ├── analyzer.py            # 分析引擎（统计/趋势/相关/分布/对比/移动平均/季节性）
│   │   ├── intent_parser.py       # 意图解析（LLM + 规则混合）
│   │   ├── visualizer.py          # 可视化生成器（ECharts JSON）
│   │   ├── ml_engine.py           # 机器学习引擎（模型训练/评估/公平性/交叉验证）
│   │   ├── logger_config.py       # 日志配置（彩色控制台 + 文件 + JSON）
│   │   └── logging_middleware.py  # 请求日志中间件
│   ├── agent/
│   │   └── llm_client.py          # DEEPSEEK API 客户端（同步/异步/流式）
│   ├── session/
│   │   └── manager.py             # 会话管理器（多数据集、聊天历史持久化）
│   ├── cache/
│   │   └── cache.py               # 缓存管理器
│   └── models/
│       └── schemas.py             # Pydantic 数据模型
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── main.js
│       ├── App.vue                # 主应用（三栏布局）
│       ├── stores/app.js          # Pinia 状态管理
│       ├── api/client.js          # API 客户端（含 SSE 流式）
│       └── components/
│           ├── FileUpload.vue     # 文件上传组件
│           ├── ChatPanel.vue      # 聊天面板
│           ├── ChartViewer.vue    # 图表查看器
│           ├── SessionSidebar.vue # 会话侧边栏
│           └── ErrorMessage.vue   # 错误提示
├── wechat_agent/                  # 微信 AI 托管子项目
│   ├── main.py                    # 微信托管入口
│   ├── config/                    # 配置模块
│   ├── core/                      # 核心功能（微信客户端、AI引擎、模板检测）
│   ├── storage/                   # 数据存储（SQLite）
│   ├── web/                       # Flask 网页管理后台
│   ├── tray/                      # 系统托盘
│   ├── utils/                     # 工具函数（校准、日志）
│   └── data/                      # 数据目录
├── data/                          # 示例数据目录
├── output/                        # 输出目录
├── sessions/                      # 会话存储目录
├── logs/                          # 日志目录
├── tests/                         # 测试文件
│   ├── test_analyzer.py
│   ├── test_cache.py
│   ├── test_data_loader.py
│   ├── test_intent_parser.py
│   ├── test_session.py
│   ├── test_visualizer.py
│   └── fixtures/                  # 测试数据
├── .env                           # 环境变量配置
├── .env.example                   # 环境变量模板
├── requirements.txt               # Python 依赖
├── start.bat                      # 一键启动脚本
├── start-backend.bat              # 单独启动后端
├── start-frontend.bat             # 单独启动前端
├── start-debug.bat                # 调试模式启动
├── install.bat                    # 一键安装依赖
├── poster.png                     # 项目海报
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
# 安装 Python 依赖（建议使用 conda 虚拟环境）
conda create -n datavis python=3.10
conda activate datavis
pip install -r requirements.txt

# 安装前端依赖
cd frontend
npm install
```

### 4. 启动服务

**方式一：一键启动（Windows）**
```bash
# 双击 start.bat 或运行：
start.bat
```

**方式二：手动启动**

启动后端服务器：
```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

启动前端服务器（新终端）：
```bash
cd frontend
npm run dev
```

### 5. 访问应用

- **前端界面**: http://localhost:5173
- **API 文档**: http://localhost:8000/docs
- **健康检查**: http://localhost:8000/health

## 使用示例

### 1. 上传数据

支持多种格式：CSV、Excel (.xlsx, .xls)、JSON、UCI 格式 (.data, .test, .names, .index)，最大 60MB。

支持多文件同时上传，系统自动识别 `.names` 元数据文件并与 `.data` 文件关联。

### 2. 自然语言查询

| 查询类型 | 示例 |
|----------|------|
| 数据概览 | "看看数据概览"、"数据有什么" |
| 趋势分析 | "分析销售额趋势"、"利润变化趋势" |
| 相关性 | "销售额和利润的相关性" |
| 分组对比 | "各地区的销售额对比" |
| 分布分析 | "销售额的分布情况" |
| 移动平均 | "计算销售额的7天移动平均" |
| 季节性分解 | "对销售额做季节性分解" |
| 分类关联 | "各分类列之间的关联分析" |
| 模型训练 | "训练模型"、"用随机森林训练" |
| 模型评估 | "评估模型效果" |
| 特征重要性 | "哪些特征最重要" |
| 公平性审计 | "模型的公平性分析" |
| 交叉验证 | "对比不同模型的效果" |

## API 端点

### 数据上传
| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/upload` | POST | 上传数据文件（支持多文件） |
| `/api/session/{id}/dataset/{did}` | DELETE | 从会话中删除数据集 |

### 分析请求
| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/analysis` | POST | 分析请求（SSE 流式响应） |
| `/api/analysis/sync` | POST | 分析请求（同步响应，调试用） |
| `/api/analysis/history/{id}` | GET | 获取会话聊天历史 |
| `/api/analysis/rechart` | POST | 切换图表类型 |

### 会话管理
| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/session/{id}` | GET | 检查会话有效性 |
| `/api/session/{id}` | DELETE | 删除会话 |
| `/api/session/{id}` | PATCH | 重命名会话 |
| `/api/sessions` | GET | 列出所有会话 |
| `/api/sessions/stats` | GET | 获取会话统计信息 |
| `/api/sessions/cleanup` | POST | 清理过期会话 |

### 系统
| 端点 | 方法 | 功能 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/` | GET | 根路径 |

## 配置说明

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DEEPSEEK_API_KEY` | DEEPSEEK API 密钥 | 必填 |
| `HOST` | 服务器地址 | 0.0.0.0 |
| `PORT` | 服务器端口 | 8000 |
| `DEBUG` | 调试模式 | False |
| `ALLOWED_ORIGINS` | CORS 允许的来源 | localhost:5173 |
| `SESSION_EXPIRE_MINUTES` | 会话过期时间 | 30 |
| `MAX_CACHE_SIZE` | 最大缓存数 | 100 |

### 文件上传限制

- 文件大小：最大 60MB
- 支持格式：`.csv`, `.xlsx`, `.xls`, `.json`, `.data`, `.test`, `.names`, `.index`
- 每个会话最多 10 个数据集

## 开发

### 运行测试

```bash
# 运行所有测试
python -m pytest tests/

# 运行特定模块测试
python tests/test_analyzer.py
python tests/test_cache.py
python tests/test_data_loader.py
python tests/test_intent_parser.py
python tests/test_session.py
python tests/test_visualizer.py
```

### 代码规范

- Python: 遵循 PEP 8
- JavaScript: 遵循 ESLint 默认规则
- 提交信息: 遵循 Conventional Commits

### 日志系统

日志文件存储在 `logs/` 目录下：
- `datavis_YYYYMMDD.log` - 主日志（纯文本）
- `errors.log` - 错误日志
- `datavis_json.log` - JSON 格式日志（便于机器分析）

控制台输出支持彩色显示（Windows 下使用 colorama）。

## 注意事项

1. **DEEPSEEK API Key** - 请妥善保管，不要提交到版本控制
2. **会话数据** - 存储在 `sessions/` 目录，会自动清理过期会话
3. **CORS 配置** - 生产环境需修改 `ALLOWED_ORIGINS`
4. **ML 功能** - 依赖 scikit-learn，如未安装则 ML 相关功能不可用
5. **季节性分解** - 依赖 statsmodels，如未安装则季节性分解功能不可用
6. **微信托管** - wechat_agent 为独立子项目，需单独安装和配置，详见 `wechat_agent/README.md`

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！

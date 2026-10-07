# DataVis — 自然语言驱动的交互式数据分析平台

一个用**自然语言对话**即可完成数据分析、可视化与机器学习建模的 Web 平台。
用户上传数据集后，用一句话描述需求（如「按性别对比收入分布」「公平性审计」），
系统自动识别意图、执行真实统计/机器学习计算、生成 ECharts 交互图表，
并以 SSE 流式方式返回 AI 解读。

> 本项目为 Python 课程期末作业。所有统计与模型指标均由 Python / scikit-learn 实际计算得出，
> 大语言模型（DeepSeek）仅负责**意图识别**与**结果解读**，不参与数值计算。

---

## 一、项目简介

### 1.1 选题背景

传统数据分析门槛较高：使用者需要掌握 SQL / Pandas / 统计学知识，
还要手动编写绘图代码，非专业用户难以快速从数据中获取洞见。
近年来大语言模型（LLM）的成熟，让「用自然语言完成数据分析」成为可能。

本项目尝试构建一个端到端的**对话式数据分析平台**：
把「数据加载 → 意图理解 → 统计计算 → 可视化 → 智能解读」全流程串联起来，
让不具备编程基础的用户也能完成专业的数据分析与建模。

### 1.2 分析目标

以经典的 **UCI Adult Income（人口收入）数据集**为载体，目标包括：

1. **探索性数据分析（EDA）**：数据概览、目标变量分布、数值/分类特征分布、相关性分析；
2. **关联分析**：数值特征 Pearson 相关、分类特征 Cramér's V 关联、收入按敏感属性（性别/种族）分组差异；
3. **机器学习建模**：逻辑回归 vs 随机森林，预测个人年收入是否 >50K；
4. **模型评估与对比**：准确率/F1/ROC-AUC/PR-AUC/混淆矩阵、5 折交叉验证；
5. **可解释性与公平性**：特征重要性排序、按性别/种族分组的 TPR/FPR 公平性审计。

### 1.3 数据集

| 项目 | 内容 |
|------|------|
| 名称 | Census Income（Adult） |
| 来源 | UCI Machine Learning Repository |
| **原始链接** | <https://archive.ics.uci.edu/dataset/20/census+income> |
| 规模 | 约 48842 条记录，14 个属性 + 1 个目标变量（收入是否 >50K） |
| 背景 | 1994 年美国人口普查抽取数据，用于预测个人年收入是否超过 5 万美元 |
| 关键属性 | age（年龄）、workclass（工作类别）、education-num（教育年限）、occupation（职业）、hours-per-week（周工时）、capital-gain/loss（资本收益/损失）、sex（性别）、race（种族） |

> 说明：本作业阶段聚焦单一公开数据集（Adult）完成端到端分析，未额外划分子集。
> 平台本身支持任意 CSV / Excel / JSON / UCI 格式（.data/.test/.names）数据上传分析。

---

## 二、技术方案

### 2.1 技术栈

| 层 | 技术 | 用途 |
|----|------|------|
| 后端框架 | FastAPI + Uvicorn | 高性能异步 Web 框架，提供 REST API 与自动文档 |
| 数据处理 | pandas / NumPy | 数据加载、清洗、分组统计、交叉表 |
| 统计分析 | SciPy / statsmodels | 统计检验、时间序列季节性分解 |
| 可视化 | pyecharts（ECharts） | 后端生成图表 JSON，前端交互渲染 |
| 机器学习 | scikit-learn | 模型训练、评估、特征重要性、公平性审计、交叉验证 |
| LLM 接入 | httpx + DeepSeek API | 异步调用大模型完成意图识别与结果解读 |
| 数据校验 | Pydantic | 请求/响应模型定义与校验 |
| 持久化 | pyarrow（Parquet） | 数据集与会话状态序列化存储 |
| 前端框架 | Vue 3 + Vite | 渐进式前端框架与构建工具 |
| 状态管理 | Pinia | 会话、缓存、聊天历史状态 |
| 图表渲染 | vue-echarts / ECharts | 前端图表渲染 |
| HTTP | Axios | 前端请求与 SSE 流式处理 |

### 2.2 分析思路（整体架构）

```
用户输入自然语言查询
        │
        ▼
┌───────────────────┐
│ 1. 会话校验 + 缓存 │  ← 命中缓存直接回放结果
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ 2. 意图解析        │  ← LLM + 规则混合：把一句话拆成若干分析任务(task)
│  (intent_parser)  │     识别 分析类型/目标列/分组列/图表类型
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ 3. 执行分析        │  ← pandas 统计 / scikit-learn 建模，真实计算
│  (analyzer/ml)    │     产出 statistics 数据
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ 4. 可视化生成      │  ← pyecharts 把统计结果转成 ECharts JSON
│  (visualizer)     │     SSE 先推送 charts（图表立即可见）
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ 5. LLM 流式解读    │  ← 把统计结果 + 数据集上下文 + 聊天历史喂给 DeepSeek
│  (llm_client)     │     流式逐字返回 Markdown 解读
└───────────────────┘
        │
        ▼
  缓存结果 + 写入聊天历史 → 结束
```

**核心理念**：计算与解读分离——所有数字由确定性 Python 代码算出（可复现、不幻觉），
LLM 只做语言层面的意图理解与自然语言总结。

### 2.3 核心模块

| 模块 | 职责 |
|------|------|
| `core/data_loader.py` | 多格式数据加载（CSV/Excel/JSON/UCI），自动识别 `.names` 元数据 |
| `core/preprocessor.py` | 数据预处理（缺失值、类型推断、异常值） |
| `core/intent_parser.py` | 意图解析（LLM + 规则混合） |
| `core/analyzer.py` | 统计分析引擎（概览/趋势/相关/分布/对比/移动平均/季节性） |
| `core/ml_engine.py` | 机器学习引擎（训练/评估/特征重要性/公平性/交叉验证） |
| `core/visualizer.py` | 可视化生成器（ECharts JSON） |
| `agent/llm_client.py` | DeepSeek API 客户端（同步/异步/流式） |
| `session/manager.py` | 会话管理（多数据集、聊天历史、ML 状态持久化） |
| `cache/cache.py` | 查询结果智能缓存 |
| `api/analysis.py` | SSE 流式分析接口（核心入口） |

---

## 三、分析结果（基于 Adult 数据集）

> 以下结论均可由平台通过自然语言查询复现，数值来自 Python / scikit-learn 真实计算。

### 3.1 关键发现

1. **类别不平衡**：目标变量中约 76% 为 `<=50K`，仅约 24% 为 `>50K`，
   训练时需采用分层抽样与 `class_weight='balanced'` 以避免模型偏向多数类。

2. **收入与个人属性强相关**：教育年限（education-num）、年龄（age）、
   每周工时（hours-per-week）与高收入呈正相关。

3. **资本收益是强预测因子**：`capital-gain` 虽大量为零，
   但在随机森林特征重要性中通常位列前茅——非零的资本收益强烈指向高收入。

4. **性别差距**：男性中 `>50K` 的比例显著高于女性，
   反映在分组对比的归一化柱状图中。

5. **种族差距**：不同种族间高收入占比存在差异，
   公平性审计可量化这种差异。

6. **公平性风险**：模型在不同性别/种族分组上的 TPR（真正率）、
   FPR（假阳性率）存在差异（gap > 0.1 时系统自动告警），
   提示模型可能存在偏向性。

### 3.2 可视化图表说明

平台可根据查询自动生成并支持运行时切换以下图表类型：

| 图表 | 用途 |
|------|------|
| 饼图 | 目标变量 `>50K / <=50K` 占比，直观展示类别不平衡 |
| 直方图 / 箱线图 | 数值特征（age、hours-per-week 等）的分布、异常值 |
| 频数柱状图 | 分类特征（occupation、workclass 等）的频次分布 |
| 相关性热力图 | 数值特征 Pearson 相关系数矩阵 |
| Cramér's V 热力图 | 分类特征之间的关联强度 |
| 堆叠/归一化柱状图 | 收入按性别、种族分组的占比对比（公平性可视化） |
| 混淆矩阵 | 模型预测的 TP/FP/FN/TN 分布 |
| ROC 曲线 | 模型分类性能（AUC） |
| 特征重要性柱状图 | 随机森林 Top-N 重要特征排序 |
| 公平性分组柱状图 | 各敏感属性分组的 TPR/FPR 对比 |

---

## 四、总结与反思

### 4.1 遇到的问题与解决过程

1. **SSE 流式响应被缓冲，图表迟迟不显示**
   问题：uvicorn 默认会缓冲 SSE 数据块，导致前端要等全部生成完才一次性显示。
   解决：实现 `_flushing_sse_wrapper`，在每个数据块 yield 后 `await asyncio.sleep(0)`
   主动让出事件循环，强制服务器立即刷新到网络，实现「先出图、文本逐字补齐」。

2. **多轮对话到第三轮卡住**
   问题：前端 `handleSendMessage` 中 `await` 阻塞了整个函数，导致后续消息无法发送。
   解决：将分析调用改为非阻塞（后台执行 + `.catch()` 兜底），并加入 SSE 超时保护（180s 无数据自动终止）。

3. **图表关闭后无法重新打开**
   问题：ChartViewer 用 `v-if` 控制，关闭时 ECharts 实例被销毁，再次打开初始化失败。
   解决：改用 `v-show` + `chartsVisible` 状态，保留 ECharts 实例不销毁。

4. **ML 模型状态无法跨请求保留**
   问题：训练与评估是两次独立请求，模型对象不能直接传递。
   解决：通过 `session_manager` 把模型状态序列化保存到会话，评估时再反序列化恢复。

5. **类别不平衡影响模型**
   问题：约 76% 为负类，模型容易全预测为 `<=50K`。
   解决：80/20 分层拆分 + `class_weight='balanced'`，并关注 F1/PR-AUC 而非单纯准确率。

6. **DeepSeek 偶尔返回非结构化文本**
   问题：LLM 未按预期返回结构化意图 JSON。
   解决：设置 `raw_response` 降级路径直接展示原文，同时保留规则匹配兜底。

### 4.2 局限与改进方向

- 公平性审计目前针对 Adult 数据集的 sex/race 固定属性，通用化需自动检测敏感属性；
- 缓存基于「会话+查询+文件哈希」，对相似表述的不同问法无法去重；
- 前端图表类型较多，部分图表在特殊数据分布下可读性有限，可进一步智能推荐。

---

## 五、AI 使用声明

### 5.1 整体使用情况

- **AI 代码贡献比例：约 98% 及以上**。项目绝大部分代码（后端引擎、API、前端组件、注释、文档）
  由 AI 辅助生成或修改。
- **使用工具**：Claude（Anthropic 的 Claude 模型，通过 Claude Code CLI 调用）。
- **使用方式**：依据 `research_plan.md` 中规划的六阶段分析步骤
  （探索性数据分析 → 关联分析 → 特征工程 → 建模与交叉验证 → 可解释性与公平性 → 报告与结论），
  **将每个分析问题拆解为独立提问，逐个推进**，由 AI对用户需求进行分析并生成对应json文件进一步进行后端分析；
  人工负责选题方向、需求拆解、分析计划制定、运行结果校验与少量逻辑修改。

### 5.2 函数级标注规范

代码中所有由 AI 辅助生成或修改的关键函数 / 代码块，均在定义前以注释形式标注，
格式示例：

```python
# AI-assisted: 使用 Claude 生成初始框架，手动调整了数据过滤逻辑
def analyze_overview(df):
    ...
```

```python
# AI-assisted: 使用 Claude 补全此可视化函数，调整了配色与坐标轴
def create_correlation_heatmap(matrix, columns, title):
    ...
```

标注覆盖范围：
- **后端核心模块**：`data_loader` / `preprocessor` / `analyzer` / `intent_parser` /
  `ml_engine` / `visualizer` / `session/manager` / `llm_client` / `cache` / `api`(upload, analysis, session)；
- **前端核心组件**：`App.vue` / `ChartViewer.vue` / `ChatPanel.vue` /
  `FileUpload.vue` / `SessionSidebar.vue` / `stores/app.js` / `api/client.js`。

### 5.3 人机分工

| 角色 | 工作 |
|------|------|
| AI（Claude） | 初始代码框架、算法实现、函数补全、注释与文档撰写 |
| 人工 | 选题与目标定义、分析计划（`research_plan.md`）、提问拆解、结果验证、问题定位与调试方向把控、最终审阅 |

---

## 六、快速开始

### 6.1 环境准备

```bash
# 建议使用 conda 虚拟环境（Python 3.10）
conda create -n datavis python=3.10
conda activate datavis

# 安装后端依赖
pip install -r requirements.txt

# 安装前端依赖
cd frontend
npm install
```

### 6.2 配置

复制 `.env.example` 为 `.env`，填入 DeepSeek API Key（获取：<https://platform.deepseek.com/>）：

```bash
DEEPSEEK_API_KEY=your_key_here
```

### 6.3 启动

```bash
# 方式一：一键启动（Windows）
start.bat

# 方式二：手动分别启动
# 后端
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
# 前端（新终端）
cd frontend && npm run dev
```

访问：
- 前端界面：<http://localhost:5173>
- API 文档：<http://localhost:8000/docs>
- 健康检查：<http://localhost:8000/health>

---

## 七、项目结构

```
py_final_homework/
├── backend/                     # 后端（FastAPI）
│   ├── main.py                  # 应用入口
│   ├── api/                     # 路由层（upload / analysis / session）
│   ├── core/                    # 核心引擎（加载/预处理/分析/ML/可视化/意图/日志）
│   ├── agent/                   # DeepSeek LLM 客户端
│   ├── session/                 # 会话管理（持久化）
│   ├── cache/                   # 查询缓存
│   └── models/                  # Pydantic 数据模型
├── frontend/                    # 前端（Vue 3 + Vite）
│   └── src/
│       ├── App.vue              # 主应用（三栏布局）
│       ├── components/          # 组件（上传/聊天/图表/侧边栏/错误）
│       ├── stores/app.js        # Pinia 状态管理
│       └── api/client.js        # API 客户端（含 SSE 流式）
├── py_final_homework_database/  # Adult 数据集（.data/.test/.names）
├── tests/                       # 测试
├── sessions/                    # 会话存储（运行时生成）
├── logs/                        # 日志（运行时生成）
├── research_plan.md             # 分析计划（六阶段，AI 使用的提问依据）
├── requirements.txt             # Python 依赖
├── .env.example                 # 环境变量模板
└── README.md
```

## 八、许可证

MIT License

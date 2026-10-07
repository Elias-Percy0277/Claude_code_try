# Claude Code 项目配置

本项目使用 Claude Code 进行开发。

## 项目概述

**项目名称**: wechat_custody - 微信托管/监控工具

**项目路径**: `E:\claude_code_project_try\wechat_custody`

**项目描述**: 使用本地 AI 模型（Ollama + qwen2.5）自动回复微信私聊消息。

## 开发规范

### 代码风格
- Python 3.12
- 遵循 PEP 8 规范
- 使用类型注解

### 提交规范
- 提交信息使用中文
- 描述清晰，说明改动目的

## 项目结构

```
wechat_custody/
├── core/              # 核心模块
│   ├── ai_engine.py   # AI 引擎
│   ├── personality.py # 个性配置
│   ├── yolo_detector.py # YOLO 检测器
│   ├── contact_scanner.py # 联系人扫描器
│   ├── username_validator.py # 用户名验证器
│   └── wechat_client.py # 微信客户端
├── config/            # 配置文件
├── data/              # 数据目录
│   ├── dataset/       # 训练数据集
│   │   └── yolo/      # YOLO 格式数据集
│   ├── logs/          # 日志文件
│   └── models/        # 模型文件
├── storage/           # 数据存储
├── tests/             # 测试文件
├── training/          # 训练脚本
├── tray/              # 托盘图标
├── utils/             # 工具函数
├── env/               # Conda 环境 (Python 3.12.13)
├── web/               # Web 界面
└── runs/              # 训练运行输出
```

## YOLO 训练

### 检测类别 (5类)
- `bubble_other`: 对方消息气泡
- `bubble_own`: 自己消息气泡
- `red_dot`: 新消息红点
- `contact_item`: 联系人列表项
- `chat_title`: 聊天窗口标题

### 训练配置
- **模型**: YOLOv8s
- **数据集**: `data/dataset/yolo/`
- **训练集**: 391 张图片
- **验证集**: 172 张图片

### 当前训练状态
- **已完成**: 5/50 epochs
- **最佳模型**: Epoch 4 (mAP50=0.221)
- **模型路径**: `runs/detect/train_cpu_v2/weights/best.pt`
- 详细记录见: `TRAINING_PROGRESS.md`

## 常用命令

### 虚拟环境

本项目使用 conda 虚拟环境（Python 3.12.13，位于 `env/` 目录）。

```bash
# 激活环境（Windows）
conda activate E:\claude_code_project_try\wechat_custody\env

# 或直接使用环境中的 Python
env\python.exe <command>

# 安装依赖
env\Scripts\pip install -r requirements.txt
```

### 运行 YOLO 检测
```python
from core.yolo_detector import create_detector

detector = create_detector()
detections = detector.detect(image)
```

### 训练 YOLO 模型

```bash
# GPU 训练（推荐，RTX 5070 支持）
env\python.exe training/train_yolo.py

# CPU 训练
env\python.exe training/train_cpu.py
```

## 硬件环境

- **CPU**: Intel Core i9-13900HX
- **GPU**: NVIDIA GeForce RTX 5070 Laptop (8151 MB)
- **AI**: 本地运行 Ollama + qwen2.5 模型

### 软件环境
- **Python**: 3.12.13 (conda)
- **PyTorch**: 2.12.0.dev20260403+cu128 (Nightly, 支持 RTX 5070)
- **CUDA**: 12.4 / 12.8
- **ultralytics**: 8.4.33

## 工作规范

### 自动报告要求

以下任务会每 5 分钟自动报告一次进度（**可由用户随时暂停**）：

1. **模型训练**: YOLO 训练过程
2. **包安装**: pip/conda 安装大型包
3. **长时间运行的任务**: 超过 5 分钟的操作

### 报告内容要求
- 当前进度/阶段
- 完成百分比（如可用）
- 预计剩余时间
- 任何错误或警告
- 下一步行动

### 用户控制
- 用户可随时暂停/恢复自动报告
- 通过命令 `/clear` 清除定时任务

### 代码测试规范

**重要**: 每次完成编写代码后，自动运行测试并向用户报告结果。

#### 测试要求
- 运行相关测试用例
- 报告测试结果（通过/失败）
- 如有失败，显示错误信息
- 建议修复方案（如适用）

#### 测试命令
```bash
# 运行所有测试
pytest tests/

# 运行特定测试
pytest tests/test_yolo_detector.py

# 运行联系人扫描器测试
pytest tests/test_contact_scanner.py
```

---

## 注意事项

### 环境要求
- Windows 10/11
- Python 3.12.13（已包含在项目 conda 环境中）
- 微信 PC 客户端
- Ollama + qwen2.5 模型（用于 AI 回复）

### GPU 支持
- 项目已安装 PyTorch Nightly 版本，支持 RTX 5070 GPU
- CUDA 自动检测并可用
- 训练时默认使用 GPU（如无 GPU 可自动切换到 CPU）

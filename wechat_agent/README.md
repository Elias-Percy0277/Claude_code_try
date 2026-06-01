# wechat_custody

微信 AI 托管服务 - 使用本地 AI 模型自动回复微信私聊消息

## 功能特性

- 自动回复微信私聊消息（基于白名单）
- 使用本地 Ollama 模型（qwen2.5）
- **坐标模板快速检测**（优化性能，低 CPU 占用）
- 支持从聊天记录学习你的说话风格
- 按联系人设置不同 AI 人设
- 网页管理后台（5001 端口）
- 系统托盘应用，支持暂停/恢复
- 对话上下文持久化保存

## 环境要求

- Windows 10/11
- Python 3.10+
- 微信 PC 客户端（推荐 4.x 版本）
- Ollama + qwen2.5 模型

## 安装

```bash
# 1. 创建虚拟环境（重要！）
python -m venv venv

# 2. 激活虚拟环境
venv\Scripts\activate

# 3. 安装依赖（必须在虚拟环境中安装）
pip install -r requirements.txt

# 4. 确保 Ollama 正在运行
ollama serve

# 5. 启动程序（使用虚拟环境中的 Python）
python main.py
```

**⚠️ 重要提示**：
- **必须使用虚拟环境**，不要直接安装到全局 Python
- 每次启动前先激活虚拟环境：`venv\Scripts\activate`
- 或使用虚拟环境中的 Python 直接运行：`venv\Scripts\python.exe main.py`

## 消息检测模式

项目支持三种消息检测模式，可在 `config/settings.json` 中配置：

| 模式 | 说明 | 速度 | CPU 占用 |
|------|------|------|----------|
| `hybrid` | 模板检测 + OCR（推荐） | 快 | 低 |
| `template` | 纯模板检测 | 最快 | 最低 |
| `ocr_only` | 纯 OCR 检测 | 慢 | 高 |

```json
{
  "wechat": {
    "detection_mode": "hybrid",
    "poll_interval": 3
  }
}
```

## 模板校准

首次使用建议运行校准工具，验证模板区域是否正确：

```bash
# 方式1：双击运行
calibrate.bat

# 方式2：命令行运行
python utils/calibrate_template.py
```

校准工具会：
1. 连接微信窗口
2. 截取当前界面
3. 在图像上标注各检测区域
4. 保存校准结果到 `data/template_calibration.png`

如果检测区域不准确，可修改 `core/template_detector.py` 中的模板参数。

## 使用说明

1. 首次运行会自动创建数据库
2. 打开网页后台 `http://localhost:5001`
3. 添加白名单联系人
4. 上传聊天记录以学习说话风格（可选）
5. 开始自动回复

## 项目结构

```
wechat_custody/
├── main.py                      # 程序入口
├── config/                      # 配置模块
├── core/                        # 核心功能
│   ├── wechat_client.py         # 微信客户端
│   ├── template_detector.py     # 坐标模板检测（新增）
│   ├── ai_engine.py             # AI 引擎
│   ├── message_handler.py       # 消息处理
│   └── personality.py           # 风格学习
├── storage/                     # 数据存储
├── web/                         # Web 后台
├── tray/                        # 托盘应用
├── utils/                       # 工具函数
│   └── calibrate_template.py    # 模板校准工具
├── data/                        # 数据目录
└── calibrate.bat                # 校准工具快捷启动
```

## 配置

配置文件位于 `config/settings.json`：

```json
{
  "web": {
    "host": "127.0.0.1",
    "port": 5001
  },
  "ollama": {
    "base_url": "http://localhost:11434",
    "model": "qwen2.5"
  },
  "wechat": {
    "auto_reply": true,
    "whitelist_only": true,
    "detection_mode": "hybrid",
    "poll_interval": 3
  },
  "detector": {
    "diff_threshold": 30,
    "change_ratio": 0.02
  }
}
```

## 技术方案

### 坐标模板检测（新增）

通过预先定义的消息区域坐标模板，直接读取像素变化来检测新消息：

- **快速响应**：毫秒级检测，无需等待 OCR
- **低 CPU 占用**：仅进行图像差分，不运行 OCR
- **高可靠性**：基于固定 UI 布局，不受 OCR 误识别影响

### OCR 作为补充

- 仅在模板检测到新消息后，对特定区域进行 OCR 提取内容
- 大幅减少 OCR 调用频率

## 许可证

MIT

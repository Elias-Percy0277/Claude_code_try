# 微信托管项目改造任务记录

## 项目背景

- **原项目**：使用 `wxauto4` 库，仅支持微信 4.0.5 版本
- **当前微信版本**：4.1.8.29
- **改造方案**：使用 pyautogui + OpenCV + PaddleOCR 图像识别方案

---

## 已完成的工作

### 1. 更新依赖文件
- **文件**：`requirements.txt`
- **修改**：
  - 移除 `wxauto4`
  - 新增 `pyautogui`, `pyperclip`, `opencv-python`, `paddleocr`, `paddlepaddle`, `pywin32`

### 2. 重写微信客户端
- **文件**：`core/wechat_client.py`
- **实现**：
  - 使用 `win32gui` 查找微信窗口
  - 使用 `pyautogui` 模拟鼠标键盘操作
  - 使用 `PaddleOCR` 识别消息内容
  - 保持原有接口兼容性

### 3. 修改主程序
- **文件**：`main.py`
- **修改**：更新依赖检查逻辑

### 4. 可复用代码（约 70%）
- `core/ai_engine.py` - AI 引擎
- `core/personality.py` - 人设学习
- `core/message_handler.py` - 消息处理
- `storage/database.py` - 数据库操作
- `web/` - Web 后台
- `tray/` - 系统托盘
- `utils/logger.py` - 日志工具
- `config/settings.py` - 配置管理

---

## 待完成的工作

### 1. 安装依赖
```bash
cd E:/claude_code_project_try/wechat_custody
# 激活虚拟环境
venv\Scripts\activate
# 安装缺失的依赖（如有）
pip install pyautogui opencv-python paddleocr paddlepaddle
```

### 2. 测试启动
```bash
python main.py
```

### 3. 功能测试
- [ ] 窗口定位测试
- [ ] 新消息检测测试
- [ ] OCR 识别测试
- [ ] 消息发送测试
- [ ] 完整流程测试

### 4. 可能需要的调试
- [ ] 调整轮询间隔
- [ ] 优化 OCR 识别区域
- [ ] 处理微信 UI 变化
- [ ] 优化新消息检测算法

---

## 环境状态

| 组件 | 状态 |
|------|------|
| pyperclip | ✅ 已安装 |
| pywin32 | ✅ 已安装 |
| pyautogui | ❌ 未安装 |
| opencv-python | ❌ 未安装 |
| paddleocr | ❌ 未安装 |
| Ollama | ✅ 运行中 |
| qwen2.5 模型 | ✅ 可用 |

---

## 技术方案

### 消息监听流程
1. 定时截取微信窗口
2. 使用 OpenCV 检测新消息红点
3. 点击进入聊天窗口
4. 使用 PaddleOCR 识别消息内容
5. 对比判断是否为新消息
6. 触发回调函数

### 消息发送流程
1. Ctrl+F 搜索联系人
2. 输入联系人名称
3. Enter 进入聊天
4. 点击输入框
5. 粘贴消息内容
6. Enter 发送

---

## 注意事项

1. 微信窗口需要保持可见（不能最小化）
2. 首次运行需要手动添加白名单联系人
3. OCR 识别准确率依赖 PaddleOCR 性能
4. 轮询间隔默认 5 秒，可在配置中调整

---

## 相关文件

- 计划文件：`C:\Users\nobody-yhy\.claude\plans\partitioned-fluttering-token.md`
- 项目路径：`E:/claude_code_project_try/wechat_custody`

"""
微信客户端模块 - 使用坐标模板 + OCR 混合方案

优化方案：
1. 主使用坐标模板检测新消息（快速、低开销）
2. OCR 仅用于提取消息内容（按需调用）
3. 支持微信、钉钉等多种应用
"""
import time
import win32gui
import win32con
import win32api
import pyautogui
import pyperclip
import cv2
import numpy as np
from typing import Callable, Optional, List, Dict, Tuple
from threading import Thread, Event
from pathlib import Path
from collections import defaultdict

# PaddleOCR 延迟导入（首次使用时加载）
try:
    from paddleocr import PaddleOCR
    PADDLEOCR_AVAILABLE = True
except ImportError:
    PADDLEOCR_AVAILABLE = False
    PaddleOCR = None

from config.settings import settings
from core.template_detector import template_detector, get_template
from utils.logger import logger


# 禁用 pyautogui 的安全检查（需要用户确认）
pyautogui.PAUSE = 0.1
pyautogui.FAILSAFE = False


class MessageType:
    """消息类型"""
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    OTHER = "other"


class WeChatClient:
    """微信客户端封装类 - 坐标模板 + OCR 混合方案"""

    # 微信窗口类名
    WECHAT_WINDOW_CLASS = "WeChatMainWndForPC"
    # 微信进程名
    WECHAT_PROCESS = "WeChat.exe"

    def __init__(self):
        self.wx_hwnd: Optional[int] = None
        self.wx_rect: Optional[Tuple[int, int, int, int]] = None  # (left, top, right, bottom)
        self._running = False
        self._listen_thread: Optional[Thread] = None
        self._stop_event = Event()
        self._message_callbacks: List[Callable] = []
        self._whitelist_contacts: List[str] = []
        self._last_messages: Dict[str, str] = {}  # 记录每个联系人的最后一条消息
        self._last_screenshot = None
        self._last_ocr_texts = []  # 记录上次的 OCR 识别结果
        self._paused = False

        # OCR 引擎（延迟初始化）
        self._ocr_engine = None

        # 图像模板
        self._templates_dir = Path(__file__).parent.parent / "data" / "templates"
        self._templates_dir.mkdir(parents=True, exist_ok=True)

        # 轮询间隔（秒）
        self._poll_interval = settings.get("wechat.poll_interval", 3)

        # 检测模式：template（模板优先）/ ocr_only（纯OCR）/ hybrid（混合）
        self._detection_mode = settings.get("wechat.detection_mode", "hybrid")

        # 使用全局模板检测器
        self._detector = template_detector

        logger.info(f"WeChatClient 初始化完成（检测模式: {self._detection_mode}）")

    def _init_ocr(self):
        """初始化 OCR 引擎"""
        if self._ocr_engine is not None:
            return self._ocr_engine

        if not PADDLEOCR_AVAILABLE:
            logger.error("PaddleOCR 未安装，请运行: pip install paddleocr paddlepaddle")
            return None

        try:
            # PaddleOCR 新版本参数简化
            self._ocr_engine = PaddleOCR(
                use_angle_cls=True,
                lang='ch'
            )
            logger.info("PaddleOCR 初始化成功")
            return self._ocr_engine
        except Exception as e:
            logger.error(f"PaddleOCR 初始化失败: {e}")
            return None

    def connect(self) -> bool:
        """连接微信 - 查找微信窗口"""
        try:
            # 查找微信主窗口
            self.wx_hwnd = win32gui.FindWindow(self.WECHAT_WINDOW_CLASS, None)

            if self.wx_hwnd == 0:
                # 尝试通过窗口标题查找
                def callback(hwnd, windows):
                    if win32gui.IsWindowVisible(hwnd):
                        title = win32gui.GetWindowText(hwnd)
                        if "微信" in title:
                            windows.append(hwnd)
                    return True

                windows = []
                win32gui.EnumWindows(callback, windows)
                if windows:
                    self.wx_hwnd = windows[0]

            if self.wx_hwnd == 0:
                logger.error("未找到微信窗口，请确保微信已打开")
                return False

            # 获取窗口位置
            self._update_window_rect()

            # 确保窗口可见
            if self.wx_rect:
                left, top, right, bottom = self.wx_rect
                if right - left < 100 or bottom - top < 100:
                    # 窗口可能最小化了，尝试还原
                    win32gui.ShowWindow(self.wx_hwnd, win32con.SW_RESTORE)
                    time.sleep(0.5)
                    self._update_window_rect()

            logger.info(f"微信连接成功 - 窗口句柄: {self.wx_hwnd}, 位置: {self.wx_rect}")
            return True

        except Exception as e:
            logger.error(f"微信连接失败: {e}")
            return False

    def _update_window_rect(self):
        """更新窗口位置信息"""
        if self.wx_hwnd:
            try:
                rect = win32gui.GetWindowRect(self.wx_hwnd)
                self.wx_rect = rect
            except:
                pass

    def is_connected(self) -> bool:
        """检查是否已连接"""
        if self.wx_hwnd == 0:
            return False
        try:
            # 尝试获取窗口标题验证窗口仍存在
            win32gui.GetWindowText(self.wx_hwnd)
            return True
        except:
            return False

    def bring_to_front(self):
        """将微信窗口置顶（不改变窗口位置和大小）"""
        if self.wx_hwnd:
            try:
                # 检查窗口是否最小化
                if win32gui.IsIconic(self.wx_hwnd):
                    # 只在最小化时才还原
                    win32gui.ShowWindow(self.wx_hwnd, win32con.SW_RESTORE)
                    time.sleep(0.2)

                # 置顶（不影响位置）
                win32gui.SetForegroundWindow(self.wx_hwnd)
                time.sleep(0.1)
            except Exception as e:
                logger.warning(f"窗口置顶失败: {e}")

    def capture_screen(self) -> Optional[np.ndarray]:
        """截取整个屏幕（用于匹配校准工具的坐标）"""
        try:
            screenshot = pyautogui.screenshot()
            img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
            return img
        except Exception as e:
            logger.error(f"截屏失败: {e}")
            return None

    def capture_wechat_window(self) -> Optional[np.ndarray]:
        """截取微信窗口"""
        if not self.wx_rect:
            self._update_window_rect()
            if not self.wx_rect:
                return None

        try:
            left, top, right, bottom = self.wx_rect
            width = right - left
            height = bottom - top

            # 使用 pyautogui 截图
            screenshot = pyautogui.screenshot(
                region=(left, top, width, height)
            )

            # 转换为 OpenCV 格式
            img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
            return img

        except Exception as e:
            logger.error(f"截图失败: {e}")
            return None

    def _find_template(self, image: np.ndarray, template_name: str,
                       threshold: float = 0.8) -> Optional[Tuple[int, int]]:
        """在图像中查找模板"""
        template_path = self._templates_dir / f"{template_name}.png"

        if not template_path.exists():
            logger.debug(f"模板不存在: {template_name}")
            return None

        try:
            template = cv2.imread(str(template_path))
            if template is None:
                return None

            # 模板匹配
            result = cv2.matchTemplate(image, template, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

            if max_val >= threshold:
                return max_loc
            return None

        except Exception as e:
            logger.error(f"模板匹配失败 {template_name}: {e}")
            return None

    def _ocr_image(self, image: np.ndarray) -> List[str]:
        """使用 OCR 识别图像中的文字"""
        ocr = self._init_ocr()
        if ocr is None:
            return []

        try:
            # PaddleOCR 新版本不支持 cls 参数
            result = ocr.ocr(image)
            texts = []
            if result and result[0]:
                for line in result[0]:
                    if line and len(line) >= 2:
                        text = line[1][0]  # 获取识别的文本
                        if text:
                            texts.append(text.strip())
            return texts
        except Exception as e:
            logger.error(f"OCR 识别失败: {e}")
            return []

    def get_contacts(self) -> List[dict]:
        """获取联系人列表

        注意：由于使用图像识别，需要用户手动配置联系人
        """
        logger.warning("图像识别模式下，get_contacts 返回空列表")
        logger.warning("请在 Web 后台手动添加白名单联系人")
        return []

    def get_recent_messages(self, contact_name: str, limit: int = 10) -> List[dict]:
        """获取与某人的最近消息

        注意：图像识别模式下此功能不可用
        """
        logger.warning("图像识别模式下，get_recent_messages 不可用")
        return []

    def send_message(self, contact_name: str, content: str, skip_search: bool = True) -> bool:
        """发送消息给指定联系人

        实现方式：
        1. 搜索联系人（可选）
        2. 点击输入框
        3. 粘贴消息
        4. 发送

        Args:
            contact_name: 联系人名称
            content: 消息内容
            skip_search: 是否跳过搜索步骤（默认True，假设已经在当前聊天窗口）
        """
        if not self.is_connected():
            logger.warning("微信未连接")
            return False

        try:
            self.bring_to_front()

            # 搜索联系人（仅在需要时）
            if not skip_search:
                # Ctrl+F 打开搜索框
                pyautogui.hotkey('ctrl', 'f')
                time.sleep(0.3)

                # 输入联系人名称
                pyperclip.copy(contact_name)
                pyautogui.hotkey('ctrl', 'v')
                time.sleep(0.5)

                # 按回车进入聊天
                pyautogui.press('enter')
                time.sleep(0.5)

            # 点击输入框（右下角）
            if self.wx_rect:
                left, top, right, bottom = self.wx_rect
                # 点击输入框区域（右下角）
                input_x = int(right - 100)
                input_y = int(bottom - 50)
                pyautogui.click(input_x, input_y)
                time.sleep(0.2)

            # 复制消息内容
            pyperclip.copy(content)

            # 粘贴消息
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(0.2)

            # 发送消息
            pyautogui.press('enter')

            logger.info(f"[完全自动] 发送消息给 {contact_name}: {content[:50]}...")
            return True

        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            return False

    def add_message_callback(self, callback: Callable):
        """添加消息回调函数"""
        self._message_callbacks.append(callback)

    def start_listening(self, contacts: Optional[List[str]] = None):
        """开始监听消息"""
        if self._running:
            logger.warning("消息监听已在运行")
            return

        if not self.is_connected():
            if not self.connect():
                return

        try:
            self._running = True
            self._stop_event.clear()

            if not contacts:
                logger.warning("未指定监听联系人，请在 Web 后台添加白名单联系人")
                self._whitelist_contacts = []
            else:
                self._whitelist_contacts = contacts
                logger.info(f"准备监听 {len(contacts)} 个白名单联系人: {contacts}")

            # 初始化 OCR
            self._init_ocr()
            if self._ocr_engine is None:
                logger.error("OCR 初始化失败，无法启动监听")
                self._running = False
                return

            # 启动轮询线程
            self._listen_thread = Thread(target=self._poll_messages, daemon=True)
            self._listen_thread.start()
            logger.info("消息轮询监听已启动")

        except Exception as e:
            logger.error(f"启动监听失败: {e}")
            self._running = False

    def _poll_messages(self):
        """轮询检查新消息"""
        logger.info("开始轮询检查新消息...")

        while self._running and not self._stop_event.is_set():
            try:
                if not self.is_connected():
                    time.sleep(self._poll_interval)
                    continue

                # 检查是否暂停
                if self._paused:
                    time.sleep(self._poll_interval)
                    continue

                # 截取屏幕（使用全屏，与校准工具坐标匹配）
                screenshot = self.capture_screen()
                if screenshot is None:
                    time.sleep(self._poll_interval)
                    continue

                # 根据检测模式选择检测方式
                if self._detection_mode == "ocr_only":
                    # 纯 OCR 模式（原方案，作为备用）
                    self._poll_with_ocr(screenshot)
                else:
                    # 模板检测模式（快速）
                    self._poll_with_template(screenshot)

                time.sleep(self._poll_interval)

            except Exception as e:
                logger.error(f"轮询消息异常: {e}")
                time.sleep(self._poll_interval)

    def _poll_with_template(self, screenshot: np.ndarray):
        """使用坐标模板检测新消息（快速模式）"""
        try:
            if not self.wx_rect:
                return

            # 确保 OCR 已初始化
            ocr = self._init_ocr()
            if ocr is None:
                logger.debug("OCR 未初始化，跳过检测")
                return

            # 使用屏幕尺寸（与校准工具匹配）
            screen_height, screen_width = screenshot.shape[:2]
            screen_rect = (0, 0, screen_width, screen_height)

            # 使用模板检测器检测新消息
            detected_messages = self._detector.detect_new_messages(
                screenshot=screenshot,
                window_rect=screen_rect,
                whitelist_contacts=self._whitelist_contacts,
                ocr_engine=ocr
            )

            for msg_data in detected_messages:
                contact_name = msg_data.get("contact_name")
                content = msg_data.get("content")

                if not content or content == "__NEW_MESSAGE_DETECTED__":
                    # 需要用 OCR 获取具体内容
                    content = self._get_message_content_with_template(contact_name, screenshot)

                if content:
                    # 检查是否是新消息
                    msg_key = f"{contact_name}:{content}"
                    last_msg_key = self._last_messages.get(contact_name)

                    if msg_key != last_msg_key:
                        self._last_messages[contact_name] = msg_key

                        # 触发回调
                        message_data = {
                            "contact_name": contact_name,
                            "content": content,
                            "type": MessageType.TEXT,
                            "sender": contact_name,
                            "time": "",
                            "method": "template"
                        }

                        logger.info(f"[模板检测] 收到来自 {contact_name} 的新消息: {content[:50]}...")

                        for callback in self._message_callbacks:
                            try:
                                callback(message_data)
                            except Exception as e:
                                logger.error(f"消息回调异常: {e}")

        except Exception as e:
            logger.error(f"模板检测失败: {e}")

    def _poll_with_ocr(self, screenshot: np.ndarray):
        """使用纯 OCR 检测新消息（备用模式）"""
        try:
            # 检测是否有新消息（通过颜色检测新消息标识）
            new_message_contacts = self._detect_new_messages(screenshot)

            for contact_name in new_message_contacts:
                if contact_name in self._whitelist_contacts:
                    # 获取消息内容
                    message_content = self._get_message_content(contact_name, screenshot)

                    if message_content:
                        # 检查是否是新消息
                        msg_key = f"{contact_name}:{message_content}"
                        last_msg_key = self._last_messages.get(contact_name)

                        if msg_key != last_msg_key:
                            self._last_messages[contact_name] = msg_key

                            # 触发回调
                            message_data = {
                                "contact_name": contact_name,
                                "content": message_content,
                                "type": MessageType.TEXT,
                                "sender": contact_name,
                                "time": "",
                                "method": "ocr"
                            }

                            logger.info(f"[OCR检测] 收到来自 {contact_name} 的新消息: {message_content[:50]}...")

                            for callback in self._message_callbacks:
                                try:
                                    callback(message_data)
                                except Exception as e:
                                    logger.error(f"消息回调异常: {e}")

        except Exception as e:
            logger.error(f"OCR 检测失败: {e}")

    def _get_message_content_with_template(self, contact_name: str, screenshot: np.ndarray) -> Optional[str]:
        """使用模板定位 + OCR 提取消息内容"""
        try:
            ocr = self._init_ocr()
            if ocr is None:
                return None

            # 使用模板检测器获取消息内容
            content = self._detector.get_message_content_ocr(
                screenshot=screenshot,
                window_rect=self.wx_rect,
                ocr_engine=ocr,
                contact_name=contact_name,
                is_own_message=False
            )

            return content

        except Exception as e:
            logger.error(f"模板OCR获取消息失败: {e}")
            return None

    def _detect_new_messages(self, screenshot: np.ndarray) -> List[str]:
        """检测新消息

        通过检测红色标识（新消息红点）来判断
        """
        new_messages = []

        try:
            # 转换到 HSV 颜色空间
            hsv = cv2.cvtColor(screenshot, cv2.COLOR_BGR2HSV)

            # 红色范围（微信红点颜色）
            lower_red1 = np.array([0, 100, 100])
            upper_red1 = np.array([10, 255, 255])
            lower_red2 = np.array([160, 100, 100])
            upper_red2 = np.array([180, 255, 255])

            # 创建红色掩码
            mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
            mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
            mask = cv2.bitwise_or(mask1, mask2)

            # 查找轮廓
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            if contours:
                # 有新消息
                # 这里简化处理：返回所有白名单联系人
                # 实际应该通过位置匹配具体联系人
                if self._whitelist_contacts:
                    new_messages.extend(self._whitelist_contacts)

        except Exception as e:
            logger.debug(f"检测新消息失败: {e}")

        return new_messages

    def _get_message_content(self, contact_name: str,
                             screenshot: np.ndarray) -> Optional[str]:
        """获取消息内容 - 使用差分检测找到新消息"""
        try:
            if not self.wx_rect:
                return None

            # 获取窗口尺寸
            left, top, right, bottom = self.wx_rect
            width = right - left
            height = bottom - top

            # 只截取消息区域的底部（最新消息区域）
            area_height = 200
            margin_bottom = 140  # 避开输入框
            margin_left = 20
            margin_right = 20

            msg_top = height - margin_bottom - area_height
            msg_bottom = height - margin_bottom
            msg_left = margin_left
            msg_right = width - margin_right

            msg_top = max(0, msg_top)
            msg_bottom = min(height, msg_bottom)

            # 截取底部消息区域
            message_area = screenshot[msg_top:msg_bottom, msg_left:msg_right]

            # OCR 识别
            current_texts = self._ocr_image(message_area)

            if not current_texts:
                return None

            # 使用差分检测：对比上次识别结果，找出新增的文本
            new_message = self._find_new_message(current_texts)

            # 更新历史记录
            self._last_ocr_texts = current_texts

            return new_message

        except Exception as e:
            logger.error(f"获取消息内容失败: {e}")
            return None

    def _find_new_message(self, current_texts: List[str]) -> Optional[str]:
        """通过对比找出新消息

        策略：
        1. 如果是第一次识别，返回最后一条有意义的文本
        2. 否则对比上次结果，找出新增的文本
        """
        import re

        # 过滤函数：移除时间戳和系统消息
        def filter_texts(texts):
            filtered = []
            for text in texts:
                text = text.strip()
                if not text:
                    continue
                if re.match(r'^\d{1,2}:\d{2}$', text):
                    continue
                if re.match(r'^(今天|昨天)\s*\d{1,2}:\d{2}$', text):
                    continue
                if text.startswith('[') or '微信' in text:
                    continue
                if len(text) < 2 or len(text) > 150:
                    continue
                filtered.append(text)
            return filtered

        current_filtered = filter_texts(current_texts)

        # 如果是第一次识别或没有历史记录
        if not self._last_ocr_texts:
            if current_filtered:
                return current_filtered[-1]  # 返回最后一条

        # 对比找出新增的文本
        last_filtered = filter_texts(self._last_ocr_texts)

        # 找出在当前结果中但不在上次结果中的文本
        new_texts = [t for t in current_filtered if t not in last_filtered]

        if new_texts:
            # 返回第一条新增的文本（最可能是新消息）
            return new_texts[0]

        # 如果没有找到新增文本，但有新内容出现（OCR 识别结果变化）
        # 尝试通过位置变化判断
        if len(current_filtered) > len(last_filtered):
            return current_filtered[-1]

        return None

    def _extract_latest_from_bottom(self, texts: List[str]) -> Optional[str]:
        """从底部区域的 OCR 结果中提取最新消息

        策略：
        1. 新消息通常在最底部
        2. 过滤掉时间戳、系统消息
        3. 返回最后一条有意义的文本
        """
        import re

        if not texts:
            return None

        # 从下往上查找，找到第一条有意义的消息
        for text in reversed(texts):
            text = text.strip()

            # 跳过空文本
            if not text:
                continue

            # 跳过纯时间戳
            if re.match(r'^\d{1,2}:\d{2}$', text):
                continue

            # 跳过"今天/昨天 + 时间"
            if re.match(r'^(今天|昨天)\s*\d{1,2}:\d{2}$', text):
                continue

            # 跳过系统消息
            if text.startswith('[') or '微信' in text:
                continue

            # 跳过太短的内容（可能是误识别）
            if len(text) < 2:
                continue

            # 跳过可能是联系人名称的短文本（如果包含冒号，可能是"名字: 内容"格式）
            if ':' in text and len(text.split(':')[0]) < 10:
                # 提取冒号后的内容
                parts = text.split(':', 1)
                if len(parts) > 1 and parts[1].strip():
                    return parts[1].strip()

            # 找到了合适的消息
            if len(text) < 200:  # 避免识别到长串内容
                return text

        return None

    def _extract_latest_message(self, texts: List[str]) -> Optional[str]:
        """从 OCR 识别的文本中提取最新消息

        方法：
        1. 查找时间戳 (格式: HH:MM 或 今天/昨天 HH:MM)
        2. 时间戳后面的文本即为消息内容
        """
        import re

        if not texts:
            return None

        # 时间戳正则表达式
        time_patterns = [
            r'(\d{1,2}:\d{2})',           # 9:30 或 09:30
            r'(今天\s*\d{1,2}:\d{2})',    # 今天 9:30
            r'(昨天\s*\d{1,2}:\d{2})',    # 昨天 9:30
            r'(\d{1,2}月\d{1,2}日)',      # 4月2日
        ]

        latest_time = None
        latest_message = None
        latest_index = -1

        # 遍历所有识别到的文本
        for i, text in enumerate(texts):
            # 检查是否包含时间戳
            for pattern in time_patterns:
                match = re.search(pattern, text)
                if match:
                    time_str = match.group(1)
                    # 如果这条文本后面还有内容，那可能是消息
                    if i + 1 < len(texts):
                        next_text = texts[i + 1].strip()
                        # 过滤掉明显不是消息的内容
                        if (next_text and
                            len(next_text) > 1 and
                            not re.match(r'^\d+:\d+$', next_text) and  # 不是纯时间
                            not next_text.startswith('[') and           # 不是系统消息
                            not '微信' in next_text and                # 不是微信相关
                            len(next_text) < 200):                     # 避免识别到长文本
                            latest_index = i
                            latest_time = time_str
                            latest_message = next_text
                            break

        # 如果没找到通过时间戳定位的消息，使用备选方案
        if latest_message is None:
            # 备选方案：返回最后一行有意义的文本
            for text in reversed(texts):
                text = text.strip()
                if (text and
                    len(text) > 1 and
                    len(text) < 200 and
                    not text.startswith('[') and
                    not re.match(r'^\d+:\d+$', text) and
                    not '微信' in text):
                    return text

        return latest_message

    def stop_listening(self):
        """停止监听消息"""
        if not self._running:
            return

        try:
            self._running = False
            self._stop_event.set()

            if self._listen_thread and self._listen_thread.is_alive():
                self._listen_thread.join(timeout=2)

            logger.info("停止监听微信消息")
        except Exception as e:
            logger.error(f"停止监听异常: {e}")

    def pause(self):
        """暂停消息监听"""
        self._paused = True
        logger.info("微信消息监听已暂停")

    def resume(self):
        """恢复消息监听"""
        self._paused = False
        logger.info("微信消息监听已恢复")

    def is_paused(self) -> bool:
        """检查是否暂停"""
        return self._paused

    def reconnect(self) -> bool:
        """重新连接"""
        self.stop_listening()
        self.wx_hwnd = None
        self.wx_rect = None
        return self.connect()

    def get_current_chat(self) -> Optional[str]:
        """获取当前聊天窗口"""
        logger.debug("图像识别模式下，get_current_chat 不可用")
        return None


# 全局微信客户端实例
wechat_client = WeChatClient()

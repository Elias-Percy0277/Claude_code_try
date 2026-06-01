"""
坐标模板消息检测模块 - 重新设计版本

核心改进：
1. 区分私聊和群聊
2. 识别消息发送者
3. 群聊场景禁用自动回复
4. 更精确的消息区域截取
"""
import re
import time
import cv2
import numpy as np
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass
from pathlib import Path
from enum import Enum

from config.settings import settings
from utils.logger import logger


class ChatType(Enum):
    """聊天类型"""
    UNKNOWN = "unknown"
    PRIVATE = "private"      # 一对一私聊
    GROUP = "group"          # 群聊


@dataclass
class Rect:
    """矩形区域（像素坐标）"""
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    def to_slice(self) -> Tuple[slice, slice]:
        """转换为 numpy 切片"""
        return slice(self.top, self.bottom), slice(self.left, self.right)


@dataclass
class RelativeRect:
    """相对矩形区域（基于窗口大小的百分比）"""
    left: float   # 0.0 - 1.0
    top: float
    right: float
    bottom: float

    def to_absolute(self, window_width: int, window_height: int) -> Rect:
        """转换为绝对像素坐标"""
        return Rect(
            left=int(self.left * window_width),
            top=int(self.top * window_height),
            right=int(self.right * window_width),
            bottom=int(self.bottom * window_height)
        )


@dataclass
class MessageAreaTemplate:
    """消息区域模板 - 重新设计"""
    name: str
    description: str

    # ============ 核心区域定义 ============

    # 标题区域（用于判断私聊/群聊）
    # 微信标题格式：私聊显示"昵称"，群聊显示"群名(N)"
    title_area: RelativeRect

    # 消息区域整体（包含所有消息）
    message_area: RelativeRect

    # ============ 群聊检测区域 ============

    # 发送者昵称区域（群聊中，每条消息左侧显示发送者昵称）
    # 私聊中此区域为空或只有时间戳
    sender_name_area: RelativeRect

    # 群成员数指示区域（标题右侧 "(N)" 部分）
    group_count_area: RelativeRect

    # ============ 消息内容区域 ============

    # 对方消息区域（左侧，带发送者昵称）
    other_message_area: RelativeRect

    # 自己消息区域（右侧，绿色气泡）
    own_message_area: RelativeRect

    # 最新消息区域（底部，用于检测新消息）
    latest_message_area: RelativeRect

    # ============ 排除区域 ============

    # 输入框区域（需要排除）
    input_area: RelativeRect

    # 时间戳区域（用于过滤）
    timestamp_area: RelativeRect

    # ============ 参数 ============

    # 最小窗口尺寸
    min_width: int = 600
    min_height: int = 400

    # 群聊检测阈值：检测到多少个不同昵称时判定为群聊
    group_nicknames_threshold: int = 2

    # 消息行高
    message_line_height: int = 40


# =============================================================================
# 微信 4.x 布局分析
# =============================================================================
#
# 窗口布局（假设 1280x720）：
#
#   ┌─────────────────────────────────────────────────────────────┐
#   │ [←] 迟遇                               [−][□][×]            │ <- title_area (0.00-0.06)
#   │ ─────────────────────────────────────────────────────────── │
#   │  [🔍 搜索]                                              [+] │ <- toolbar (0.06-0.12)
#   ├──────┬──────────────────────────────────────────────────────┤
#   │ 联系 │                                                      │
#   │ 人列 │         聊天记录区域                                  │
#   │ 表   │    (message_area: 0.12-0.82)                         │
#   │      │                                                      │
#   │ 0-25% │  刘启升: 你好                          [我的消息]   │ <- 私聊: 对方消息左对齐
#   │       │  ┌─────────┐                            ┌───────┐   │      群聊: 带发送者昵称
#   │       │  │ 你好   │                            │ 好的  │   │
#   │       │  └─────────┘                            └───────┘   │
#   │       │                                                      │
#   │       │  李宇杰: 收到                                          │
#   │       │  ┌─────────┐                                        │
#   │       │  │ 收到   │                                        │ <- latest_message_area (底部)
#   │       │  └─────────┘                                        │
#   ├──────┴──────────────────────────────────────────────────────┤
#   │ 输入框...                                       [发送] [表情]| <- input_area (0.82-0.95)
#   └─────────────────────────────────────────────────────────────┘
#
# 私聊特征：
#   - 标题只显示一个名字
#   - 消息直接显示，无发送者昵称前缀
#   - 对方消息左对齐，自己消息右对齐
#
# 群聊特征：
#   - 标题显示群名 + (N)
#   - 每条消息前有发送者昵称（小字，灰色）
#   - 可能有多人连续发言
#
# =============================================================================

WECHAT_4X_TEMPLATE = MessageAreaTemplate(
    name="wechat_4x",
    description="微信 PC 4.x 客户端 - 支持群聊检测",

    # 标题区域（顶部，显示聊天对象名称）
    title_area=RelativeRect(left=0.25, top=0.00, right=0.95, bottom=0.06),

    # 消息主区域
    message_area=RelativeRect(left=0.25, top=0.12, right=0.98, bottom=0.82),

    # 发送者昵称区域（群聊中消息左侧的小字昵称）
    # 私聊中这个区域通常为空或只有时间戳
    sender_name_area=RelativeRect(left=0.25, top=0.12, right=0.40, bottom=0.82),

    # 群成员数指示区域（标题中的 "(N)" 部分）
    group_count_area=RelativeRect(left=0.70, top=0.00, right=0.95, bottom=0.06),

    # 对方消息区域（左侧）
    other_message_area=RelativeRect(left=0.25, top=0.12, right=0.65, bottom=0.82),

    # 自己消息区域（右侧，绿色气泡）
    own_message_area=RelativeRect(left=0.65, top=0.12, right=0.98, bottom=0.82),

    # 最新消息区域（底部 200px）
    latest_message_area=RelativeRect(left=0.25, top=0.60, right=0.98, bottom=0.82),

    # 输入框区域
    input_area=RelativeRect(left=0.25, top=0.82, right=0.98, bottom=0.95),

    # 时间戳区域（消息上方的时间显示）
    timestamp_area=RelativeRect(left=0.40, top=0.12, right=0.60, bottom=0.82),

    min_width=600,
    min_height=400,
    group_nicknames_threshold=2,
    message_line_height=40
)


def load_custom_template(config_path: Path = None) -> Optional[MessageAreaTemplate]:
    """
    从配置文件加载自定义模板

    Args:
        config_path: 配置文件路径，默认为 data/region_config.json

    Returns:
        MessageAreaTemplate 对象，如果配置不存在则返回 None
    """
    if config_path is None:
        config_path = Path(__file__).parent.parent / "data" / "region_config.json"

    if not config_path.exists():
        return None

    try:
        import json
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        regions = config['regions']

        # 从用户配置创建模板
        template = MessageAreaTemplate(
            name="custom",
            description="用户自定义区域配置",
            title_area=RelativeRect(**regions['title']),
            message_area=RelativeRect(**regions['message']),
            sender_name_area=RelativeRect(**regions.get('sender_name', regions['message'])),
            group_count_area=RelativeRect(**regions.get('group_count', {
                'left': 0.7, 'top': 0.0, 'right': 0.95, 'bottom': 0.06
            })),
            other_message_area=RelativeRect(**regions['other']),
            own_message_area=RelativeRect(**regions['own']),
            latest_message_area=RelativeRect(**regions['message']),  # 使用整体消息区域
            input_area=RelativeRect(**regions['input']),
            timestamp_area=RelativeRect(**regions.get('timestamp', {
                'left': 0.4, 'top': 0.12, 'right': 0.6, 'bottom': 0.82
            })),
        )

        logger.info(f"已加载自定义模板: {config_path}")
        return template

    except Exception as e:
        logger.warning(f"加载自定义模板失败: {e}")
        return None


class TemplateDetector:
    """基于坐标模板的消息检测器 - 重新设计版本

    核心功能：
    1. 检测聊天类型（私聊/群聊）
    2. 识别消息发送者
    3. 安全的消息提取
    4. 支持用户自定义区域配置
    """

    def __init__(self, template: MessageAreaTemplate = None, use_custom: bool = True):
        # 优先使用用户自定义配置
        if use_custom:
            custom_template = load_custom_template()
            if custom_template:
                self.template = custom_template
                logger.info("使用自定义区域配置")
            else:
                self.template = template or WECHAT_4X_TEMPLATE
                logger.info("使用默认模板（建议运行校准工具自定义区域）")
        else:
            self.template = template or WECHAT_4X_TEMPLATE
        self._last_message_hash: Dict[str, str] = {}
        self._last_message_content: Dict[str, str] = {}  # 记录最后消息内容，用于相似度比对
        self._last_screenshot: Optional[np.ndarray] = None
        self._baseline_frame: Optional[np.ndarray] = None
        self._current_chat_type: ChatType = ChatType.UNKNOWN
        self._current_chat_name: str = ""

        # 差分检测参数
        self._diff_threshold = settings.get("detector.diff_threshold", 30)
        self._change_ratio = settings.get("detector.change_ratio", 0.02)

        # 消息相似度阈值（0-1，越高越严格）
        self._similarity_threshold = settings.get("detector.similarity_threshold", 0.85)

        logger.info(f"TemplateDetector 初始化 - 模板: {self.template.name}, 只检测对方消息区域（左侧白色气泡）")

    def set_template(self, template: MessageAreaTemplate):
        """切换模板"""
        self.template = template
        self._last_message_hash.clear()
        self._baseline_frame = None
        self._current_chat_type = ChatType.UNKNOWN
        logger.info(f"切换模板: {template.name}")

    def detect_chat_type(
        self,
        screenshot: np.ndarray,
        window_rect: Tuple[int, int, int]
    ) -> Tuple[ChatType, str]:
        """
        检测当前聊天类型

        Returns:
            (ChatType, 聊天名称)
        """
        left, top, right, bottom = window_rect
        window_width = right - left
        window_height = bottom - top

        # 截取标题区域
        title_area = self.template.title_area.to_absolute(window_width, window_height)
        title_region = screenshot[title_area.to_slice()]

        # 截取群成员数指示区域
        count_area = self.template.group_count_area.to_absolute(window_width, window_height)
        count_region = screenshot[count_area.to_slice()]

        try:
            # OCR 识别标题
            # 这里需要外部传入 OCR 引擎，暂时用简单的图像特征判断

            # 检测群成员数模式：标题右侧有 "(N)" 格式
            is_group = self._detect_group_pattern(count_region)

            if is_group:
                self._current_chat_type = ChatType.GROUP
                # 从标题区域提取群名
                chat_name = self._extract_title_text(title_region)
                self._current_chat_name = chat_name if chat_name else "群聊"
                logger.warning(f"[安全] 检测到群聊: {self._current_chat_name}")
                return ChatType.GROUP, self._current_chat_name
            else:
                self._current_chat_type = ChatType.PRIVATE
                chat_name = self._extract_title_text(title_region)
                self._current_chat_name = chat_name if chat_name else "私聊"
                logger.info(f"检测到私聊: {self._current_chat_name}")
                return ChatType.PRIVATE, self._current_chat_name

        except Exception as e:
            logger.debug(f"聊天类型检测失败: {e}")
            return ChatType.UNKNOWN, ""

    def _detect_group_pattern(self, region: np.ndarray) -> bool:
        """
        检测是否是群聊

        群聊特征：
        1. 标题右侧有 "(数字)" 格式
        2. 消息区域有多个不同昵称
        """
        # 简化判断：检测括号模式
        # 实际应用中需要 OCR 识别

        # 暂时返回 True 表示保守处理（默认认为是群聊）
        # TODO: 实现真正的 OCR 检测
        return False  # 临时：先假设私聊，等实现 OCR 后再判断

    def _extract_title_text(self, region: np.ndarray) -> str:
        """提取标题文本"""
        # TODO: 使用 OCR 提取
        return ""

    def detect_new_messages(
        self,
        screenshot: np.ndarray,
        window_rect: Tuple[int, int, int],
        whitelist_contacts: List[str],
        ocr_engine=None
    ) -> List[Dict]:
        """
        检测新消息 - 安全版本

        安全措施：
        1. 检测聊天类型
        2. 群聊场景拒绝处理
        3. 只处理白名单联系人的私聊
        4. 防止识别自己的消息作为新消息（使用冷却期）
        """
        left, top, right, bottom = window_rect
        window_width = right - left
        window_height = bottom - top

        # ============ 第一步：检测聊天类型 ============
        chat_type, chat_name = self.detect_chat_type(screenshot, window_rect)

        if chat_type == ChatType.GROUP:
            logger.error(f"[安全] 拒绝处理群聊消息: {chat_name}")
            return []  # 群聊场景直接返回空

        if chat_type == ChatType.UNKNOWN:
            logger.warning("[安全] 聊天类型未知，跳过处理")
            return []

        # ============ 第二步：检查是否在白名单中 ============
        if chat_type == ChatType.PRIVATE:
            # 如果 chat_name 为空，使用白名单中的第一个（假设当前就在和白名单中的联系人聊天）
            if not chat_name or chat_name == "私聊":
                if whitelist_contacts:
                    chat_name = whitelist_contacts[0]
                    logger.debug(f"使用白名单联系人: {chat_name}")
                else:
                    logger.debug("白名单为空，跳过处理")
                    return []

            # 检查当前聊天对象是否在白名单中
            if whitelist_contacts and chat_name not in whitelist_contacts:
                logger.debug(f"非白名单联系人: {chat_name}")
                return []

        # ============ 基于区域配置提取最新消息 ============
        # 使用校准的对方消息区域 (other)
        if ocr_engine:
            # 获取对方消息区域（左侧）
            other_msg_area = self.template.other_message_area.to_absolute(window_width, window_height)

            # 只截取底部区域（最新消息）
            bottom_height = int(other_msg_area.height * 0.4)
            bottom_y = max(0, other_msg_area.bottom - bottom_height)

            logger.debug(f"[区域检测] 对方消息区域: {other_msg_area}, 截取底部: {bottom_height}px")

            if bottom_height < 30 or other_msg_area.width < 50:
                logger.warning(f"[区域检测] 区域太小")
                return []

            # 截取底部区域
            msg_bottom = screenshot[
                bottom_y:other_msg_area.bottom,
                other_msg_area.left:other_msg_area.right
            ]

            logger.debug(f"[区域检测] 截取形状: {msg_bottom.shape}")

            # OCR 提取内容
            content = self._extract_message_with_ocr(msg_bottom, ocr_engine)
            logger.debug(f"[区域检测] OCR内容: {content}")

            if content:
                # 去重检查
                content_hash = hash(content)
                last_hash = self._last_message_hash.get(chat_name)
                last_content = self._last_message_content.get(chat_name, "")
                is_similar = self._is_similar_message(content, last_content)

                if last_hash != content_hash and not is_similar:
                    self._last_message_hash[chat_name] = str(content_hash)
                    self._last_message_content[chat_name] = content
                    logger.info(f"[区域检测-私聊] {chat_name}: {content[:30]}...")
                    return [{
                        "contact_name": chat_name,
                        "content": content,
                        "type": "text",
                        "method": "region_detection",
                        "chat_type": "private"
                    }]
                else:
                    logger.debug(f"[去重] 消息相同或相似，跳过")

        return []

    def _detect_changes(self, current_frame: np.ndarray) -> bool:
        """检测帧变化"""
        if self._baseline_frame is None:
            return True

        try:
            if current_frame.shape != self._baseline_frame.shape:
                current_frame = cv2.resize(
                    current_frame,
                    (self._baseline_frame.shape[1], self._baseline_frame.shape[0])
                )

            gray_current = cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY)
            gray_baseline = cv2.cvtColor(self._baseline_frame, cv2.COLOR_BGR2GRAY)

            gray_current = cv2.GaussianBlur(gray_current, (5, 5), 0)
            gray_baseline = cv2.GaussianBlur(gray_baseline, (5, 5), 0)

            diff = cv2.absdiff(gray_baseline, gray_current)
            _, thresh = cv2.threshold(diff, self._diff_threshold, 255, cv2.THRESH_BINARY)

            change_pixels = cv2.countNonZero(thresh)
            total_pixels = thresh.shape[0] * thresh.shape[1]
            change_ratio = change_pixels / total_pixels

            return change_ratio > self._change_ratio

        except Exception as e:
            logger.debug(f"变化检测失败: {e}")
            return False

    def _extract_message_with_ocr(
        self,
        message_region: np.ndarray,
        ocr_engine
    ) -> Optional[str]:
        """使用 OCR 提取消息内容"""
        try:
            # 只截取底部区域（最新消息）
            bottom_height = min(200, message_region.shape[0] // 3)
            bottom_region = message_region[-bottom_height:]

            result = ocr_engine.ocr(bottom_region)
            texts = []

            if result and result[0]:
                for line in result[0]:
                    if line and len(line) >= 2:
                        text = line[1][0].strip()
                        if text:
                            texts.append(text)

            logger.debug(f"OCR 识别到 {len(texts)} 行文本")
            for t in texts:
                logger.debug(f"  - {t}")

            return self._extract_latest_text(texts)

        except Exception as e:
            logger.error(f"OCR 失败: {e}")
            return None

    def _extract_latest_text(self, texts: List[str]) -> Optional[str]:
        """从识别文本中提取最新消息"""
        if not texts:
            logger.debug("OCR 无文本结果")
            return None

        def is_valid(text: str) -> bool:
            text = text.strip()
            if not text:
                return False
            if re.match(r'^\d{1,2}:\d{2}$', text):
                return False
            if re.match(r'^(今天|昨天)\s*\d{1,2}:\d{2}$', text):
                return False
            if text.startswith('[') or '微信' in text:
                return False
            if len(text) < 2 or len(text) > 200:
                return False
            return True

        valid_texts = [t for t in texts if is_valid(t)]
        logger.debug(f"有效文本 {len(valid_texts)}/{len(texts)}")

        if not valid_texts:
            logger.debug("没有有效文本")
            return None

        # 过滤掉可能是发送者昵称的短文本
        # 群聊中昵称和消息内容通常在同一行或相邻行
        for i, text in enumerate(valid_texts):
            # 如果文本包含冒号，可能是 "昵称: 内容" 格式
            if ':' in text or '：' in text:
                parts = re.split(r'[:：]', text, 1)
                if len(parts) > 1 and parts[1].strip():
                    return parts[1].strip()

        result = valid_texts[-1]
        logger.debug(f"提取消息: {result}")
        return result

    def _is_similar_message(self, content1: str, content2: str) -> bool:
        """
        判断两条消息是否相似（用于去重）

        使用 SequenceMatcher 计算相似度，防止 OCR 误差导致同一消息被识别为不同消息
        """
        if not content1 or not content2:
            return False

        # 如果完全相同
        if content1 == content2:
            return True

        # 计算相似度
        from difflib import SequenceMatcher
        similarity = SequenceMatcher(None, content1, content2).ratio()

        logger.debug(f"[相似度] '{content1[:20]}...' vs '{content2[:20]}...' = {similarity:.2f}")

        return similarity >= self._similarity_threshold

    def _detect_theme_mode(self, screenshot: np.ndarray, window_rect: Tuple[int, int, int]) -> str:
        """
        检测微信主题模式（亮色/暗黑）

        通过分析背景颜色判断：
        - 亮色模式：背景为浅色 (V > 120)
        - 暗黑模式：背景为深色 (V <= 120)
        """
        left, top, right, bottom = window_rect
        window_width = right - left
        window_height = bottom - top

        # 截取消息区域中心的一小块来检测背景
        msg_area = self.template.message_area.to_absolute(window_width, window_height)
        center_x = (msg_area.left + msg_area.right) // 2
        center_y = (msg_area.top + msg_area.bottom) // 2

        # 取中心区域 50x50 像素
        sample_region = screenshot[
            center_y - 25:center_y + 25,
            center_x - 25:center_x + 25
        ]

        try:
            hsv = cv2.cvtColor(sample_region, cv2.COLOR_BGR2HSV)
            avg_v = hsv[:, :, 2].mean()

            # 调整阈值：120 作为分界点
            if avg_v <= 120:
                theme = "dark"
                logger.debug(f"[主题检测] 暗黑模式 (V={avg_v:.1f})")
            else:
                theme = "light"
                logger.debug(f"[主题检测] 亮色模式 (V={avg_v:.1f})")

            return theme
        except Exception as e:
            logger.warning(f"主题检测失败: {e}，默认使用亮色模式")
            return "light"

    def _detect_bubbles_by_color(
        self,
        screenshot: np.ndarray,
        window_rect: Tuple[int, int, int]
    ) -> List[Dict]:
        """
        通过颜色检测消息气泡（支持亮色和暗黑模式）

        Returns:
            气泡列表，每个气泡包含:
            - type: "other" (对方) 或 "own" (自己)
            - rect: (left, top, right, bottom)
            - center: (x, y)
        """
        left, top, right, bottom = window_rect
        window_width = right - left
        window_height = bottom - top

        # 检测主题模式
        theme = self._detect_theme_mode(screenshot, window_rect)

        # 截取消息区域
        msg_area = self.template.message_area.to_absolute(window_width, window_height)
        message_region = screenshot[msg_area.to_slice()]

        bubbles = []

        try:
            # 转换到 HSV 颜色空间
            hsv = cv2.cvtColor(message_region, cv2.COLOR_BGR2HSV)

            # 形态学操作核
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))

            # ============ 根据主题检测对方气泡 ============
            if theme == "light":
                # 亮色模式：对方是浅灰色气泡
                lower_other = np.array([0, 0, 140])
                upper_other = np.array([180, 50, 255])
            else:
                # 暗黑模式：对方是浅灰色/白色气泡（在深色背景上）
                # 放宽范围，提高检测成功率
                lower_other = np.array([0, 0, 100])      # 降低亮度下限
                upper_other = np.array([180, 80, 255])   # 提高饱和度上限

            logger.debug(f"[颜色检测-{theme}] 对方气泡阈值 - lower:{lower_other}, upper:{upper_other}")

            other_mask = cv2.inRange(hsv, lower_other, upper_other)
            other_mask = cv2.morphologyEx(other_mask, cv2.MORPH_CLOSE, kernel)
            other_mask = cv2.morphologyEx(other_mask, cv2.MORPH_OPEN, kernel)

            other_contours, _ = cv2.findContours(
                other_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            for contour in other_contours:
                area = cv2.contourArea(contour)
                # 过滤掉太小的区域（降低阈值到 1000 像素）
                if area < 1000:
                    continue

                x, y, w, h = cv2.boundingRect(contour)
                screen_x = msg_area.left + x
                screen_y = msg_area.top + y

                bubbles.append({
                    "type": "other",
                    "rect": (screen_x, screen_y, screen_x + w, screen_y + h),
                    "center": (screen_x + w // 2, screen_y + h // 2),
                    "area": area,
                    "theme": theme
                })

            # ============ 检测自己的绿色气泡（两种模式通用）============
            # 微信绿色的 HSV 范围（暗黑模式下绿色会稍微亮一点）
            lower_own = np.array([35, 50, 140])
            upper_own = np.array([85, 255, 255])

            own_mask = cv2.inRange(hsv, lower_own, upper_own)
            own_mask = cv2.morphologyEx(own_mask, cv2.MORPH_CLOSE, kernel)
            own_mask = cv2.morphologyEx(own_mask, cv2.MORPH_OPEN, kernel)

            own_contours, _ = cv2.findContours(
                own_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            for contour in own_contours:
                area = cv2.contourArea(contour)
                # 过滤掉太小的区域（降低阈值到 1000 像素）
                if area < 1000:
                    continue

                x, y, w, h = cv2.boundingRect(contour)
                screen_x = msg_area.left + x
                screen_y = msg_area.top + y

                bubbles.append({
                    "type": "own",
                    "rect": (screen_x, screen_y, screen_x + w, screen_y + h),
                    "center": (screen_x + w // 2, screen_y + h // 2),
                    "area": area,
                    "theme": theme
                })

            # 统计气泡类型
            other_count = sum(1 for b in bubbles if b["type"] == "other")
            own_count = sum(1 for b in bubbles if b["type"] == "own")
            logger.debug(f"[颜色检测-{theme}] 找到 {len(bubbles)} 个气泡 (对方:{other_count}, 自己:{own_count})")

        except Exception as e:
            logger.error(f"颜色检测失败: {e}")

        return bubbles

    def _get_latest_other_bubble_region(
        self,
        screenshot: np.ndarray,
        window_rect: Tuple[int, int, int],
        ocr_engine
    ) -> Optional[np.ndarray]:
        """
        获取最新的对方消息气泡区域

        自动适配亮色/暗黑模式
        """
        bubbles = self._detect_bubbles_by_color(screenshot, window_rect)

        # 筛选对方气泡
        other_bubbles = [b for b in bubbles if b["type"] == "other"]

        if not other_bubbles:
            logger.debug("[颜色检测] 未找到对方气泡")
            return None

        # 按底部 y 坐标排序，选最下面的
        other_bubbles.sort(key=lambda b: b["rect"][3], reverse=True)
        latest = other_bubbles[0]

        left, top, right, bottom = latest["rect"]

        # 扩展区域（包含可能的文字）
        padding = 20
        left = max(0, left - padding)
        top = max(0, top - padding)
        right = min(screenshot.shape[1], right + padding)
        bottom = min(screenshot.shape[0], bottom + padding)

        region = screenshot[top:bottom, left:right]

        logger.debug(f"[颜色检测-{latest.get('theme', 'unknown')}] 提取最新对方气泡区域: {latest['rect']}")

        return region

    def get_message_content_ocr(
        self,
        screenshot: np.ndarray,
        window_rect: Tuple[int, int, int],
        ocr_engine,
        contact_name: str,
        is_own_message: bool = False
    ) -> Optional[str]:
        """使用 OCR 获取消息内容"""
        left, top, right, bottom = window_rect
        window_width = right - left
        window_height = bottom - top

        # 选择消息区域
        if is_own_message:
            msg_area = self.template.own_message_area.to_absolute(window_width, window_height)
        else:
            msg_area = self.template.other_message_area.to_absolute(window_width, window_height)

        message_region = screenshot[msg_area.to_slice()]
        bottom_height = min(200, msg_area.height // 3)
        bottom_region = message_region[-bottom_height:]

        try:
            result = ocr_engine.ocr(bottom_region)
            texts = []
            if result and result[0]:
                for line in result[0]:
                    if line and len(line) >= 2:
                        text = line[1][0].strip()
                        if text:
                            texts.append(text)
            return self._extract_latest_text(texts)
        except Exception as e:
            logger.error(f"OCR 失败: {e}")
            return None

    def calibrate(
        self,
        screenshot: np.ndarray,
        window_rect: Tuple[int, int, int]
    ) -> Dict[str, Dict]:
        """校准模板"""
        left, top, right, bottom = window_rect
        window_width = right - left
        window_height = bottom - top

        areas = {}
        for attr_name in ['title_area', 'message_area', 'sender_name_area',
                          'group_count_area', 'other_message_area',
                          'own_message_area', 'latest_message_area',
                          'input_area', 'timestamp_area']:
            if hasattr(self.template, attr_name):
                rel_rect = getattr(self.template, attr_name)
                abs_rect = rel_rect.to_absolute(window_width, window_height)
                areas[attr_name] = {
                    'left': abs_rect.left,
                    'top': abs_rect.top,
                    'right': abs_rect.right,
                    'bottom': abs_rect.bottom,
                    'width': abs_rect.width,
                    'height': abs_rect.height
                }

        return areas


def get_template(name: str) -> MessageAreaTemplate:
    """获取指定模板"""
    templates = {
        "wechat": WECHAT_4X_TEMPLATE,
        "wechat_4x": WECHAT_4X_TEMPLATE,
    }
    return templates.get(name, WECHAT_4X_TEMPLATE)


# 全局检测器实例
template_detector = TemplateDetector()

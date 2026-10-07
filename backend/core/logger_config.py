"""
日志配置模块

模块职责：
- 统一配置项目日志系统：彩色控制台输出 + 文本/错误/JSON 三类滚动文件。
- 提供多种日志格式化器（彩色、JSON、纯文本）以适配控制台与机器分析场景。
- 暴露 setup_logging() 初始化入口与 get_logger() 取用入口。
- Windows 下自动处理 emoji → ASCII 替换，避免 GBK 编码报错。
"""
import logging
import sys
import os
from pathlib import Path
from datetime import datetime
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from typing import Optional
import json

# Windows 颜色支持
try:
    import colorama
    colorama.init(autoreset=True)
    HAS_COLORAMA = True
except ImportError:
    HAS_COLORAMA = False


# AI-assisted: 使用 Claude 定义终端日志 ANSI 颜色常量表，人工校验后保留级别颜色映射
# 日志颜色代码
class LogColors:
    """终端日志颜色配置（ANSI 转义码与级别/模块/时间颜色映射）"""
    RESET = "\033[0m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    BOLD_RED = "\033[1;31m"
    BOLD_GREEN = "\033[1;32m"
    BOLD_YELLOW = "\033[1;33m"
    BOLD_BLUE = "\033[1;34m"
    BOLD_MAGENTA = "\033[1;35m"
    BOLD_CYAN = "\033[1;36m"

    # 日志级别颜色映射
    LEVEL_COLORS = {
        logging.DEBUG: CYAN,
        logging.INFO: GREEN,
        logging.WARNING: YELLOW,
        logging.ERROR: RED,
        logging.CRITICAL: BOLD_RED,
    }

    # 模块名颜色
    MODULE_COLOR = BLUE
    # 时间颜色
    TIME_COLOR = WHITE
    # 消息颜色
    MESSAGE_COLOR = RESET


# AI-assisted: 使用 Claude 实现彩色控制台日志格式化器，手动调整了 emoji 到 ASCII 的替换映射(GBK 兼容)
class ColoredFormatter(logging.Formatter):
    """彩色控制台日志格式化器（按级别着色并替换 emoji 以兼容 Windows GBK）"""

    def __init__(self, fmt: Optional[str] = None, datefmt: Optional[str] = None, use_colors: bool = True):
        """
        初始化彩色格式化器

        Args:
            fmt: 日志格式字符串
            datefmt: 时间格式字符串
            use_colors: 是否启用彩色输出
        """
        super().__init__(fmt, datefmt)
        self.use_colors = use_colors

    def format(self, record):
        """格式化日志记录：着色时手动拼接时间/级别/模块/消息；否则退回父类格式化

        Args:
            record: logging.LogRecord 实例

        Returns:
            格式化后的日志字符串
        """
        if self.use_colors:
            # 获取颜色
            level_color = LogColors.LEVEL_COLORS.get(record.levelno, LogColors.RESET)
            level_name = record.levelname.ljust(8)

            # 格式化时间
            time_str = self.formatTime(record, self.datefmt)
            colored_time = f"{LogColors.TIME_COLOR}{time_str}{LogColors.RESET}"

            # 格式化级别
            colored_level = f"{level_color}{level_name}{LogColors.RESET}"

            # 格式化模块名
            module_name = record.name.split('.')[-1] if '.' in record.name else record.name
            colored_module = f"{LogColors.MODULE_COLOR}[{module_name}]{LogColors.RESET}"

            # 格式化消息 - 移除 emoji 以兼容 Windows GBK
            message = record.getMessage()
            # 移除常见 emoji
            emoji_map = {
                '🚀': '[START]',
                '👋': '[STOP]',
                '✓': '[OK]',
                '✗': '[ERR]',
                '⚠': '[WARN]',
                '▶': '[REQ]',
                '◀': '[RES]',
                '📊': '[CHART]',
            }
            for emoji, replacement in emoji_map.items():
                message = message.replace(emoji, replacement)

            colored_message = f"{LogColors.MESSAGE_COLOR}{message}{LogColors.RESET}"

            # 组合格式
            result = f"{colored_time} {colored_level} {colored_module} {colored_message}"

            # 添加异常信息（如果有）
            if record.exc_info:
                if not record.exc_text:
                    record.exc_text = self.formatException(record.exc_info)
                result += f"\n{LogColors.RED}{record.exc_text}{LogColors.RESET}"

            return result
        else:
            return super().format(record)


# AI-assisted: 使用 Claude 实现 JSON 格式日志格式化器，手动补充了 user_id/session_id 等扩展字段
class DetailedFormatter(logging.Formatter):
    """详细的文件日志格式化器（JSON 格式，便于机器分析）"""

    def format(self, record):
        """将日志记录序列化为 JSON 字符串

        Args:
            record: logging.LogRecord 实例

        Returns:
            包含时间/级别/模块/异常等字段的 JSON 字符串
        """
        log_data = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # 添加额外字段
        if hasattr(record, 'user_id'):
            log_data['user_id'] = record.user_id
        if hasattr(record, 'session_id'):
            log_data['session_id'] = record.session_id
        if hasattr(record, 'request_id'):
            log_data['request_id'] = record.request_id

        # 添加异常信息
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False)


# AI-assisted: 使用 Claude 实现纯文本日志格式化器，未做大幅修改
class PlainTextFormatter(logging.Formatter):
    """纯文本文件日志格式化器（固定列宽对齐）"""

    def __init__(self):
        """初始化纯文本格式化器，设定固定 fmt 与 datefmt"""
        super().__init__(
            fmt='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )


# AI-assisted: 使用 Claude 实现日志目录定位与创建，未做大幅修改
def get_log_dir() -> Path:
    """获取日志目录（项目根下 logs/，不存在则自动创建）

    Returns:
        日志目录 Path 对象
    """
    # 项目根目录
    project_root = Path(__file__).parent.parent.parent
    log_dir = project_root / "logs"

    # 创建日志目录
    log_dir.mkdir(exist_ok=True)
    return log_dir


# AI-assisted: 使用 Claude 实现日志系统初始化，手动调整了三类文件处理器与第三方库日志级别
def setup_logging(
    level: int = logging.INFO,
    log_to_file: bool = True,
    log_file: Optional[str] = None,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    use_colors: bool = True
) -> None:
    """
    配置日志系统

    Args:
        level: 日志级别
        log_to_file: 是否记录到文件
        log_file: 日志文件路径（可选，默认使用自动生成的文件名）
        max_bytes: 单个日志文件最大大小
        backup_count: 保留的日志文件数量
        use_colors: 是否使用彩色输出
    """
    # 获取根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # 清除现有的处理器
    root_logger.handlers.clear()

    # 控制台处理器（彩色）
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_formatter = ColoredFormatter(use_colors=use_colors)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # 文件处理器
    if log_to_file:
        log_dir = get_log_dir()

        # 主日志文件（所有日志）
        if log_file is None:
            date_str = datetime.now().strftime("%Y%m%d")
            log_file = log_dir / f"datavis_{date_str}.log"

        # 创建主日志文件处理器（文本格式）
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(level)
        file_formatter = PlainTextFormatter()
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

        # 错误日志文件（只记录错误和严重错误）
        error_file = log_dir / "errors.log"
        error_handler = RotatingFileHandler(
            error_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_formatter = PlainTextFormatter()
        error_handler.setFormatter(error_formatter)
        root_logger.addHandler(error_handler)

        # JSON 格式日志文件（便于机器分析）
        json_file = log_dir / "datavis_json.log"
        json_handler = RotatingFileHandler(
            json_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        json_handler.setLevel(level)
        json_formatter = DetailedFormatter()
        json_handler.setFormatter(json_formatter)
        root_logger.addHandler(json_handler)

    # 配置第三方库的日志级别
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)  # 改为 INFO 以显示访问日志
    logging.getLogger("fastapi").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.INFO)  # 改为 INFO 以显示 API 调用详情

    # 记录日志系统启动
    root_logger.info("=" * 60)
    root_logger.info("日志系统初始化完成")
    root_logger.info(f"日志级别: {logging.getLevelName(level)}")
    if log_to_file:
        root_logger.info(f"日志目录: {get_log_dir()}")
    root_logger.info("=" * 60)


# AI-assisted: 使用 Claude 实现日志记录器取用封装，未做大幅修改
def get_logger(name: str) -> logging.Logger:
    """
    获取指定名称的日志记录器

    Args:
        name: 日志记录器名称（通常使用 __name__）

    Returns:
        已由 setup_logging 配置好的 logging.Logger 实例
    """
    return logging.getLogger(name)

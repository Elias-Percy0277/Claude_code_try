"""
系统托盘应用模块
"""
import webbrowser
from threading import Thread
from PIL import Image, ImageDraw
import pystray
from typing import Optional

from config.settings import settings
from core.message_handler import message_handler
from core.wechat_client import wechat_client
from utils.logger import logger

# 导入主程序的退出事件（延迟导入避免循环依赖）
_EXIT_EVENT = None


def set_exit_event(event):
    """设置退出事件"""
    global _EXIT_EVENT
    _EXIT_EVENT = event


class TrayApp:
    """系统托盘应用类"""

    def __init__(self):
        self.icon: Optional[pystray.Icon] = None
        self._running = False

    def _create_icon_image(self, paused: bool = False) -> Image.Image:
        """创建托盘图标"""
        # 创建一个简单的图标
        size = 64
        image = Image.new("RGB", (size, size), (255, 255, 255))
        draw = ImageDraw.Draw(image)

        # 绘制圆形背景
        color = (255, 193, 7) if paused else (40, 167, 69)  # 暂停黄色，运行绿色
        draw.ellipse([8, 8, size - 8, size - 8], fill=color)

        # 绘制文字
        text = "||" if paused else "AI"
        draw.text((size // 2, size // 2), text, fill="white", anchor="mm")

        return image

    def _create_menu(self) -> pystray.Menu:
        """创建右键菜单"""
        return pystray.Menu(
            pystray.MenuItem("打开管理后台", self._open_dashboard),
            pystray.MenuItem("暂停回复" if not self._paused else "恢复回复", self._toggle_pause),
            pystray.MenuItem("状态", self._show_status),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", self._quit)
        )

    def _open_dashboard(self):
        """打开管理后台"""
        host = settings.get("web.host", "127.0.0.1")
        port = settings.get("web.port", 5001)
        url = f"http://{host}:{port}"
        webbrowser.open(url)
        logger.info(f"已打开管理后台: {url}")

    def _toggle_pause(self):
        """切换暂停/恢复状态"""
        if message_handler.is_paused():
            message_handler.resume()
            self._paused = False
            self._update_icon()
            logger.info("已恢复自动回复")
        else:
            message_handler.pause()
            self._paused = True
            self._update_icon()
            logger.info("已暂停自动回复")

    def _show_status(self):
        """显示状态"""
        paused = message_handler.is_paused()
        status = "已暂停" if paused else "运行中"
        # 可以显示一个通知框
        logger.info(f"当前状态: {status}")

    def _update_icon(self):
        """更新托盘图标"""
        if self.icon:
            self.icon.icon = self._create_icon_image(self._paused)
            self.icon.menu = self._create_menu()

    def _quit(self):
        """退出程序"""
        logger.info("正在退出程序...")
        self._running = False

        # 【关键】停止微信消息监听
        if wechat_client.is_connected():
            wechat_client.stop_listening()
            logger.info("已停止微信消息监听")

        # 设置退出事件，通知主程序退出
        global _EXIT_EVENT
        if _EXIT_EVENT:
            _EXIT_EVENT.set()

        if self.icon:
            self.icon.stop()

    def start(self):
        """启动托盘应用"""
        self._paused = message_handler.is_paused()

        # 创建图标
        icon_image = self._create_icon_image(self._paused)
        menu = self._create_menu()

        self.icon = pystray.Icon(
            "wechat_custody",
            icon_image,
            "微信托管",
            menu
        )

        self._running = True

        # 在单独的线程中运行托盘
        def run_icon():
            self.icon.run()

        thread = Thread(target=run_icon, daemon=True)
        thread.start()

        logger.info("系统托盘已启动")

    def stop(self):
        """停止托盘应用"""
        if self.icon:
            self.icon.stop()
        self._running = False

    def update_status(self, paused: bool):
        """更新状态"""
        self._paused = paused
        self._update_icon()


# 全局托盘应用实例
tray_app = TrayApp()

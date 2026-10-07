"""
事件循环管理器 - 解决事件循环泄漏问题

问题：每次请求都创建新的事件循环，导致资源泄漏和性能下降
解决：使用线程本地存储复用事件循环
"""
import asyncio
import threading
from typing import TypeVar, Awaitable

T = TypeVar('T')

# 线程本地存储 - 每个线程有自己的事件循环
_loop_local = threading.local()


def get_event_loop() -> asyncio.AbstractEventLoop:
    """获取线程级事件循环（复用）"""
    if not hasattr(_loop_local, 'loop') or _loop_local.loop is None:
        _loop_local.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop_local.loop)
    return _loop_local.loop


def run_async(coro: Awaitable[T]) -> T:
    """
    运行异步函数（复用事件循环）

    替代原有的 run_async 函数，避免每次创建新循环
    """
    loop = get_event_loop()
    if loop.is_running():
        # 如果循环正在运行，在新线程中运行
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    else:
        return loop.run_until_complete(coro)


def cleanup():
    """清理资源（应用关闭时调用）"""
    if hasattr(_loop_local, 'loop') and _loop_local.loop:
        try:
            _loop_local.loop.close()
        except Exception:
            pass  # 忽略关闭时的错误
        _loop_local.loop = None

"""
请求日志中间件
记录所有 HTTP 请求和响应的详细信息

使用纯 ASGI 中间件实现，避免 BaseHTTPMiddleware 对 SSE 流式响应的缓冲问题。
BaseHTTPMiddleware 内部使用 anyio.MemoryObjectStream 缓冲响应体，
导致 SSE 事件被积压直到生成器完全结束才一次性发送给客户端。
纯 ASGI 实现直接透传所有响应数据，不做任何缓冲。
"""
import time
import uuid
import json
import logging
from typing import Callable
from fastapi import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send
import logging

from .logger_config import get_logger

logger = get_logger(__name__)

# SSE 流式端点路径集合（这些端点使用 StreamingResponse，需要特殊处理）
SSE_PATHS = {"/api/analysis"}


class RequestLoggingMiddleware:
    """
    纯 ASGI 请求日志中间件

    不继承 BaseHTTPMiddleware，直接实现 __call__ 接口。
    所有响应体数据（包括 SSE 事件流）直接透传，不做缓冲。
    仅拦截 http.response.start 消息来记录响应状态码和耗时。
    """

    def __init__(self, app: ASGIApp):
        self.app = app
        self.logger = logger

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        # 非 HTTP 请求（WebSocket、lifespan 等）直接透传
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid.uuid4())[:8]
        start_time = time.time()

        # 提取请求基本信息
        path = scope.get("path", "")
        method = scope.get("method", "")

        # 判断是否为 SSE 流式端点
        is_sse = path in SSE_PATHS and method == "POST"

        # 记录请求信息
        self._log_request(scope, request_id)

        # 标记响应是否已记录（防止重复记录）
        response_logged = False

        async def send_with_logging(message: Message):
            """包装 send 回调：拦截响应头用于日志，其余数据直接透传"""
            nonlocal response_logged

            if message["type"] == "http.response.start" and not response_logged:
                response_logged = True
                status_code = message.get("status", 0)
                process_time = time.time() - start_time

                # SSE 端点使用不同的日志格式
                if is_sse:
                    self.logger.info(
                        f"[RES] [{request_id}] [SSE] Status: {status_code} "
                        f"(streaming started at {process_time * 1000:.1f}ms)"
                    )
                else:
                    self._log_response_from_status(
                        path, status_code, request_id, process_time
                    )

                # 注入自定义响应头（X-Request-ID、X-Process-Time）
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                if not is_sse:
                    # SSE 端点不注入 Process-Time，因为此时响应尚未完成
                    headers.append(
                        (b"x-process-time", f"{process_time:.3f}".encode())
                    )
                message = {**message, "headers": headers}

            # 关键：直接将消息转发给真实的 send，不做任何缓冲
            await send(message)

        try:
            await self.app(scope, receive, send_with_logging)
        except Exception as e:
            # 记录异常（仅在响应头尚未发送时）
            process_time = time.time() - start_time
            if not response_logged:
                self._log_error(path, e, request_id, process_time)
            raise

    def _log_request(self, scope: Scope, request_id: str):
        """记录请求信息（从 ASGI scope 提取，不消费 request body）"""
        method = scope.get("method", "")
        path = scope.get("path", "")
        query_string = scope.get("query_string", b"").decode("utf-8", errors="ignore")

        # 基本信息
        log_parts = [
            f"▶ [{request_id}]",
            method,
            path,
        ]

        # 添加查询参数
        if query_string:
            log_parts.append(f"?{query_string}")

        self.logger.info(" ".join(log_parts))

        # 详细信息（DEBUG 级别）
        if self.logger.isEnabledFor(logging.DEBUG):
            headers = dict(scope.get("headers", []))
            client = scope.get("client")
            client_ip = f"{client[0]}:{client[1]}" if client else "unknown"
            user_agent = ""
            for key, val in scope.get("headers", []):
                if key == b"user-agent":
                    user_agent = val.decode("utf-8", errors="ignore")
                    break
            self.logger.debug(f"  ├─ Client: {client_ip}")
            self.logger.debug(f"  ├─ User-Agent: {user_agent}")

    def _log_response_from_status(
        self, path: str, status_code: int, request_id: str, process_time: float
    ):
        """根据状态码记录响应信息"""
        if status_code < 300:
            log_func = self.logger.info
            status_symbol = "✓"
        elif status_code < 400:
            log_func = self.logger.warning
            status_symbol = "↻"
        elif status_code < 500:
            log_func = self.logger.error
            status_symbol = "✗"
        else:
            log_func = self.logger.critical
            status_symbol = "⚠"

        log_parts = [
            f"◀ [{request_id}]",
            status_symbol,
            f"Status: {status_code}",
            f"Time: {process_time * 1000:.1f}ms",
        ]

        log_func(" ".join(log_parts))

    def _log_error(
        self, path: str, error: Exception, request_id: str, process_time: float
    ):
        """记录错误信息"""
        self.logger.error(
            f"✗ [{request_id}] Error: {type(error).__name__}: {str(error)} "
            f"(Time: {process_time * 1000:.1f}ms)"
        )


class FileUploadLogger:
    """文件上传专用日志记录器"""

    @staticmethod
    def log_upload_start(files: list, session_id: str = None):
        """记录上传开始"""
        file_info = ", ".join([f"{f.filename} ({f.size/1024:.1f}KB)" for f in files])
        logger.info(f"[UPLOAD] 文件上传开始 | 文件: {file_info} {f'| Session: {session_id}' if session_id else ''}")

    @staticmethod
    def log_upload_success(files: list, session_id: str, total_rows: int):
        """记录上传成功"""
        logger.info(f"[UPLOAD] 文件上传成功 | Session: {session_id} | 文件数: {len(files)} | 总行数: {total_rows}")

    @staticmethod
    def log_data_processing(stage: str, details: dict):
        """记录数据处理阶段"""
        details_str = " | ".join([f"{k}: {v}" for k, v in details.items()])
        logger.debug(f"[PROCESS] 数据处理 | {stage} | {details_str}")

    @staticmethod
    def log_names_parsing(filename: str, attributes_count: int):
        """记录 .names 文件解析"""
        logger.info(f"[NAMES] .names 文件解析 | 文件: {filename} | 属性数: {attributes_count}")

    @staticmethod
    def log_column_mapping(data_columns: int, names_attributes: int, mapped: bool):
        """记录列名映射"""
        if mapped:
            logger.info(f"[MAP] 列名映射 | 数据列数: {data_columns} | 属性数: {names_attributes} | [OK] 已应用")
        else:
            logger.warning(f"[MAP] 列名映射 | 数据列数: {data_columns} | 属性数: {names_attributes} | [SKIP] 数量不匹配，跳过")


class AnalysisLogger:
    """分析请求专用日志记录器"""

    @staticmethod
    def log_analysis_start(session_id: str, query: str):
        """记录分析开始"""
        query_short = query[:50] + "..." if len(query) > 50 else query
        logger.info(f"[ANALYSIS] 分析请求 | Session: {session_id} | Query: \"{query_short}\"")

    @staticmethod
    def log_intent_parsed(intents: list):
        """记录意图解析结果"""
        intents_str = ", ".join([f"{i['intent']}" for i in intents])
        logger.debug(f"[INTENT] 意图解析 | 识别到: {intents_str}")

    @staticmethod
    def log_analysis_complete(session_id: str, charts_count: int, cache_hit: bool = False):
        """记录分析完成"""
        cache_info = " [缓存]" if cache_hit else ""
        logger.info(f"[ANALYSIS] 分析完成 | Session: {session_id} | 图表数: {charts_count}{cache_info}")

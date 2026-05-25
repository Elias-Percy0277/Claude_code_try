"""
请求日志中间件
记录所有 HTTP 请求和响应的详细信息
"""
import time
import uuid
import json
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import logging

from .logger_config import get_logger

logger = get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    请求日志中间件
    记录请求和响应的详细信息
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.logger = logger

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 生成请求ID
        request_id = str(uuid.uuid4())[:8]
        start_time = time.time()

        # 记录请求信息
        self._log_request(request, request_id)

        # 处理请求
        try:
            response = await call_next(request)

            # 计算处理时间
            process_time = time.time() - start_time

            # 记录响应信息
            self._log_response(request, response, request_id, process_time)

            # 添加自定义响应头
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = f"{process_time:.3f}"

            return response

        except Exception as e:
            # 记录异常
            process_time = time.time() - start_time
            self._log_error(request, e, request_id, process_time)
            raise

    def _log_request(self, request: Request, request_id: str):
        """记录请求信息"""
        client_ip = self._get_client_ip(request)

        # 基本信息
        log_parts = [
            f"▶ [{request_id}]",
            f"{request.method}",
            f"{request.url.path}",
        ]

        # 添加查询参数（如果有）
        if request.query_params:
            log_parts.append(f"?{dict(request.query_params)}")

        self.logger.info(" ".join(log_parts))

        # 详细信息（DEBUG级别）
        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug(f"  ├─ Client: {client_ip}")
            self.logger.debug(f"  ├─ User-Agent: {request.headers.get('user-agent', 'N/A')}")
            self.logger.debug(f"  └─ Headers: {self._format_headers(request.headers)}")

        # 记录请求体（对于 POST/PUT/PATCH 请求）
        if request.method in ("POST", "PUT", "PATCH"):
            self._log_request_body(request, request_id)

    def _log_response(self, request: Request, response: Response, request_id: str, process_time: float):
        """记录响应信息"""
        status_code = response.status_code

        # 根据状态码选择日志级别
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
            f"Time: {process_time*1000:.1f}ms"
        ]

        log_func(" ".join(log_parts))

    def _log_error(self, request: Request, error: Exception, request_id: str, process_time: float):
        """记录错误信息"""
        self.logger.error(
            f"✗ [{request_id}] Error: {type(error).__name__}: {str(error)} "
            f"(Time: {process_time*1000:.1f}ms)"
        )

    def _log_request_body(self, request: Request, request_id: str):
        """记录请求体（如果有且不是文件上传）"""
        content_type = request.headers.get("content-type", "")

        # 跳过文件上传
        if "multipart/form-data" in content_type:
            self.logger.debug(f"  └─ Body: [File Upload]")
            return

        # 跳过大型请求体
        content_length = int(request.headers.get("content-length", 0))
        if content_length > 1024:  # 大于1KB的请求体只记录摘要
            self.logger.debug(f"  └─ Body Size: {content_length} bytes")
            return

        # 对于其他内容类型，尝试记录请求体
        try:
            # 注意：这会消耗请求体，需要重新创建
            body = request._body

            if body:
                try:
                    body_json = json.loads(body)
                    self.logger.debug(f"  └─ Body: {json.dumps(body_json, ensure_ascii=False)}")
                except json.JSONDecodeError:
                    # 不是JSON格式
                    body_str = body.decode('utf-8', errors='ignore')
                    self.logger.debug(f"  └─ Body: {body_str[:200]}")
        except Exception as e:
            self.logger.debug(f"  └─ Body: [Unable to read: {e}]")

    def _get_client_ip(self, request: Request) -> str:
        """获取客户端IP地址"""
        # 尝试从各种头部获取真实IP
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()

        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip

        return request.client.host if request.client else "unknown"

    def _format_headers(self, headers: dict) -> dict:
        """格式化请求头（过滤敏感信息）"""
        sensitive_headers = {"authorization", "cookie", "set-cookie"}
        return {
            k: (v if k.lower() not in sensitive_headers else "***")
            for k, v in headers.items()
        }


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

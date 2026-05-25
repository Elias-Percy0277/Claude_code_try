"""
FastAPI 应用入口
DataVis 交互式数据分析平台
"""
import os
import logging

# 必须在导入其他模块之前配置日志
from backend.core.logger_config import setup_logging, get_logger

# 配置日志系统（必须在导入 uvicorn 之前）
setup_logging(
    level=logging.INFO,  # 可通过环境变量 LOG_LEVEL 覆盖
    log_to_file=True,
    use_colors=True
)

# 加载 .env 文件
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from backend.models.schemas import ErrorResponse, ErrorDetail, ErrorCode, SuccessResponse
from backend.core.logging_middleware import RequestLoggingMiddleware
import uvicorn

# 获取应用日志记录器
logger = get_logger(__name__)


# 创建 FastAPI 应用实例
app = FastAPI(
    title="DataVis API",
    description="交互式数据分析平台 - 自然语言驱动数据分析",
    version="1.0.0"
)


# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 添加请求日志中间件
app.add_middleware(RequestLoggingMiddleware)


# ============ 启动和关闭事件 ============
@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    logger.info("=" * 60)
    logger.info("[START] DataVis API 启动中...")
    logger.info(f"   版本: {app.version}")
    logger.info(f"   环境: {os.getenv('ENV', 'development')}")
    logger.info("=" * 60)


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭事件"""
    logger.info("=" * 60)
    logger.info("[STOP] DataVis API 正在关闭...")
    logger.info("=" * 60)


# ============ 健康检查端点 ============
@app.get("/health", response_model=SuccessResponse)
async def health_check():
    """健康检查端点"""
    return SuccessResponse(
        success=True,
        data={"status": "ok", "service": "datavis"},
        message="Service is running"
    )


@app.get("/", response_model=SuccessResponse)
async def root():
    """根路径"""
    return SuccessResponse(
        success=True,
        data={"message": "Welcome to DataVis API"},
        message="DataVis 交互式数据分析平台"
    )


# ============ 异常处理器 ============
class DataVisException(Exception):
    """自定义异常基类"""
    def __init__(self, code: str, message: str, detail: dict = None):
        self.code = code
        self.message = message
        self.detail = detail or {}
        super().__init__(message)


@app.exception_handler(DataVisException)
async def datavis_exception_handler(request, exc: DataVisException):
    """处理自定义异常"""
    return JSONResponse(
        status_code=400,
        content=ErrorResponse(
            success=False,
            error=ErrorDetail(
                code=exc.code,
                message=exc.message,
                detail=exc.detail
            )
        ).model_dump()
    )


# ============ API 路由注册 ============
from backend.api import upload, analysis, session

app.include_router(upload.router, prefix="/api", tags=["upload"])
app.include_router(analysis.router, prefix="/api", tags=["analysis"])
app.include_router(session.router, prefix="/api", tags=["session"])


if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )

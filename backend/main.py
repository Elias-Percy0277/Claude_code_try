"""
FastAPI 应用入口

模块职责：
- DataVis 交互式数据分析平台的启动入口与全局装配。
- 最先初始化日志系统，随后加载环境变量并创建 FastAPI 应用。
- 注册 CORS、请求日志中间件，定义健康检查/根路径/异常处理，并挂载各业务路由。
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
# AI-assisted: 使用 Claude 实现应用启动事件钩子，未做大幅修改
@app.on_event("startup")
async def startup_event():
    """应用启动事件：打印版本与环境的启动分隔日志"""
    logger.info("=" * 60)
    logger.info("[START] DataVis API 启动中...")
    logger.info(f"   版本: {app.version}")
    logger.info(f"   环境: {os.getenv('ENV', 'development')}")
    logger.info("=" * 60)


# AI-assisted: 使用 Claude 实现应用关闭事件钩子，未做大幅修改
@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭事件：打印关闭分隔日志"""
    logger.info("=" * 60)
    logger.info("[STOP] DataVis API 正在关闭...")
    logger.info("=" * 60)


# ============ 健康检查端点 ============
# AI-assisted: 使用 Claude 实现健康检查端点，未做大幅修改
@app.get("/health", response_model=SuccessResponse)
async def health_check():
    """健康检查端点：返回服务运行状态"""
    return SuccessResponse(
        success=True,
        data={"status": "ok", "service": "datavis"},
        message="Service is running"
    )


# AI-assisted: 使用 Claude 实现根路径欢迎端点，未做大幅修改
@app.get("/", response_model=SuccessResponse)
async def root():
    """根路径：返回欢迎信息"""
    return SuccessResponse(
        success=True,
        data={"message": "Welcome to DataVis API"},
        message="DataVis 交互式数据分析平台"
    )


# ============ 异常处理器 ============
# AI-assisted: 使用 Claude 定义项目自定义异常基类，未做大幅修改
class DataVisException(Exception):
    """自定义异常基类（携带错误码与详情，用于统一错误响应）"""
    def __init__(self, code: str, message: str, detail: dict = None):
        """初始化自定义异常

        Args:
            code: 错误码（对应 ErrorCode 常量）
            message: 错误信息
            detail: 详细错误信息字典，默认空字典
        """
        self.code = code
        self.message = message
        self.detail = detail or {}
        super().__init__(message)


# AI-assisted: 使用 Claude 实现自定义异常处理器，人工校验后保留 400 状态码与 ErrorResponse 封装
@app.exception_handler(DataVisException)
async def datavis_exception_handler(request, exc: DataVisException):
    """处理自定义异常，转换为统一的 ErrorResponse 并返回 400

    Args:
        request: FastAPI Request 对象
        exc: 抛出的 DataVisException 实例

    Returns:
        携带错误详情的 JSONResponse
    """
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

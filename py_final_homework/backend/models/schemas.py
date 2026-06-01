"""
Pydantic 数据模型定义
统一错误响应格式和请求数据模型
"""
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """错误详情"""
    code: str = Field(..., description="错误码")
    message: str = Field(..., description="错误信息")
    detail: Dict[str, Any] = Field(default_factory=dict, description="详细错误信息")


class ErrorResponse(BaseModel):
    """统一错误响应格式"""
    success: bool = Field(default=False, description="请求状态")
    error: ErrorDetail = Field(..., description="错误详情")


class SuccessResponse(BaseModel):
    """统一成功响应格式"""
    success: bool = Field(default=True, description="请求状态")
    data: Optional[Dict[str, Any]] = Field(default=None, description="响应数据")
    message: Optional[str] = Field(default=None, description="响应消息")


# ============ 错误码定义 ============
class ErrorCode:
    """错误码常量"""
    INVALID_FILE_FORMAT = "INVALID_FILE_FORMAT"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    FILE_PARSE_FAILED = "FILE_PARSE_FAILED"
    NO_ANALYZABLE_COLUMNS = "NO_ANALYZABLE_COLUMNS"
    LLM_PARSE_ERROR = "LLM_PARSE_ERROR"
    ANALYSIS_FAILED = "ANALYSIS_FAILED"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    API_RATE_LIMIT = "API_RATE_LIMIT"


# ============ 请求模型 ============
class DatasetInfo(BaseModel):
    """数据集信息"""
    dataset_id: str
    dataset_name: str
    original_filename: str
    row_count: int
    columns: List[str]


class UploadResponse(BaseModel):
    """文件上传响应"""
    success: bool
    session_id: str
    datasets: List[DatasetInfo]
    dataset_count: int
    total_rows: int
    message: Optional[str] = None


class AnalysisRequest(BaseModel):
    """分析请求"""
    session_id: str = Field(..., description="会话ID")
    query: str = Field(..., description="用户自然语言查询")


class TaskInfo(BaseModel):
    """分析任务信息"""
    intent: str = Field(..., description="意图类型")
    target_columns: List[str] = Field(default_factory=list, description="目标列名")
    groupby: Optional[str] = Field(default=None, description="分组列名")
    params: Dict[str, Any] = Field(default_factory=dict, description="参数")


class IntentParseResult(BaseModel):
    """意图解析结果"""
    confidence: float = Field(..., description="解析置信度 0-1")
    tasks: List[TaskInfo] = Field(..., description="分析任务列表")
    warning: Optional[str] = Field(default=None, description="警告信息")


class ChartOption(BaseModel):
    """图表配置"""
    chart_type: str = Field(..., description="图表类型")
    option: Dict[str, Any] = Field(..., description="ECharts 配置")
    title: str = Field(default="", description="图表标题")


class AnalysisResult(BaseModel):
    """分析结果"""
    summary: str = Field(..., description="分析摘要")
    charts: List[ChartOption] = Field(default_factory=list, description="图表列表")
    statistics: Optional[Dict[str, Any]] = Field(default=None, description="统计信息")


class SessionInfo(BaseModel):
    """会话信息"""
    session_id: str
    valid: bool = True
    created_at: Optional[str] = None
    last_accessed: Optional[str] = None
    datasets: List[DatasetInfo] = Field(default_factory=list)
    dataset_count: int = 0
    total_rows: int = 0


class ColumnInfo(BaseModel):
    """列信息"""
    dtype: str = Field(..., description="数据类型")
    nullable: bool = Field(default=False, description="是否可为空")
    nunique: Optional[int] = Field(default=None, description="唯一值数量")


class RechartRequest(BaseModel):
    """图表类型切换请求"""
    session_id: str = Field(..., description="会话ID")
    query: str = Field(..., description="原始查询文本")
    chart_type: str = Field(..., description="目标图表类型")


class SessionMeta(BaseModel):
    """会话元数据"""
    session_id: str
    created_at: str
    last_accessed: str
    file_hash: str
    original_filename: str
    columns_info: Dict[str, ColumnInfo]
    row_count: int
    chat_history: List[Dict[str, Any]] = Field(default_factory=list)

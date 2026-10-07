"""
Pydantic 数据模型定义

模块职责：
- 定义贯穿 DataVis 后端的统一响应/请求/结果数据模型。
- 统一成功(SuccessResponse)与错误(ErrorResponse)响应结构及错误码常量。
- 覆盖上传、分析、图表、会话、列信息等业务场景的序列化模型。
"""
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


# AI-assisted: 使用 Claude 定义错误详情模型，未做大幅修改
class ErrorDetail(BaseModel):
    """错误详情（错误码 + 错误信息 + 详细信息字典）"""
    code: str = Field(..., description="错误码")
    message: str = Field(..., description="错误信息")
    detail: Dict[str, Any] = Field(default_factory=dict, description="详细错误信息")


# AI-assisted: 使用 Claude 定义统一错误响应模型，未做大幅修改
class ErrorResponse(BaseModel):
    """统一错误响应格式（success=False + error 详情）"""
    success: bool = Field(default=False, description="请求状态")
    error: ErrorDetail = Field(..., description="错误详情")


# AI-assisted: 使用 Claude 定义统一成功响应模型，未做大幅修改
class SuccessResponse(BaseModel):
    """统一成功响应格式（success=True + 可选 data/message）"""
    success: bool = Field(default=True, description="请求状态")
    data: Optional[Dict[str, Any]] = Field(default=None, description="响应数据")
    message: Optional[str] = Field(default=None, description="响应消息")


# ============ 错误码定义 ============
# AI-assisted: 使用 Claude 定义项目错误码常量，未做大幅修改
class ErrorCode:
    """错误码常量（与 ErrorResponse.code 配合使用的字符串标识）"""
    INVALID_FILE_FORMAT = "INVALID_FILE_FORMAT"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    FILE_PARSE_FAILED = "FILE_PARSE_FAILED"
    NO_ANALYZABLE_COLUMNS = "NO_ANALYZABLE_COLUMNS"
    LLM_PARSE_ERROR = "LLM_PARSE_ERROR"
    ANALYSIS_FAILED = "ANALYSIS_FAILED"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    API_RATE_LIMIT = "API_RATE_LIMIT"


# ============ 请求模型 ============
# AI-assisted: 使用 Claude 定义数据集信息模型，未做大幅修改
class DatasetInfo(BaseModel):
    """数据集信息（ID、名称、原始文件名、行数与列名列表）"""
    dataset_id: str
    dataset_name: str
    original_filename: str
    row_count: int
    columns: List[str]


# AI-assisted: 使用 Claude 定义文件上传响应模型，未做大幅修改
class UploadResponse(BaseModel):
    """文件上传响应（会话 ID + 数据集列表 + 汇总统计）"""
    success: bool
    session_id: str
    datasets: List[DatasetInfo]
    dataset_count: int
    total_rows: int
    message: Optional[str] = None


# AI-assisted: 使用 Claude 定义分析请求模型，未做大幅修改
class AnalysisRequest(BaseModel):
    """分析请求（会话 ID + 用户自然语言查询）"""
    session_id: str = Field(..., description="会话ID")
    query: str = Field(..., description="用户自然语言查询")


# AI-assisted: 使用 Claude 定义分析任务信息模型，未做大幅修改
class TaskInfo(BaseModel):
    """分析任务信息（意图 + 目标列 + 分组列 + 参数）"""
    intent: str = Field(..., description="意图类型")
    target_columns: List[str] = Field(default_factory=list, description="目标列名")
    groupby: Optional[str] = Field(default=None, description="分组列名")
    params: Dict[str, Any] = Field(default_factory=dict, description="参数")


# AI-assisted: 使用 Claude 定义意图解析结果模型，未做大幅修改
class IntentParseResult(BaseModel):
    """意图解析结果（置信度 + 任务列表 + 可选警告）"""
    confidence: float = Field(..., description="解析置信度 0-1")
    tasks: List[TaskInfo] = Field(..., description="分析任务列表")
    warning: Optional[str] = Field(default=None, description="警告信息")


# AI-assisted: 使用 Claude 定义图表配置模型，未做大幅修改
class ChartOption(BaseModel):
    """图表配置（类型 + ECharts option + 标题）"""
    chart_type: str = Field(..., description="图表类型")
    option: Dict[str, Any] = Field(..., description="ECharts 配置")
    title: str = Field(default="", description="图表标题")


# AI-assisted: 使用 Claude 定义分析结果模型，未做大幅修改
class AnalysisResult(BaseModel):
    """分析结果（摘要 + 图表列表 + 可选统计信息）"""
    summary: str = Field(..., description="分析摘要")
    charts: List[ChartOption] = Field(default_factory=list, description="图表列表")
    statistics: Optional[Dict[str, Any]] = Field(default=None, description="统计信息")


# AI-assisted: 使用 Claude 定义会话信息模型，未做大幅修改
class SessionInfo(BaseModel):
    """会话信息（会话 ID + 有效性 + 数据集汇总）"""
    session_id: str
    valid: bool = True
    created_at: Optional[str] = None
    last_accessed: Optional[str] = None
    datasets: List[DatasetInfo] = Field(default_factory=list)
    dataset_count: int = 0
    total_rows: int = 0


# AI-assisted: 使用 Claude 定义列信息模型，未做大幅修改
class ColumnInfo(BaseModel):
    """列信息（数据类型 + 是否可空 + 唯一值数量）"""
    dtype: str = Field(..., description="数据类型")
    nullable: bool = Field(default=False, description="是否可为空")
    nunique: Optional[int] = Field(default=None, description="唯一值数量")


# AI-assisted: 使用 Claude 定义图表类型切换请求模型，未做大幅修改
class RechartRequest(BaseModel):
    """图表类型切换请求（会话 ID + 原始查询 + 目标图表类型）"""
    session_id: str = Field(..., description="会话ID")
    query: str = Field(..., description="原始查询文本")
    chart_type: str = Field(..., description="目标图表类型")


# AI-assisted: 使用 Claude 定义会话元数据模型，未做大幅修改
class SessionMeta(BaseModel):
    """会话元数据（创建/访问时间 + 文件哈希 + 列信息 + 聊天历史）"""
    session_id: str
    created_at: str
    last_accessed: str
    file_hash: str
    original_filename: str
    columns_info: Dict[str, ColumnInfo]
    row_count: int
    chat_history: List[Dict[str, Any]] = Field(default_factory=list)

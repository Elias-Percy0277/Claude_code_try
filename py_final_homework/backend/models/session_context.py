"""
会话上下文模型
维护每个会话的数据画像、分析历史和最近操作结果
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.core.operations import OPERATION_REGISTRY


@dataclass
class DataProfile:
    """数据集画像"""
    columns: List[str] = field(default_factory=list)
    dtypes: Dict[str, str] = field(default_factory=dict)
    numeric_columns: List[str] = field(default_factory=list)
    categorical_columns: List[str] = field(default_factory=list)
    datetime_columns: List[str] = field(default_factory=list)
    unique_values_preview: Dict[str, List[str]] = field(default_factory=dict)
    row_count: int = 0
    column_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "columns": self.columns,
            "dtypes": self.dtypes,
            "numeric_columns": self.numeric_columns,
            "categorical_columns": self.categorical_columns,
            "datetime_columns": self.datetime_columns,
            "unique_values_preview": self.unique_values_preview,
            "row_count": self.row_count,
            "column_count": self.column_count,
        }

    def to_prompt_text(self) -> str:
        lines = [
            f"数据集共 {self.row_count} 行、{self.column_count} 列。",
            "列信息：",
        ]
        for col in self.columns:
            dtype = self.dtypes.get(col, "unknown")
            line = f"  - {col}: {dtype}"
            if col in self.unique_values_preview:
                preview = ", ".join(self.unique_values_preview[col][:5])
                line += f" (示例值: {preview})"
            lines.append(line)
        if self.numeric_columns:
            lines.append(f"数值列: {', '.join(self.numeric_columns)}")
        if self.categorical_columns:
            lines.append(f"分类列: {', '.join(self.categorical_columns)}")
        if self.datetime_columns:
            lines.append(f"日期列: {', '.join(self.datetime_columns)}")
        return "\n".join(lines)


@dataclass
class AnalysisStep:
    """已完成的分析步骤"""
    step: int
    operation: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step,
            "operation": self.operation,
            "parameters": self.parameters,
            "summary": self.summary,
        }


@dataclass
class OperationResult:
    """操作执行结果"""
    operation: str
    status: str = "success"  # "success" | "error"
    statistics: Dict[str, Any] = field(default_factory=dict)
    chart_options: List[Dict[str, Any]] = field(default_factory=list)
    summary_text: str = ""
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "operation": self.operation,
            "status": self.status,
            "statistics": self.statistics,
            "chart_options": self.chart_options,
            "summary_text": self.summary_text,
        }
        if self.error_message:
            result["error_message"] = self.error_message
        return result

    def to_prompt_text(self) -> str:
        if self.status == "error":
            return f"操作 {self.operation} 失败: {self.error_message}"
        lines = [f"操作: {self.operation}"]
        if self.statistics:
            lines.append("统计结果:")
            for key, value in self.statistics.items():
                if isinstance(value, dict):
                    lines.append(f"  {key}:")
                    for k, v in value.items():
                        lines.append(f"    {k}: {v}")
                else:
                    lines.append(f"  {key}: {value}")
        if self.summary_text:
            lines.append(f"摘要: {self.summary_text[:200]}")
        return "\n".join(lines)


@dataclass
class SessionContext:
    """会话上下文：贯穿每次 Agent 调用"""
    data_id: str = ""
    data_profile: DataProfile = field(default_factory=DataProfile)
    available_operations: List[Dict[str, Any]] = field(default_factory=lambda: list(OPERATION_REGISTRY))
    analysis_history: List[AnalysisStep] = field(default_factory=list)
    last_operation_result: Optional[OperationResult] = None

    def update_with_result(self, result: OperationResult):
        """操作完成后更新历史和最后结果"""
        step_num = len(self.analysis_history) + 1
        self.analysis_history.append(AnalysisStep(
            step=step_num,
            operation=result.operation,
            summary=result.summary_text[:100] if result.summary_text else "",
        ))
        self.last_operation_result = result

    def to_dict(self) -> Dict[str, Any]:
        return {
            "data_id": self.data_id,
            "data_profile": self.data_profile.to_dict(),
            "analysis_history": [s.to_dict() for s in self.analysis_history],
            "last_operation_result": self.last_operation_result.to_dict() if self.last_operation_result else None,
        }

    def to_prompt_dict(self) -> Dict[str, Any]:
        """生成 LLM 友好的上下文字典"""
        ops_desc = []
        for op in self.available_operations:
            ops_desc.append(f"{op['name']}: {op['description']}")

        history_text = ""
        if self.analysis_history:
            lines = []
            for step in self.analysis_history:
                lines.append(f"步骤{step.step}: {step.operation} - {step.summary}")
            history_text = "\n".join(lines)
        else:
            history_text = "尚无分析历史"

        last_result_text = ""
        if self.last_operation_result:
            last_result_text = self.last_operation_result.to_prompt_text()
        else:
            last_result_text = "无"

        return {
            "data_profile": self.data_profile.to_prompt_text(),
            "available_operations": "\n".join(ops_desc),
            "analysis_history": history_text,
            "last_operation_result": last_result_text,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionContext":
        profile_data = data.get("data_profile", {})
        data_profile = DataProfile(
            columns=profile_data.get("columns", []),
            dtypes=profile_data.get("dtypes", {}),
            numeric_columns=profile_data.get("numeric_columns", []),
            categorical_columns=profile_data.get("categorical_columns", []),
            datetime_columns=profile_data.get("datetime_columns", []),
            unique_values_preview=profile_data.get("unique_values_preview", {}),
            row_count=profile_data.get("row_count", 0),
            column_count=profile_data.get("column_count", 0),
        )
        history = []
        for h in data.get("analysis_history", []):
            history.append(AnalysisStep(
                step=h.get("step", 0),
                operation=h.get("operation", ""),
                parameters=h.get("parameters", {}),
                summary=h.get("summary", ""),
            ))
        last_result = None
        lr = data.get("last_operation_result")
        if lr:
            last_result = OperationResult(
                operation=lr.get("operation", ""),
                status=lr.get("status", "success"),
                statistics=lr.get("statistics", {}),
                chart_options=lr.get("chart_options", []),
                summary_text=lr.get("summary_text", ""),
                error_message=lr.get("error_message"),
            )
        return cls(
            data_id=data.get("data_id", ""),
            data_profile=data_profile,
            analysis_history=history,
            last_operation_result=last_result,
        )

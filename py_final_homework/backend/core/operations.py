"""
操作注册表
定义所有可用的后端数据分析操作，供 Agent1（规划调度）和 Agent2（分析顾问）共享
"""
import logging
from typing import Dict, List, Any, Optional

import pandas as pd

logger = logging.getLogger(__name__)

OPERATION_REGISTRY = [
    {
        "name": "overview",
        "description": "数据概览 - 展示数据集基本信息、列类型、缺失值统计、基础统计量",
        "parameters": [],
        "required_columns": [],
    },
    {
        "name": "trend",
        "description": "趋势分析 - 数值列的变化趋势、线性回归斜率、变化率、R²拟合优度",
        "parameters": ["columns", "chart_type"],
        "required_columns": ["至少一个数值列"],
    },
    {
        "name": "distribution",
        "description": "分布分析 - 直方图、箱线图、异常值检测、均值/中位数/标准差/分位数",
        "parameters": ["column", "chart_type"],
        "required_columns": ["一个数值列"],
    },
    {
        "name": "comparison",
        "description": "分组对比 - 按分类变量分组对比数值差异（含ANOVA检验），支持交叉表/列联表分析",
        "parameters": ["target_columns", "groupby", "groupby2", "chart_type"],
        "required_columns": ["一个数值列或分类列 + 一个分组列"],
    },
    {
        "name": "correlation",
        "description": "相关性分析 - 数值列间的Pearson/Spearman相关系数矩阵、热力图、散点图",
        "parameters": ["columns", "chart_type"],
        "required_columns": ["至少两个数值列"],
    },
    {
        "name": "moving_avg",
        "description": "移动平均 - SMA简单移动平均/EMA指数移动平均平滑处理",
        "parameters": ["column", "window", "chart_type"],
        "required_columns": ["一个数值列"],
    },
    {
        "name": "seasonality",
        "description": "季节性分解 - 时间序列STL分解为趋势/季节/残差分量（需要日期列和statsmodels）",
        "parameters": ["column", "chart_type"],
        "required_columns": ["一个数值列 + 一个日期列"],
    },
]

# 用于 LLM prompt 的操作名集合
OPERATION_NAMES = {op["name"] for op in OPERATION_REGISTRY}


def get_operations_description() -> str:
    """生成 LLM 可读的操作清单描述"""
    lines = []
    for op in OPERATION_REGISTRY:
        params = ", ".join(op["parameters"]) if op["parameters"] else "无"
        lines.append(f"- {op['name']}: {op['description']} (参数: {params})")
    return "\n".join(lines)


def get_operation(name: str) -> Optional[Dict[str, Any]]:
    """按名称查找操作定义"""
    for op in OPERATION_REGISTRY:
        if op["name"] == name:
            return op
    return None


def validate_operation(name: str, params: dict, df: pd.DataFrame) -> Dict[str, Any]:
    """
    验证操作参数是否合法，返回校验结果

    Returns:
        {"valid": bool, "errors": [str], "warnings": [str]}
    """
    result = {"valid": True, "errors": [], "warnings": []}

    op = get_operation(name)
    if not op:
        result["valid"] = False
        result["errors"].append(f"未知操作: {name}")
        return result

    actual_columns = set(df.columns.tolist())
    numeric_cols = set(df.select_dtypes(include=["number"]).columns.tolist())
    categorical_cols = set(df.select_dtypes(include=["object", "category"]).columns.tolist())
    datetime_cols = set(df.select_dtypes(include=["datetime64"]).columns.tolist())

    if name == "correlation":
        cols = params.get("columns", [])
        if cols:
            invalid = set(cols) - actual_columns
            if invalid:
                result["warnings"].append(f"列不存在: {invalid}，将使用可用数值列")
            numeric_requested = [c for c in cols if c in numeric_cols]
            if len(numeric_requested) < 2:
                result["valid"] = False
                result["errors"].append("相关性分析至少需要2个数值列")
        elif len(numeric_cols) < 2:
            result["valid"] = False
            result["errors"].append(f"数据集数值列不足({len(numeric_cols)}个)，相关性分析需要至少2个")

    elif name == "seasonality":
        if not datetime_cols:
            result["valid"] = False
            result["errors"].append("季节性分解需要至少一个日期列")
        if not numeric_cols:
            result["valid"] = False
            result["errors"].append("季节性分解需要至少一个数值列")

    elif name in ("trend", "distribution", "moving_avg"):
        if not numeric_cols:
            result["valid"] = False
            result["errors"].append(f"{name} 操作需要至少一个数值列")

    elif name == "comparison":
        groupby = params.get("groupby")
        target = params.get("target_columns", [])
        if groupby and groupby not in actual_columns:
            result["warnings"].append(f"分组列 {groupby} 不存在，将尝试自动选择")
        if target:
            invalid = set(target) - actual_columns
            if invalid:
                result["warnings"].append(f"目标列不存在: {invalid}")

    return result


def build_data_profile(df: pd.DataFrame) -> Dict[str, Any]:
    """基于 DataFrame 构建数据画像"""
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
    categorical_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()
    datetime_cols = df.select_dtypes(include=["datetime64"]).columns.tolist()

    dtypes = {col: str(dtype) for col, dtype in df.dtypes.items()}

    unique_values_preview = {}
    for col in categorical_cols:
        unique_vals = df[col].dropna().unique().tolist()
        unique_values_preview[col] = [str(v) for v in unique_vals[:5]]

    return {
        "columns": df.columns.tolist(),
        "dtypes": dtypes,
        "numeric_columns": numeric_cols,
        "categorical_columns": categorical_cols,
        "datetime_columns": datetime_cols,
        "unique_values_preview": unique_values_preview,
        "row_count": len(df),
        "column_count": len(df.columns),
    }

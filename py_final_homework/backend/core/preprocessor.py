"""
数据预处理器
处理缺失值、类型推断、数据清洗
"""
import pandas as pd
import numpy as np
from typing import Optional, Dict, Any, List, Tuple
import logging

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """数据验证错误"""
    pass


def validate_dataframe(df: pd.DataFrame, min_rows: int = 1) -> None:
    """
    验证 DataFrame 是否可进行分析

    Args:
        df: pandas DataFrame
        min_rows: 最小行数要求

    Raises:
        ValidationError: 数据验证失败
    """
    if df is None or df.empty:
        raise ValidationError("数据集为空，无法进行分析")

    if len(df) < min_rows:
        raise ValidationError(f"数据行数不足，至少需要 {min_rows} 行，当前仅有 {len(df)} 行")

    # 检查是否有列
    if len(df.columns) == 0:
        raise ValidationError("数据集没有列")

    logger.info(f"数据验证通过: {len(df)} 行 x {len(df.columns)} 列")


def detect_column_types(df: pd.DataFrame) -> Dict[str, List[str]]:
    """
    检测各列的数据类型

    Args:
        df: pandas DataFrame

    Returns:
        包含各类型列名的字典
    """
    result = {
        'numeric': [],
        'datetime': [],
        'categorical': [],
        'boolean': []
    }

    for col in df.columns:
        # 跳过全为空的列
        if df[col].isna().all():
            continue

        dtype = df[col].dtype

        if pd.api.types.is_numeric_dtype(dtype):
            result['numeric'].append(col)
        elif pd.api.types.is_datetime64_any_dtype(dtype):
            result['datetime'].append(col)
        elif pd.api.types.is_bool_dtype(dtype):
            result['boolean'].append(col)
        else:
            # 尝试推断是否为日期（使用 format='mixed' 避免警告）
            try:
                pd.to_datetime(df[col], errors='raise', format='mixed')
                result['datetime'].append(col)
            except (ValueError, TypeError):
                result['categorical'].append(col)

    return result


def analyze_columns(df: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
    """
    分析列的统计信息（用于会话元数据）

    Args:
        df: pandas DataFrame

    Returns:
        列信息字典
    """
    result = {}

    for col in df.columns:
        info = {
            "dtype": str(df[col].dtype),
            "nullable": bool(df[col].isna().any()),
            "nunique": None
        }

        # 对于低基数列，计算唯一值数量
        nunique = df[col].nunique()
        if nunique < 100:
            info["nunique"] = int(nunique)
        else:
            info["nunique"] = "high"

        # 添加缺失值比例
        if info["nullable"]:
            info["null_ratio"] = round(df[col].isna().sum() / len(df), 4)

        result[col] = info

    return result


def handle_missing_values(
    df: pd.DataFrame,
    strategy: str = 'auto',
    numeric_fill: str = 'mean',
    categorical_fill: str = 'most_frequent'
) -> pd.DataFrame:
    """
    处理缺失值

    Args:
        df: pandas DataFrame
        strategy: 填充策略 ('auto', 'drop', 'fill')
        numeric_fill: 数值列填充方式 ('mean', 'median', 'forward', 'backward')
        categorical_fill: 分类型列填充方式 ('most_frequent', 'constant', 'forward', 'backward')

    Returns:
        处理后的 DataFrame
    """
    df = df.copy()

    if strategy == 'drop':
        # 删除包含缺失值的行
        before_rows = len(df)
        df = df.dropna()
        dropped = before_rows - len(df)
        if dropped > 0:
            logger.warning(f"删除了 {dropped} 行包含缺失值的数据")

    elif strategy == 'fill' or strategy == 'auto':
        # 处理数值列（使用非 inplace 方式，兼容 pandas 3.0）
        numeric_cols = df.select_dtypes(include=['number']).columns
        for col in numeric_cols:
            if df[col].isna().any():
                if numeric_fill == 'mean':
                    df[col] = df[col].fillna(df[col].mean())
                elif numeric_fill == 'median':
                    df[col] = df[col].fillna(df[col].median())
                elif numeric_fill == 'forward':
                    df[col] = df[col].ffill()
                elif numeric_fill == 'backward':
                    df[col] = df[col].bfill()

        # 处理分类型列（使用非 inplace 方式，兼容 pandas 3.0）
        categorical_cols = df.select_dtypes(include=['object', 'category']).columns
        for col in categorical_cols:
            if df[col].isna().any():
                if categorical_fill == 'most_frequent':
                    most_freq = df[col].mode()
                    if len(most_freq) > 0:
                        df[col] = df[col].fillna(most_freq[0])
                elif categorical_fill == 'forward':
                    df[col] = df[col].ffill()
                elif categorical_fill == 'backward':
                    df[col] = df[col].bfill()
                else:
                    # 使用 'unknown' 填充
                    df[col] = df[col].fillna('unknown')

    return df


def infer_datetime_columns(
    df: pd.DataFrame,
    date_formats: Optional[List[str]] = None
) -> Tuple[pd.DataFrame, List[str]]:
    """
    推断并转换日期时间列

    Args:
        df: pandas DataFrame
        date_formats: 尝试的日期格式列表

    Returns:
        (转换后的 DataFrame, 转换的列名列表)
    """
    df = df.copy()
    converted_cols = []

    # 默认尝试的日期格式
    default_formats = [
        '%Y-%m-%d',
        '%Y/%m/%d',
        '%d-%m-%Y',
        '%d/%m/%Y',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%dT%H:%M:%S',
        '%Y%m%d',
    ]

    date_formats = date_formats or default_formats

    for col in df.columns:
        # 跳过已经是日期类型的列
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            continue

        # 只尝试对象类型列
        if df[col].dtype != 'object':
            continue

        # 检查列名是否包含日期关键词
        date_keywords = ['date', 'time', '日期', '时间', 'day', 'month', 'year']
        col_lower = col.lower()
        if not any(kw in col_lower for kw in date_keywords):
            # 如果列名不包含日期关键词，采样检查数据内容
            sample = df[col].dropna().head(5)
            if sample.empty:
                continue

        # 尝试转换（使用 format='mixed' 避免警告）
        # 保存原始数据，以便转换失败时还原
        original_data = df[col].copy()

        try:
            df[col] = pd.to_datetime(df[col], errors='coerce', format='mixed')
            # 如果转换成功率超过 80%，认为转换成功
            success_rate = df[col].notna().sum() / len(df)
            if success_rate > 0.8:
                converted_cols.append(col)
                logger.info(f"成功推断日期列: {col}")
            else:
                # 转换失败太多，还原原始数据
                df[col] = original_data
                logger.debug(f"列 '{col}' 转换成功率 {success_rate:.2%}，已还原")
        except Exception:
            # 转换出错，还原原始数据
            df[col] = original_data

    return df, converted_cols


def clean_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """
    清理列名：去除空格、统一大小写、处理特殊字符

    Args:
        df: pandas DataFrame

    Returns:
        清理后的 DataFrame（注意：返回新的 DataFrame，不修改原数据）
    """
    # 创建新 DataFrame，确保与原数据完全独立
    result = df[[col for col in df.columns]].copy()

    # 先将列名转换为字符串（处理整数列名的情况，如 .data 文件）
    new_columns = [str(col) for col in df.columns]

    # 去除列名前后空格
    new_columns = [col.strip() for col in new_columns]

    # 替换空格为下划线
    import re
    new_columns = [re.sub(r'\s+', '_', col) for col in new_columns]

    # 去除特殊字符（保留中文、字母、数字、下划线、连字符）
    new_columns = [re.sub(r'[^\w一-鿿-]', '_', col) for col in new_columns]

    # 去除重复列名
    seen = {}
    for i, col in enumerate(new_columns):
        if col in seen:
            seen[col] += 1
            new_columns[i] = f"{col}_{seen[col]}"
        else:
            seen[col] = 0

    result.columns = new_columns

    return result


def preprocess_data(
    df: pd.DataFrame,
    clean_names: bool = True,
    infer_dates: bool = True,
    handle_missing: bool = True,
    validate: bool = True
) -> pd.DataFrame:
    """
    完整的数据预处理流程

    Args:
        df: 原始 DataFrame
        clean_names: 是否清理列名
        infer_dates: 是否推断日期列
        handle_missing: 是否处理缺失值
        validate: 是否验证数据

    Returns:
        预处理后的 DataFrame
    """
    logger.info("开始数据预处理...")

    if clean_names:
        df = clean_column_names(df)
        logger.info("列名清理完成")

    if infer_dates:
        df, date_cols = infer_datetime_columns(df)
        if date_cols:
            logger.info(f"推断日期列: {date_cols}")

    if handle_missing:
        df = handle_missing_values(df, strategy='auto')
        logger.info("缺失值处理完成")

    if validate:
        validate_dataframe(df)
        logger.info("数据验证通过")

    logger.info(f"预处理完成: {len(df)} 行 x {len(df.columns)} 列")

    return df


def get_data_summary(df: pd.DataFrame) -> Dict[str, Any]:
    """
    获取数据集摘要信息

    Args:
        df: pandas DataFrame

    Returns:
        数据摘要字典
    """
    column_types = detect_column_types(df)

    summary = {
        "row_count": len(df),
        "column_count": len(df.columns),
        "numeric_columns": column_types['numeric'],
        "datetime_columns": column_types['datetime'],
        "categorical_columns": column_types['categorical'],
        "memory_usage_mb": round(df.memory_usage(deep=True).sum() / 1024 / 1024, 2),
        "missing_values": df.isna().sum().to_dict(),
    }

    return summary

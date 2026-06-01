"""
分析引擎
提供统计分析、相关性分析、时序分析、移动平均等功能
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
import logging
from scipy import stats

# 可选导入 statsmodels
try:
    from statsmodels.tsa.seasonal import STL
    HAS_STATSMODELS = True
except ImportError:
    HAS_STATSMODELS = False
    logger = logging.getLogger(__name__)
    logger.warning("statsmodels 未安装，季节性分解功能将不可用")

logger = logging.getLogger(__name__)


class AnalysisError(Exception):
    """分析错误"""
    pass


def calculate_statistics(df: pd.DataFrame, columns: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    计算数值列的统计摘要

    Args:
        df: 数据集
        columns: 要分析的列，默认为所有数值列

    Returns:
        统计摘要字典
    """
    if columns is None:
        columns = df.select_dtypes(include=[np.number]).columns.tolist()

    if not columns:
        raise AnalysisError("没有数值列可供分析")

    result = {}

    for col in columns:
        if col not in df.columns:
            logger.warning(f"列 '{col}' 不存在，跳过")
            continue

        col_data = df[col].dropna()

        if len(col_data) == 0:
            result[col] = {"error": "列数据为空"}
            continue

        result[col] = {
            "count": len(col_data),
            "mean": float(col_data.mean()) if len(col_data) > 0 else None,
            "median": float(col_data.median()) if len(col_data) > 0 else None,
            "std": float(col_data.std()) if len(col_data) > 1 else None,
            "min": float(col_data.min()) if len(col_data) > 0 else None,
            "max": float(col_data.max()) if len(col_data) > 0 else None,
            "q25": float(col_data.quantile(0.25)) if len(col_data) > 0 else None,
            "q75": float(col_data.quantile(0.75)) if len(col_data) > 0 else None,
            "skewness": float(col_data.skew()) if len(col_data) > 2 else None,
            "kurtosis": float(col_data.kurtosis()) if len(col_data) > 3 else None,
        }

    return result


def analyze_correlation(df: pd.DataFrame, columns: Optional[List[str]] = None, method: str = "pearson") -> Dict[str, Any]:
    """
    分析相关性

    Args:
        df: 数据集
        columns: 要分析的列，默认为所有数值列
        method: 相关系数方法 ('pearson', 'spearman', 'kendall')

    Returns:
        相关性分析结果
    """
    if columns is None:
        columns = df.select_dtypes(include=[np.number]).columns.tolist()

    if len(columns) < 2:
        raise AnalysisError("相关性分析至少需要 2 个数值列")

    # 只使用存在的列
    valid_columns = [col for col in columns if col in df.columns]
    if len(valid_columns) < 2:
        raise AnalysisError("有效的数值列少于 2 个")

    data = df[valid_columns].dropna()

    if data.empty:
        raise AnalysisError("删除缺失值后没有数据")

    try:
        if method == "pearson":
            corr_matrix = data.corr(method="pearson")
        elif method == "spearman":
            corr_matrix = data.corr(method="spearman")
        elif method == "kendall":
            corr_matrix = data.corr(method="kendall")
        else:
            raise AnalysisError(f"不支持的相关系数方法: {method}")

        # 转换为列表格式（便于前端渲染）
        corr_list = []
        for i, col1 in enumerate(corr_matrix.columns):
            for j, col2 in enumerate(corr_matrix.columns):
                if i < j:  # 只取上三角
                    corr_list.append({
                        "x": col1,
                        "y": col2,
                        "value": round(float(corr_matrix.loc[col1, col2]), 4)
                    })

        return {
            "method": method,
            "columns": valid_columns,
            "matrix": corr_matrix.to_dict(),
            "pairs": corr_list
        }

    except Exception as e:
        raise AnalysisError(f"相关性分析失败: {e}")


def analyze_trend(
    df: pd.DataFrame,
    value_column: str,
    date_column: Optional[str] = None
) -> Dict[str, Any]:
    """
    分析趋势

    Args:
        df: 数据集
        value_column: 数值列名
        date_column: 日期列名（可选）

    Returns:
        趋势分析结果
    """
    if value_column not in df.columns:
        raise AnalysisError(f"列 '{value_column}' 不存在")

    data = df[[value_column]].copy()

    # 如果有日期列，按日期排序
    if date_column and date_column in df.columns:
        try:
            data[date_column] = pd.to_datetime(df[date_column], errors='coerce', format='mixed')
            data = data.sort_values(date_column)
        except Exception as e:
            logger.warning(f"日期列处理失败: {e}，使用原始顺序")

    values = data[value_column].dropna()

    if len(values) < 2:
        raise AnalysisError(f"数据点太少，无法分析趋势: {len(values)}")

    # 计算线性趋势
    x = np.arange(len(values))
    y = values.values

    try:
        slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)

        # 判断趋势方向
        if slope > 0.001:
            direction = "上升"
        elif slope < -0.001:
            direction = "下降"
        else:
            direction = "平稳"

        # 计算变化率
        if len(values) >= 2:
            change_rate = (values.iloc[-1] - values.iloc[0]) / values.iloc[0] * 100 if values.iloc[0] != 0 else 0
        else:
            change_rate = 0

        return {
            "direction": direction,
            "slope": float(slope),
            "intercept": float(intercept),
            "r_squared": float(r_value ** 2),
            "p_value": float(p_value),
            "change_rate": float(change_rate),
            "start_value": float(values.iloc[0]),
            "end_value": float(values.iloc[-1]),
            "min_value": float(values.min()),
            "max_value": float(values.max()),
        }

    except Exception as e:
        raise AnalysisError(f"趋势分析失败: {e}")


def calculate_moving_average(
    df: pd.DataFrame,
    value_column: str,
    window: int = 7,
    method: str = "simple"
) -> Dict[str, Any]:
    """
    计算移动平均

    Args:
        df: 数据集
        value_column: 数值列名
        window: 窗口大小
        method: 方法 ('simple', 'exponential')

    Returns:
        移动平均结果
    """
    if value_column not in df.columns:
        raise AnalysisError(f"列 '{value_column}' 不存在")

    data = df[value_column].copy()

    if len(data) < window:
        raise AnalysisError(f"数据点 ({len(data)}) 少于窗口大小 ({window})")

    try:
        if method == "simple":
            ma = data.rolling(window=window).mean()
            ma_name = f"SMA({window})"
        elif method == "exponential":
            ma = data.ewm(span=window).mean()
            ma_name = f"EMA({window})"
        else:
            raise AnalysisError(f"不支持的移动平均方法: {method}")

        # 转换为列表格式
        result_data = []
        for idx, (original, smoothed) in enumerate(zip(data, ma)):
            result_data.append({
                "index": int(idx),
                "original": float(original) if pd.notna(original) else None,
                "smoothed": float(smoothed) if pd.notna(smoothed) else None
            })

        return {
            "method": method,
            "window": window,
            "name": ma_name,
            "data": result_data
        }

    except Exception as e:
        raise AnalysisError(f"移动平均计算失败: {e}")


def prepare_timeseries(
    df: pd.DataFrame,
    date_column: str,
    value_column: str
) -> Tuple[pd.DataFrame, str]:
    """
    预处理时间序列数据以满足 STL 分解要求

    Args:
        df: 数据集
        date_column: 日期列名
        value_column: 数值列名

    Returns:
        (预处理后的 DataFrame, 时间间隔字符串)
    """
    df = df.copy()

    # 确保日期列是 datetime 类型
    df[date_column] = pd.to_datetime(df[date_column], errors='coerce', format='mixed')

    # 删除日期无效的行
    df = df.dropna(subset=[date_column])

    if len(df) < 2:
        raise AnalysisError("有效数据点太少，无法进行时序分析")

    # 按日期排序
    df = df.sort_values(date_column)

    # 设置日期为索引
    df = df.set_index(date_column)

    # 检查时间间隔
    intervals = df.index.to_series().diff().dropna()
    if len(intervals) == 0:
        raise AnalysisError("无法计算时间间隔")

    most_common_interval = intervals.mode()[0] if len(intervals.mode()) > 0 else intervals.median()

    # 尝试推断频率
    try:
        inferred_freq = pd.infer_freq(df.index)
        if inferred_freq is None:
            # 无法推断，使用最常见间隔重采样
            df = df.asfreq(most_common_interval)
        else:
            df = df.asfreq(inferred_freq)
    except Exception as e:
        logger.warning(f"频率推断失败: {e}，使用原始索引")
        # 保持原样，不重采样

    # 前向填充缺失值
    df[value_column] = df[value_column].ffill()

    # 检查是否还有缺失值
    if df[value_column].isna().any():
        # ffill 仍有缺失，用均值填充
        df[value_column] = df[value_column].fillna(df[value_column].mean())

    return df, str(most_common_interval)


def safe_seasonal_decompose(
    df: pd.DataFrame,
    date_column: str,
    value_column: str,
    period: Optional[int] = None
) -> Dict[str, Any]:
    """
    安全的季节性分解，失败时降级为简单趋势

    Args:
        df: 数据集
        date_column: 日期列名
        value_column: 数值列名
        period: 周期长度，自动推断为 None

    Returns:
        分解结果
    """
    # 检查 statsmodels 是否可用
    if not HAS_STATSMODELS:
        return {
            "success": False,
            "reason": "statsmodels 模块未安装",
            "fallback": "trend_only",
            "message": "季节性分解需要安装 statsmodels: pip install statsmodels"
        }

    try:
        # 预处理
        ts_df, interval = prepare_timeseries(df, date_column, value_column)

        # STL 分解要求至少 2 个完整周期
        if len(ts_df) < 24:
            return {
                "success": False,
                "reason": f"数据点不足 ({len(ts_df)} 个，需要至少 24 个)",
                "fallback": "trend_only"
            }

        # 自动确定周期
        if period is None:
            # 根据数据量推断周期
            n = len(ts_df)
            if n >= 365:
                period = 365  # 年度数据
            elif n >= 52:
                period = 52   # 周度数据
            elif n >= 12:
                period = 12   # 月度数据
            else:
                period = max(7, n // 4)  # 至少 7，或数据量的 1/4

        # 确保周期不超过数据长度的一半
        period = min(period, len(ts_df) // 2)

        # 执行 STL 分解
        stl = STL(ts_df[value_column], period=period)
        result = stl.fit()

        return {
            "success": True,
            "period": period,
            "trend": result.trend.tolist(),
            "seasonal": result.seasonal.tolist(),
            "residual": result.resid.tolist(),
            "dates": ts_df.index.strftime('%Y-%m-%d').tolist(),
        }

    except Exception as e:
        logger.error(f"季节性分解失败: {e}")
        return {
            "success": False,
            "reason": str(e),
            "fallback": "trend_only",
            "message": "数据不满足季节性分解要求，已降级为趋势分析"
        }


def analyze_distribution(
    df: pd.DataFrame,
    value_column: str
) -> Dict[str, Any]:
    """
    分析数据分布

    Args:
        df: 数据集
        value_column: 数值列名

    Returns:
        分布分析结果
    """
    if value_column not in df.columns:
        raise AnalysisError(f"列 '{value_column}' 不存在")

    data = df[value_column].dropna()

    if len(data) == 0:
        raise AnalysisError("没有有效数据")

    try:
        # 计算分位数
        quantiles = data.quantile([0.25, 0.5, 0.75]).to_dict()

        # 计算箱线图数据
        q1 = quantiles[0.25]
        q3 = quantiles[0.75]
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr

        outliers = data[(data < lower_bound) | (data > upper_bound)]

        # 生成直方图数据
        hist, bins = np.histogram(data, bins='auto')

        hist_data = [
            {"bin_start": float(bins[i]), "bin_end": float(bins[i + 1]), "count": int(hist[i])}
            for i in range(len(hist))
        ]

        return {
            "count": len(data),
            "mean": float(data.mean()),
            "median": float(data.median()),
            "std": float(data.std()),
            "min": float(data.min()),
            "max": float(data.max()),
            "q1": float(q1),
            "q3": float(q3),
            "iqr": float(iqr),
            "lower_bound": float(lower_bound),
            "upper_bound": float(upper_bound),
            "outlier_count": len(outliers),
            "outliers": outliers.tolist()[:100],  # 最多返回 100 个异常值
            "histogram": hist_data
        }

    except Exception as e:
        raise AnalysisError(f"分布分析失败: {e}")


def analyze_comparison(
    df: pd.DataFrame,
    value_column: str,
    groupby_column: str
) -> Dict[str, Any]:
    """
    分组对比分析

    Args:
        df: 数据集
        value_column: 数值列名
        groupby_column: 分组列名

    Returns:
        分组对比结果
    """
    if value_column not in df.columns:
        raise AnalysisError(f"列 '{value_column}' 不存在")

    if groupby_column not in df.columns:
        raise AnalysisError(f"列 '{groupby_column}' 不存在")

    try:
        grouped = df.groupby(groupby_column)[value_column]

        result = {
            "groups": [],
            "statistics": []
        }

        for group_name, group_data in grouped:
            group_data_clean = group_data.dropna()

            if len(group_data_clean) == 0:
                continue

            result["groups"].append(str(group_name))
            result["statistics"].append({
                "group": str(group_name),
                "count": len(group_data_clean),
                "mean": float(group_data_clean.mean()),
                "median": float(group_data_clean.median()),
                "std": float(group_data_clean.std()) if len(group_data_clean) > 1 else 0,
                "min": float(group_data_clean.min()),
                "max": float(group_data_clean.max())
            })

        # ANOVA 检验（如果有 2 个以上组）
        if len(result["statistics"]) >= 2:
            group_lists = [group[value_column].dropna().values for name, group in df.groupby(groupby_column)]
            try:
                f_stat, p_value = stats.f_oneway(*group_lists)
                result["anova"] = {
                    "f_statistic": float(f_stat),
                    "p_value": float(p_value),
                    "significant": p_value < 0.05
                }
            except Exception as e:
                logger.warning(f"ANOVA 检验失败: {e}")

        return result

    except Exception as e:
        raise AnalysisError(f"分组对比分析失败: {e}")


def analyze_overview(df: pd.DataFrame) -> Dict[str, Any]:
    """
    数据概览分析

    Args:
        df: 数据集

    Returns:
        概览分析结果
    """
    row_count = len(df)
    column_count = len(df.columns)

    result = {
        "row_count": row_count,
        "column_count": column_count,
        "shape": {"rows": row_count, "columns": column_count},
        "columns": {},
        "missing_values": {},
        "memory_usage": f"{df.memory_usage(deep=True).sum() / 1024 / 1024:.2f} MB"
    }

    for col in df.columns:
        col_info = {
            "dtype": str(df[col].dtype),
            "non_null_count": int(df[col].notna().sum()),
            "null_count": int(df[col].isna().sum()),
            "null_ratio": float(df[col].isna().sum() / len(df))
        }

        if pd.api.types.is_numeric_dtype(df[col]):
            col_info["statistics"] = {
                "mean": float(df[col].mean()),
                "min": float(df[col].min()),
                "max": float(df[col].max()),
                "std": float(df[col].std())
            }
        else:
            unique_count = df[col].nunique()
            col_info["unique_count"] = int(unique_count)
            if unique_count <= 20:
                col_info["unique_values"] = df[col].dropna().unique().tolist()

        result["columns"][col] = col_info
        result["missing_values"][col] = int(df[col].isna().sum())

    return result


def analyze_cross_comparison(
    df: pd.DataFrame,
    value_column: str,
    groupby: str,
    groupby2: str,
    max_series: int = 8
) -> Dict[str, Any]:
    """
    多维交叉对比分析：按两个分类变量分组，计算数值列均值。

    Args:
        df: 数据集
        value_column: 数值列名
        groupby: 主分组列（X 轴类别）
        groupby2: 次分组列（每条线/系列）
        max_series: 最大系列数（取 groupby2 中出现次数最多的类别）

    Returns:
        交叉对比结果，可直接传入 create_grouped_bar_chart
    """
    for col in [value_column, groupby, groupby2]:
        if col not in df.columns:
            raise AnalysisError(f"列 '{col}' 不存在")

    # 取 groupby2 中频次最高的 max_series 个类别
    top_cats = df[groupby2].value_counts().head(max_series).index.tolist()
    df_filtered = df[df[groupby2].isin(top_cats)].copy()

    # 获取主分组的所有类别
    all_groups = sorted(df_filtered[groupby].dropna().unique().tolist())

    series_data = []
    for cat in top_cats:
        subset = df_filtered[df_filtered[groupby2] == cat]
        grouped = subset.groupby(groupby)[value_column].mean()
        data = [round(float(grouped.get(g, 0)), 4) if g in grouped.index else None for g in all_groups]
        series_data.append({
            "name": str(cat),
            "data": data
        })

    return {
        "groups": [str(g) for g in all_groups],
        "series_data": series_data,
        "groupby2_categories": [str(c) for c in top_cats],
        "groupby": groupby,
        "groupby2": groupby2,
        "value_column": value_column
    }

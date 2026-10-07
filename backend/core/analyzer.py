"""
分析引擎
提供统计分析、相关性分析、时序分析、移动平均等功能

模块职责：
    本模块是 DataVis 平台的核心数据分析层，面向已加载的 pandas DataFrame，
    提供一组无状态的分析函数，涵盖：
      - 描述性统计 (calculate_statistics)
      - 相关性分析 (analyze_correlation / analyze_categorical_association)
      - 分类列 Cramér's V 矩阵 (analyze_categorical_correlation_matrix)
      - 趋势与移动平均 (analyze_trend / calculate_moving_average)
      - 时序预处理与 STL 季节性分解 (prepare_timeseries / safe_seasonal_decompose)
      - 分布与异常值检测 (analyze_distribution / analyze_categorical_distribution)
      - 分组与交叉对比 (analyze_comparison / analyze_cross_comparison)
      - 数据概览 (analyze_overview)
    所有函数以字典形式返回结构化结果，供后端 API 直接序列化后交付前端渲染。
    分析过程中遇到的错误统一抛出 AnalysisError，便于上层捕获并转换为用户提示。
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


# AI-assisted: 使用 Claude 生成数值列统计摘要逻辑，人工校验后保留原逻辑
def calculate_statistics(df: pd.DataFrame, columns: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    计算数值列的统计摘要（计数、均值、中位数、标准差、分位数、偏度、峰度等）。

    Args:
        df: 待分析的数据集。
        columns: 要分析的列名列表；为 None 时自动选取全部数值列。

    Returns:
        以列名为键、统计指标字典为值的映射；空列或异常列以 {"error": ...} 标记。
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


# AI-assisted: 使用 Claude 实现数值列相关性分析与上三角提取，人工校验后保留原逻辑
def analyze_correlation(df: pd.DataFrame, columns: Optional[List[str]] = None, method: str = "pearson") -> Dict[str, Any]:
    """
    分析数值列之间的相关性（Pearson / Spearman / Kendall）。

    Args:
        df: 待分析的数据集。
        columns: 参与计算的列名列表；为 None 时自动选取全部数值列。
        method: 相关系数方法，可选 'pearson'、'spearman'、'kendall'。

    Returns:
        包含 method、columns、完整 matrix 及上三角 pairs（便于前端散点/热力渲染）的字典。
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


# AI-assisted: 使用 Claude 生成趋势分析逻辑，手动调整了方向判定阈值与变化率口径
def analyze_trend(
    df: pd.DataFrame,
    value_column: str,
    date_column: Optional[str] = None
) -> Dict[str, Any]:
    """
    基于线性回归分析数值列的整体趋势（方向、斜率、R²、变化率等）。

    Args:
        df: 待分析的数据集。
        value_column: 用于趋势分析的数值列名。
        date_column: 日期列名（可选），提供时按日期排序后再拟合。

    Returns:
        包含 direction、slope、intercept、r_squared、p_value、change_rate 等指标的字典。
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


# AI-assisted: 使用 Claude 实现简单/指数移动平均计算，手动微调了窗口默认值
def calculate_moving_average(
    df: pd.DataFrame,
    value_column: str,
    window: int = 7,
    method: str = "simple"
) -> Dict[str, Any]:
    """
    计算数值列的移动平均（SMA 或 EMA），用于平滑与短期波动可视化。

    Args:
        df: 待分析的数据集。
        value_column: 待平滑的数值列名。
        window: 移动平均窗口大小，默认 7。
        method: 计算方法，可选 'simple'（简单）或 'exponential'（指数）。

    Returns:
        包含 method、window、name 及按索引对齐的原始/平滑值序列的字典。
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


# AI-assisted: 使用 Claude 编写时序预处理与频率推断逻辑，人工校验后保留原逻辑
def prepare_timeseries(
    df: pd.DataFrame,
    date_column: str,
    value_column: str
) -> Tuple[pd.DataFrame, str]:
    """
    预处理时间序列数据以满足 STL 分解要求（类型转换、排序、重采样、缺失值填充）。

    Args:
        df: 原始数据集。
        date_column: 日期/时间列名。
        value_column: 待分解的数值列名。

    Returns:
        元组 (预处理后的 DataFrame（日期已设为索引）, 最常见时间间隔字符串)。
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


# AI-assisted: 使用 Claude 实现 STL 季节性分解与降级策略，手动微调了周期推断阈值
def safe_seasonal_decompose(
    df: pd.DataFrame,
    date_column: str,
    value_column: str,
    period: Optional[int] = None
) -> Dict[str, Any]:
    """
    安全的季节性分解：优先尝试 statsmodels 的 STL 分解，失败时降级为仅趋势结果。

    Args:
        df: 待分解的数据集。
        date_column: 日期/时间列名。
        value_column: 待分解的数值列名。
        period: 季节性周期长度；为 None 时根据数据量自动推断。

    Returns:
        成功时返回 trend/seasonal/residual 等分解分量；失败时返回 success=False 与降级原因。
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


# AI-assisted: 使用 Claude 生成分箱直方图与箱线图/异常值检测逻辑，人工校验后保留原逻辑
def analyze_distribution(
    df: pd.DataFrame,
    value_column: str
) -> Dict[str, Any]:
    """
    分析数值列的分布特征（分位数、IQR、异常值、自动分箱直方图）。

    Args:
        df: 待分析的数据集。
        value_column: 数值列名。

    Returns:
        包含均值、分位数、IQR、上下界、异常值列表（最多 100 个）及直方图数据的字典。
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


# AI-assisted: 使用 Claude 实现分类列频次统计与低频合并逻辑，手动微调了默认合并上限
def analyze_categorical_distribution(
    df: pd.DataFrame,
    column: str,
    max_categories: int = 20
) -> Dict[str, Any]:
    """
    分类列频次分析：统计各类别计数与占比，超出上限的低频类别合并为 "Other"。

    Args:
        df: 待分析的数据集。
        column: 分类列名。
        max_categories: 最大展示类别数，超出部分合并为 "Other"，默认 20。

    Returns:
        包含总数、唯一值数、众数及各类别 count/percentage 列表的字典。
    """
    if column not in df.columns:
        raise AnalysisError(f"列 '{column}' 不存在")

    data = df[column].dropna()
    if len(data) == 0:
        raise AnalysisError("没有有效数据")

    try:
        vc = data.value_counts()
        total = len(data)
        unique_count = len(vc)

        # 合并低频类别
        if unique_count > max_categories:
            top = vc.head(max_categories - 1)
            other_count = vc.iloc[max_categories - 1:].sum()
            vc = pd.concat([top, pd.Series({"Other": other_count})])

        categories = []
        for name, count in vc.items():
            categories.append({
                "name": str(name).strip(),
                "count": int(count),
                "percentage": round(count / total * 100, 2)
            })

        return {
            "column": column,
            "total_count": total,
            "unique_count": unique_count,
            "mode": str(data.mode().iloc[0]).strip() if len(data.mode()) > 0 else None,
            "categories": categories
        }

    except Exception as e:
        raise AnalysisError(f"分类分布分析失败: {e}")


# AI-assisted: 使用 Claude 实现分类列 Cramér's V 关联与卡方检验逻辑，人工校验后保留原逻辑
def analyze_categorical_association(
    df: pd.DataFrame,
    col1: str,
    col2: str
) -> Dict[str, Any]:
    """
    计算两个分类列之间的 Cramér's V 关联系数及卡方检验显著性。

    Args:
        df: 待分析的数据集。
        col1: 第一个分类列名。
        col2: 第二个分类列名。

    Returns:
        包含 chi2、p_value、cramers_v 及关联强度评级（弱/中等/强）的字典。
    """
    for col in [col1, col2]:
        if col not in df.columns:
            raise AnalysisError(f"列 '{col}' 不存在")

    try:
        ct = pd.crosstab(df[col1].dropna(), df[col2].dropna())
        chi2 = stats.chi2_contingency(ct)[0]
        n = ct.sum().sum()
        min_dim = min(ct.shape[0], ct.shape[1]) - 1
        cramers_v = np.sqrt(chi2 / (n * min_dim)) if min_dim > 0 else 0

        if cramers_v > 0.3:
            strength = "强关联"
        elif cramers_v > 0.1:
            strength = "中等关联"
        else:
            strength = "弱关联"

        return {
            "col1": col1,
            "col2": col2,
            "chi2": float(chi2),
            "p_value": float(stats.chi2_contingency(ct)[1]),
            "cramers_v": float(cramers_v),
            "strength": strength,
            "n": int(n)
        }

    except Exception as e:
        raise AnalysisError(f"分类关联分析失败: {e}")


# AI-assisted: 使用 Claude 实现分类列 Cramér's V 矩阵与对称缓存优化，人工校验后保留原逻辑
def analyze_categorical_correlation_matrix(
    df: pd.DataFrame,
    columns: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    计算所有分类列两两之间的 Cramér's V 关联矩阵（利用对称性避免重复计算）。

    Args:
        df: 待分析的数据集。
        columns: 参与计算的分类列；为 None 时自动选取所有 object/category 列。

    Returns:
        包含 method、columns 及对称 matrix 的字典，可直接用于热力图渲染。
    """
    if columns is None:
        columns = df.select_dtypes(include=['object', 'category']).columns.tolist()

    if len(columns) < 2:
        raise AnalysisError("Cramér's V 矩阵至少需要 2 个分类列")

    try:
        n = len(columns)
        matrix = {}
        for col1 in columns:
            matrix[col1] = {}
            for col2 in columns:
                if col1 == col2:
                    matrix[col1][col2] = 1.0
                elif col2 in matrix and col1 in matrix[col2]:
                    matrix[col1][col2] = matrix[col2][col1]
                else:
                    ct = pd.crosstab(df[col1].dropna(), df[col2].dropna())
                    chi2 = stats.chi2_contingency(ct)[0]
                    total = ct.sum().sum()
                    min_dim = min(ct.shape[0], ct.shape[1]) - 1
                    matrix[col1][col2] = round(float(np.sqrt(chi2 / (total * min_dim))) if min_dim > 0 else 0, 4)

        return {
            "method": "cramers_v",
            "columns": columns,
            "matrix": matrix
        }

    except Exception as e:
        raise AnalysisError(f"Cramér's V 矩阵计算失败: {e}")


# AI-assisted: 使用 Claude 实现分组统计与 ANOVA 显著性检验逻辑，人工校验后保留原逻辑
def analyze_comparison(
    df: pd.DataFrame,
    value_column: str,
    groupby_column: str
) -> Dict[str, Any]:
    """
    分组对比分析：按分组列对数值列计算各组统计量，组数≥2 时附 ANOVA 检验。

    Args:
        df: 待分析的数据集。
        value_column: 数值列名。
        groupby_column: 用于分组的列名。

    Returns:
        包含各组 count/mean/median/std/min/max，及 anova（F 统计量、p 值、显著性）的字典。
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


# AI-assisted: 使用 Claude 生成数据概览与列画像分析逻辑，人工校验后保留原逻辑
def analyze_overview(df: pd.DataFrame) -> Dict[str, Any]:
    """
    数据概览分析：汇总行列规模、内存占用、各列类型与缺失情况，并附简要统计/枚举值。

    Args:
        df: 待分析的数据集。

    Returns:
        包含 row_count、column_count、shape、逐列 col_info（含缺失率/统计量/唯一值）、
        memory_usage 的概览字典。
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


# AI-assisted: 使用 Claude 实现双分类维度的交叉对比与系列裁剪逻辑，手动微调了默认系列上限
def analyze_cross_comparison(
    df: pd.DataFrame,
    value_column: str,
    groupby: str,
    groupby2: str,
    max_series: int = 8
) -> Dict[str, Any]:
    """
    多维交叉对比分析：按两个分类变量分组，计算数值列的组内均值，输出可直接渲染的系列数据。

    Args:
        df: 待分析的数据集。
        value_column: 数值列名。
        groupby: 主分组列（对应 X 轴类别）。
        groupby2: 次分组列（每条系列对应一个该列取值）。
        max_series: 最大系列数，取 groupby2 中出现次数最多的前若干类别，默认 8。

    Returns:
        包含 groups（X 轴类别）、series_data（每系列名称与对齐数据）及元信息的字典，
        可直接传入 create_grouped_bar_chart 进行可视化。
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

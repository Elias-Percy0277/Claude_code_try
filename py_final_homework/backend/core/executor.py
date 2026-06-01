"""
操作执行器
接收结构化的操作指令，调用分析引擎和可视化引擎，返回 OperationResult。
"""
import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from backend.cache.cache import template_polish
from backend.core.analyzer import (
    analyze_overview,
    analyze_trend,
    analyze_correlation,
    calculate_moving_average,
    analyze_distribution,
    analyze_comparison,
    analyze_cross_comparison,
    safe_seasonal_decompose,
)
from backend.core.visualizer import (
    create_line_chart,
    create_correlation_heatmap,
    create_scatter_plot,
    create_bar_chart,
    create_grouped_bar_chart,
    create_grouped_line_chart,
    create_grouped_pie_chart,
    create_area_chart,
    create_radar_chart,
    create_grouped_scatter_chart,
    create_histogram_chart,
    create_moving_average_chart,
    create_seasonal_chart,
    create_pie_chart,
    create_box_plot,
)
from backend.models.session_context import OperationResult

logger = logging.getLogger(__name__)


async def execute_operation(df: pd.DataFrame, operation: str, params: Dict[str, Any]) -> OperationResult:
    """
    执行操作并返回结构化结果

    Args:
        df: 数据集
        operation: 操作名称
        params: 操作参数

    Returns:
        OperationResult
    """
    try:
        handler = _OPERATION_HANDLERS.get(operation)
        if handler:
            return await handler(df, params)
        return OperationResult(
            operation=operation,
            status="error",
            error_message=f"未知操作: {operation}",
        )
    except Exception as e:
        logger.error(f"操作执行失败 ({operation}): {e}")
        return OperationResult(
            operation=operation,
            status="error",
            error_message=str(e),
        )


async def _exec_overview(df: pd.DataFrame, params: dict) -> OperationResult:
    stats = analyze_overview(df)
    summary = template_polish(stats, "overview")
    return OperationResult(operation="overview", statistics=stats, summary_text=summary)


async def _exec_trend(df: pd.DataFrame, params: dict) -> OperationResult:
    columns = params.get("columns", [])
    chart_type = params.get("chart_type") or "line"
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()

    if not columns:
        columns = numeric_cols[:1]
    valid = [c for c in columns if c in df.columns and c in numeric_cols]
    if not valid:
        valid = numeric_cols[:1]
    columns = valid

    date_cols = df.select_dtypes(include=["datetime64"]).columns.tolist()
    date_col = date_cols[0] if date_cols else None

    if date_col:
        x_col = date_col
        df_plot = df
    else:
        x_col = "index"
        df_plot = df.reset_index()
    x_label = date_col or "序号"

    charts = []
    if len(columns) > 1:
        chart = create_line_chart(
            df_plot.head(500), x_col, columns,
            " / ".join(columns) + " 趋势对比", smooth=True, x_name=x_label, y_name="数值"
        )
        charts.append(chart)
        parts = []
        for col in columns:
            try:
                r = analyze_trend(df, col, date_col)
                parts.append(f"**{col}**: {template_polish(r, 'trend')}")
            except Exception:
                pass
        summary = "\n".join(parts)
    else:
        col = columns[0]
        trend_result = analyze_trend(df, col, date_col)
        summary = template_polish(trend_result, "trend")
        y_data = df_plot[col].tolist()[:200]
        chart = _create_chart_by_type(df, df_plot, col, x_col, x_label, y_data, chart_type, "趋势分析")
        charts.append(chart)

    statistics = {"trend": trend_result if len(columns) == 1 else {"multi": True}}
    return OperationResult(operation="trend", statistics=statistics, chart_options=charts, summary_text=summary)


async def _exec_distribution(df: pd.DataFrame, params: dict) -> OperationResult:
    column = params.get("column")
    chart_type = params.get("chart_type") or "histogram"
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()

    if not column or column not in df.columns:
        column = numeric_cols[0] if numeric_cols else None
    if not column:
        return OperationResult(operation="distribution", status="error", error_message="无数值列可供分析")

    dist_result = analyze_distribution(df, column)
    summary = template_polish(dist_result, "distribution")

    hist_data = dist_result["histogram"]
    bin_edges = [h["bin_start"] for h in hist_data]
    counts = [h["count"] for h in hist_data]
    bin_edges.append(hist_data[-1]["bin_end"])

    if chart_type == "pie":
        pie_data = [{"name": f"{h['bin_start']:.1f}-{h['bin_end']:.1f}", "value": h["count"]} for h in hist_data]
        chart = create_pie_chart(pie_data, f"{column} 分布占比", donut=False)
    elif chart_type == "boxplot":
        col_data = df[column].dropna()
        q1, q2, q3 = float(col_data.quantile(0.25)), float(col_data.quantile(0.50)), float(col_data.quantile(0.75))
        iqr = q3 - q1
        lower, upper = max(float(col_data.min()), q1 - 1.5 * iqr), min(float(col_data.max()), q3 + 1.5 * iqr)
        chart = create_box_plot([column], [[lower, q1, q2, q3, upper]], f"{column} 箱线图")
    elif chart_type == "line":
        x_data = [(bin_edges[i] + bin_edges[i + 1]) / 2 for i in range(len(bin_edges) - 1)]
        df_dist = pd.DataFrame({"bin_center": x_data, column: counts})
        chart = create_line_chart(df_dist, "bin_center", [column], f"{column} 分布折线图", smooth=True)
    elif chart_type == "bar":
        chart = create_histogram_chart(bin_edges, counts, f"{column} 分布", x_name=column, y_name="频数")
    else:
        chart = create_histogram_chart(bin_edges, counts, f"{column} 分布", x_name=column, y_name="频数")

    return OperationResult(
        operation="distribution",
        statistics={k: v for k, v in dist_result.items() if k != "histogram"},
        chart_options=[chart],
        summary_text=summary,
    )


async def _exec_comparison(df: pd.DataFrame, params: dict) -> OperationResult:
    target_columns = params.get("target_columns", [])
    groupby = params.get("groupby")
    groupby2 = params.get("groupby2")
    chart_type = params.get("chart_type") or "bar"

    if not groupby or not target_columns:
        return OperationResult(operation="comparison", status="error", error_message="分组对比需要指定分组列和目标列")

    if groupby2:
        return await _exec_cross_comparison(df, target_columns[0], groupby, groupby2, chart_type)

    value_col = target_columns[0]
    is_numeric = pd.api.types.is_numeric_dtype(df[value_col])

    if not is_numeric:
        return await _exec_crosstab(df, value_col, groupby, chart_type)

    comp_result = analyze_comparison(df, value_col, groupby)
    summary = template_polish(comp_result, "comparison")

    groups = comp_result["groups"]
    means = [s["mean"] for s in comp_result["statistics"]]
    series_data = [{"name": s["group"], "data": [s["mean"]]} for s in comp_result["statistics"]]
    chart_title = f"{value_col} 按 {groupby} 分组"

    chart = _create_comparison_chart(chart_type, groups, means, series_data, chart_title, groupby, value_col)

    return OperationResult(
        operation="comparison",
        statistics=comp_result,
        chart_options=[chart],
        summary_text=summary,
    )


async def _exec_cross_comparison(df, value_col, groupby, groupby2, chart_type) -> OperationResult:
    cross_result = analyze_cross_comparison(df, value_col, groupby, groupby2)
    chart_title = f"{value_col} 按 {groupby} 与 {groupby2} 交叉对比"
    cross_groups = cross_result["groups"]
    cross_series = cross_result["series_data"]

    chart = create_grouped_bar_chart(cross_groups, cross_series, chart_title, x_name=groupby, y_name=f"{value_col} 均值")
    if chart_type == "line":
        for s in chart["option"]["series"]:
            s["type"] = "line"
            s["smooth"] = True
        chart["chart_type"] = "line"

    lines = [f"**{value_col}** 按 **{groupby}** 和 **{groupby2}** 交叉分组："]
    for sd in cross_series:
        vals = [f"{v}" if v is not None else "-" for v in sd["data"]]
        lines.append(f"  - {sd['name']}: {', '.join(vals)}")

    return OperationResult(
        operation="comparison",
        statistics=cross_result,
        chart_options=[chart],
        summary_text="\n".join(lines),
    )


async def _exec_crosstab(df, value_col, groupby, chart_type) -> OperationResult:
    ct = pd.crosstab(df[groupby], df[value_col])
    total_per_group = ct.sum(axis=1)

    groups = []
    for group_name in ct.index:
        row = ct.loc[group_name]
        group_total = total_per_group[group_name]
        group_data = {"group": str(group_name), "total": int(group_total)}
        for cat in row.index:
            count = int(row[cat])
            pct = round(count / group_total * 100, 1) if group_total > 0 else 0
            group_data[str(cat)] = count
            group_data[f"{cat}_pct"] = pct
        groups.append(group_data)

    chart_title = f"{value_col} 按 {groupby} 分组占比"
    if chart_type == "pie":
        largest_group = max(groups, key=lambda g: g["total"])
        pie_data = [{"name": str(cat), "value": largest_group.get(str(cat), 0)} for cat in ct.columns if largest_group.get(str(cat), 0) > 0]
        chart = create_pie_chart(pie_data, f"{groupby}={largest_group['group']} 的 {value_col} 分布", donut=True)
    else:
        bar_data = [{"name": str(cat), "data": [int(ct.loc[g, cat]) for g in ct.index]} for cat in ct.columns]
        chart = create_grouped_bar_chart([str(g) for g in ct.index], bar_data, chart_title, x_name=groupby, y_name="数量")
        for s in chart["option"]["series"]:
            s["stack"] = "total"

    lines = [f"**{value_col}** 按 **{groupby}** 分组分布：\n"]
    for g in groups:
        parts = [f"{cat}: {g.get(f'{cat}_pct', 0)}%" for cat in ct.columns]
        lines.append(f"- **{g['group']}** (共{g['total']}条): {', '.join(parts)}")

    return OperationResult(
        operation="comparison",
        statistics={"crosstab": True, "groups": groups, "categories": [str(c) for c in ct.columns]},
        chart_options=[chart],
        summary_text="\n".join(lines),
    )


async def _exec_correlation(df: pd.DataFrame, params: dict) -> OperationResult:
    columns = params.get("columns", [])
    chart_type = params.get("chart_type")
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()

    if not columns:
        columns = numeric_cols[:5]

    if len(columns) < 2:
        return OperationResult(operation="correlation", status="error", error_message="相关性分析至少需要2个数值列")

    corr_result = analyze_correlation(df, columns[:5])
    summary = template_polish(corr_result, "correlation")

    charts = []
    if chart_type == "scatter":
        x_data = df[columns[0]].tolist()
        y_data = df[columns[1]].tolist()
        charts.append(create_scatter_plot(x_data, y_data, columns[0], columns[1], f"{columns[0]} vs {columns[1]}"))
    elif chart_type == "bar":
        for pair in corr_result.get("pairs", []):
            charts.append(create_bar_chart([f"{pair['x']}-{pair['y']}"], [pair["value"]], "相关系数"))
    else:
        charts.append(create_correlation_heatmap(corr_result["matrix"], corr_result["columns"], "相关性分析"))
        if len(columns) >= 2:
            x_data = df[columns[0]].tolist()
            y_data = df[columns[1]].tolist()
            charts.append(create_scatter_plot(x_data, y_data, columns[0], columns[1], f"{columns[0]} vs {columns[1]}"))

    return OperationResult(
        operation="correlation",
        statistics=corr_result,
        chart_options=charts,
        summary_text=summary,
    )


async def _exec_moving_avg(df: pd.DataFrame, params: dict) -> OperationResult:
    column = params.get("column")
    window = params.get("window", 7)
    chart_type = params.get("chart_type") or "line"
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()

    if not column or column not in df.columns:
        column = numeric_cols[0] if numeric_cols else None
    if not column:
        return OperationResult(operation="moving_avg", status="error", error_message="无数值列")

    ma_result = calculate_moving_average(df, column, window=window)
    summary = template_polish(ma_result, "moving_avg")

    original = df[column].tolist()
    smoothed = [p.get("smoothed") for p in ma_result["data"]]

    if chart_type == "bar":
        chart = create_bar_chart(list(range(len(smoothed))), [v if v is not None else 0 for v in smoothed], f"{column} 移动平均", x_name="序号", y_name=column)
    else:
        chart = create_moving_average_chart(original, smoothed, f"{column} 移动平均", x_name="序号", y_name=column)

    return OperationResult(
        operation="moving_avg",
        statistics=ma_result,
        chart_options=[chart],
        summary_text=summary,
    )


async def _exec_seasonality(df: pd.DataFrame, params: dict) -> OperationResult:
    column = params.get("column")
    chart_type = params.get("chart_type") or "line"
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
    date_cols = df.select_dtypes(include=["datetime64"]).columns.tolist()

    if not date_cols or not numeric_cols:
        return OperationResult(operation="seasonality", status="error", error_message="需要日期列和数值列")

    if not column or column not in df.columns:
        column = numeric_cols[0]

    seasonal_result = safe_seasonal_decompose(df, date_cols[0], column)
    if not seasonal_result["success"]:
        return OperationResult(
            operation="seasonality",
            status="error",
            error_message=seasonal_result.get("message", "季节性分解失败"),
        )

    dates = seasonal_result["dates"]
    original = df[column].tolist()[:len(seasonal_result["trend"])]
    trend = seasonal_result["trend"]
    seasonal = seasonal_result["seasonal"]

    if chart_type == "bar":
        chart = create_bar_chart(dates[:200], trend[:200], f"{column} 季节性分解", x_name="日期", y_name=column)
    else:
        chart = create_seasonal_chart(dates, original, trend, seasonal, f"{column} 季节性分解", x_name="日期", y_name=column)

    return OperationResult(
        operation="seasonality",
        statistics=seasonal_result,
        chart_options=[chart],
        summary_text="季节性分解成功，已检测到周期性模式",
    )


# 图表创建辅助函数
def _create_chart_by_type(df, df_plot, col, x_col, x_label, y_data, chart_type, title_suffix):
    """根据 chart_type 创建对应图表"""
    chart_title = f"{col} {title_suffix}"
    y_label = col

    if chart_type == "bar":
        x_data = df_plot[x_col].astype(str).tolist()[:200]
        return create_bar_chart(x_data, y_data, chart_title, x_name=x_label, y_name=y_label)
    elif chart_type == "area":
        series_data = [{"name": col, "data": df_plot[col].tolist()[:500]}]
        x_labels = df_plot[x_col].astype(str).tolist()[:500]
        return create_area_chart(x_labels, series_data, chart_title, x_name=x_label, y_name=y_label)
    elif chart_type == "scatter":
        return create_scatter_plot(list(range(len(y_data))), y_data, x_label, y_label, chart_title)
    elif chart_type == "pie":
        n_slices = min(8, len(y_data))
        slice_size = len(y_data) // n_slices
        pie_data = []
        for si in range(n_slices):
            start = si * slice_size
            end = start + slice_size if si < n_slices - 1 else len(y_data)
            avg = sum(y_data[start:end]) / (end - start) if end > start else 0
            pie_data.append({"name": f"{start}-{end}", "value": round(avg, 2)})
        return create_pie_chart(pie_data, chart_title, donut=False)
    elif chart_type == "boxplot":
        col_data = df[col].dropna()
        q1, q2, q3 = float(col_data.quantile(0.25)), float(col_data.quantile(0.50)), float(col_data.quantile(0.75))
        iqr = q3 - q1
        lower = max(float(col_data.min()), q1 - 1.5 * iqr)
        upper = min(float(col_data.max()), q3 + 1.5 * iqr)
        return create_box_plot([col], [[lower, q1, q2, q3, upper]], chart_title)
    elif chart_type == "histogram":
        col_clean = df[col].dropna().tolist()
        hist_counts, bin_edges = np.histogram(col_clean, bins='auto')
        return create_histogram_chart(bin_edges.tolist(), hist_counts.tolist(), chart_title, x_name=y_label, y_name="频数")
    else:
        return create_line_chart(df_plot, x_col, [col], chart_title, x_name=x_label, y_name=y_label)


def _create_comparison_chart(chart_type, groups, means, series_data, chart_title, groupby, value_col):
    """根据 chart_type 创建分组对比图表"""
    if chart_type == "line":
        chart = create_bar_chart(groups, means, chart_title, x_name=groupby, y_name=f"{value_col} 均值")
        chart["chart_type"] = "line"
        chart["option"]["series"][0]["type"] = "line"
        chart["option"]["series"][0]["smooth"] = True
    elif chart_type == "area":
        chart = create_bar_chart(groups, means, chart_title, x_name=groupby, y_name=f"{value_col} 均值")
        chart["chart_type"] = "area"
        s = chart["option"]["series"][0]
        s["type"] = "line"
        s["smooth"] = True
        s["areaStyle"] = {"opacity": 0.3}
    elif chart_type == "pie":
        chart = create_grouped_pie_chart(groups, series_data, chart_title)
    elif chart_type == "radar":
        chart = create_radar_chart(groups, series_data, chart_title)
    elif chart_type == "scatter":
        chart = create_scatter_plot(list(range(len(means))), means, groupby, f"{value_col} 均值", chart_title)
        chart["option"]["xAxis"] = {"type": "category", "data": groups, "name": groupby, "axisLabel": {"rotate": 45}}
    else:
        chart = create_bar_chart(groups, means, chart_title, x_name=groupby, y_name=f"{value_col} 均值")
    return chart


# 操作处理函数映射
_OPERATION_HANDLERS = {
    "overview": _exec_overview,
    "trend": _exec_trend,
    "distribution": _exec_distribution,
    "comparison": _exec_comparison,
    "correlation": _exec_correlation,
    "moving_avg": _exec_moving_avg,
    "seasonality": _exec_seasonality,
}

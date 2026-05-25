"""
分析请求 API
处理用户自然语言查询，返回分析结果和图表
支持 SSE 流式响应
"""
import json
import logging
import pandas as pd
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.session.manager import get_session_manager, SessionNotFoundError
from backend.core.intent_parser import parse_intent_async
from backend.core.analyzer import (
    analyze_overview,
    analyze_trend,
    analyze_correlation,
    calculate_moving_average,
    analyze_distribution,
    analyze_comparison,
    analyze_cross_comparison,
    safe_seasonal_decompose
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
from backend.cache.cache import get_cache_manager, template_polish
from backend.agent.llm_client import LLMClient, LLMClientError, get_llm_client
from backend.core.logger_config import get_logger
from backend.core.logging_middleware import AnalysisLogger
from backend.models.schemas import AnalysisRequest, RechartRequest, ErrorCode

logger = get_logger(__name__)

router = APIRouter()


class AnalysisResponse(BaseModel):
    """分析响应"""
    success: bool
    summary: str
    charts: list = []
    statistics: dict = None
    warning: str = None


async def analyze_stream_generator(request: AnalysisRequest) -> AsyncGenerator[str, None]:
    """
    生成 SSE 格式的流式响应

    Args:
        request: 分析请求

    Yields:
        SSE 格式的数据行
    """
    try:
        session_manager = get_session_manager()
        cache_manager = get_cache_manager()

        # 获取会话
        try:
            session = session_manager.get_session(request.session_id)
        except SessionNotFoundError:
            logger.warning(f"会话不存在: {request.session_id}")
            yield _format_sse({
                "type": "error",
                "message": f"会话不存在或已过期: {request.session_id}"
            })
            return

        df = session.primary_dataset.dataframe
        file_hash = session.primary_dataset.file_hash

        # 记录分析开始
        AnalysisLogger.log_analysis_start(request.session_id, request.query)

        # 检查缓存
        cached_result = cache_manager.get(request.session_id, request.query, file_hash)
        if cached_result:
            logger.info(f"✓ 使用缓存结果: {request.query[:50]}...")
            yield _format_sse({
                "type": "charts",
                "data": cached_result.get("charts", [])
            })
            yield _format_sse({
                "type": "text",
                "delta": cached_result.get("summary", "")
            })
            yield _format_sse({"type": "done"})
            AnalysisLogger.log_analysis_complete(request.session_id, len(cached_result.get("charts", [])), cache_hit=True)
            return

        # 意图解析
        intent_result = await parse_intent_async(request.query, df)
        logger.debug(f"意图解析结果: {intent_result}")
        AnalysisLogger.log_intent_parsed(intent_result.get("tasks", []))

        # 处理原始 AI 响应（非结构化）
        if "raw_response" in intent_result:
            logger.info("返回原始 AI 响应")
            yield _format_sse({
                "type": "text",
                "delta": intent_result["raw_response"]
            })
            if intent_result.get("warning"):
                yield _format_sse({
                    "type": "warning",
                    "message": intent_result["warning"]
                })
            yield _format_sse({"type": "done"})
            AnalysisLogger.log_analysis_complete(request.session_id, 0)
            return

        # 处理解析错误
        if "error" in intent_result:
            yield _format_sse({
                "type": "error",
                "message": intent_result["error"]
            })
            return

        tasks = intent_result.get("tasks", [])
        if not tasks:
            yield _format_sse({
                "type": "error",
                "message": "无法识别分析意图"
            })
            return

        # 执行分析任务
        charts = []
        statistics = {}
        analysis_descriptions = []
        warning = intent_result.get("warning")

        for task in tasks:
            intent = task.get("intent")
            target_columns = task.get("target_columns", [])
            groupby = task.get("groupby")
            params = task.get("params", {})
            chart_type = task.get("chart_type")

            try:
                result = await _execute_analysis(
                    df, intent, target_columns, groupby,
                    task.get("groupby2"), params, request.query, chart_type
                )
                if result:
                    charts.extend(result.get("charts", []))
                    if result.get("statistics"):
                        statistics.update(result["statistics"])
                    # 收集每个任务的分析描述（用于传给 LLM）
                    analysis_descriptions.append({
                        "intent": intent,
                        "target_columns": target_columns,
                        "groupby": groupby,
                        "statistics": result.get("statistics", {}),
                        "summary_template": result.get("summary", "")
                    })
            except Exception as e:
                logger.error(f"分析任务执行失败 ({intent}): {e}")
                analysis_descriptions.append({
                    "intent": intent,
                    "error": str(e)
                })

        # 发送图表数据
        yield _format_sse({
            "type": "charts",
            "data": charts
        })

        # 使用 LLM 进行智能分析（带历史记忆）
        summary = ""
        try:
            messages = _build_analysis_messages(
                request.query, analysis_descriptions, request.session_id
            )
            llm_client = get_llm_client()
            async for delta in llm_client.achat_stream(
                messages, temperature=0.3, max_tokens=5000
            ):
                summary += delta
                yield _format_sse({"type": "text", "delta": delta})
        except Exception as e:
            logger.warning(f"LLM 智能分析失败，降级为模板: {e}")
            # 降级：使用模板生成
            if analysis_descriptions:
                parts = [d.get("summary_template", "") for d in analysis_descriptions if d.get("summary_template")]
                summary = "\n\n".join(parts) if parts else template_polish({"row_count": len(df)}, "overview")
            else:
                summary = template_polish({"row_count": len(df)}, "overview")
            for char in summary:
                yield _format_sse({"type": "text", "delta": char})

        # 缓存结果
        cache_result = {
            "summary": summary,
            "charts": charts,
            "statistics": statistics
        }
        cache_manager.set(request.session_id, request.query, file_hash, cache_result)

        # 持久化聊天历史
        try:
            session_manager.add_chat_entry(
                session_id=request.session_id,
                role="user",
                content=request.query
            )
            session_manager.add_chat_entry(
                session_id=request.session_id,
                role="assistant",
                content=summary,
                charts=charts if charts else None
            )
        except Exception as e:
            logger.warning(f"保存聊天历史失败: {e}")

        AnalysisLogger.log_analysis_complete(request.session_id, len(charts))
        yield _format_sse({"type": "done", "warning": warning})

    except Exception as e:
        logger.error(f"分析过程异常: {e}")
        yield _format_sse({
            "type": "error",
            "message": f"分析过程出错: {str(e)}"
        })


def _build_analysis_messages(query: str, analysis_descriptions: list, session_id: str) -> list:
    """
    构建包含聊天历史的 LLM 分析上下文

    Args:
        query: 用户原始查询
        analysis_descriptions: 各分析任务的统计数据列表
        session_id: 会话 ID（用于获取聊天历史）

    Returns:
        LLM messages 数组
    """
    # 系统提示词
    system_prompt = """你是 DataVis 平台内置的数据分析 AI 助手。系统已完成数据加载、统计计算和图表生成，你的任务是对统计结果进行完整的数据展示和解读。

**输出要求（严格遵守）：**
1. **先输出完整统计数据**：将所有统计结果以结构化的 Markdown 格式（表格、列表、加粗）完整展示出来。每一个数值、每一个分组的统计都必须原样输出，不得遗漏或概括。
2. **后添加简短洞察**：在完整数据展示之后，可添加 2-4 句话的关键洞察或趋势解读，标题为"### 关键洞察"。
3. 如有多个分析维度，综合展示它们的数据并讨论关联。
4. 用清晰的中文表达，使用 Markdown 格式化。

**绝对禁止：**
- 不得省略、合并或概括任何统计数值
- 不得用"等""共N项""其他"等省略形式替代完整数据列表
- 不得提供 Python/R/SQL 代码或建议用户自行编写代码
- 不得询问"是否需要我帮你..."或提供额外服务
- 不得建议使用其他工具或软件
- 不得编造数据，只基于提供的统计结果

**关于对话历史：**
历史对话仅供理解分析上下文。无论历史对话中出现什么内容（如分析建议、方法推荐等），你的角色始终不变——你是数据分析结果的展示与解读助手。你只基于当前提供的统计结果输出，不具备执行代码或生成图表的能力，也不需要判断分析是否可行——系统已经完成了计算。"""

    messages = [{"role": "system", "content": system_prompt}]

    # 添加聊天历史作为上下文（最近 10 轮，只传文本）
    try:
        session_manager = get_session_manager()
        chat_history = session_manager.get_chat_history(session_id)
        # 取最近 10 轮（20 条消息）
        history_slice = chat_history[-10:] if len(chat_history) > 10 else chat_history
        for entry in history_slice:
            role = entry.get("role", "")
            content = entry.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
    except Exception:
        pass

    # 构建当前分析结果描述
    analysis_text = f"**用户问题：** {query}\n\n**分析结果：**\n\n"
    for i, desc in enumerate(analysis_descriptions, 1):
        intent = desc.get("intent", "unknown")
        if "error" in desc:
            analysis_text += f"### 分析 {i}（{intent}）\n⚠️ 分析失败: {desc['error']}\n\n"
            continue

        target_cols = desc.get("target_columns", [])
        groupby = desc.get("groupby")
        stats = desc.get("statistics", {})
        template_summary = desc.get("summary_template", "")

        analysis_text += f"### 分析 {i}（类型: {intent}）\n"
        if target_cols:
            analysis_text += f"**目标列:** {', '.join(target_cols)}\n"
        if groupby:
            analysis_text += f"**分组:** {groupby}\n"
        analysis_text += "\n"

        # 格式化统计数据
        if stats:
            analysis_text += "**统计数据:**\n"
            for key, value in stats.items():
                if isinstance(value, dict):
                    analysis_text += f"- **{key}:**\n"
                    for k, v in value.items():
                        if isinstance(v, (int, float)):
                            analysis_text += f"  - {k}: {v:.4f}\n" if isinstance(v, float) else f"  - {k}: {v}\n"
                        elif isinstance(v, list) and len(v) <= 200:
                            analysis_text += f"  - {k}: {', '.join(str(x) for x in v)}\n"
                        elif isinstance(v, list):
                            analysis_text += f"  - {k}: [{len(v)} 项]\n"
                        else:
                            analysis_text += f"  - {k}: {v}\n"
                elif isinstance(value, list) and len(value) <= 200:
                    analysis_text += f"- **{key}:** {', '.join(str(x) for x in value)}\n"
                elif isinstance(value, (int, float)):
                    analysis_text += f"- **{key}:** {value:.4f}\n" if isinstance(value, float) else f"- **{key}:** {value}\n"
                else:
                    analysis_text += f"- **{key}:** {value}\n"
            analysis_text += "\n"

        # 附上模板摘要作为参考
        if template_summary:
            analysis_text += f"**基础统计摘要:**\n{template_summary}\n\n"

    messages.append({"role": "user", "content": analysis_text})
    return messages


def _format_sse(data: dict) -> str:
    """格式化为 SSE 格式"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _execute_analysis(
    df,
    intent: str,
    target_columns: list,
    groupby: str = None,
    groupby2: str = None,
    params: dict = None,
    query: str = "",
    chart_type: str = None
) -> dict:
    """
    执行分析任务

    Args:
        df: 数据集
        intent: 意图类型
        target_columns: 目标列
        groupby: 分组列
        params: 参数
        query: 原始查询
        chart_type: 图表类型（bar/line/pie/scatter/histogram）

    Returns:
        分析结果字典
    """
    params = params or {}
    result = {"charts": [], "summary": "", "statistics": {}}

    if intent == "overview":
        # 数据概览
        stats = analyze_overview(df)
        result["summary"] = template_polish(stats, "overview")
        result["statistics"] = stats

    elif intent == "trend":
        # 趋势分析
        if len(target_columns) == 0:
            target_columns = df.select_dtypes(include=['number']).columns.tolist()[:1]

        # 过滤到实际存在的数值列
        numeric_cols_all = df.select_dtypes(include=['number']).columns.tolist()
        valid_target_cols = [c for c in target_columns if c in df.columns and c in numeric_cols_all]
        if not valid_target_cols:
            valid_target_cols = numeric_cols_all[:1]
        target_columns = valid_target_cols

        # 检测日期列
        date_cols = df.select_dtypes(include=['datetime64']).columns.tolist()
        date_col = date_cols[0] if date_cols else None
        if date_col:
            x_col = date_col
            df_plot = df
        else:
            x_col = "index"
            df_plot = df.reset_index()

        x_label = date_col or "序号"

        # 多列时画在同一张图上
        if len(target_columns) > 1:
            chart_title = " / ".join(target_columns) + " 趋势对比"
            chart = create_line_chart(
                df_plot.head(500), x_col, target_columns,
                chart_title, smooth=True, x_name=x_label, y_name="数值"
            )
            result["charts"].append(chart)
            summary_parts_list = []
            for col in target_columns:
                try:
                    trend_result = analyze_trend(df, col, date_col)
                    summary_parts_list.append(f"**{col}**: {template_polish(trend_result, 'trend')}")
                except Exception:
                    pass
            result["summary"] = "\n".join(summary_parts_list)
        else:
            # 单列走原有逻辑
            col = target_columns[0]
            trend_result = analyze_trend(df, col, date_col)
            result["summary"] = template_polish(trend_result, "trend")

            chart_title = f"{col} 趋势分析"
            y_data = df_plot[col].tolist()[:200]
            y_label = col
            requested_chart_type = chart_type or "line"

            if requested_chart_type == "bar":
                x_data = df_plot[x_col].astype(str).tolist()[:200]
                chart = create_bar_chart(x_data, y_data, chart_title, x_name=x_label, y_name=y_label)
            elif requested_chart_type == "area":
                series_data = [{"name": col, "data": df_plot[col].tolist()[:500]}]
                x_labels = df_plot[x_col].astype(str).tolist()[:500]
                chart = create_area_chart(x_labels, series_data, chart_title, x_name=x_label, y_name=y_label)
            elif requested_chart_type == "scatter":
                x_numeric = list(range(len(y_data)))
                chart = create_scatter_plot(x_numeric, y_data, x_label, y_label, chart_title)
            elif requested_chart_type == "pie":
                n_slices = min(8, len(y_data))
                slice_size = len(y_data) // n_slices
                pie_data = []
                for si in range(n_slices):
                    start = si * slice_size
                    end = start + slice_size if si < n_slices - 1 else len(y_data)
                    slice_avg = sum(y_data[start:end]) / (end - start) if end > start else 0
                    label = f"{start}-{end}"
                    pie_data.append({"name": label, "value": round(slice_avg, 2)})
                chart = create_pie_chart(pie_data, chart_title, donut=False)
            elif requested_chart_type == "radar":
                n_parts = min(6, len(y_data))
                part_size = len(y_data) // n_parts
                labels = []
                values = []
                for pi in range(n_parts):
                    start = pi * part_size
                    end = start + part_size if pi < n_parts - 1 else len(y_data)
                    part_avg = sum(y_data[start:end]) / (end - start) if end > start else 0
                    labels.append(f"段{pi + 1}")
                    values.append(round(part_avg, 2))
                series_data = [{"name": l, "data": [v]} for l, v in zip(labels, values)]
                chart = create_radar_chart(labels, series_data, chart_title)
            elif requested_chart_type == "boxplot":
                col_data = df[col].dropna()
                q1 = float(col_data.quantile(0.25))
                q2 = float(col_data.quantile(0.50))
                q3 = float(col_data.quantile(0.75))
                iqr = q3 - q1
                lower = max(float(col_data.min()), q1 - 1.5 * iqr)
                upper = min(float(col_data.max()), q3 + 1.5 * iqr)
                chart = create_box_plot([col], [[lower, q1, q2, q3, upper]], chart_title)
            elif requested_chart_type == "histogram":
                import numpy as _np
                col_clean = df[col].dropna().tolist()
                hist_counts, bin_edges = _np.histogram(col_clean, bins='auto')
                bin_list = bin_edges.tolist()
                chart = create_histogram_chart(bin_list, hist_counts.tolist(), chart_title, x_name=y_label, y_name="频数")
            else:
                chart = create_line_chart(df_plot, x_col, [col], chart_title, x_name=x_label, y_name=y_label)

            result["charts"].append(chart)

    elif intent == "correlation":
        # 相关性分析
        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
        if len(numeric_cols) < 2:
            result["summary"] = "数值列少于 2 个，无法进行相关性分析"
        else:
            corr_result = analyze_correlation(df, numeric_cols[:5])
            result["summary"] = template_polish(corr_result, "correlation")

            requested_chart_type = chart_type

            if requested_chart_type == "scatter":
                # 仅散点图
                x_data = df[numeric_cols[0]].tolist()
                y_data = df[numeric_cols[1]].tolist()
                chart = create_scatter_plot(
                    x_data, y_data,
                    numeric_cols[0], numeric_cols[1],
                    f"{numeric_cols[0]} vs {numeric_cols[1]}"
                )
                result["charts"].append(chart)
            elif requested_chart_type == "pie":
                # 饼图展示相关系数绝对值占比
                pie_data = []
                for pair in corr_result.get("pairs", []):
                    label = f"{pair['x']} vs {pair['y']}"
                    pie_data.append({"name": label, "value": round(abs(pair["value"]), 4)})
                if pie_data:
                    chart = create_pie_chart(pie_data, "相关系数绝对值占比")
                    result["charts"].append(chart)
            elif requested_chart_type == "bar":
                # 柱状图展示各对相关系数
                for pair in corr_result.get("pairs", []):
                    label = f"{pair['x']}-{pair['y']}"
                    chart = create_bar_chart([label], [pair["value"]], "相关系数")
                    result["charts"].append(chart)
            else:
                # 默认：热力图 + 散点图
                chart = create_correlation_heatmap(
                    corr_result["matrix"],
                    corr_result["columns"],
                    "相关性分析"
                )
                result["charts"].append(chart)

                if len(numeric_cols) >= 2:
                    x_data = df[numeric_cols[0]].tolist()
                    y_data = df[numeric_cols[1]].tolist()
                    chart = create_scatter_plot(
                        x_data, y_data,
                        numeric_cols[0], numeric_cols[1],
                        f"{numeric_cols[0]} vs {numeric_cols[1]}"
                    )
                    result["charts"].append(chart)

    elif intent == "moving_avg":
        # 移动平均
        window = params.get("window", 7)
        if len(target_columns) == 0:
            target_columns = df.select_dtypes(include=['number']).columns.tolist()[:1]

        for col in target_columns:
            if col in df.columns:
                ma_result = calculate_moving_average(df, col, window=window)
                result["summary"] = template_polish(ma_result, "moving_avg")

                original = df[col].tolist()
                smoothed = [p.get("smoothed") for p in ma_result["data"]]
                requested_chart_type = chart_type or "line"
                chart_title = f"{col} 移动平均"
                ma_x_label = "序号"
                ma_y_label = col

                if requested_chart_type == "bar":
                    chart = create_bar_chart(
                        list(range(len(smoothed))),
                        [v if v is not None else 0 for v in smoothed],
                        chart_title, x_name=ma_x_label, y_name=ma_y_label
                    )
                elif requested_chart_type == "area":
                    series_data = [
                        {"name": "原始数据", "data": [v if v is not None else 0 for v in original[:200]]},
                        {"name": "移动平均", "data": [v if v is not None else 0 for v in smoothed[:200]]}
                    ]
                    chart = create_area_chart(
                        [str(i) for i in range(len(original[:200]))],
                        series_data, chart_title, x_name=ma_x_label, y_name=ma_y_label
                    )
                elif requested_chart_type == "scatter":
                    chart = create_scatter_plot(
                        list(range(len(smoothed))),
                        [v if v is not None else 0 for v in smoothed],
                        ma_x_label, ma_y_label, chart_title
                    )
                elif requested_chart_type == "pie":
                    n_slices = min(8, len(smoothed))
                    slice_size = len(smoothed) // n_slices
                    pie_data = []
                    for si in range(n_slices):
                        start = si * slice_size
                        end = start + slice_size if si < n_slices - 1 else len(smoothed)
                        vals = [v for v in smoothed[start:end] if v is not None]
                        avg = sum(vals) / len(vals) if vals else 0
                        pie_data.append({"name": f"段{si + 1}", "value": round(avg, 2)})
                    chart = create_pie_chart(pie_data, chart_title)
                elif requested_chart_type == "radar":
                    n_parts = min(6, len(smoothed))
                    part_size = len(smoothed) // n_parts
                    labels, values = [], []
                    for pi in range(n_parts):
                        start = pi * part_size
                        end = start + part_size if pi < n_parts - 1 else len(smoothed)
                        vals = [v for v in smoothed[start:end] if v is not None]
                        avg = sum(vals) / len(vals) if vals else 0
                        labels.append(f"段{pi + 1}")
                        values.append(round(avg, 2))
                    series_data = [{"name": l, "data": [v]} for l, v in zip(labels, values)]
                    chart = create_radar_chart(labels, series_data, chart_title)
                else:
                    chart = create_moving_average_chart(original, smoothed, chart_title, x_name=ma_x_label, y_name=ma_y_label)

                result["charts"].append(chart)

    elif intent == "distribution":
        # 分布分析
        if len(target_columns) == 0:
            target_columns = df.select_dtypes(include=['number']).columns.tolist()[:1]

        for col in target_columns:
            if col in df.columns:
                dist_result = analyze_distribution(df, col)
                result["summary"] = template_polish(dist_result, "distribution")

                # 准备直方图基础数据
                hist_data = dist_result["histogram"]
                bin_edges = []
                counts = []
                for h in hist_data:
                    bin_edges.append(h["bin_start"])
                    counts.append(h["count"])
                bin_edges.append(hist_data[-1]["bin_end"])

                requested_chart_type = chart_type or "histogram"
                dist_x_label = col
                dist_y_label = "频数"

                if requested_chart_type == "pie":
                    pie_data = []
                    for h in hist_data:
                        label = f"{h['bin_start']:.1f}-{h['bin_end']:.1f}"
                        pie_data.append({"name": label, "value": h["count"]})
                    chart = create_pie_chart(pie_data, f"{col} 分布占比", donut=False)
                elif requested_chart_type == "boxplot":
                    col_data = df[col].dropna()
                    q1 = float(col_data.quantile(0.25))
                    q2 = float(col_data.quantile(0.50))
                    q3 = float(col_data.quantile(0.75))
                    iqr = q3 - q1
                    lower = max(float(col_data.min()), q1 - 1.5 * iqr)
                    upper = min(float(col_data.max()), q3 + 1.5 * iqr)
                    chart = create_box_plot([col], [[lower, q1, q2, q3, upper]], f"{col} 箱线图")
                elif requested_chart_type == "line":
                    x_data = [(bin_edges[i] + bin_edges[i + 1]) / 2 for i in range(len(bin_edges) - 1)]
                    df_dist = pd.DataFrame({"bin_center": x_data, col: counts})
                    chart = create_line_chart(df_dist, "bin_center", [col], f"{col} 分布折线图", smooth=True, x_name=dist_x_label, y_name=dist_y_label)
                elif requested_chart_type == "bar":
                    chart = create_histogram_chart(bin_edges, counts, f"{col} 分布", x_name=dist_x_label, y_name=dist_y_label)
                elif requested_chart_type == "area":
                    x_data = [(bin_edges[i] + bin_edges[i + 1]) / 2 for i in range(len(bin_edges) - 1)]
                    x_labels = [f"{x:.1f}" for x in x_data]
                    series_data = [{"name": label, "data": [count]} for label, count in zip(x_labels, counts)]
                    chart = create_area_chart(x_labels, series_data, f"{col} 分布面积图", x_name=dist_x_label, y_name=dist_y_label)
                elif requested_chart_type == "radar":
                    stats_labels = ["均值", "中位数", "标准差", "最小值", "最大值", "Q1", "Q3"]
                    stats_values = [
                        dist_result.get("mean", 0), dist_result.get("median", 0),
                        dist_result.get("std", 0), dist_result.get("min", 0),
                        dist_result.get("max", 0), dist_result.get("q1", 0),
                        dist_result.get("q3", 0)
                    ]
                    series_data = [{"name": label, "data": [val]} for label, val in zip(stats_labels, stats_values)]
                    chart = create_radar_chart(stats_labels, series_data, f"{col} 统计量雷达图")
                else:
                    chart = create_histogram_chart(bin_edges, counts, f"{col} 分布", x_name=dist_x_label, y_name=dist_y_label)

                result["charts"].append(chart)

    elif intent == "comparison":
        # 分组对比
        if not groupby or len(target_columns) == 0:
            result["summary"] = "分组对比需要指定分组列和数值列"
        elif groupby2:
            # 多维交叉对比：两个分类变量 + 一个数值变量
            try:
                cross_result = analyze_cross_comparison(df, target_columns[0], groupby, groupby2)
                chart_title = f"{target_columns[0]} 按 {groupby} 与 {groupby2} 交叉对比"
                comp_x_label = groupby
                comp_y_label = f"{target_columns[0]} 均值"
                cross_groups = cross_result["groups"]
                cross_series = cross_result["series_data"]

                requested_chart_type = chart_type or "bar"

                if requested_chart_type == "line":
                    chart = create_grouped_bar_chart(
                        cross_groups, cross_series, chart_title,
                        x_name=comp_x_label, y_name=comp_y_label
                    )
                    # 把所有 series 改为 line
                    for s in chart["option"]["series"]:
                        s["type"] = "line"
                        s["smooth"] = True
                    chart["chart_type"] = "line"
                else:
                    chart = create_grouped_bar_chart(
                        cross_groups, cross_series, chart_title,
                        x_name=comp_x_label, y_name=comp_y_label
                    )

                result["charts"].append(chart)

                lines = [f"**{target_columns[0]}** 按 **{groupby}** 和 **{groupby2}** 交叉分组："]
                for sd in cross_series:
                    vals = [f"{v}" if v is not None else "-" for v in sd["data"]]
                    lines.append(f"  - {sd['name']}: {', '.join(vals)}")
                result["summary"] = "\n".join(lines)
            except Exception as e:
                result["summary"] = f"多维交叉对比失败: {str(e)}"
        else:
            value_col = target_columns[0]
            # 判断目标列是数值列还是分类列
            is_numeric = pd.api.types.is_numeric_dtype(df[value_col])

            if not is_numeric:
                # 分类列：做频次/占比统计（交叉表）
                try:
                    ct = pd.crosstab(df[groupby], df[value_col])
                    total_per_group = ct.sum(axis=1)

                    result["statistics"] = {"crosstab": True}
                    result["statistics"]["column_type"] = "categorical"
                    result["statistics"]["value_column"] = value_col
                    result["statistics"]["groupby"] = groupby

                    groups = []
                    for group_name in ct.index:
                        row = ct.loc[group_name]
                        group_total = total_per_group[group_name]
                        group_data = {
                            "group": str(group_name),
                            "total": int(group_total)
                        }
                        for cat in row.index:
                            count = int(row[cat])
                            pct = round(count / group_total * 100, 1) if group_total > 0 else 0
                            group_data[str(cat)] = count
                            group_data[f"{cat}_pct"] = pct
                        groups.append(group_data)

                    result["statistics"]["groups"] = groups
                    result["statistics"]["categories"] = [str(c) for c in ct.columns]

                    # 生成图表：堆叠柱状图或饼图
                    requested_chart_type = chart_type or "bar"
                    chart_title = f"{value_col} 按 {groupby} 分组占比"

                    if requested_chart_type == "pie":
                        # 每组一个饼图（用第一个大组）
                        largest_group = max(groups, key=lambda g: g["total"])
                        pie_data = []
                        for cat in ct.columns:
                            if largest_group.get(str(cat), 0) > 0:
                                pie_data.append({"name": str(cat), "value": largest_group[str(cat)]})
                        chart = create_pie_chart(pie_data, f"{groupby}={largest_group['group']} 的 {value_col} 分布", donut=True)
                    else:
                        # 堆叠柱状图
                        bar_data = []
                        for cat in ct.columns:
                            bar_data.append({
                                "name": str(cat),
                                "data": [int(ct.loc[g, cat]) for g in ct.index]
                            })
                        chart = create_grouped_bar_chart(
                            [str(g) for g in ct.index],
                            bar_data,
                            chart_title,
                            x_name=groupby,
                            y_name="数量"
                        )
                        # 设置为堆叠
                        for s in chart["option"]["series"]:
                            s["stack"] = "total"

                    result["charts"].append(chart)

                    # 生成摘要
                    lines = [f"**{value_col}** 按 **{groupby}** 分组分布：\n"]
                    for g in groups:
                        parts = []
                        for cat in ct.columns:
                            pct = g.get(f"{cat}_pct", 0)
                            if pct > 0:
                                parts.append(f"{cat}: {pct}%")
                        lines.append(f"- **{g['group']}** (共{g['total']}条): {', '.join(parts)}")
                    result["summary"] = "\n".join(lines)

                except Exception as e:
                    result["summary"] = f"交叉表分析失败: {str(e)}"
            else:
                # 数值列：原有逻辑
                comp_result = analyze_comparison(df, value_col, groupby)
            result["summary"] = template_polish(comp_result, "comparison")

            groups = comp_result["groups"]
            means = [s["mean"] for s in comp_result["statistics"]]
            # 用于 pie/radar 等 group-name + single-value 格式
            series_data = [
                {"name": s["group"], "data": [s["mean"]]}
                for s in comp_result["statistics"]
            ]

            requested_chart_type = chart_type or "bar"
            chart_title = f"{target_columns[0]} 按 {groupby} 分组"
            comp_x_label = groupby
            comp_y_label = f"{target_columns[0]} 均值"

            if requested_chart_type == "line":
                # 单条折线连接各组均值
                chart = create_bar_chart(
                    groups, means, chart_title,
                    x_name=comp_x_label, y_name=comp_y_label
                )
                chart["chart_type"] = "line"
                chart["option"]["series"][0]["type"] = "line"
                chart["option"]["series"][0]["smooth"] = True
            elif requested_chart_type == "area":
                chart = create_bar_chart(
                    groups, means, chart_title,
                    x_name=comp_x_label, y_name=comp_y_label
                )
                chart["chart_type"] = "area"
                s = chart["option"]["series"][0]
                s["type"] = "line"
                s["smooth"] = True
                s["areaStyle"] = {"opacity": 0.3}
            elif requested_chart_type == "pie":
                chart = create_grouped_pie_chart(groups, series_data, chart_title)
            elif requested_chart_type == "radar":
                chart = create_radar_chart(groups, series_data, chart_title)
            elif requested_chart_type == "scatter":
                # 用散点图：每个组在 x=序号, y=均值 处画点
                chart = create_scatter_plot(
                    list(range(len(means))), means,
                    comp_x_label, comp_y_label, chart_title
                )
                # 覆盖 xAxis 为类别标签
                chart["option"]["xAxis"] = {
                    "type": "category",
                    "data": groups,
                    "name": comp_x_label,
                    "nameLocation": "middle",
                    "nameGap": 50,
                    "axisLabel": {"rotate": 45}
                }
            else:
                # 默认柱状图 — 单 series，每个组一个柱子
                chart = create_bar_chart(
                    groups, means, chart_title,
                    x_name=comp_x_label, y_name=comp_y_label
                )

            result["charts"].append(chart)

    elif intent == "seasonality":
        # 季节性分解
        date_cols = df.select_dtypes(include=['datetime64']).columns.tolist()
        if not date_cols or len(target_columns) == 0:
            result["summary"] = "季节性分解需要日期列和数值列"
        else:
            seasonal_result = safe_seasonal_decompose(
                df, date_cols[0], target_columns[0]
            )
            if seasonal_result["success"]:
                result["summary"] = "季节性分解成功，已检测到周期性模式"

                chart_title = f"{target_columns[0]} 季节性分解"
                requested_chart_type = chart_type or "line"
                dates = seasonal_result["dates"]
                original = df[target_columns[0]].tolist()[:len(seasonal_result["trend"])]
                trend = seasonal_result["trend"]
                seasonal = seasonal_result["seasonal"]
                sea_x_label = "日期"
                sea_y_label = target_columns[0]

                if requested_chart_type == "bar":
                    chart = create_bar_chart(
                        dates[:200], trend[:200], chart_title,
                        x_name=sea_x_label, y_name=sea_y_label
                    )
                elif requested_chart_type == "scatter":
                    chart = create_scatter_plot(
                        list(range(len(trend))), trend,
                        sea_x_label, sea_y_label, chart_title
                    )
                elif requested_chart_type == "area":
                    series_data = [
                        {"name": "原始", "data": original[:200]},
                        {"name": "趋势", "data": trend[:200]},
                        {"name": "季节", "data": seasonal[:200]}
                    ]
                    chart = create_area_chart(
                        [str(i) for i in range(min(len(original), 200))],
                        series_data, chart_title, x_name=sea_x_label, y_name=sea_y_label
                    )
                elif requested_chart_type == "pie":
                    n_slices = min(8, len(trend))
                    slice_size = len(trend) // n_slices
                    pie_data = []
                    for si in range(n_slices):
                        start = si * slice_size
                        end = start + slice_size if si < n_slices - 1 else len(trend)
                        avg = sum(trend[start:end]) / (end - start) if end > start else 0
                        pie_data.append({"name": f"段{si + 1}", "value": round(avg, 2)})
                    chart = create_pie_chart(pie_data, chart_title)
                elif requested_chart_type == "radar":
                    n_parts = min(6, len(trend))
                    part_size = len(trend) // n_parts
                    labels, values = [], []
                    for pi in range(n_parts):
                        start = pi * part_size
                        end = start + part_size if pi < n_parts - 1 else len(trend)
                        avg = sum(trend[start:end]) / (end - start) if end > start else 0
                        labels.append(f"段{pi + 1}")
                        values.append(round(avg, 2))
                    series_data = [{"name": l, "data": [v]} for l, v in zip(labels, values)]
                    chart = create_radar_chart(labels, series_data, chart_title)
                else:
                    chart = create_seasonal_chart(dates, original, trend, seasonal, chart_title, x_name=sea_x_label, y_name=sea_y_label)

                result["charts"].append(chart)
            else:
                result["summary"] = seasonal_result.get("message", "季节性分解失败")

    return result


@router.post("/analysis")
async def analyze(request: AnalysisRequest):
    """
    分析请求接口（SSE 流式响应）

    Args:
        request: 分析请求

    Returns:
        StreamingResponse: SSE 格式的流式响应
    """
    return StreamingResponse(
        analyze_stream_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/analysis/sync")
async def analyze_sync(request: AnalysisRequest):
    """
    分析请求接口（同步响应，用于调试）

    Args:
        request: 分析请求

    Returns:
        AnalysisResponse: 分析结果
    """
    try:
        session_manager = get_session_manager()
        cache_manager = get_cache_manager()

        session = session_manager.get_session(request.session_id)
        df = session.primary_dataset.dataframe
        file_hash = session.primary_dataset.file_hash

        # 检查缓存
        cached_result = cache_manager.get(request.session_id, request.query, file_hash)
        if cached_result:
            return {
                "success": True,
                "summary": cached_result.get("summary", ""),
                "charts": cached_result.get("charts", []),
                "statistics": cached_result.get("statistics")
            }

        # 意图解析
        intent_result = await parse_intent_async(request.query, df)

        # 处理原始 AI 响应（非结构化）
        if "raw_response" in intent_result:
            return {
                "success": True,
                "summary": intent_result["raw_response"],
                "charts": [],
                "statistics": {},
                "warning": intent_result.get("warning")
            }

        # 处理解析错误
        if "error" in intent_result:
            raise HTTPException(
                status_code=500,
                detail={
                    "success": False,
                    "error": {
                        "code": ErrorCode.ANALYSIS_FAILED,
                        "message": intent_result["error"]
                    }
                }
            )

        tasks = intent_result.get("tasks", [])
        charts = []
        statistics = {}
        analysis_descriptions = []
        warning = intent_result.get("warning")

        for task in tasks:
            intent = task.get("intent")
            target_columns = task.get("target_columns", [])
            groupby = task.get("groupby")
            params = task.get("params", {})
            chart_type = task.get("chart_type")

            result = await _execute_analysis(
                df, intent, target_columns, groupby,
                task.get("groupby2"), params, request.query, chart_type
            )
            if result:
                charts.extend(result.get("charts", []))
                if result.get("statistics"):
                    statistics.update(result["statistics"])
                analysis_descriptions.append({
                    "intent": intent,
                    "target_columns": target_columns,
                    "groupby": groupby,
                    "statistics": result.get("statistics", {}),
                    "summary_template": result.get("summary", "")
                })

        # LLM 智能分析
        try:
            messages = _build_analysis_messages(
                request.query, analysis_descriptions, request.session_id
            )
            llm_client = get_llm_client()
            summary = await llm_client.achat(
                messages, temperature=0.3, max_tokens=5000
            )
        except Exception as e:
            logger.warning(f"LLM 智能分析失败，降级为模板: {e}")
            parts = [d.get("summary_template", "") for d in analysis_descriptions if d.get("summary_template")]
            summary = "\n\n".join(parts) if parts else template_polish({"row_count": len(df)}, "overview")

        # 缓存结果
        cache_result = {
            "summary": summary,
            "charts": charts,
            "statistics": statistics
        }
        cache_manager.set(request.session_id, request.query, file_hash, cache_result)
        logger.debug(f"结果已缓存: {request.query[:30]}...")

        # 持久化聊天历史到 meta.json
        try:
            session_manager.add_chat_entry(
                session_id=request.session_id,
                role="user",
                content=request.query
            )
            session_manager.add_chat_entry(
                session_id=request.session_id,
                role="assistant",
                content=summary,
                charts=charts if charts else None
            )
        except Exception as e:
            logger.warning(f"保存聊天历史失败: {e}")

        # 记录分析完成
        AnalysisLogger.log_analysis_complete(request.session_id, len(charts))

        return {
            "success": True,
            "summary": summary,
            "charts": charts,
            "statistics": statistics,
            "warning": warning
        }

    except SessionNotFoundError:
        raise HTTPException(
            status_code=404,
            detail={
                "success": False,
                "error": {
                    "code": ErrorCode.SESSION_NOT_FOUND,
                    "message": f"会话不存在或已过期: {request.session_id}"
                }
            }
        )
    except Exception as e:
        logger.error(f"分析失败: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": {
                    "code": ErrorCode.ANALYSIS_FAILED,
                    "message": f"分析失败: {str(e)}"
                }
            }
        )


@router.get("/analysis/history/{session_id}")
async def get_analysis_history(session_id: str):
    """
    获取会话的分析历史

    Args:
        session_id: 会话 ID

    Returns:
        聊天历史条目列表
    """
    session_manager = get_session_manager()

    try:
        history = session_manager.get_chat_history(session_id)
        return {
            "success": True,
            "session_id": session_id,
            "history": history,
            "count": len(history)
        }
    except SessionNotFoundError:
        raise HTTPException(
            status_code=404,
            detail={
                "success": False,
                "error": {
                    "code": ErrorCode.SESSION_NOT_FOUND,
                    "message": f"会话不存在或已过期: {session_id}"
                }
            }
        )


@router.post("/analysis/rechart")
async def rechart(request: RechartRequest):
    """
    图表类型切换接口
    复用已有的意图解析和分析执行逻辑，但覆盖 chart_type

    Args:
        request: RechartRequest 包含 session_id, query, chart_type

    Returns:
        新的图表 JSON
    """
    try:
        session_manager = get_session_manager()
        session = session_manager.get_session(request.session_id)
        df = session.primary_dataset.dataframe

        # 意图解析
        intent_result = await parse_intent_async(request.query, df)

        if "raw_response" in intent_result:
            return {
                "success": False,
                "message": "原始查询无法生成图表"
            }

        if "error" in intent_result:
            return {
                "success": False,
                "message": intent_result["error"]
            }

        tasks = intent_result.get("tasks", [])
        if not tasks:
            return {
                "success": False,
                "message": "无法识别分析意图"
            }

        # 执行分析任务，覆盖 chart_type
        charts = []
        for task in tasks:
            intent = task.get("intent")
            target_columns = task.get("target_columns", [])
            groupby = task.get("groupby")
            params = task.get("params", {})

            try:
                result = await _execute_analysis(
                    df, intent, target_columns, groupby,
                    task.get("groupby2"), params,
                    request.query, request.chart_type
                )
                if result:
                    charts.extend(result.get("charts", []))
            except Exception as e:
                logger.error(f"Rechart 分析任务失败 ({intent}): {e}")

        return {
            "success": True,
            "charts": charts
        }

    except SessionNotFoundError:
        raise HTTPException(
            status_code=404,
            detail={
                "success": False,
                "error": {
                    "code": ErrorCode.SESSION_NOT_FOUND,
                    "message": f"会话不存在或已过期: {request.session_id}"
                }
            }
        )
    except Exception as e:
        logger.error(f"Rechart 失败: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": {
                    "code": ErrorCode.ANALYSIS_FAILED,
                    "message": f"图表类型切换失败: {str(e)}"
                }
            }
        )

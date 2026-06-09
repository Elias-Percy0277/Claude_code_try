"""
分析请求 API
处理用户自然语言查询，返回分析结果和图表
支持 SSE 流式响应
"""
import asyncio
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
    analyze_categorical_distribution,
    analyze_categorical_association,
    analyze_categorical_correlation_matrix,
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
    create_confusion_matrix_chart,
    create_roc_curve_chart,
    create_feature_importance_chart,
    create_fairness_chart,
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

        # 立即发送进度事件，让前端知道请求已被接收
        yield _format_sse({"type": "progress", "message": "正在解析分析意图..."})

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

        # 意图解析完成，发送进度
        task_names = [t.get("intent", "") for t in intent_result.get("tasks", [])]
        if task_names:
            intent_labels = {
                "overview": "数据概览", "trend": "趋势分析", "correlation": "相关性分析",
                "moving_avg": "移动平均", "distribution": "分布分析", "comparison": "分组对比",
                "categorical_distribution": "分类分布", "seasonality": "季节性分析",
                "cross_comparison": "交叉对比", "categorical_association": "分类关联分析",
                "categorical_correlation": "分类相关性", "suggest": "建议查询",
                "train_model": "模型训练", "predict": "预测", "evaluate": "模型评估",
                "fairness_audit": "公平性审计", "feature_importance": "特征重要性",
            }
            labels = [intent_labels.get(n, n) for n in task_names]
            yield _format_sse({"type": "progress", "message": f"正在执行{'、'.join(labels)}..."})
        else:
            yield _format_sse({"type": "progress", "message": "正在执行数据分析..."})

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
            yield _format_sse({"type": "done"})
            return

        tasks = intent_result.get("tasks", [])
        if not tasks:
            yield _format_sse({
                "type": "error",
                "message": "无法识别分析意图"
            })
            yield _format_sse({"type": "done"})
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
                    task.get("groupby2"), params, request.query, chart_type,
                    query_session_id=request.session_id
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

        # 图表已发送，准备生成分析报告
        yield _format_sse({"type": "progress", "message": "正在生成分析报告..."})

        # 检查是否所有分析都失败（无图表、无统计数据）
        all_failed = (
            not charts
            and not any(d.get("summary_template") or d.get("statistics") for d in analysis_descriptions if "error" not in d)
        )

        # 使用 LLM 进行智能分析（带历史记忆）
        summary = ""
        if all_failed:
            # 全部失败时跳过 LLM 调用，直接用模板
            logger.info("所有分析任务失败，跳过 LLM 调用")
            error_parts = [f"- {d.get('intent', 'unknown')}: {d.get('error', '未知错误')}" for d in analysis_descriptions if "error" in d]
            summary = f"分析未能完成：\n" + "\n".join(error_parts) if error_parts else "分析未能完成，请尝试重新表述您的问题。"
            yield _format_sse({"type": "text", "delta": summary})
        else:
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
        yield _format_sse({"type": "done"})


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

    # 注入数据集上下文（如果有 Adult Income 相关特征）
    try:
        session_manager = get_session_manager()
        session = session_manager.get_session(session_id)
        df = session.primary_dataset.dataframe
        dataset_context = _detect_dataset_context(df)
        if dataset_context:
            messages.append({"role": "system", "content": dataset_context})
    except Exception:
        pass

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
    chart_type: str = None,
    query_session_id: str = None
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
        # 相关性分析 — 检测是否涉及分类列
        requested_chart_type = chart_type
        # 检查用户指定的列是否包含分类列
        mentioned_cols = [c for c in target_columns if c in df.columns]
        cat_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
        num_cols = df.select_dtypes(include=['number']).columns.tolist()
        has_cat = any(c in cat_cols for c in mentioned_cols) if mentioned_cols else False

        if has_cat or (not mentioned_cols and len(num_cols) < 2 and len(cat_cols) >= 2):
            # 分类列关联分析（Cramér's V）
            if mentioned_cols:
                cat_target = [c for c in mentioned_cols if c in cat_cols]
            else:
                cat_target = cat_cols[:8]
            if len(cat_target) >= 2:
                cat_corr_result = analyze_categorical_correlation_matrix(df, cat_target)
                result["summary"] = _format_categorical_correlation_summary(cat_corr_result)
                result["statistics"] = cat_corr_result

                chart = create_correlation_heatmap(
                    cat_corr_result["matrix"],
                    cat_corr_result["columns"],
                    "Cramér's V 分类关联热力图"
                )
                result["charts"].append(chart)
            else:
                result["summary"] = "分类列少于 2 个，无法进行关联分析"
        else:
            # 数值列相关性分析（Pearson）
            if len(num_cols) < 2:
                result["summary"] = "数值列少于 2 个，无法进行相关性分析"
            else:
                cols_to_use = mentioned_cols if mentioned_cols else num_cols[:5]
                cols_to_use = [c for c in cols_to_use if c in num_cols]
                if len(cols_to_use) < 2:
                    cols_to_use = num_cols[:5]
                corr_result = analyze_correlation(df, cols_to_use)
                result["summary"] = template_polish(corr_result, "correlation")

                if requested_chart_type == "scatter":
                    x_data = df[cols_to_use[0]].tolist()
                    y_data = df[cols_to_use[1]].tolist()
                    chart = create_scatter_plot(
                        x_data, y_data,
                        cols_to_use[0], cols_to_use[1],
                        f"{cols_to_use[0]} vs {cols_to_use[1]}"
                    )
                    result["charts"].append(chart)
                elif requested_chart_type == "pie":
                    pie_data = []
                    for pair in corr_result.get("pairs", []):
                        label = f"{pair['x']} vs {pair['y']}"
                        pie_data.append({"name": label, "value": round(abs(pair["value"]), 4)})
                    if pie_data:
                        chart = create_pie_chart(pie_data, "相关系数绝对值占比")
                        result["charts"].append(chart)
                elif requested_chart_type == "bar":
                    for pair in corr_result.get("pairs", []):
                        label = f"{pair['x']}-{pair['y']}"
                        chart = create_bar_chart([label], [pair["value"]], "相关系数")
                        result["charts"].append(chart)
                else:
                    chart = create_correlation_heatmap(
                        corr_result["matrix"],
                        corr_result["columns"],
                        "数值特征相关性分析"
                    )
                    result["charts"].append(chart)
                    if len(cols_to_use) >= 2:
                        x_data = df[cols_to_use[0]].tolist()
                        y_data = df[cols_to_use[1]].tolist()
                        chart = create_scatter_plot(
                            x_data, y_data,
                            cols_to_use[0], cols_to_use[1],
                            f"{cols_to_use[0]} vs {cols_to_use[1]}"
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
            if col not in df.columns:
                continue

            is_numeric = pd.api.types.is_numeric_dtype(df[col])

            if not is_numeric:
                # 分类列：频次统计 + 饼图/柱状图
                cat_result = analyze_categorical_distribution(df, col)
                result["summary"] = _format_categorical_summary(cat_result)
                result["statistics"] = cat_result

                requested_chart_type = chart_type or "bar"
                categories = cat_result["categories"]

                if requested_chart_type == "pie":
                    pie_data = [{"name": c["name"], "value": c["count"]} for c in categories]
                    chart = create_pie_chart(pie_data, f"{col} 分布占比", donut=False)
                else:
                    # 默认频数柱状图
                    names = [c["name"] for c in categories]
                    counts = [c["count"] for c in categories]
                    chart = create_bar_chart(names, counts, f"{col} 频数分布", x_name=col, y_name="频数")

                result["charts"].append(chart)
            else:
                # 数值列：原有逻辑
                dist_result = analyze_distribution(df, col)
                result["summary"] = template_polish(dist_result, "distribution")

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
                    # 归一化版本（百分比）
                    ct_normalized = pd.crosstab(df[groupby], df[value_col], normalize='index') * 100

                    result["statistics"] = {"crosstab": True}
                    result["statistics"]["column_type"] = "categorical"
                    result["statistics"]["value_column"] = value_col
                    result["statistics"]["groupby"] = groupby

                    groups = []
                    for group_name in ct.index:
                        row = ct.loc[group_name]
                        group_total = total_per_group[group_name]
                        group_data = {
                            "group": str(group_name).strip(),
                            "total": int(group_total)
                        }
                        for cat in row.index:
                            count = int(row[cat])
                            pct = round(count / group_total * 100, 1) if group_total > 0 else 0
                            group_data[str(cat).strip()] = count
                            group_data[f"{str(cat).strip()}_pct"] = pct
                        groups.append(group_data)

                    result["statistics"]["groups"] = groups
                    result["statistics"]["categories"] = [str(c).strip() for c in ct.columns]

                    group_labels = [str(g).strip() for g in ct.index]
                    requested_chart_type = chart_type or "bar"
                    chart_title = f"{value_col} 按 {groupby} 分组占比"

                    if requested_chart_type == "pie":
                        largest_group = max(groups, key=lambda g: g["total"])
                        pie_data = []
                        for cat in ct.columns:
                            cat_str = str(cat).strip()
                            if largest_group.get(cat_str, 0) > 0:
                                pie_data.append({"name": cat_str, "value": largest_group[cat_str]})
                        chart = create_pie_chart(pie_data, f"{groupby}={largest_group['group']} 的 {value_col} 分布", donut=True)
                        result["charts"].append(chart)
                    else:
                        # 原始计数堆叠柱状图
                        count_bar_data = []
                        for cat in ct.columns:
                            count_bar_data.append({
                                "name": str(cat).strip(),
                                "data": [int(ct.loc[g, cat]) for g in ct.index]
                            })
                        count_chart = create_grouped_bar_chart(
                            group_labels, count_bar_data,
                            f"{value_col} 按 {groupby} 分组（计数）",
                            x_name=groupby, y_name="数量"
                        )
                        for s in count_chart["option"]["series"]:
                            s["stack"] = "total"
                        result["charts"].append(count_chart)

                        # 归一化百分比堆叠柱状图
                        pct_bar_data = []
                        for cat in ct.columns:
                            pct_bar_data.append({
                                "name": str(cat).strip(),
                                "data": [round(float(ct_normalized.loc[g, cat]), 1) for g in ct.index]
                            })
                        pct_chart = create_grouped_bar_chart(
                            group_labels, pct_bar_data,
                            f"{value_col} 按 {groupby} 分组（占比%）",
                            x_name=groupby, y_name="百分比 (%)"
                        )
                        for s in pct_chart["option"]["series"]:
                            s["stack"] = "total"
                        pct_chart["option"]["yAxis"]["max"] = 100
                        result["charts"].append(pct_chart)

                    # 生成摘要
                    lines = [f"**{value_col}** 按 **{groupby}** 分组分布：\n"]
                    for g in groups:
                        parts = []
                        for cat in ct.columns:
                            cat_str = str(cat).strip()
                            pct = g.get(f"{cat_str}_pct", 0)
                            if pct > 0:
                                parts.append(f"{cat_str}: {pct}%")
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
                series_data = [
                    {"name": s["group"], "data": [s["mean"]]}
                    for s in comp_result["statistics"]
                ]

                requested_chart_type = chart_type or "bar"
                chart_title = f"{target_columns[0]} 按 {groupby} 分组"
                comp_x_label = groupby
                comp_y_label = f"{target_columns[0]} 均值"

                if requested_chart_type == "line":
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
                    chart = create_scatter_plot(
                        list(range(len(means))), means,
                        comp_x_label, comp_y_label, chart_title
                    )
                    chart["option"]["xAxis"] = {
                        "type": "category",
                        "data": groups,
                        "name": comp_x_label,
                        "nameLocation": "middle",
                        "nameGap": 50,
                        "axisLabel": {"rotate": 45}
                    }
                else:
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

    elif intent == "ml_train":
        # ML 模型训练
        from backend.core.ml_engine import AdultMLEngine, MLError, HAS_SKLEARN

        if not query_session_id:
            result["summary"] = "ML 功能需要有效的会话"
        elif not HAS_SKLEARN:
            result["summary"] = "机器学习功能不可用：scikit-learn 未安装"
        else:
            try:
                engine = AdultMLEngine()
                model_type = params.get("model_type", "random_forest")
                prep = engine.prepare(df)
                train_result = engine.train(prep["X_train"], prep["y_train"], model_type=model_type)

                # 保存 ML 状态到 session
                try:
                    session_manager = get_session_manager()
                    ml_state = engine.get_state()
                    session_manager.save_ml_state(query_session_id, ml_state)
                except Exception as e:
                    logger.warning(f"保存 ML 状态失败: {e}")

                stats = prep["stats"]
                stats["model_name"] = train_result["model_name"]
                stats["status"] = train_result["status"]
                result["statistics"] = stats

                lines = [
                    f"### 模型训练完成\n",
                    f"- **模型类型:** {train_result['model_name']}",
                    f"- **训练样本:** {stats['train_samples']}",
                    f"- **测试样本:** {stats['test_samples']}",
                    f"- **目标分布:** {stats['target_ratio']}",
                    f"- **数值特征:** {', '.join(stats['numeric_features'])}",
                    f"- **分类特征:** {', '.join(stats['categorical_features'])}",
                ]
                result["summary"] = "\n".join(lines)
            except MLError as e:
                result["summary"] = f"模型训练失败: {str(e)}"
            except Exception as e:
                logger.error(f"ML 训练异常: {e}")
                result["summary"] = f"模型训练出错: {str(e)}"

    elif intent == "ml_evaluate":
        # ML 模型评估
        from backend.core.ml_engine import AdultMLEngine, MLError, HAS_SKLEARN

        if not query_session_id:
            result["summary"] = "ML 功能需要有效的会话"
        elif not HAS_SKLEARN:
            result["summary"] = "机器学习功能不可用：scikit-learn 未安装"
        else:
            try:
                session_manager = get_session_manager()
                ml_state = session_manager.load_ml_state(query_session_id)

                if not ml_state or not ml_state.get("is_fitted"):
                    result["summary"] = "请先训练模型（输入「训练模型」）"
                else:
                    engine = AdultMLEngine()
                    engine.load_state(ml_state)
                    eval_result = engine.evaluate()
                    result["statistics"] = eval_result

                    # 混淆矩阵图
                    cm_chart = create_confusion_matrix_chart(
                        eval_result["confusion_matrix"],
                        f"{eval_result['model_name']} 混淆矩阵"
                    )
                    result["charts"].append(cm_chart)

                    # ROC 曲线
                    roc_chart = create_roc_curve_chart(
                        eval_result["roc_curve"]["fpr"],
                        eval_result["roc_curve"]["tpr"],
                        eval_result["roc_auc"],
                        f"{eval_result['model_name']} ROC 曲线"
                    )
                    result["charts"].append(roc_chart)

                    cm = eval_result["confusion_matrix"]
                    lines = [
                        f"### 模型评估结果（{eval_result['model_name']}）\n",
                        f"- **准确率:** {eval_result['accuracy']}",
                        f"- **精确率:** {eval_result['precision']}",
                        f"- **召回率:** {eval_result['recall']}",
                        f"- **F1-score:** {eval_result['f1_score']}",
                        f"- **ROC-AUC:** {eval_result['roc_auc']}",
                        f"- **PR-AUC:** {eval_result['pr_auc']}",
                        f"\n**混淆矩阵:**",
                        f"  - 真阴性 (TN): {cm['tn']}",
                        f"  - 假阳性 (FP): {cm['fp']}",
                        f"  - 假阴性 (FN): {cm['fn']}",
                        f"  - 真阳性 (TP): {cm['tp']}",
                    ]
                    result["summary"] = "\n".join(lines)
            except MLError as e:
                result["summary"] = f"模型评估失败: {str(e)}"
            except Exception as e:
                logger.error(f"ML 评估异常: {e}")
                result["summary"] = f"模型评估出错: {str(e)}"

    elif intent == "ml_feature_imp":
        # ML 特征重要性
        from backend.core.ml_engine import AdultMLEngine, MLError, HAS_SKLEARN

        if not query_session_id:
            result["summary"] = "ML 功能需要有效的会话"
        elif not HAS_SKLEARN:
            result["summary"] = "机器学习功能不可用：scikit-learn 未安装"
        else:
            try:
                session_manager = get_session_manager()
                ml_state = session_manager.load_ml_state(query_session_id)

                if not ml_state or not ml_state.get("is_fitted"):
                    result["summary"] = "请先训练模型（输入「训练模型」）"
                else:
                    engine = AdultMLEngine()
                    engine.load_state(ml_state)
                    imp_result = engine.feature_importance()
                    result["statistics"] = imp_result

                    # 特征重要性图
                    imp_chart = create_feature_importance_chart(
                        imp_result["top_features"],
                        f"{imp_result['model_name']} 特征重要性"
                    )
                    result["charts"].append(imp_chart)

                    lines = [f"### 特征重要性（{imp_result['model_name']}）\n"]
                    for i, feat in enumerate(imp_result["top_features"][:10], 1):
                        lines.append(f"{i}. **{feat['feature']}**: {feat['importance']:.4f}")
                    result["summary"] = "\n".join(lines)
            except MLError as e:
                result["summary"] = f"特征重要性分析失败: {str(e)}"
            except Exception as e:
                logger.error(f"ML 特征重要性异常: {e}")
                result["summary"] = f"特征重要性分析出错: {str(e)}"

    elif intent == "ml_fairness":
        # ML 公平性审计
        from backend.core.ml_engine import AdultMLEngine, MLError, HAS_SKLEARN

        if not query_session_id:
            result["summary"] = "ML 功能需要有效的会话"
        elif not HAS_SKLEARN:
            result["summary"] = "机器学习功能不可用：scikit-learn 未安装"
        else:
            try:
                session_manager = get_session_manager()
                ml_state = session_manager.load_ml_state(query_session_id)

                if not ml_state or not ml_state.get("is_fitted"):
                    result["summary"] = "请先训练模型（输入「训练模型」）"
                else:
                    engine = AdultMLEngine()
                    engine.load_state(ml_state)
                    fair_result = engine.fairness_audit()
                    result["statistics"] = fair_result

                    # 公平性图表
                    fair_charts = create_fairness_chart(fair_result)
                    result["charts"].extend(fair_charts)

                    lines = [f"### 公平性审计（{fair_result['model_name']}）\n"]
                    for attr_name, attr_data in fair_result.get("sensitive_attributes", {}).items():
                        lines.append(f"#### {attr_name}")
                        lines.append(f"- TPR 差异: {attr_data['tpr_gap']}")
                        lines.append(f"- FPR 差异: {attr_data['fpr_gap']}")
                        for g in attr_data["groups"]:
                            lines.append(f"  - **{g['group']}** (n={g['count']}): TPR={g['tpr']}, FPR={g['fpr']}, 准确率={g['accuracy']}")
                        lines.append("")
                    if fair_result.get("warning"):
                        lines.append(f"> {fair_result['warning']}")
                    result["summary"] = "\n".join(lines)
            except MLError as e:
                result["summary"] = f"公平性审计失败: {str(e)}"
            except Exception as e:
                logger.error(f"ML 公平性审计异常: {e}")
                result["summary"] = f"公平性审计出错: {str(e)}"

    elif intent == "ml_crossval":
        # ML 交叉验证（多模型对比）
        from backend.core.ml_engine import AdultMLEngine, MLError, HAS_SKLEARN

        if not query_session_id:
            result["summary"] = "ML 功能需要有效的会话"
        elif not HAS_SKLEARN:
            result["summary"] = "机器学习功能不可用：scikit-learn 未安装"
        else:
            try:
                session_manager = get_session_manager()
                session = session_manager.get_session(query_session_id)
                cv_df = session.primary_dataset.dataframe

                engine = AdultMLEngine()
                prep = engine.prepare(cv_df)
                X_train = prep["X_train"]
                y_train = prep["y_train"]

                # 逻辑回归交叉验证
                engine.train(X_train, y_train, model_type="logistic_regression")
                lr_cv = engine.cross_validate(X_train, y_train, cv=5)

                # 随机森林交叉验证
                engine.train(X_train, y_train, model_type="random_forest")
                rf_cv = engine.cross_validate(X_train, y_train, cv=5)

                # 保存随机森林模型到 session（后续评估使用）
                ml_state = engine.get_state()
                session_manager.save_ml_state(query_session_id, ml_state)

                cv_stats = {
                    "logistic_regression": lr_cv,
                    "random_forest": rf_cv,
                    "training_stats": prep["stats"],
                }
                result["statistics"] = cv_stats

                # 生成对比摘要
                lines = [
                    "### 5 折交叉验证结果对比\n",
                    f"- **训练样本:** {prep['stats']['train_samples']}",
                    f"- **测试样本:** {prep['stats']['test_samples']}",
                    f"- **目标分布:** {prep['stats']['target_ratio']}\n",
                    "| 模型 | 平均 F1 | 标准差 | 各折 F1 |",
                    "|------|---------|--------|---------|",
                    f"| 逻辑回归 | {lr_cv['mean_f1']} | {lr_cv['std_f1']} | {', '.join(str(s) for s in lr_cv['fold_scores'])} |",
                    f"| 随机森林 | {rf_cv['mean_f1']} | {rf_cv['std_f1']} | {', '.join(str(s) for s in rf_cv['fold_scores'])} |",
                    "",
                ]

                # 推荐模型
                if rf_cv["mean_f1"] > lr_cv["mean_f1"]:
                    lines.append(f"**推荐模型：随机森林**（F1: {rf_cv['mean_f1']} vs {lr_cv['mean_f1']}）")
                else:
                    lines.append(f"**推荐模型：逻辑回归**（F1: {lr_cv['mean_f1']} vs {rf_cv['mean_f1']}）")

                lines.append("\n随机森林模型已训练并保存，可输入「评估模型效果」查看完整评估。")
                result["summary"] = "\n".join(lines)

                # 对比柱状图
                chart = create_grouped_bar_chart(
                    ["平均F1", "标准差"],
                    [
                        {"name": "逻辑回归", "data": [lr_cv["mean_f1"], lr_cv["std_f1"]]},
                        {"name": "随机森林", "data": [rf_cv["mean_f1"], rf_cv["std_f1"]]},
                    ],
                    "交叉验证结果对比",
                    x_name="指标", y_name="分数"
                )
                result["charts"].append(chart)

            except MLError as e:
                result["summary"] = f"交叉验证失败: {str(e)}"
            except Exception as e:
                logger.error(f"ML 交叉验证异常: {e}")
                result["summary"] = f"交叉验证出错: {str(e)}"

    return result


async def _flushing_sse_wrapper(gen: AsyncGenerator) -> AsyncGenerator[str, None]:
    """
    包装 SSE 生成器，每次 yield 后强制交出事件循环控制权。

    这确保 ASGI 服务器（uvicorn）在生成每个 SSE 数据块后立即将其刷新到网络，
    而不是在内部缓冲区中积压多个块后再批量发送。
    """
    async for chunk in gen:
        yield chunk
        await asyncio.sleep(0)


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
        _flushing_sse_wrapper(analyze_stream_generator(request)),
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
                task.get("groupby2"), params, request.query, chart_type,
                query_session_id=request.session_id
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
                    request.query, request.chart_type,
                    query_session_id=request.session_id
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


def _detect_dataset_context(df: pd.DataFrame) -> str:
    """
    检测数据集是否为 Adult Income 数据集，返回上下文提示词
    """
    cols = set(df.columns.tolist())
    adult_indicators = {'age', 'education-num', 'capital-gain', 'capital-loss', 'hours-per-week',
                        'workclass', 'occupation', 'marital-status', 'relationship'}

    match_count = len(cols & adult_indicators)
    if match_count < 4:
        return ""

    # 检测目标列
    target_col = None
    for col in df.columns:
        unique_vals = df[col].dropna().astype(str).unique()
        if any(v in {'<=50K', '>50K', '<=50K.', '>50K.'} for v in unique_vals):
            target_col = col
            break

    context_parts = [
        "**数据集上下文（系统自动检测）：**",
        "当前数据集为 **Adult Income（人口收入）数据集**，来自 1994 年美国人口普查。",
        f"- 目标变量：`{target_col}`（<=50K / >50K，预测个人年收入是否超过 5 万美元）",
        "- 关键特征：age（年龄）、education-num（教育年限）、occupation（职业）、hours-per-week（每周工时）、capital-gain/loss（资本收益/损失）",
        "- `fnlwgt` 是抽样权重，非个人属性，分析时应注意",
        "- `education` 与 `education-num` 重复（前者为文字标签）",
        "- 数据存在类别不平衡（约 75% 为 <=50K）",
        "",
        "请在解读分析结果时结合此背景知识。例如：",
        "- 讨论收入差异时应注意性别/种族的公平性",
        "- capital-gain/loss 大量为零是正常现象",
        "- 教育水平与收入的正相关是已知的社会学规律",
    ]

    return "\n".join(context_parts)


def _format_categorical_summary(cat_result: dict) -> str:
    """格式化分类列频次统计摘要"""
    lines = [f"**{cat_result['column']}** 分类分布（共 {cat_result['total_count']} 条，{cat_result['unique_count']} 个类别）：\n"]
    if cat_result["mode"]:
        lines.append(f"- 众数：**{cat_result['mode']}**\n")
    for cat in cat_result["categories"]:
        lines.append(f"- **{cat['name']}**：{cat['count']} 条（{cat['percentage']}%）")
    return "\n".join(lines)


def _format_categorical_correlation_summary(corr_result: dict) -> str:
    """格式化 Cramér's V 关联分析摘要"""
    lines = ["Cramér's V 分类关联分析结果：\n"]
    columns = corr_result["columns"]
    matrix = corr_result["matrix"]
    for i, col1 in enumerate(columns):
        for j, col2 in enumerate(columns):
            if i < j:
                v = matrix[col1][col2]
                if v > 0.3:
                    strength = "强关联"
                elif v > 0.1:
                    strength = "中等关联"
                else:
                    strength = "弱关联"
                lines.append(f"- **{col1}** ↔ **{col2}**：V = {v:.4f}（{strength}）")
    return "\n".join(lines)

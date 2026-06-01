"""
分析请求 API — 双 Agent 架构
Agent1（规划调度）→ 后端执行 → Agent2（分析顾问，按需）→ SSE 响应
"""
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.session.manager import get_session_manager, SessionNotFoundError
from backend.agent.planner import plan as agent1_plan
from backend.agent.advisor import consult as agent2_consult
from backend.core.executor import execute_operation
from backend.core.operations import validate_operation
from backend.agent.llm_client import get_planner_client, get_advisor_client
from backend.core.logger_config import get_logger
from backend.core.logging_middleware import AnalysisLogger
from backend.models.schemas import AnalysisRequest, RechartRequest, ErrorCode

logger = get_logger(__name__)

router = APIRouter()


class ExecuteSuggestionRequest(BaseModel):
    """执行采纳建议的请求"""
    session_id: str
    operation: str
    parameters: dict


def _format_sse(data: dict) -> str:
    """格式化为 SSE 格式"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


async def analyze_stream_generator(request: AnalysisRequest) -> AsyncGenerator[str, None]:
    """
    双 Agent 架构的 SSE 流式分析流程

    1. 获取 session + context
    2. Agent1 生成计划
    3. 按计划执行：operation → executor, consultation → Agent2
    4. SSE 推送各阶段结果
    """
    try:
        session_manager = get_session_manager()
        session = session_manager.get_session(request.session_id)
        context = session.get_context()

        df = session.primary_dataset.dataframe
        AnalysisLogger.log_analysis_start(request.session_id, request.query)

        # --- Agent1: 规划调度 ---
        planner_client = get_planner_client()
        advisor_client = get_advisor_client()
        plan_result = await agent1_plan(request.query, context, planner_client)
        steps = plan_result.get("plan", [])

        if not steps:
            yield _format_sse({"type": "error", "message": "无法识别分析意图"})
            yield _format_sse({"type": "done"})
            return

        logger.info(f"Agent1 计划: {json.dumps(steps, ensure_ascii=False)[:200]}")

        all_charts = []
        all_summaries = []

        for step in steps:
            step_type = step.get("type")

            # --- 操作步骤 ---
            if step_type == "operation":
                op_name = step.get("operation", "")
                op_params = step.get("parameters", {})

                validation = validate_operation(op_name, op_params, df)
                if not validation["valid"]:
                    yield _format_sse({"type": "warning", "message": f"操作 {op_name} 参数无效: {'; '.join(validation['errors'])}"})
                    continue

                result = await execute_operation(df, op_name, op_params)

                # 更新会话上下文
                session.update_context(result)
                session_manager.save_context(request.session_id)

                if result.chart_options:
                    all_charts.extend(result.chart_options)
                    yield _format_sse({"type": "charts", "data": result.chart_options})

                if result.summary_text:
                    all_summaries.append(result.summary_text)
                    yield _format_sse({"type": "text", "delta": result.summary_text + "\n\n"})

                if result.status == "error":
                    yield _format_sse({"type": "warning", "message": result.error_message})

            # --- 咨询步骤 ---
            elif step_type == "consultation":
                user_ctx = step.get("context", request.query)
                context = session.get_context()

                suggestion_result = await agent2_consult(context, user_ctx, advisor_client)

                if suggestion_result.get("interpretation"):
                    yield _format_sse({"type": "text", "delta": suggestion_result["interpretation"] + "\n\n"})

                suggestions = suggestion_result.get("suggestions", [])
                if suggestions:
                    yield _format_sse({"type": "suggestions", "data": suggestions})

            # --- 错误步骤 ---
            elif step_type == "error":
                yield _format_sse({"type": "warning", "message": step.get("message", "操作无法执行")})

        # 持久化聊天历史
        combined_summary = "\n".join(all_summaries) if all_summaries else ""
        try:
            session_manager.add_chat_entry(session_id=request.session_id, role="user", content=request.query)
            session_manager.add_chat_entry(
                session_id=request.session_id,
                role="assistant",
                content=combined_summary,
                charts=all_charts if all_charts else None,
            )
        except Exception as e:
            logger.warning(f"保存聊天历史失败: {e}")

        AnalysisLogger.log_analysis_complete(request.session_id, len(all_charts))
        yield _format_sse({"type": "done"})

    except SessionNotFoundError:
        yield _format_sse({"type": "error", "message": f"会话不存在或已过期"})
    except Exception as e:
        logger.error(f"分析过程异常: {e}")
        yield _format_sse({"type": "error", "message": f"分析过程出错: {str(e)}"})


async def execute_suggestion_generator(request: ExecuteSuggestionRequest) -> AsyncGenerator[str, None]:
    """
    执行用户采纳的建议（跳过 Agent1，直接执行操作）
    """
    try:
        session_manager = get_session_manager()
        session = session_manager.get_session(request.session_id)
        df = session.primary_dataset.dataframe

        validation = validate_operation(request.operation, request.parameters, df)
        if not validation["valid"]:
            yield _format_sse({"type": "error", "message": "; ".join(validation["errors"])})
            return

        result = await execute_operation(df, request.operation, request.parameters)

        session.update_context(result)
        session_manager.save_context(request.session_id)

        if result.chart_options:
            yield _format_sse({"type": "charts", "data": result.chart_options})

        if result.summary_text:
            yield _format_sse({"type": "text", "delta": result.summary_text})

        if result.status == "error":
            yield _format_sse({"type": "warning", "message": result.error_message})

        try:
            session_manager.add_chat_entry(
                session_id=request.session_id,
                role="user",
                content=f"[执行建议] {request.operation}({request.parameters})",
            )
            session_manager.add_chat_entry(
                session_id=request.session_id,
                role="assistant",
                content=result.summary_text,
                charts=result.chart_options if result.chart_options else None,
            )
        except Exception as e:
            logger.warning(f"保存聊天历史失败: {e}")

        yield _format_sse({"type": "done"})

    except SessionNotFoundError:
        yield _format_sse({"type": "error", "message": "会话不存在或已过期"})
    except Exception as e:
        logger.error(f"建议执行异常: {e}")
        yield _format_sse({"type": "error", "message": f"执行失败: {str(e)}"})


# ---- API 路由 ----

@router.post("/analysis")
async def analyze(request: AnalysisRequest):
    """主分析端点（SSE 流式响应）"""
    return StreamingResponse(
        analyze_stream_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/analysis/execute")
async def execute_suggestion(request: ExecuteSuggestionRequest):
    """执行采纳的建议（SSE 流式响应）"""
    return StreamingResponse(
        execute_suggestion_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/analysis/history/{session_id}")
async def get_analysis_history(session_id: str):
    """获取会话的分析历史"""
    session_manager = get_session_manager()
    try:
        history = session_manager.get_chat_history(session_id)
        return {"success": True, "session_id": session_id, "history": history, "count": len(history)}
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail={"success": False, "error": {"code": ErrorCode.SESSION_NOT_FOUND, "message": f"会话不存在或已过期: {session_id}"}})


@router.post("/analysis/rechart")
async def rechart(request: RechartRequest):
    """图表类型切换"""
    try:
        session_manager = get_session_manager()
        session = session_manager.get_session(request.session_id)
        df = session.primary_dataset.dataframe

        # 使用 Agent1 解析意图，然后覆盖 chart_type
        context = session.get_context()
        plan_result = await agent1_plan(request.query, context, get_planner_client())

        charts = []
        for step in plan_result.get("plan", []):
            if step.get("type") != "operation":
                continue
            params = step.get("parameters", {})
            params["chart_type"] = request.chart_type
            result = await execute_operation(df, step["operation"], params)
            charts.extend(result.chart_options)

        return {"success": True, "charts": charts}

    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail={"success": False, "error": {"code": ErrorCode.SESSION_NOT_FOUND, "message": f"会话不存在或已过期: {request.session_id}"}})
    except Exception as e:
        logger.error(f"Rechart 失败: {e}")
        raise HTTPException(status_code=500, detail={"success": False, "error": {"code": ErrorCode.ANALYSIS_FAILED, "message": f"图表类型切换失败: {str(e)}"}})

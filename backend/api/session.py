# 模块职责：会话管理 API，提供会话重命名、有效性检查、列表查询、删除及过期清理等接口，
# 负责将 HTTP 请求转发至会话管理器（SessionManager）并统一包装响应与错误码。
"""
会话管理 API
提供会话检查、列表、删除等接口
"""
import logging
from typing import List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.session.manager import get_session_manager, SessionNotFoundError
from backend.models.schemas import ErrorCode

logger = logging.getLogger(__name__)

router = APIRouter()


class RenameRequest(BaseModel):
    name: str


# AI-assisted: 使用 Claude 生成会话重命名路由，人工校验后保留原逻辑
@router.patch("/session/{session_id}")
async def rename_session(session_id: str, body: RenameRequest):
    """
    重命名会话

    功能：更新指定会话的显示名称，会话不存在时返回 404，内部错误返回 500。

    Args:
        session_id: 目标会话 ID
        body: RenameRequest 对象，包含新的会话名称 name

    Returns:
        dict: 重命名成功时返回 {"success": True, "message": "已重命名"}；
              失败时抛出 HTTPException（404 或 500）
    """
    session_manager = get_session_manager()

    try:
        session_manager.rename_session(session_id, body.name)
        return {"success": True, "message": "已重命名"}
    except SessionNotFoundError:
        raise HTTPException(
            status_code=404,
            detail={"success": False, "error": {"code": "SESSION_NOT_FOUND", "message": f"会话不存在: {session_id}"}}
        )
    except Exception as e:
        logger.error(f"重命名会话失败: {e}")
        raise HTTPException(status_code=500, detail={"success": False, "error": {"message": str(e)}})


# AI-assisted: 使用 Claude 实现会话有效性检查接口，人工校验后保留原逻辑
@router.get("/session/{session_id}")
async def check_session(session_id: str):
    """
    检查会话是否有效

    功能：查询会话是否存在且有效，返回主数据集的文件名、行数、列名等概要信息；
    会话不存在时返回 valid=False 而非抛异常，便于前端静默处理。

    Args:
        session_id: 会话 ID

    Returns:
        dict: 会话有效性标志及概要信息（filename、row_count、columns 等）
    """
    session_manager = get_session_manager()

    try:
        info = session_manager.get_session_info(session_id)
        primary = info["datasets"][0] if info["datasets"] else {}
        return {
            "success": True,
            "valid": True,
            "session_id": info["session_id"],
            "filename": primary.get("original_filename", ""),
            "created_at": info["created_at"],
            "last_accessed": info["last_accessed"],
            "row_count": info["total_rows"],
            "columns": primary.get("columns", []),
            "datasets": info["datasets"],
            "dataset_count": info["dataset_count"],
            "total_rows": info["total_rows"]
        }
    except SessionNotFoundError:
        return {
            "success": False,
            "valid": False,
            "error": {
                "code": ErrorCode.SESSION_NOT_FOUND,
                "message": f"会话不存在或已过期: {session_id}"
            }
        }


# AI-assisted: 使用 Claude 实现会话列表查询接口，手动调整了过期会话过滤逻辑
@router.get("/sessions")
async def list_sessions(
    include_expired: bool = Query(False, description="是否包含过期会话")
):
    """
    列出所有会话

    功能：返回当前所有会话的概要列表，默认过滤掉已过期会话，可通过参数保留。

    Args:
        include_expired: 是否在结果中包含已过期的会话（默认 False）

    Returns:
        dict: {"success": True, "sessions": [...], "count": N}
    """
    session_manager = get_session_manager()

    sessions = session_manager.list_sessions()

    if not include_expired:
        sessions = [s for s in sessions if not s.get("is_expired", False)]

    return {
        "success": True,
        "sessions": sessions,
        "count": len(sessions)
    }


# AI-assisted: 使用 Claude 实现会话删除接口，手动调整了删除失败的错误码
@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """
    删除会话

    功能：删除指定会话及其关联的资源（数据集、聊天历史等），失败时返回 500。

    Args:
        session_id: 待删除的会话 ID

    Returns:
        dict: 删除成功时返回 {"success": True, "message": "会话 {id} 已删除"}
    """
    session_manager = get_session_manager()

    try:
        session_manager.delete_session(session_id)
        return {
            "success": True,
            "message": f"会话 {session_id} 已删除"
        }
    except Exception as e:
        logger.error(f"删除会话失败: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": {
                    "code": "DELETE_FAILED",
                    "message": f"删除会话失败: {str(e)}"
                }
            }
        )


# AI-assisted: 使用 Claude 实现过期会话批量清理接口，人工校验后保留原逻辑
@router.post("/sessions/cleanup")
async def cleanup_sessions():
    """
    清理过期会话

    功能：触发会话管理器的过期清理流程，回收失效会话占用的资源。

    Returns:
        dict: {"success": True, "message": "已清理 N 个过期会话", "deleted_count": N}
    """
    session_manager = get_session_manager()

    count = session_manager.cleanup_expired_sessions()

    return {
        "success": True,
        "message": f"已清理 {count} 个过期会话",
        "deleted_count": count
    }


# AI-assisted: 使用 Claude 实现会话统计信息接口，人工校验后保留原逻辑
@router.get("/sessions/stats")
async def get_session_stats():
    """
    获取会话统计信息

    功能：返回会话管理器的聚合统计（总数、活跃数、过期数等），用于前端展示运行状态。

    Returns:
        dict: {"success": True, "stats": {...}}
    """
    session_manager = get_session_manager()

    stats = session_manager.get_stats()

    return {
        "success": True,
        "stats": stats
    }

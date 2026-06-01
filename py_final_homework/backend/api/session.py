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


@router.patch("/session/{session_id}")
async def rename_session(session_id: str, body: RenameRequest):
    """重命名会话"""
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


@router.get("/session/{session_id}")
async def check_session(session_id: str):
    """
    检查会话是否有效

    Args:
        session_id: 会话 ID

    Returns:
        会话信息
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


@router.get("/sessions")
async def list_sessions(
    include_expired: bool = Query(False, description="是否包含过期会话")
):
    """
    列出所有会话

    Args:
        include_expired: 是否包含过期会话

    Returns:
        会话列表
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


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """
    删除会话

    Args:
        session_id: 会话 ID

    Returns:
        删除结果
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


@router.post("/sessions/cleanup")
async def cleanup_sessions():
    """
    清理过期会话

    Returns:
        清理结果
    """
    session_manager = get_session_manager()

    count = session_manager.cleanup_expired_sessions()

    return {
        "success": True,
        "message": f"已清理 {count} 个过期会话",
        "deleted_count": count
    }


@router.get("/sessions/stats")
async def get_session_stats():
    """
    获取会话统计信息

    Returns:
        统计信息
    """
    session_manager = get_session_manager()

    stats = session_manager.get_stats()

    return {
        "success": True,
        "stats": stats
    }

"""
文件上传 API
处理数据文件上传、会话创建、多数据集管理
"""
import io
import os
import hashlib
import logging
import tempfile
from typing import Dict, Any, List, Optional
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse

from backend.session.manager import get_session_manager, SessionNotFoundError
from backend.core.data_loader import load_from_fileobj, validate_file_extension, load_names_file, load_index_file
from backend.core.preprocessor import preprocess_data, validate_dataframe
from backend.core.logger_config import get_logger
from backend.core.logging_middleware import FileUploadLogger
from backend.models.schemas import (
    UploadResponse,
    DatasetInfo,
    ErrorResponse,
    ErrorDetail,
    ErrorCode
)

logger = get_logger(__name__)

router = APIRouter()

# 配置
MAX_FILE_SIZE = 60 * 1024 * 1024  # 60MB
ALLOWED_EXTENSIONS = {'.csv', '.xlsx', '.json', '.xls', '.data', '.test', '.names', '.index'}
MAX_DATASETS_PER_SESSION = 10  # 每个会话最多数据集数量


def _process_uploaded_file(file: UploadFile, content: bytes) -> tuple:
    """
    处理单个上传文件

    Returns:
        (dataframe, filename, file_hash) 或 (None, metadata_dict, file_hash) for .names files
    """
    import io
    import pandas as pd

    file_hash = hashlib.md5(content).hexdigest()[:8]
    logger.debug(f"开始处理文件: {file.filename}, 大小: {len(content)} bytes")

    # 验证文件扩展名
    try:
        ext = validate_file_extension(file.filename)
        logger.debug(f"文件扩展名验证通过: {file.filename} -> {ext}")
    except Exception as e:
        logger.error(f"文件扩展名验证失败: {file.filename} - {e}")
        raise HTTPException(
            status_code=400,
            detail={
                "success": False,
                "error": {
                    "code": ErrorCode.INVALID_FILE_FORMAT,
                    "message": str(e)
                }
            }
        )

    # 重置文件指针
    file.file = io.BytesIO(content)

    # 处理 .names 和 .index 文件（返回元数据）
    if ext == '.names':
        try:
            # 尝试多种编码解码
            decoded_content = None
            for encoding in ['utf-8', 'gbk', 'latin-1', 'iso-8859-1']:
                try:
                    decoded_content = content.decode(encoding)
                    break
                except (UnicodeDecodeError, LookupError):
                    continue

            if decoded_content is None:
                raise ValueError("无法解码文件内容，尝试了 UTF-8、GBK、Latin-1、ISO-8859-1 编码")

            # 创建临时文件来处理 .names 文件
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.names', encoding='utf-8') as tmp:
                tmp.write(decoded_content)
                tmp_path = tmp.name
            try:
                metadata = load_names_file(tmp_path)
                attrs_count = len(metadata.get('attributes', []))
                FileUploadLogger.log_names_parsing(file.filename, attrs_count)
                return None, metadata, file_hash
            finally:
                os.unlink(tmp_path)
        except Exception as e:
            logger.error(f".names 文件解析失败 {file.filename}: {e}")
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "error": {
                        "code": ErrorCode.FILE_PARSE_FAILED,
                        "message": f".names 文件解析失败: {str(e)}"
                    }
                }
            )

    if ext == '.index':
        try:
            # 尝试多种编码解码
            decoded_content = None
            for encoding in ['utf-8', 'gbk', 'latin-1', 'iso-8859-1']:
                try:
                    decoded_content = content.decode(encoding)
                    break
                except (UnicodeDecodeError, LookupError):
                    continue

            if decoded_content is None:
                raise ValueError("无法解码文件内容，尝试了 UTF-8、GBK、Latin-1、ISO-8859-1 编码")

            # 创建临时文件来处理 .index 文件
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.index', encoding='utf-8') as tmp:
                tmp.write(decoded_content)
                tmp_path = tmp.name
            try:
                metadata = load_index_file(tmp_path)
                files_count = len(metadata.get('files', []))
                logger.info(f"✓ 解析 .index 文件: {file.filename}, 标题: {metadata.get('title', '')}, 文件数: {files_count}")
                return None, metadata, file_hash
            finally:
                os.unlink(tmp_path)
        except Exception as e:
            logger.error(f".index 文件解析失败 {file.filename}: {e}")
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "error": {
                        "code": ErrorCode.FILE_PARSE_FAILED,
                        "message": f".index 文件解析失败: {str(e)}"
                    }
                }
            )

    # 加载数据文件
    try:
        logger.debug(f"开始加载数据文件: {file.filename}")
        df = load_from_fileobj(file.file, file.filename)
        logger.info(f"✓ 数据加载成功: {file.filename}, {len(df)} 行 x {len(df.columns)} 列")
        FileUploadLogger.log_data_processing("加载完成", {
            "文件名": file.filename,
            "行数": len(df),
            "列数": len(df.columns)
        })

        # 预处理数据
        logger.debug(f"开始预处理数据...")
        df = preprocess_data(
            df,
            clean_names=True,
            infer_dates=True,
            handle_missing=True,
            validate=True
        )
        logger.info(f"✓ 数据预处理完成: {len(df)} 行 x {len(df.columns)} 列")
        FileUploadLogger.log_data_processing("预处理完成", {
            "处理后行数": len(df),
            "处理后列数": len(df.columns)
        })

        # 检查是否有可分析的列
        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
        logger.debug(f"数值列: {numeric_cols}")
        if not numeric_cols:
            raise ValueError("数据集中没有数值列可供分析")

        return df, file.filename, file_hash

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "success": False,
                "error": {
                    "code": ErrorCode.NO_ANALYZABLE_COLUMNS if "数值列" in str(e) else ErrorCode.FILE_PARSE_FAILED,
                    "message": str(e)
                }
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail={
                "success": False,
                "error": {
                    "code": ErrorCode.FILE_PARSE_FAILED,
                    "message": f"文件解析失败: {str(e)}"
                }
            }
        )


@router.post("/upload", response_model=UploadResponse)
async def upload_files(
    files: List[UploadFile] = File(...),
    session_id: Optional[str] = Query(None, description="向现有会话添加文件（可选）")
):
    """
    上传数据文件并创建/更新会话

    Args:
        files: 上传的文件列表（支持多文件）
        session_id: 现有会话 ID（可选，提供则向现有会话添加文件）

    Returns:
        UploadResponse: 包含 session_id 和数据集信息

    Raises:
        HTTPException: 文件格式错误、文件过大、解析失败等
    """
    session_manager = get_session_manager()

    # 记录上传开始
    FileUploadLogger.log_upload_start(files, session_id)

    # 区分数据文件和元数据文件（.names 和 .index）
    metadata_extensions = ('.names', '.index')
    data_files = [f for f in files if not f.filename.endswith(metadata_extensions)]
    metadata_files = [f for f in files if f.filename.endswith(metadata_extensions)]

    logger.debug(f"文件分类: {len(data_files)} 个数据文件, {len(metadata_files)} 个元数据文件")

    # 验证所有文件名
    for file in files:
        if not file.filename:
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "error": {
                        "code": ErrorCode.INVALID_FILE_FORMAT,
                        "message": "文件名不能为空"
                    }
                }
            )

    # 如果指定了 session_id，验证会话是否存在
    existing_session = None
    if session_id:
        try:
            existing_session = session_manager.get_session(session_id)
            if existing_session.dataset_count >= MAX_DATASETS_PER_SESSION:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "success": False,
                        "error": {
                            "code": ErrorCode.INVALID_FILE_FORMAT,
                            "message": f"会话已达到最大数据集数量 ({MAX_DATASETS_PER_SESSION})"
                        }
                    }
                )
        except SessionNotFoundError:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": {
                        "code": ErrorCode.SESSION_NOT_FOUND,
                        "message": "会话不存在或已过期"
                    }
                }
            )

    # 第一阶段：收集所有文件内容
    file_contents = []
    for file in files:
        content = await file.read()
        file_size = len(content)

        if file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail={
                    "success": False,
                    "error": {
                        "code": ErrorCode.FILE_TOO_LARGE,
                        "message": f"文件 {file.filename} 过大 ({file_size / 1024 / 1024:.1f}MB)，最大支持 60MB"
                    }
                }
            )

        if file_size == 0:
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "error": {
                        "code": ErrorCode.FILE_PARSE_FAILED,
                        "message": f"文件 {file.filename} 为空"
                    }
                }
            )

        file_contents.append((file, content))
        logger.info(f"接收文件: {file.filename}, 大小: {file_size} bytes")

    # 第二阶段：先处理元数据文件（.names 和 .index），再处理数据文件
    metadata_dict = {}  # 存储元数据文件内容

    # 先处理所有元数据文件
    for file, content in file_contents:
        try:
            ext = validate_file_extension(file.filename)
        except Exception:
            continue  # 跳过无效文件

        if ext in ('.names', '.index'):
            try:
                _, metadata, _ = _process_uploaded_file(file, content)
                metadata_dict[file.filename] = metadata
                logger.debug(f"✓ 解析元数据文件: {file.filename} ({ext})")
            except HTTPException:
                raise
            except Exception as e:
                logger.warning(f"⚠ 元数据文件解析失败 {file.filename}: {e}，跳过该文件")

    # 再处理数据文件
    processed_datasets = []
    failed_files = []
    for file, content in file_contents:
        try:
            ext = validate_file_extension(file.filename)
        except Exception as e:
            logger.warning(f"跳过无效文件 {file.filename}: {e}")
            continue  # 跳过无效文件

        logger.info(f"检查文件: {file.filename}, 扩展名: {ext}")

        if ext not in ('.names', '.index'):
            logger.info(f"开始处理数据文件: {file.filename}")
            try:
                df, filename_or_metadata, file_hash = _process_uploaded_file(file, content)

                # 生成数据集名称并应用列名（如果有对应的元数据文件）
                dataset_name = filename_or_metadata
                base_name = Path(filename_or_metadata).stem
                for meta_file, metadata in metadata_dict.items():
                    if Path(meta_file).stem == base_name:
                        # .names 文件有 title 和 attributes
                        if metadata.get('title'):
                            dataset_name = metadata['title']

                        # 应用列名（只有当 .names 文件有属性且数量与列数匹配时才应用）
                        attributes = metadata.get('attributes', [])
                        actual_cols = len(df.columns)

                        if attributes:
                            # 如果属性数量与列数完全匹配，或者只多一个（class列）
                            if len(attributes) == actual_cols or len(attributes) == actual_cols - 1 or len(attributes) == actual_cols + 1:
                                column_names = [attr.get('name', f'col_{i}') for i, attr in enumerate(attributes)]
                                # 调整列数以匹配实际数据
                                if len(column_names) > actual_cols:
                                    column_names = column_names[:actual_cols]
                                elif len(column_names) < actual_cols:
                                    # 添加默认列名（通常是 class 列）
                                    while len(column_names) < actual_cols:
                                        column_names.append(f'col_{len(column_names)}')
                                df.columns = column_names
                                FileUploadLogger.log_column_mapping(actual_cols, len(attributes), True)
                                logger.debug(f"  应用的列名: {column_names[:5]}... (共{len(column_names)}列)")
                            else:
                                FileUploadLogger.log_column_mapping(actual_cols, len(attributes), False)
                        break

                processed_datasets.append({
                    'dataframe': df,
                    'filename': filename_or_metadata,
                    'file_hash': file_hash,
                    'dataset_name': dataset_name
                })

            except HTTPException as he:
                error_msg = he.detail.get('error', {}).get('message', str(he)) if isinstance(he.detail, dict) else str(he)
                logger.error(f"处理文件失败 {file.filename}: {error_msg}")
                failed_files.append({'filename': file.filename, 'error': error_msg})
                continue
            except Exception as e:
                logger.error(f"处理文件失败 {file.filename}: {type(e).__name__} - {e}")
                import traceback
                logger.error(traceback.format_exc())
                failed_files.append({'filename': file.filename, 'error': str(e)})
                continue

    if not processed_datasets:
        failed_names = ', '.join(f['filename'] for f in failed_files)
        raise HTTPException(
            status_code=400,
            detail={
                "success": False,
                "error": {
                    "code": ErrorCode.FILE_PARSE_FAILED,
                    "message": f"所有数据文件处理失败: {failed_names}"
                }
            }
        )

    # 创建会话或添加到现有会话
    try:
        if existing_session:
            # 添加到现有会话
            for ds in processed_datasets:
                dataset = session_manager.add_dataset_to_session(
                    session_id=session_id,
                    dataframe=ds['dataframe'],
                    original_filename=ds['filename'],
                    file_hash=ds['file_hash'],
                    dataset_name=ds['dataset_name']
                )
                processed_datasets[processed_datasets.index(ds)]['dataset_id'] = dataset.dataset_id

            # 获取更新后的会话信息
            session = session_manager.get_session(session_id)
        else:
            # 创建新会话
            if len(processed_datasets) == 1:
                ds = processed_datasets[0]
                session = session_manager.create_session(
                    dataframe=ds['dataframe'],
                    original_filename=ds['filename'],
                    file_hash=ds['file_hash'],
                    dataset_name=ds['dataset_name']
                )
                processed_datasets[0]['dataset_id'] = session.primary_dataset.dataset_id
            else:
                # 多文件：创建会话后逐个添加
                first_ds = processed_datasets[0]
                session = session_manager.create_session(
                    dataframe=first_ds['dataframe'],
                    original_filename=first_ds['filename'],
                    file_hash=first_ds['file_hash'],
                    dataset_name=first_ds['dataset_name']
                )
                processed_datasets[0]['dataset_id'] = session.primary_dataset.dataset_id

                # 添加其余数据集
                for ds in processed_datasets[1:]:
                    dataset = session_manager.add_dataset_to_session(
                        session_id=session.session_id,
                        dataframe=ds['dataframe'],
                        original_filename=ds['filename'],
                        file_hash=ds['file_hash'],
                        dataset_name=ds['dataset_name']
                    )
                    processed_datasets[processed_datasets.index(ds)]['dataset_id'] = dataset.dataset_id

        # 构建响应
        dataset_infos = []
        for ds in processed_datasets:
            df = ds['dataframe']
            dataset_infos.append(DatasetInfo(
                dataset_id=ds['dataset_id'],
                dataset_name=ds['dataset_name'],
                original_filename=ds['filename'],
                row_count=len(df),
                columns=df.columns.tolist()
            ))

        # 构建响应消息，包含元数据文件信息
        metadata_extensions = ('.names', '.index')
        metadata_count = len([f for f in metadata_dict.keys() if any(f.endswith(ext) for ext in metadata_extensions)])
        message_parts = []
        if failed_files:
            failed_names = ', '.join(f['filename'] for f in failed_files)
            message_parts.append(f"警告: {len(failed_files)} 个文件处理失败 ({failed_names})")
        if metadata_count > 0:
            message_parts.append(f"成功解析 {metadata_count} 个元数据文件")
        message_parts.append(f"成功上传 {len(processed_datasets)} 个数据集")

        # 记录上传成功
        FileUploadLogger.log_upload_success(
            files=[f for f in files if not f.filename.endswith(metadata_extensions)],
            session_id=session.session_id,
            total_rows=session.total_rows
        )
        if existing_session:
            message_parts.append("到现有会话")

        return UploadResponse(
            success=True,
            session_id=session.session_id,
            datasets=dataset_infos,
            dataset_count=session.dataset_count,
            total_rows=session.total_rows,
            message="，".join(message_parts) + "。"
        )

    except Exception as e:
        logger.error(f"上传处理失败: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": {
                    "code": ErrorCode.ANALYSIS_FAILED,
                    "message": f"处理上传时出错: {str(e)}"
                }
            }
        )


@router.delete("/session/{session_id}/dataset/{dataset_id}")
async def delete_dataset(session_id: str, dataset_id: str):
    """
    从会话中删除数据集

    Args:
        session_id: 会话 ID
        dataset_id: 数据集 ID

    Returns:
        成功/失败响应
    """
    session_manager = get_session_manager()

    try:
        # 检查会话是否存在
        session = session_manager.get_session(session_id)

        # 不允许删除最后一个数据集
        if session.dataset_count <= 1:
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "error": {
                        "code": ErrorCode.INVALID_FILE_FORMAT,
                        "message": "不能删除会话中唯一的数据集"
                    }
                }
            )

        # 删除数据集
        success = session_manager.remove_dataset_from_session(session_id, dataset_id)

        if not success:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": {
                        "code": ErrorCode.SESSION_NOT_FOUND,
                        "message": "数据集不存在"
                    }
                }
            )

        return {
            "success": True,
            "message": "数据集已删除"
        }

    except SessionNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail={
                "success": False,
                "error": {
                    "code": ErrorCode.SESSION_NOT_FOUND,
                    "message": str(e)
                }
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除数据集失败: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": {
                    "code": ErrorCode.ANALYSIS_FAILED,
                    "message": f"删除数据集时出错: {str(e)}"
                }
            }
        )

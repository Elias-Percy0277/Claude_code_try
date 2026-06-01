"""
数据加载器
支持 CSV、JSON、Excel (.xlsx, .xls)、.data、.names、.index 文件加载
支持 SQL 数据库连接（预留接口）
"""
import pandas as pd
from pathlib import Path
from typing import Optional, Union
import logging

logger = logging.getLogger(__name__)


class FileFormatError(Exception):
    """文件格式错误"""
    pass


class FileParseError(Exception):
    """文件解析错误"""
    pass


# 支持的文件扩展名
ALLOWED_EXTENSIONS = {'.csv', '.xlsx', '.json', '.xls', '.data', '.names', '.index', '.test'}

# 支持的无扩展名文件名（如 UCI 的 Index 文件）
ALLOWED_FILENAMES = {'index'}


def validate_file_extension(filename: str) -> str:
    """
    验证文件扩展名是否支持

    Args:
        filename: 文件名

    Returns:
        文件扩展名（小写）或 '.index'（对于无扩展名的 Index 文件）

    Raises:
        FileFormatError: 不支持的文件格式
    """
    ext = Path(filename).suffix.lower()
    stem = Path(filename).stem.lower()

    # 检查是否有扩展名
    if not ext:
        # 无扩展名，检查文件名（如 UCI 的 Index 文件）
        if stem in ALLOWED_FILENAMES:
            return '.index'  # 返回 .index 扩展名以便后续处理
        raise FileFormatError(
            f"不支持的文件格式: {filename}。"
            f"请上传以下格式的文件: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    if ext not in ALLOWED_EXTENSIONS:
        raise FileFormatError(
            f"不支持的文件格式: {ext}。"
            f"请上传以下格式的文件: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    return ext


def load_csv(file_path: Union[str, Path], **kwargs) -> pd.DataFrame:
    """
    加载 CSV 文件

    Args:
        file_path: 文件路径
        **kwargs: 传递给 pd.read_csv 的额外参数

    Returns:
        pandas DataFrame
    """
    try:
        # 自动检测编码
        kwargs.setdefault('encoding', 'utf-8')
        kwargs.setdefault('low_memory', False)

        df = pd.read_csv(file_path, **kwargs)
        logger.info(f"成功加载 CSV 文件: {file_path}, 形状: {df.shape}")
        return df

    except UnicodeDecodeError:
        # 尝试其他编码
        try:
            df = pd.read_csv(file_path, encoding='gbk', **kwargs)
            logger.info(f"使用 GBK 编码加载 CSV 文件: {file_path}")
            return df
        except Exception as e:
            raise FileParseError(f"CSV 文件编码解析失败: {e}")

    except pd.errors.EmptyDataError:
        raise FileParseError("CSV 文件为空")
    except Exception as e:
        raise FileParseError(f"CSV 文件解析失败: {e}")


def load_json(file_path: Union[str, Path], **kwargs) -> pd.DataFrame:
    """
    加载 JSON 文件

    Args:
        file_path: 文件路径
        **kwargs: 传递给 pd.read_json 的额外参数

    Returns:
        pandas DataFrame
    """
    try:
        kwargs.setdefault('orient', 'records')
        df = pd.read_json(file_path, **kwargs)
        logger.info(f"成功加载 JSON 文件: {file_path}, 形状: {df.shape}")
        return df

    except ValueError as e:
        raise FileParseError(f"JSON 格式错误: {e}")
    except Exception as e:
        raise FileParseError(f"JSON 文件解析失败: {e}")


def load_excel(file_path: Union[str, Path], **kwargs) -> pd.DataFrame:
    """
    加载 Excel 文件 (.xlsx, .xls)

    Args:
        file_path: 文件路径
        **kwargs: 传递给 pd.read_excel 的额外参数

    Returns:
        pandas DataFrame
    """
    try:
        kwargs.setdefault('engine', 'openpyxl')
        df = pd.read_excel(file_path, **kwargs)
        logger.info(f"成功加载 Excel 文件: {file_path}, 形状: {df.shape}")
        return df

    except ValueError as e:
        if "Worksheet" in str(e):
            raise FileParseError("Excel 文件没有工作表或工作表为空")
        raise FileParseError(f"Excel 文件格式错误: {e}")
    except Exception as e:
        raise FileParseError(f"Excel 文件解析失败: {e}")


def load_from_fileobj(file_obj, filename: str) -> pd.DataFrame:
    """
    从文件对象加载数据（用于上传文件处理）

    Args:
        file_obj: 文件对象（需有 read 方法）
        filename: 文件名

    Returns:
        pandas DataFrame

    Note:
        .names 和 .index 文件返回包含元数据的字典，而非 DataFrame
    """
    import io

    # 验证文件扩展名
    ext = validate_file_extension(filename)

    # .names 文件需要特殊处理（返回元数据而非 DataFrame）
    if ext == '.names':
        content = file_obj.read().decode('utf-8')
        # 创建临时文件来处理
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.names') as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        try:
            return load_names_file(tmp_path)
        finally:
            import os
            os.unlink(tmp_path)

    # .index 文件需要特殊处理（返回元数据而非 DataFrame）
    if ext == '.index':
        content = file_obj.read().decode('utf-8')
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.index') as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        try:
            return load_index_file(tmp_path)
        finally:
            import os
            os.unlink(tmp_path)

    # 读取文件内容到内存
    content = file_obj.read()

    if ext == '.csv':
        # 尝试 UTF-8 解码
        try:
            return pd.read_csv(io.BytesIO(content))
        except UnicodeDecodeError:
            # 尝试 GBK
            return pd.read_csv(io.BytesIO(content), encoding='gbk')

    elif ext == '.json':
        return pd.read_json(io.BytesIO(content))

    elif ext in ('.xlsx', '.xls'):
        return pd.read_excel(io.BytesIO(content), engine='openpyxl')

    elif ext in ('.data', '.test'):
        # 检测分隔符并加载数据
        try:
            content_str = content.decode('utf-8-sig')
        except UnicodeDecodeError:
            try:
                content_str = content.decode('gbk')
            except UnicodeDecodeError:
                content_str = content.decode('latin-1')

        # 调试：打印前5行内容
        debug_lines = content_str.split('\n')[:5]
        for idx, dl in enumerate(debug_lines):
            logger.info(f"[DEBUG] .{ext} line {idx}: {dl[:120]}")

        lines = content_str.split('\n')

        # 扫描前50行，跳过注释行，找到字段最多的行作为数据起始
        comment_char = None
        max_fields = 0
        data_start_line = 0

        for i, line in enumerate(lines[:50]):
            stripped = line.strip()
            if not stripped:
                continue
            if stripped[0] in '|#':
                if comment_char is None:
                    comment_char = stripped[0]
                continue
            count = stripped.count(',')
            if count > max_fields:
                max_fields = count
                data_start_line = i

        logger.info(f"[DEBUG] .{ext} parse: comment_char={comment_char}, max_fields={max_fields}, data_start_line={data_start_line}")

        sep = ','
        kwargs = {
            'sep': sep,
            'engine': 'python',
            'header': None,
            'na_values': ['?'],
            'skip_blank_lines': True,
            'skiprows': data_start_line,
            'quotechar': '"',
            'skipinitialspace': True,
            'encoding': 'utf-8',
        }

        if comment_char:
            kwargs['comment'] = comment_char

        df = pd.read_csv(io.BytesIO(content), **kwargs)

        if all(str(col).startswith('Unnamed') or str(col).isdigit() for col in df.columns):
            df.columns = [f'feature_{i}' for i in range(df.shape[1])]

        return df

    else:
        raise FileFormatError(f"不支持的文件格式: {ext}")


def load_data(source: Union[str, Path], **kwargs) -> Union[pd.DataFrame, dict]:
    """
    通用数据加载函数，根据文件扩展名自动选择加载方式

    Args:
        source: 文件路径或文件对象
        **kwargs: 传递给具体加载函数的额外参数

    Returns:
        pandas DataFrame 或 dict（.names 和 .index 文件返回包含元数据的字典）

    Raises:
        FileFormatError: 不支持的文件格式
        FileParseError: 文件解析失败
    """
    # 处理文件对象
    if hasattr(source, 'read'):
        if not hasattr(source, 'name'):
            raise ValueError("文件对象必须包含 'name' 属性")
        return load_from_fileobj(source, source.name)

    # 处理文件路径
    source_path = Path(source)
    ext = validate_file_extension(source_path.name)

    loader_map = {
        '.csv': load_csv,
        '.json': load_json,
        '.xlsx': load_excel,
        '.xls': load_excel,
        '.data': load_data_file,
        '.test': load_data_file,
        '.names': load_names_file,
        '.index': load_index_file,
    }

    loader = loader_map.get(ext)
    if loader:
        return loader(source_path, **kwargs)

    raise FileFormatError(f"不支持的文件格式: {ext}")


def get_numeric_columns(df: pd.DataFrame) -> list:
    """
    获取数值类型的列名列表

    Args:
        df: pandas DataFrame

    Returns:
        数值列名列表
    """
    return df.select_dtypes(include=['number']).columns.tolist()


def get_datetime_columns(df: pd.DataFrame) -> list:
    """
    获取日期时间类型的列名列表

    Args:
        df: pandas DataFrame

    Returns:
        日期时间列名列表
    """
    return df.select_dtypes(include=['datetime64']).columns.tolist()


def get_categorical_columns(df: pd.DataFrame) -> list:
    """
    获取分类型（字符串/对象）的列名列表

    Args:
        df: pandas DataFrame

    Returns:
        分类型列名列表
    """
    return df.select_dtypes(include=['object', 'category']).columns.tolist()


def load_data_file(file_path: Union[str, Path], **kwargs) -> pd.DataFrame:
    """
    加载 .data 文件（UCI Machine Learning 数据集格式）

    Args:
        file_path: 文件路径
        **kwargs: 传递给 pd.read_csv 的额外参数

    Returns:
        pandas DataFrame
    """
    try:
        # .data 文件通常是空格或逗号分隔的
        kwargs.setdefault('sep', None)  # 自动检测分隔符
        kwargs.setdefault('engine', 'python')  # 支持自动检测
        kwargs.setdefault('header', None)  # 通常没有表头
        kwargs.setdefault('na_values', ['?'])  # UCI 数据集常用 ? 表示缺失值

        # 尝试读取文件前几行来检测分隔符和注释行
        comment_char = None
        with open(file_path, 'r', encoding='utf-8') as f:
            for _ in range(10):  # 检查前10行
                line = f.readline()
                if not line:
                    break
                stripped = line.strip()
                # 跳过空行
                if not stripped:
                    continue
                # 检查是否是注释行（以 | 或 # 开头）
                if stripped[0] in '|#':
                    comment_char = stripped[0]
                    continue
                # 找到第一个非空、非注释行来检测分隔符
                if ',' in stripped and stripped.count(',') > stripped.count('\t'):
                    kwargs['sep'] = ','
                    kwargs['quotechar'] = '"'
                    kwargs['skipinitialspace'] = True
                elif '\t' in stripped:
                    kwargs['sep'] = '\t'
                    kwargs['quotechar'] = '"'
                else:
                    kwargs['sep'] = r'\s+'
                    kwargs['quotechar'] = '"'
                break

        # 如果检测到注释字符，添加到参数中
        if comment_char:
            kwargs['comment'] = comment_char

        df = pd.read_csv(file_path, **kwargs)
        logger.info(f"成功加载 .data 文件: {file_path}, 形状: {df.shape}")

        # 如果没有列名，生成默认列名
        if all(str(col).startswith('Unnamed') or str(col).isdigit() for col in df.columns):
            df.columns = [f'feature_{i}' for i in range(df.shape[1])]

        return df

    except UnicodeDecodeError:
        try:
            df = pd.read_csv(file_path, encoding='gbk', **kwargs)
            logger.info(f"使用 GBK 编码加载 .data 文件: {file_path}")
            return df
        except Exception as e:
            raise FileParseError(f".data 文件编码解析失败: {e}")

    except pd.errors.EmptyDataError:
        raise FileParseError(".data 文件为空")
    except Exception as e:
        raise FileParseError(f".data 文件解析失败: {e}")


def load_names_file(file_path: Union[str, Path], **kwargs) -> dict:
    """
    加载 .names 文件（UCI Machine Learning 元数据格式）

    Args:
        file_path: 文件路径
        **kwargs: 额外参数

    Returns:
        包含元数据的字典，包括：
        - title: 数据集标题
        - attributes: 特征列表及其类型
        - classes: 类别列表（如果有）
        - description: 数据集描述
    """
    result = {
        'title': '',
        'attributes': [],
        'classes': [],
        'description': []
    }

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

    except UnicodeDecodeError:
        try:
            with open(file_path, 'r', encoding='gbk') as f:
                lines = f.readlines()
        except Exception as e:
            raise FileParseError(f".names 文件编码解析失败: {e}")
    except Exception as e:
        raise FileParseError(f".names 文件读取失败: {e}")

    # 解析内容
    current_section = None
    in_attribute_section = False
    found_first_attribute = False  # 标记是否找到第一个属性

    for line in lines:
        original_line = line
        line = line.rstrip()

        # 跳过空行和注释行
        if not line.strip() or line.strip().startswith('|') or line.strip().startswith('#'):
            continue

        # 检测标题（通常在第一行或以 1. 开头）
        if line.strip().startswith('1.') or 'title:' in line.lower():
            result['title'] = line.split(':', 1)[-1].strip() if ':' in line else line.strip()
            continue

        # 检测属性区域标题
        lower_line = line.lower()
        if 'attribute' in lower_line and ('information' in lower_line or ':' in line):
            in_attribute_section = True
            current_section = 'attributes'
            # 如果同一行有属性定义，解析它
            if ':' in line and line.count(':') >= 2:
                parts = line.split(':')
                for i in range(1, len(parts)):
                    attr_def = parts[i].strip()
                    if attr_def and attr_def not in ['Information', 'information']:
                        result['attributes'].append(_parse_attribute(attr_def))
            continue

        # 检测类别定义（必须是完整的 class 单词，而非包含 class 的其他词）
        # 匹配格式: "8. Class:" 或 "Class:" 等
        import re
        if re.match(r'^\d+\.\s*class\b:', lower_line) or re.match(r'^class\b:', lower_line):
            in_attribute_section = False
            if 'class distribution' not in lower_line:
                current_section = 'classes'
                # 提取类别定义
                if ':' in line and ('{' in line or ',' in line):
                    class_def = line.split(':', 1)[1].strip()
                    if class_def:
                        result['classes'] = _parse_class_values(class_def)
            continue

        # 解析缩进的属性行（格式: "   age: continuous" 或 "   workclass: Private, Self-emp"）
        # 也解析无缩进的属性行（格式: "age: continuous."）
        stripped = line.strip()
        is_attr_line = (
            ':' in stripped and
            not stripped.startswith('|') and
            not stripped.lower().startswith('title:') and
            not any(kw in stripped.lower() for kw in ['http', 'citation', 'prediction', 'donor', 'split', 'probability', 'extraction', 'split into'])
        )

        if is_attr_line or in_attribute_section or current_section == 'attributes':
            # 检查是否是属性定义行（包含冒号）
            if ':' in stripped:
                # 可能是属性定义
                attr_def = stripped.split(':', 1)[1].strip()
                attr_name = stripped.split(':', 1)[0].strip()

                # 验证是否是有效的属性行
                valid_attr = False
                if attr_def and attr_name:
                    # 检查是否包含类型关键字或值列表
                    if any(kw in attr_def.lower() for kw in ['continuous', 'integer', 'real', 'unimodal', 'discrete']) or ',' in attr_def:
                        valid_attr = True
                    elif found_first_attribute:
                        # 如果已经找到一个属性，继续解析类似格式的行
                        valid_attr = True

                    # 过滤掉明显不是属性的行（如 URL、email 等）
                    if 'http' in stripped.lower() or '@' in stripped or 'citation' in stripped.lower():
                        valid_attr = False

                if valid_attr:
                    found_first_attribute = True
                    result['attributes'].append(_parse_attribute(f"{attr_name}: {attr_def}"))
                    continue

        # 解析编号格式的属性行（格式: "1. age: continuous"）
        if line.strip() and line.strip()[0].isdigit() and '.' in line:
            if ':' in line and 'attribute' not in line.lower():
                # 提取冒号后的部分
                parts = line.split('.', 1)
                if len(parts) > 1:
                    attr_def = parts[1].strip()
                    if ':' in attr_def:
                        attr_def = attr_def.split(':', 1)[1].strip()
                        result['attributes'].append(_parse_attribute(attr_def))

    # 检查是否使用了简化的 .names 格式（只有列名，每行一个）
    if not result['attributes']:
        content = ''.join(lines)
        result['attributes'] = _parse_simple_names_format(content)

    result['description'] = '\n'.join(result['description'])
    logger.info(f"成功加载 .names 文件: {file_path}, 解析到 {len(result['attributes'])} 个属性")
    return result


def _parse_attribute(attr_def: str) -> dict:
    """
    解析单个属性定义

    Args:
        attr_def: 属性定义字符串

    Returns:
        属性字典，包含 name 和 type
    """
    attr_def = attr_def.strip()

    # 处理 name: type 格式（如 "age: continuous"）
    if ':' in attr_def and not attr_def.startswith('{'):
        parts = attr_def.split(':', 1)
        name = parts[0].strip()
        type_part = parts[1].strip() if len(parts) > 1 else ''

        # 检查类型部分
        type_lower = type_part.lower()

        if 'continuous' in type_lower:
            return {'name': name, 'type': 'continuous'}
        elif 'integer' in type_lower:
            return {'name': name, 'type': 'integer'}
        elif 'real' in type_lower:
            return {'name': name, 'type': 'real'}
        elif ',' in type_part or '{' in type_part:
            # 分类属性
            values_str = type_part.replace('{', '').replace('}', '').strip()
            values = [v.strip() for v in values_str.split(',')]
            return {
                'name': name,
                'type': 'categorical',
                'values': values
            }
        else:
            return {'name': name, 'type': type_part or 'unknown'}

    # 处理 {val1, val2, val3} 格式（分类属性）
    if attr_def.startswith('{') and '}' in attr_def:
        # 提取属性名（在 { 之前）
        brace_pos = attr_def.index('{')
        name = attr_def[:brace_pos].strip()
        values_str = attr_def[brace_pos + 1:attr_def.index('}')].strip()
        values = [v.strip() for v in values_str.split(',')]

        return {
            'name': name,
            'type': 'categorical',
            'values': values
        }

    # 处理 continuous 格式（连续属性）
    if 'continuous' in attr_def.lower():
        name = attr_def.lower().replace('continuous', '').replace(':', '').strip()
        return {
            'name': name,
            'type': 'continuous'
        }

    # 处理 integer 格式
    if 'integer' in attr_def.lower():
        name = attr_def.lower().replace('integer', '').replace(':', '').strip()
        return {
            'name': name,
            'type': 'integer'
        }

    # 处理 real 格式
    if 'real' in attr_def.lower():
        name = attr_def.lower().replace('real', '').replace(':', '').strip()
        return {
            'name': name,
            'type': 'real'
        }

    # 默认情况
    return {
        'name': attr_def,
        'type': 'unknown'
    }


def _parse_class_values(class_def: str) -> list:
    """
    解析类别值定义

    Args:
        class_def: 类别定义字符串

    Returns:
        类别值列表
    """
    class_def = class_def.strip()

    # 处理 {class1, class2, class3} 格式
    if class_def.startswith('{') and '}' in class_def:
        values_str = class_def[class_def.index('{') + 1:class_def.index('}')].strip()
        return [v.strip() for v in values_str.split(',')]

    # 处理逗号分隔格式
    if ',' in class_def:
        return [v.strip() for v in class_def.split(',')]

    # 单个类别
    return [class_def]


def _parse_simple_names_format(content: str) -> list:
    """
    解析简化的 .names 格式（每行一个列名）

    Args:
        content: 文件内容

    Returns:
        属性列表
    """
    attributes = []
    lines = content.strip().split('\n')

    for line in lines:
        line = line.strip()
        # 跳过注释和空行
        if not line or line.startswith('#') or line.startswith('|'):
            continue
        # 跳过看起来像数据值的行
        if any(c in line for c in ',\t\t\t\t'):
            # 如果包含多个连续空格或制表符，可能是数据行
            if line.count(',') > 2 or line.count('\t') > 2:
                continue
        # 将行作为属性名
        if not any(kw in line.lower() for kw in ['title', 'description', 'attribute', 'class']):
            attributes.append({
                'name': line,
                'type': 'unknown'
            })

    return attributes


def load_index_file(file_path: Union[str, Path], **kwargs) -> dict:
    """
    加载 .index 文件（UCI Machine Learning 索引文件格式）

    Args:
        file_path: 文件路径
        **kwargs: 额外参数

    Returns:
        包含元数据的字典，包括：
        - title: 数据集名称
        - files: 文件列表（包含 name, date, size）
        - description: 数据集描述
    """
    result = {
        'title': '',
        'files': [],
        'description': []
    }

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

    except UnicodeDecodeError:
        try:
            with open(file_path, 'r', encoding='gbk') as f:
                lines = f.readlines()
        except Exception as e:
            raise FileParseError(f".index 文件编码解析失败: {e}")
    except Exception as e:
        raise FileParseError(f".index 文件读取失败: {e}")

    # 解析内容
    for i, line in enumerate(lines):
        original_line = line
        line = line.rstrip()

        # 跳过空行
        if not line.strip():
            continue

        # 第一行通常是 "Index of <dataset_name>"
        if i == 0 and 'Index of' in line:
            result['title'] = line.replace('Index of', '').strip()
            continue

        # 解析文件列表行（格式: "Date Size Filename"）
        # 例如: "02 Dec 1996      140 Index"
        parts = line.split()
        if len(parts) >= 3:
            # 尝试解析日期和大小
            # UCI 格式: DD MMM YYYY Size Filename
            try:
                # 检查是否有月份缩写（Jan, Feb, Mar等）
                months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                         'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
                if any(month in line for month in months):
                    # 解析格式: "02 Dec 1996      140 adult.data"
                    # 找到文件名（最后一个部分）
                    filename = parts[-1]
                    # 找到大小（倒数第二个部分，通常是数字）
                    size_idx = -2
                    for j in range(len(parts) - 2, -1, -1):
                        if parts[j].isdigit():
                            size_idx = j
                            break

                    if size_idx > 0:
                        size = int(parts[size_idx])
                        # 日期是前面的部分
                        date_str = ' '.join(parts[:size_idx])

                        result['files'].append({
                            'name': filename,
                            'date': date_str,
                            'size': size
                        })
            except (ValueError, IndexError):
                # 如果解析失败，将整行作为描述
                if line:
                    result['description'].append(line)
        else:
            # 其他行作为描述
            if line and not line.startswith('|'):
                result['description'].append(line)

    result['description'] = '\n'.join(result['description'])
    logger.info(f"成功加载 .index 文件: {file_path}, 标题: {result['title']}, 文件数: {len(result['files'])}")
    return result

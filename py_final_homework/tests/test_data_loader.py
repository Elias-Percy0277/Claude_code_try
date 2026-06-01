"""
数据加载与预处理模块测试
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from backend.core.data_loader import (
    load_data, validate_file_extension, get_numeric_columns,
    get_datetime_columns, get_categorical_columns, FileFormatError,
    load_data_file, load_names_file
)
from backend.core.preprocessor import (
    preprocess_data, validate_dataframe, detect_column_types,
    handle_missing_values, analyze_columns, get_data_summary
)


def create_test_csv():
    """创建测试用的 CSV 文件"""
    test_data = pd.DataFrame({
        '日期': ['2024-01-01', '2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05'],
        '销售额': [1000, 1500, 1200, 1800, 2000],
        '利润': [200, 350, 250, 400, 500],
        '地区': ['北京', '上海', '广州', '深圳', '杭州'],
        '产品类别': ['电子产品', '电子产品', '家居用品', '电子产品', '家居用品']
    })

    test_file = 'tests/fixtures/test_sales_data.csv'
    os.makedirs(os.path.dirname(test_file), exist_ok=True)
    test_data.to_csv(test_file, index=False, encoding='utf-8')
    print(f"创建测试数据文件: {test_file}")
    return test_file


def test_data_loader():
    """测试数据加载模块"""
    print("\n=== 测试数据加载模块 ===")

    # 创建测试数据
    test_file = create_test_csv()

    # 测试文件扩展名验证
    try:
        ext = validate_file_extension("test.csv")
        assert ext == ".csv"
        print("[OK] 文件扩展名验证通过: CSV")

        ext = validate_file_extension("test.xlsx")
        assert ext == ".xlsx"
        print("[OK] 文件扩展名验证通过: XLSX")
    except Exception as e:
        print(f"[FAIL] 文件扩展名验证失败: {e}")

    # 测试不支持的文件格式
    try:
        validate_file_extension("test.txt")
        print("[FAIL] 应该抛出 FileFormatError")
    except FileFormatError:
        print("[OK] 正确拒绝不支持的文件格式")

    # 测试数据加载
    try:
        df = load_data(test_file)
        assert len(df) == 5
        assert len(df.columns) == 5
        print(f"[OK] 数据加载成功: {len(df)} 行 x {len(df.columns)} 列")
        print(f"  列名: {list(df.columns)}")
    except Exception as e:
        print(f"[FAIL] 数据加载失败: {e}")


def test_preprocessor():
    """测试数据预处理模块"""
    print("\n=== 测试数据预处理模块 ===")

    # 加载测试数据
    test_file = 'tests/fixtures/test_sales_data.csv'
    df = load_data(test_file)

    # 测试列类型检测
    try:
        types = detect_column_types(df)
        print(f"[OK] 列类型检测成功:")
        print(f"  数值列: {types['numeric']}")
        print(f"  分类型列: {types['categorical']}")
    except Exception as e:
        print(f"[FAIL] 列类型检测失败: {e}")

    # 测试数据验证
    try:
        validate_dataframe(df)
        print("[OK] 数据验证通过")
    except Exception as e:
        print(f"[FAIL] 数据验证失败: {e}")

    # 测试列信息分析
    try:
        col_info = analyze_columns(df)
        print(f"[OK] 列信息分析成功:")
        for col, info in col_info.items():
            print(f"  {col}: dtype={info['dtype']}, nullable={info['nullable']}, nunique={info['nunique']}")
    except Exception as e:
        print(f"[FAIL] 列信息分析失败: {e}")

    # 测试缺失值处理
    try:
        # 创建带缺失值的数据
        df_na = df.copy()
        df_na.loc[0, '销售额'] = None
        df_na.loc[1, '地区'] = None

        df_cleaned = handle_missing_values(df_na, strategy='auto')
        assert df_cleaned['销售额'].isna().sum() == 0
        print("[OK] 缺失值处理成功")
    except Exception as e:
        print(f"[FAIL] 缺失值处理失败: {e}")

    # 测试数据摘要
    try:
        summary = get_data_summary(df)
        print(f"[OK] 数据摘要获取成功:")
        print(f"  行数: {summary['row_count']}")
        print(f"  列数: {summary['column_count']}")
        print(f"  内存使用: {summary['memory_usage_mb']} MB")
    except Exception as e:
        print(f"[FAIL] 数据摘要获取失败: {e}")


def test_preprocess_pipeline():
    """测试完整预处理流程"""
    print("\n=== 测试完整预处理流程 ===")

    test_file = 'tests/fixtures/test_sales_data.csv'
    df = load_data(test_file)

    try:
        df_processed = preprocess_data(
            df,
            clean_names=True,
            infer_dates=True,
            handle_missing=True,
            validate=True
        )
        print(f"[OK] 预处理流程成功:")
        print(f"  原始数据: {len(df)} 行 x {len(df.columns)} 列")
        print(f"  处理后: {len(df_processed)} 行 x {len(df_processed.columns)} 列")
    except Exception as e:
        print(f"[FAIL] 预处理流程失败: {e}")


def test_data_file_format():
    """测试 .data 文件格式支持"""
    print("\n=== 测试 .data 文件格式 ===")

    test_file = 'tests/fixtures/test_uci.data'
    os.makedirs(os.path.dirname(test_file), exist_ok=True)

    # 创建测试 .data 文件（类似 UCI 格式）
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write("30,50,1,0,0\n")
        f.write("25,60,0,1,0\n")
        f.write("35,55,1,1,1\n")
        f.write("40,65,0,0,1\n")
        f.write("28,58,1,0,0\n")

    try:
        df = load_data(test_file)
        assert len(df) == 5
        print(f"[OK] .data 文件加载成功: {len(df)} 行 x {len(df.columns)} 列")
    except Exception as e:
        print(f"[FAIL] .data 文件加载失败: {e}")


def test_names_file_format():
    """测试 .names 文件格式支持"""
    print("\n=== 测试 .names 文件格式 ===")

    test_file = 'tests/fixtures/test_uci.names'
    os.makedirs(os.path.dirname(test_file), exist_ok=True)

    # 创建测试 .names 文件（标准 UCI 格式）
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write("1. Title: Test Dataset\n")
        f.write("\n")
        f.write("7. Attribute Information:\n")
        f.write("   age: continuous\n")
        f.write("   workclass: Private, Self-emp-not-inc, Self-emp-inc\n")
        f.write("   education: Bachelors, Some-college, HS-grad\n")
        f.write("   education-num: continuous\n")
        f.write("   marital-status: Married, Never-married\n")
        f.write("   occupation: Tech-support, Craft-repair, Sales\n")
        f.write("   hours-per-week: continuous\n")
        f.write("\n")
        f.write("8. Class: <=50K, >50K\n")

    try:
        metadata = load_names_file(test_file)
        assert 'attributes' in metadata
        assert len(metadata['attributes']) > 0
        print(f"[OK] .names 文件加载成功:")
        print(f"  标题: {metadata['title']}")
        print(f"  属性数量: {len(metadata['attributes'])}")
        print(f"  类别: {metadata['classes']}")
    except Exception as e:
        print(f"[FAIL] .names 文件加载失败: {e}")


def test_names_simple_format():
    """测试简化的 .names 文件格式"""
    print("\n=== 测试简化 .names 文件格式 ===")

    test_file = 'tests/fixtures/test_simple.names'
    os.makedirs(os.path.dirname(test_file), exist_ok=True)

    # 创建简化格式的 .names 文件（每行一个列名）
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write("# This is a comment\n")
        f.write("age\n")
        f.write("income\n")
        f.write("gender\n")
        f.write("education_level\n")

    try:
        metadata = load_names_file(test_file)
        assert 'attributes' in metadata
        assert len(metadata['attributes']) == 4
        print(f"[OK] 简化 .names 文件加载成功:")
        for attr in metadata['attributes']:
            print(f"  - {attr['name']}")
    except Exception as e:
        print(f"[FAIL] 简化 .names 文件加载失败: {e}")


def test_extension_validation():
    """测试文件扩展名验证"""
    print("\n=== 测试文件扩展名验证 ===")

    try:
        # 测试支持的格式
        for ext in ['.csv', '.json', '.xlsx', '.xls', '.data', '.names']:
            result = validate_file_extension(f"test{ext}")
            assert result == ext
            print(f"[OK] {ext} 扩展名验证通过")

        # 测试不支持的格式
        try:
            validate_file_extension("test.txt")
            print("[FAIL] 应该拒绝 .txt 扩展名")
        except FileFormatError:
            print("[OK] 正确拒绝不支持的扩展名")

    except Exception as e:
        print(f"[FAIL] 扩展名验证测试失败: {e}")


if __name__ == "__main__":
    print("=" * 50)
    print("数据加载与预处理模块测试")
    print("=" * 50)

    test_data_loader()
    test_preprocessor()
    test_preprocess_pipeline()
    test_data_file_format()
    test_names_file_format()
    test_names_simple_format()
    test_extension_validation()

    print("\n" + "=" * 50)
    print("测试完成")
    print("=" * 50)

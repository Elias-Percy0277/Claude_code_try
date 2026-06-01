"""
模板校准工具

用于可视化显示模板区域，帮助用户验证和调整坐标模板
"""
import sys
import cv2
import numpy as np
from pathlib import Path

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.template_detector import template_detector, Rect
from core.wechat_client import wechat_client
from utils.logger import logger


def draw_rectangles(image: np.ndarray, areas: dict, labels: dict) -> np.ndarray:
    """在图像上绘制矩形区域"""
    result = image.copy()

    for name, rect in areas.items():
        left = rect['left']
        top = rect['top']
        right = rect['right']
        bottom = rect['bottom']

        # 不同区域使用不同颜色
        if 'message' in name:
            color = (0, 255, 0)  # 绿色
        elif 'input' in name:
            color = (0, 0, 255)  # 红色
        elif 'indicator' in name:
            color = (255, 0, 255)  # 紫色
        else:
            color = (255, 255, 0)  # 青色

        # 绘制矩形
        cv2.rectangle(result, (left, top), (right, bottom), color, 2)

        # 添加标签
        label = labels.get(name, name)
        cv2.putText(
            result, label, (left, top - 5),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1
        )

    return result


def main():
    """主函数"""
    print("\n" + "=" * 50)
    print(" 微信托管 - 模板校准工具")
    print("=" * 50)
    print("\n请确保微信客户端已打开并可见\n")

    # 连接微信
    logger.info("连接微信...")
    if not wechat_client.connect():
        print("❌ 无法连接到微信，请确保微信已打开")
        input("\n按回车键退出...")
        return

    print("✓ 微信连接成功")

    # 获取窗口位置
    if not wechat_client.wx_rect:
        print("❌ 无法获取窗口位置")
        return

    left, top, right, bottom = wechat_client.wx_rect
    window_width = right - left
    window_height = bottom - top

    print(f"✓ 窗口位置: ({left}, {top}) - ({right}, {bottom})")
    print(f"✓ 窗口尺寸: {window_width} x {window_height}")

    # 截图
    logger.info("截取微信窗口...")
    screenshot = wechat_client.capture_wechat_window()
    if screenshot is None:
        print("❌ 截图失败")
        return

    print("✓ 截图成功")

    # 获取模板区域
    areas = template_detector.calibrate(screenshot, wechat_client.wx_rect)

    print("\n模板区域坐标:")
    print("-" * 50)

    labels = {
        'message_area': '聊天区域',
        'own_message_area': '自己消息区',
        'other_message_area': '对方消息区',
        'new_message_indicator': '新消息提示区',
        'input_area': '输入框'
    }

    for name, rect in areas.items():
        label = labels.get(name, name)
        print(f"{label:15s}: ({rect['left']:4d}, {rect['top']:4d}) - "
              f"({rect['right']:4d}, {rect['bottom']:4d}) "
              f"[{rect['width']:4d} x {rect['height']:4d}]")

    print("-" * 50)

    # 绘制并显示
    result = draw_rectangles(screenshot, areas, labels)

    # 保存结果
    output_path = PROJECT_ROOT / "data" / "template_calibration.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), result)
    print(f"\n✓ 校准图像已保存到: {output_path}")

    # 显示图像
    display_image = cv2.resize(result, (int(result.shape[1] * 0.8), int(result.shape[0] * 0.8)))
    cv2.imshow("Template Calibration - Press any key to close", display_image)

    print("\n提示:")
    print(" - 绿色框: 聊天消息区域")
    print(" - 红色框: 输入框区域")
    print(" - 紫色框: 新消息提示区域")
    print("\n如果框的位置不正确，请调整 core/template_detector.py 中的模板参数")

    cv2.waitKey(0)
    cv2.destroyAllWindows()

    print("\n校准完成！")


if __name__ == "__main__":
    main()

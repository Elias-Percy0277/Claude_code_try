"""
WeChat Region Calibrator

Usage:
1. Make sure WeChat window is open
2. Run this tool
3. Select regions with mouse
4. Press S to save

Hotkeys:
- 1: Title area (detect private/group chat)
- 2: Message area (overall)
- 3: Other person area (left side)
- 4: Own message area (right side)
- 5: Input area (bottom)
- s: Save config
- q: Quit
- r: Reset all
"""
import cv2
import numpy as np
import win32gui
import pyautogui
from pathlib import Path
from typing import Dict, Tuple, Optional
import json

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


class RegionSelector:
    """Interactive region selector"""

    COLORS = {
        'title': (0, 0, 255),        # Blue - Title
        'message': (0, 255, 0),      # Green - Message area
        'other': (0, 255, 255),      # Yellow - Other person
        'own': (255, 0, 255),        # Purple - Own message
        'input': (255, 255, 0),      # Cyan - Input box
    }

    LABELS = {
        'title': 'Title Area',
        'message': 'Message Area',
        'other': 'Other Person (Left)',
        'own': 'Own Message (Right)',
        'input': 'Input Box (Bottom)',
    }

    def __init__(self, image: np.ndarray):
        self.original_image = image.copy()
        self.current_image = image.copy()
        self.regions: Dict[str, Tuple[int, int, int, int]] = {}
        self.current_mode: Optional[str] = None
        self.drawing = False
        self.start_point = None
        self.end_point = None

        # Window setup
        self.window_name = 'WeChat Region Calibrator'
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(self.window_name, self._mouse_callback)

        # Image info
        self.height, self.width = image.shape[:2]
        print(f"\nImage size: {self.width} x {self.height}")

    def _mouse_callback(self, event, x, y, flags, param):
        """Mouse callback"""
        if event == cv2.EVENT_LBUTTONDOWN:
            self.drawing = True
            self.start_point = (x, y)
            self.end_point = (x, y)

        elif event == cv2.EVENT_MOUSEMOVE:
            if self.drawing:
                self.end_point = (x, y)
                self._refresh_display()

        elif event == cv2.EVENT_LBUTTONUP:
            self.drawing = False
            if self.start_point and self.end_point and self.current_mode:
                # Save region
                x1 = min(self.start_point[0], self.end_point[0])
                y1 = min(self.start_point[1], self.end_point[1])
                x2 = max(self.start_point[0], self.end_point[0])
                y2 = max(self.start_point[1], self.end_point[1])

                if x2 > x1 and y2 > y1:
                    self.regions[self.current_mode] = (x1, y1, x2, y2)
                    label = self.LABELS.get(self.current_mode, self.current_mode)
                    print(f"[OK] {label}: ({x1}, {y1}, {x2}, {y2})")

            self.start_point = None
            self.end_point = None
            self._refresh_display()

    def _refresh_display(self):
        """Refresh display"""
        self.current_image = self.original_image.copy()

        # Draw saved regions
        for mode, (x1, y1, x2, y2) in self.regions.items():
            color = self.COLORS.get(mode, (255, 255, 255))
            cv2.rectangle(self.current_image, (x1, y1), (x2, y2), color, 2)
            label = self.LABELS.get(mode, mode)
            # Draw label background
            (w, h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(self.current_image, (x1, y1 - h - 8), (x1 + w + 4, y1), color, -1)
            cv2.putText(self.current_image, label, (x1 + 2, y1 - 4),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        # Draw current selection
        if self.drawing and self.start_point and self.end_point:
            color = self.COLORS.get(self.current_mode, (255, 255, 255))
            cv2.rectangle(self.current_image, self.start_point, self.end_point, color, 2)

        # Draw info panel
        overlay = self.current_image.copy()
        cv2.rectangle(overlay, (5, 5), (400, 130), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.7, self.current_image, 0.3, 0, self.current_image)

        # Current mode
        if self.current_mode:
            label = self.LABELS.get(self.current_mode, self.current_mode)
            mode_text = f"Selecting: {label}"
            cv2.putText(self.current_image, mode_text, (15, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

        # Progress
        done_count = len(self.regions)
        total_count = len(self.LABELS)
        status_text = f"Progress: {done_count}/{total_count}"
        cv2.putText(self.current_image, status_text, (15, 55),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        # Help
        help_texts = [
            "Keys: 1=Title, 2=Message, 3=Other, 4=Own, 5=Input",
            "S=Save, Q=Quit, R=Reset"
        ]
        for i, text in enumerate(help_texts):
            cv2.putText(self.current_image, text, (15, 85 + i * 20),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)

        cv2.imshow(self.window_name, self.current_image)

    def run(self) -> Dict[str, Tuple[int, int, int, int]]:
        """Run selector"""
        print("\n" + "=" * 60)
        print("       WeChat Region Calibrator")
        print("=" * 60)
        print("\nInstructions:")
        for i, (key, label) in enumerate(self.LABELS.items()):
            print(f"  {i+1} - Select {label}")
        print("\n  S - Save and quit")
        print("  Q - Quit without saving")
        print("  R - Reset all regions")
        print("\nSteps:")
        print("  1. Press number key to select region type")
        print("  2. Drag mouse to select region on image")
        print("  3. Repeat until all regions are marked")
        print("  4. Press S to save")
        print("=" * 60 + "\n")

        self._refresh_display()

        while True:
            key = cv2.waitKey(1) & 0xFF

            if key == ord('q') or key == ord('Q'):
                print("\nCancelled")
                return {}

            elif key == ord('s') or key == ord('S'):
                if len(self.regions) == len(self.LABELS):
                    print("\nConfiguration saved!")
                    return self.regions
                else:
                    missing = len(self.LABELS) - len(self.regions)
                    print(f"\nStill missing {missing} region(s), please complete all")
                    cv2.waitKey(500)

            elif key == ord('r') or key == ord('R'):
                self.regions.clear()
                print("\nReset all regions")
                self._refresh_display()

            elif key in [ord(str(i)) for i in range(1, 6)]:
                keys_list = list(self.LABELS.keys())
                idx = key - ord('1')
                if 0 <= idx < len(keys_list):
                    self.current_mode = keys_list[idx]
                    label = self.LABELS[self.current_mode]
                    print(f"\n>>> Please select: {label}")
                    self._refresh_display()

        cv2.destroyAllWindows()


def capture_screen() -> Optional[np.ndarray]:
    """Capture entire screen"""
    try:
        print("Capturing screen...")

        # Capture entire screen
        screenshot = pyautogui.screenshot()
        img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

        height, width = img.shape[:2]
        print(f"Screen size: {width} x {height}")

        return img

    except Exception as e:
        print(f"Capture failed: {e}")
        return None


def save_regions_to_config(regions: Dict[str, Tuple[int, int, int, int]],
                           image_size: Tuple[int, int],
                           config_path: Path):
    """Save region config"""
    width, height = image_size

    # Convert to relative coordinates
    relative_regions = {}
    for key, (x1, y1, x2, y2) in regions.items():
        relative_regions[key] = {
            'left': round(x1 / width, 4),
            'top': round(y1 / height, 4),
            'right': round(x2 / width, 4),
            'bottom': round(y2 / height, 4),
        }

    config = {
        'image_size': {'width': width, 'height': height},
        'regions': relative_regions
    }

    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    print(f"\nConfig saved to: {config_path}")


def main():
    """Main function"""
    print("\n" + "=" * 50)
    print("       Screen Region Calibrator")
    print("=" * 50)

    # Capture screen
    print("\nCapturing screen...")
    image = capture_screen()

    if image is None:
        return

    # Save original screenshot
    screenshot_path = Path(__file__).parent.parent / "data" / "calibration_screenshot.png"
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(screenshot_path), image)
    print(f"Screenshot saved: {screenshot_path}")

    # Run selector
    selector = RegionSelector(image)
    regions = selector.run()

    if regions:
        # Save config
        config_path = Path(__file__).parent.parent / "data" / "region_config.json"
        save_regions_to_config(regions, (image.shape[1], image.shape[0]), config_path)

        # Show summary
        print("\n" + "=" * 50)
        print("       Region Configuration Summary")
        print("=" * 50)
        for key, (x1, y1, x2, y2) in regions.items():
            w, h = x2 - x1, y2 - y1
            label = selector.LABELS.get(key, key)
            print(f"{label}:")
            print(f"  Position: ({x1}, {y1}) -> ({x2}, {y2})")
            print(f"  Size: {w} x {h}")
        print("=" * 50)

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

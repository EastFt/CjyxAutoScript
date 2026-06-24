# Copyright (C) 2026 [EastFt/小心二次元]
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""夺宝奇兵 ROI 可视化 — 在截图上画出边框供确认，不执行任何点击操作。"""

import sys
from pathlib import Path
import cv2

# 项目路径
PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

from core.adb_controller import ADBController
from core.device import Device
from utils.mumu_detector import detect_mumu_device, get_adb_path


def main():
    # 连接 ADB
    adb_path = get_adb_path()
    device_addr = detect_mumu_device(adb_path)
    print(f"ADB: {adb_path}")
    print(f"设备: {device_addr}")

    adb = ADBController(device_addr=device_addr, adb_path=adb_path)
    if not adb.connect():
        print("ADB 连接失败")
        return
    print("ADB 连接成功")

    device = Device(adb)
    print(f"分辨率: {device.resolution}")

    # 截图
    screen = device.screenshot()
    h, w = screen.shape[:2]
    print(f"截图尺寸: {w}x{h}")

    # ROI 参数
    roi_left, roi_top = 0, 0
    roi_right, roi_bottom = 1140, 650

    # 画 ROI 边框（绿色，线宽3）
    img = screen.copy()
    cv2.rectangle(img, (roi_left, roi_top), (roi_right, roi_bottom), (0, 255, 0), 3)

    # 画对角线（半透明红色虚线，标注区域范围）
    cv2.line(img, (roi_left, roi_top), (roi_right, roi_bottom), (0, 0, 255), 1)

    # 标注文字
    cv2.putText(img, f"ROI: ({roi_left},{roi_top}) -> ({roi_right},{roi_bottom})",
                (10, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    # 保存
    out_path = PROJECT_DIR / "debug_treasure_hunt_roi.png"
    cv2.imwrite(str(out_path), img)
    print(f"已保存: {out_path}")

    adb.disconnect()
    print("完成")


if __name__ == "__main__":
    main()

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

"""诊断工具：保存当前截图并输出模板信息，用于对比排查。"""
import sys
sys.path.insert(0, ".")

import cv2
from pathlib import Path
from utils.logger import setup_logger
from utils.mumu_detector import detect_mumu_device, get_adb_path
from core.adb_controller import ADBController

setup_logger("./logs", "INFO")

# 连接设备
adb_path = get_adb_path()
print(f"ADB: {adb_path}")

addr = detect_mumu_device(adb_path)
print(f"设备: {addr}")

adb = ADBController(addr, adb_path)
adb.connect()

# 截图并保存
from core.device import Device
device = Device(adb)
screen = device.screenshot()
print(f"截图分辨率: {device.resolution}")
print(f"截图尺寸: {screen.shape} (H,W,C)")

cv2.imwrite("./logs/debug_screenshot.png", screen)
print("已保存截图: ./logs/debug_screenshot.png")

# 检查模板
templates = [
    "btn_social", "btn_friends_tab", "btn_send", "btn_close",
    "btn_events", "btn_event2", "btn_join", "btn_sweep"
]

for name in templates:
    path = Path(f"assets/buttons/{name}.png")
    if path.exists():
        img = cv2.imread(str(path))
        h, w = img.shape[:2]
        print(f"  {name}.png: {w}x{h}")
    else:
        print(f"  {name}.png: 不存在")

adb.disconnect()

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

"""设备操作抽象层。

在 ADBController 基础上封装高层设备操作：
截图、点击、滑动、等待画面稳定等。
"""

from __future__ import annotations

import sys
import time
import hashlib
import subprocess
from pathlib import Path

import numpy as np
import cv2
from loguru import logger

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

from core.adb_controller import ADBController


class Device:
    """设备操作抽象层。

    封装截图、点击、滑动等高层操作，
    自动处理 raw format 截图的字节解析。

    Usage:
        device = Device(adb_controller)
        screen = device.screenshot()
        device.tap(640, 360)
        device.wait_for_stable(timeout=5.0)
    """

    # 返回键
    KEYCODE_BACK = 4
    # Home 键
    KEYCODE_HOME = 3

    def __init__(self, adb: ADBController):
        self._adb = adb
        self._resolution: tuple[int, int] | None = None

    # ── 截图 ──────────────────────────────────────────

    def screenshot(self) -> np.ndarray:
        """获取当前屏幕截图。

        Returns:
            BGR 格式的 numpy 数组 (height, width, 3)

        使用 adb shell screencap 写入文件 + adb pull 拉取，
        完全避免 TTY 层的二进制数据污染。
        """
        remote = "/sdcard/_bot_screen.png"
        local = Path("./logs/_temp_screen.png")

        try:
            # 确保目录存在
            local.parent.mkdir(parents=True, exist_ok=True)

            # 截图写入模拟器存储
            self._adb.shell(f"screencap -p {remote}", timeout=15.0)

            # 拉取到本地
            result = subprocess.run(
                [self._adb.adb_path, "-s", self._adb.device_addr,
                 "pull", remote, str(local)],
                capture_output=True, text=True, timeout=10.0,
                creationflags=_CREATE_NO_WINDOW,
            )
            logger.debug(f"adb pull: {result.stdout.strip()} {result.stderr.strip()}")

            # 读取文件
            img = cv2.imread(str(local))
            if img is None:
                raise RuntimeError(f"截图文件读取失败 (local={local})")

            # 清理
            local.unlink(missing_ok=True)

            h, w = img.shape[:2]
            self._resolution = (w, h)
            return img

        except Exception as e:
            # 清理临时文件
            Path(local).unlink(missing_ok=True)
            raise RuntimeError(f"截图失败: {e}")

    # ── 分辨率 ────────────────────────────────────────

    @property
    def resolution(self) -> tuple[int, int]:
        """获取屏幕分辨率 (宽, 高)。"""
        if self._resolution is None:
            try:
                self._resolution = self._adb.get_resolution()
            except Exception:
                # 通过截图获取
                screen = self.screenshot()
                h, w = screen.shape[:2]
                self._resolution = (w, h)
        return self._resolution

    @property
    def width(self) -> int:
        return self.resolution[0]

    @property
    def height(self) -> int:
        return self.resolution[1]

    # ── 触摸操作 ──────────────────────────────────────

    def tap(self, x: int, y: int, delay: float = 0.05) -> None:
        """点击屏幕坐标。

        Args:
            x, y: 坐标
            delay: 点击后等待秒数
        """
        logger.debug(f"点击: ({x}, {y})")
        self._adb.tap(x, y)
        if delay > 0:
            time.sleep(delay)

    def tap_center(self, bbox: tuple[int, int, int, int], delay: float = 0.05) -> None:
        """点击矩形区域中心。

        Args:
            bbox: (left, top, right, bottom)
        """
        cx = (bbox[0] + bbox[2]) // 2
        cy = (bbox[1] + bbox[3]) // 2
        self.tap(cx, cy, delay)

    def swipe(
        self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300
    ) -> None:
        """滑动屏幕。"""
        logger.debug(f"滑动: ({x1},{y1}) -> ({x2},{y2}), {duration_ms}ms")
        self._adb.swipe(x1, y1, x2, y2, duration_ms)

    def press_back(self, delay: float = 0.5) -> None:
        """按返回键。"""
        self._adb.press_back()
        if delay > 0:
            time.sleep(delay)

    def press_home(self, delay: float = 0.5) -> None:
        """按 Home 键。"""
        self._adb.press_home()
        if delay > 0:
            time.sleep(delay)

    # ── 画面稳定检测 ──────────────────────────────────

    def wait_for_stable(self, timeout: float = 10.0, interval: float = 0.5) -> bool:
        """等待画面稳定（连续两帧相同）。

        Args:
            timeout: 超时秒数
            interval: 检测间隔秒数

        Returns:
            True 表示在超时前画面已稳定
        """
        logger.debug(f"等待画面稳定 (timeout={timeout}s)")
        start = time.time()

        prev_hash = None
        while time.time() - start < timeout:
            screen = self.screenshot()
            current_hash = hashlib.md5(screen.tobytes()).hexdigest()

            if prev_hash is not None and current_hash == prev_hash:
                logger.debug(f"画面已稳定 ({time.time() - start:.2f}s)")
                return True

            prev_hash = current_hash
            time.sleep(interval)

        logger.warning(f"等待画面稳定超时 ({timeout}s)")
        return False

    def is_stuck(self, num_frames: int = 5, interval: float = 0.3) -> bool:
        """检测画面是否卡死（连续多帧无变化）。

        Args:
            num_frames: 需要检测的帧数
            interval: 帧间隔秒数

        Returns:
            True 表示画面可能卡死
        """
        hashes = []
        for _ in range(num_frames):
            screen = self.screenshot()
            hashes.append(hashlib.md5(screen.tobytes()).hexdigest())
            time.sleep(interval)

        # 检查所有帧是否相同
        return len(set(hashes)) == 1

    def __repr__(self) -> str:
        return f"Device({self._adb.device_addr}, {self.resolution})"

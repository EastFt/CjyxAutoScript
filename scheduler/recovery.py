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

"""全局异常恢复管理器。

确保 7x24 无人值守稳定运行的核心模块：
- 弹窗拦截（集中式，每次操作前自动扫描并关闭）
- 卡死检测（连续帧哈希比对）
- 紧急重启流程（停止游戏 → 重启 → 登录 → 导航回主页）
- 模拟器存活检测
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from core.adb_controller import ADBController
    from core.device import Device
    from core.vision import VisionEngine
    from core.action import Action


class RecoveryManager:
    """全局异常恢复管理器。

    在每轮任务执行前和被任务内部调用，
    负责处理所有非任务逻辑的异常情况。

    Usage:
        recovery = RecoveryManager(adb, device, vision, action, config)
        recovery.ensure_game_running()
        recovery.dismiss_popups()
        # ... 执行任务 ...
    """

    def __init__(
        self,
        adb: "ADBController",
        device: "Device",
        vision: "VisionEngine",
        action: "Action | None" = None,
        game_package: str = "",
        game_activity: str = "",
        assets_dir: str = "./assets",
        max_restart_count: int = 3,
        stuck_detection_frames: int = 5,
    ):
        self._adb = adb
        self._device = device
        self._vision = vision
        self._action = action
        self._game_package = game_package
        self._game_activity = game_activity
        self._assets_dir = Path(assets_dir)
        self._max_restart_count = max_restart_count
        self._stuck_detection_frames = stuck_detection_frames

        # 运行时状态
        self._restart_count = 0
        self._popup_templates: list[str] = []

        # 加载弹窗模板列表
        self._load_popup_templates()

    # ── 弹窗模板管理 ──────────────────────────────────

    def _load_popup_templates(self) -> None:
        """扫描 assets/popups/ 目录，加载所有弹窗模板路径。"""
        popup_dir = self._assets_dir / "popups"
        if not popup_dir.exists():
            logger.debug(f"弹窗目录不存在: {popup_dir}")
            return

        self._popup_templates = []
        for ext in ["*.png", "*.jpg", "*.jpeg"]:
            for f in popup_dir.glob(ext):
                rel_path = f"popups/{f.name}"
                self._popup_templates.append(rel_path)

        logger.debug(f"已加载 {len(self._popup_templates)} 个弹窗模板: "
                     f"{[Path(p).stem for p in self._popup_templates]}")

    # ── 弹窗拦截 ──────────────────────────────────────

    def dismiss_popups(self, max_rounds: int = 3) -> int:
        """遍历所有弹窗模板，检测并关闭弹窗。

        弹窗处理是拦截式的——在每步操作前调用此方法，
        不依赖具体任务自行处理弹窗。

        Args:
            max_rounds: 最大轮数（每轮遍历所有弹窗模板一次）

        Returns:
            关闭的弹窗数量
        """
        if not self._popup_templates:
            return 0

        total_closed = 0

        for _round in range(max_rounds):
            round_closed = 0
            screen = self._device.screenshot()

            for template in self._popup_templates:
                bbox = self._vision.find(
                    screen, template, threshold=0.75
                )
                if bbox is not None:
                    logger.info(f"检测到弹窗: {Path(template).stem}，尝试关闭")

                    # 尝试点击弹窗上的关闭按钮
                    closed = self._try_close_popup(bbox)

                    # 如果关闭失败，尝试点击弹窗中心（有些弹窗点任意位置就关闭）
                    if not closed:
                        self._device.tap_center(bbox, delay=0.3)

                    round_closed += 1

            total_closed += round_closed

            if round_closed == 0:
                # 本轮没有弹窗，退出
                break

            # 等待画面稳定后继续检查
            self._device.wait_for_stable(timeout=1.0)

        if total_closed > 0:
            logger.info(f"共关闭 {total_closed} 个弹窗")
        return total_closed

    def _try_close_popup(self, popup_bbox: tuple) -> bool:
        """尝试点击弹窗的关闭按钮。

        策略：
        1. 在弹窗区域内查找关闭按钮（X 按钮）
        2. 在弹窗上部查找关闭按钮
        3. 尝试按返回键

        Returns:
            True 表示弹窗已关闭
        """
        screen = self._device.screenshot()

        # 策略1: 查找通用关闭按钮
        close_btn = self._vision.find(
            screen, "buttons/btn_close.png", threshold=0.75
        )
        if close_btn is not None:
            self._device.tap_center(close_btn, delay=0.3)
            gone = self._vision.wait_until_gone(
                self._device.screenshot, "buttons/btn_close.png", timeout=2.0
            )
            if gone:
                return True

        # 策略2: 在弹窗区域内找任何可能的关闭按钮
        close_candidates = [
            "buttons/btn_close.png",
            "buttons/btn_confirm.png",
            "buttons/btn_ok.png",
            "buttons/btn_cancel.png",
        ]
        for candidate in close_candidates:
            try:
                bbox = self._vision.find(screen, candidate, threshold=0.75)
                if bbox is not None:
                    self._device.tap_center(bbox, delay=0.3)
                    time.sleep(0.5)
                    if not self._vision.exists(self._device.screenshot(), candidate):
                        return True
            except FileNotFoundError:
                # 模板文件不存在，跳过
                continue

        # 策略3: 按返回键
        self._device.press_back(delay=0.5)
        return True  # 无法确认但已尝试

    # ── 游戏保活 ──────────────────────────────────────

    def ensure_game_running(self) -> bool:
        """确保游戏正在运行且在前台。

        检查流程：
        1. ADB 连接正常 → 否：尝试重连
        2. 游戏进程存在 → 否：启动游戏
        3. 游戏在前台 → 验证（可选，通过截图匹配主界面元素）

        Returns:
            True 表示游戏正常运行
        """
        # 1. 检查 ADB 连接
        if not self._adb.is_connected:
            logger.warning("ADB 已断开，尝试重连...")
            if not self._adb.reconnect():
                logger.error("ADB 重连失败")
                return False
            logger.info("ADB 已重连")

        # 2. 检查游戏进程（如果配置了包名）
        if self._game_package:
            if not self._adb.app_is_running(self._game_package):
                logger.warning(f"游戏进程 ({self._game_package}) 未运行，尝试启动...")
                if not self._start_game():
                    return False
            else:
                logger.debug(f"游戏进程 ({self._game_package}) 运行中")

        return True

    def _start_game(self) -> bool:
        """启动游戏应用。"""
        if not self._game_package:
            logger.warning("未配置 game_package，无法启动游戏")
            return False

        try:
            if self._game_activity:
                self._adb.start_app(self._game_package, self._game_activity)
            else:
                self._adb.start_app(self._game_package)

            # 等待游戏加载
            time.sleep(5.0)
            self._device.wait_for_stable(timeout=30.0)

            logger.info(f"游戏已启动: {self._game_package}")
            return True
        except Exception as e:
            logger.error(f"启动游戏失败: {e}")
            return False

    # ── 卡死检测 ──────────────────────────────────────

    def handle_game_stuck(self) -> bool:
        """检测并处理游戏卡死。

        卡死判定：连续 N 帧截图像素完全相同。

        Returns:
            True 表示卡死已恢复，False 表示需要进一步处理
        """
        if self._device.is_stuck(
            num_frames=self._stuck_detection_frames,
            interval=0.3,
        ):
            logger.warning(
                f"检测到画面卡死 ({self._stuck_detection_frames} 帧无变化)"
            )

            # 尝试1: 按返回键
            logger.info("尝试按返回键恢复...")
            self._device.press_back(delay=1.0)

            if not self._device.is_stuck(num_frames=3, interval=0.3):
                logger.info("按返回键后画面恢复")
                return True

            # 尝试2: 点击屏幕中央（有些卡在加载需要点击）
            logger.info("尝试点击屏幕中央...")
            w, h = self._device.resolution
            self._device.tap(w // 2, h // 2, delay=1.0)

            if not self._device.is_stuck(num_frames=3, interval=0.3):
                logger.info("点击后画面恢复")
                return True

            # 卡死未恢复
            logger.warning("卡死未恢复，需要重启")
            return False

        # 没有卡死
        return True

    # ── 紧急重启 ──────────────────────────────────────

    def emergency_restart(self) -> bool:
        """紧急重启游戏流程。

        1. 强制停止游戏
        2. 等待进程结束
        3. 重新启动游戏
        4. 等待加载完成

        Returns:
            True 表示重启成功
        """
        if self._restart_count >= self._max_restart_count:
            logger.critical(
                f"已达到最大重启次数 ({self._max_restart_count})，"
                "停止自动恢复，请手动检查。"
            )
            return False

        self._restart_count += 1
        logger.warning(
            f"执行紧急重启 ({self._restart_count}/{self._max_restart_count})"
        )

        if not self._game_package:
            logger.error("未配置 game_package，无法重启游戏")
            return False

        try:
            # 1. 强制停止
            self._adb.stop_app(self._game_package)
            time.sleep(2.0)

            # 2. 验证已停止
            if self._adb.app_is_running(self._game_package):
                logger.warning("游戏未能完全停止，再次尝试...")
                self._adb.stop_app(self._game_package)
                time.sleep(3.0)

            # 3. 重新启动
            if not self._start_game():
                return False

            # 4. 重置重启计数（成功重启后）
            logger.info("紧急重启完成")
            return True

        except Exception as e:
            logger.error(f"紧急重启异常: {e}")
            return False

    def reset_restart_count(self) -> None:
        """重置重启计数器（在稳定运行一段时间后调用）。"""
        if self._restart_count > 0:
            logger.debug(f"重置重启计数 (原值={self._restart_count})")
            self._restart_count = 0

    # ── 模拟器存活检测 ────────────────────────────────

    def check_emulator_alive(self) -> bool:
        """检测模拟器是否存活。

        Returns:
            True 表示模拟器正常响应
        """
        if not self._adb.is_connected:
            return False

        try:
            # 发送一个简单的 shell 命令测试响应
            output = self._adb.shell("echo alive", timeout=5.0)
            return "alive" in output.lower()
        except Exception:
            return False

    # ── 网络错误处理 ──────────────────────────────────

    def handle_network_error(self) -> bool:
        """检测并处理网络错误弹窗。

        游戏中常见的网络错误弹窗通常包含"重试"按钮。

        Returns:
            True 表示已处理（或没有网络错误）
        """
        network_error_templates = [
            "popups/popup_network_error.png",
            "buttons/btn_retry.png",
            "buttons/btn_reconnect.png",
        ]

        screen = self._device.screenshot()
        for template in network_error_templates:
            try:
                bbox = self._vision.find(screen, template, threshold=0.8)
                if bbox is not None:
                    logger.info("检测到网络错误弹窗，点击重试")
                    self._device.tap_center(bbox, delay=1.0)
                    self._device.wait_for_stable(timeout=5.0)
                    return True
            except FileNotFoundError:
                continue

        return False

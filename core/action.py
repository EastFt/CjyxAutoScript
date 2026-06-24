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

"""原子操作模块。

将 detect → decide → act → verify 循环封装为可复用的原子操作。
组合 Device、VisionEngine 提供带验证的高层操作。
"""

from __future__ import annotations

import time
from typing import Callable

from loguru import logger


class EmergencyStop(Exception):
    """紧急停止异常。检测到停止信号时抛出。"""
    pass


class Action:
    """原子操作封装。

    组合 Device + VisionEngine，把检测→决策→执行→验证的循环封装为一行调用。

    Usage:
        action = Action(device, vision)
        if action.click_when_appears("buttons/btn_battle.png"):
            logger.info("已进入战斗")
    """

    def __init__(self, device, vision):
        self._device = device
        self._vision = vision

    # ── 点击类操作 ────────────────────────────────────

    def click_when_appears(
        self,
        template: str,
        timeout: float = 5.0,
        roi: tuple | None = None,
        threshold: float | None = None,
        delay: float = 0.5,
    ) -> bool:
        """等待元素出现后点击其中心。

        Args:
            template: 模板路径
            timeout: 最大等待时间（秒）
            roi: 搜索区域
            threshold: 匹配置信度阈值
            delay: 点击后等待秒数

        Returns:
            True 表示找到并点击成功
        """
        logger.debug(f"等待并点击: {template}")
        bbox = self._vision.wait_until(
            self._device.screenshot, template,
            timeout=timeout, roi=roi, threshold=threshold,
        )
        if bbox is None:
            logger.debug(f"未找到元素: {template}")
            return False

        self._device.tap_center(bbox, delay=delay)
        logger.debug(f"已点击: {template} @ ({bbox[0]},{bbox[1]})")

        return True

    def click_and_confirm(
        self,
        template: str,
        confirm_template: str | None = None,
        timeout: float = 5.0,
        roi: tuple | None = None,
        threshold: float | None = None,
    ) -> bool:
        """点击元素并等待确认。

        确认方式（二选一）：
        - 如果给了 confirm_template：点击后等待该元素出现
        - 否则：点击后等待原元素消失

        Args:
            template: 要点击的模板
            confirm_template: 确认元素模板（可选）
            timeout: 确认等待超时
            roi: 搜索区域
            threshold: 置信度阈值

        Returns:
            True 表示点击且确认成功
        """
        bbox = self._vision.find(
            self._device.screenshot(), template, roi, threshold
        )
        if bbox is None:
            logger.debug(f"click_and_confirm: 未找到目标 {template}")
            return False

        self._device.tap_center(bbox, delay=0.3)

        if confirm_template:
            # 等待确认元素出现
            confirmed = self._vision.wait_until(
                self._device.screenshot, confirm_template,
                timeout=timeout, threshold=threshold,
            )
            if confirmed:
                logger.debug(f"确认成功: {confirm_template} 已出现")
                return True
            logger.debug(f"确认超时: {confirm_template} 未出现")
            return False
        else:
            # 等待原元素消失
            gone = self._vision.wait_until_gone(
                self._device.screenshot, template,
                timeout=timeout, threshold=threshold,
            )
            if gone:
                logger.debug(f"确认成功: {template} 已消失")
                return True
            logger.debug(f"确认超时: {template} 未消失")
            return False

    def click_if_exists(
        self,
        template: str,
        roi: tuple | None = None,
        threshold: float | None = None,
    ) -> bool:
        """如果元素存在则立即点击（不等待）。

        Returns:
            True 表示找到并点击
        """
        bbox = self._vision.find(
            self._device.screenshot(), template, roi, threshold
        )
        if bbox:
            self._device.tap_center(bbox, delay=0.2)
            logger.debug(f"点击已存在元素: {template}")
            return True
        return False

    # ── 滑动类操作 ────────────────────────────────────

    def swipe_until_found(
        self,
        template: str,
        direction: str = "up",
        max_swipes: int = 10,
        roi: tuple | None = None,
        threshold: float | None = None,
    ) -> bool:
        """重复滑动直到找到目标元素。

        在列表中滑动搜索时使用，如副本列表、角色列表等。

        Args:
            template: 要查找的模板
            direction: 滑动方向 "up" | "down" | "left" | "right"
            max_swipes: 最大滑动次数
            roi: 搜索区域
            threshold: 置信度阈值

        Returns:
            True 表示找到了目标
        """
        logger.debug(f"滑动查找: {template} (方向={direction}, 最多{max_swipes}次)")

        w, h = self._device.resolution
        cx, cy = w // 2, h // 2

        # 滑动参数映射
        swipe_params = {
            "up":    (cx, int(h * 0.7), cx, int(h * 0.3)),
            "down":  (cx, int(h * 0.3), cx, int(h * 0.7)),
            "left":  (int(w * 0.7), cy, int(w * 0.3), cy),
            "right": (int(w * 0.3), cy, int(w * 0.7), cy),
        }

        if direction not in swipe_params:
            logger.error(f"无效的滑动方向: {direction}")
            return False

        x1, y1, x2, y2 = swipe_params[direction]

        for i in range(max_swipes):
            # 先检查当前画面
            if self._vision.exists(
                self._device.screenshot(), template, roi, threshold
            ):
                logger.debug(f"第 {i+1} 次滑动前已找到: {template}")
                return True

            # 滑动
            self._device.swipe(x1, y1, x2, y2, duration_ms=300)
            time.sleep(2.0)

            # 再检查
            if self._vision.exists(
                self._device.screenshot(), template, roi, threshold
            ):
                logger.debug(f"第 {i+1} 次滑动后找到: {template}")
                return True

        logger.debug(f"滑动 {max_swipes} 次后仍未找到: {template}")
        return False

    # ── 重复类操作 ────────────────────────────────────

    def repeat_until(
        self,
        action_fn: Callable[[], bool],
        condition_fn: Callable[[], bool],
        max_repeat: int = 50,
        interval: float = 1.0,
    ) -> bool:
        """重复执行动作直到条件满足。

        用于战斗循环、等待加载等场景。

        Args:
            action_fn: 要重复执行的动作（如点击确认按钮）
            condition_fn: 停止条件（如检测到结算画面）
            max_repeat: 最大重复次数
            interval: 每次循环间隔秒数

        Returns:
            True 表示条件在最大次数内满足
        """
        for i in range(max_repeat):
            if condition_fn():
                logger.debug(f"条件满足，停止重复 (第 {i+1}/{max_repeat} 次)")
                return True

            action_fn()
            time.sleep(interval)

        logger.warning(f"repeat_until 达到最大次数 {max_repeat}，条件仍未满足")
        return False

    def repeat_click_until_gone(
        self,
        template: str,
        max_repeat: int = 20,
        interval: float = 0.5,
        roi: tuple | None = None,
        threshold: float | None = None,
    ) -> bool:
        """重复点击直到元素消失。

        用于关闭弹窗、跳过对话等场景。

        Returns:
            True 表示元素已消失
        """
        for i in range(max_repeat):
            bbox = self._vision.find(
                self._device.screenshot(), template, roi, threshold
            )
            if bbox is None:
                return True

            self._device.tap_center(bbox)
            time.sleep(interval)

        logger.debug(f"repeat_click_until_gone: {template} 仍存在")
        return False

    # ── 导航类操作 ────────────────────────────────────

    def navigate_home(
        self,
        home_indicator: str = "screens/screen_main_menu.png",
        max_back_presses: int = 10,
        back_delay: float = 0.5,
    ) -> bool:
        """尝试返回主界面。

        重复按返回键，直到检测到主界面标识元素，
        或达到最大返回次数。

        Args:
            home_indicator: 主界面标识模板
            max_back_presses: 最大按返回键次数
            back_delay: 每次返回键后等待秒数

        Returns:
            True 表示已回到主界面
        """
        logger.debug(f"导航回主界面 (标识={home_indicator})")

        for i in range(max_back_presses):
            if self._vision.exists(self._device.screenshot(), home_indicator):
                logger.debug(f"已回到主界面 (第 {i} 次返回键)")
                time.sleep(2.0)
                return True

            self._device.press_back(delay=back_delay)

        logger.warning("未能回到主界面")
        return False

    def tap_back_button(
        self,
        delay: float = 0.5,
        x_ratio: float = 0.05,
        y_ratio: float = 0.05,
    ) -> None:
        """点击游戏内左上角的返回按钮（固定位置）。

        游戏内的返回按钮通常固定在左上角，位置稳定但图形多变。
        这里用屏幕百分比定位，不依赖模板匹配。

        Args:
            delay: 点击后等待秒数
            x_ratio: 距左边界的比例 (默认 5%)
            y_ratio: 距上边界的比例 (默认 5%)
        """
        w, h = self._device.resolution
        x = int(w * x_ratio)
        y = int(h * y_ratio)
        logger.debug(f"点击返回按钮: ({x}, {y}) (比例 {x_ratio:.0%}, {y_ratio:.0%})")
        self._device.tap(x, y, delay=delay)

    def press_back_safe(self, delay: float = 0.5) -> None:
        """优先按游戏内返回按钮，兜底按 Android 系统返回键。

        先尝试点击左上角固定位置（游戏内返回按钮），
        然后也发送系统返回键作为兜底。
        """
        self.tap_back_button(delay=0.3)
        self._device.press_back(delay=delay)

    def tap_bottom_right_back(
        self,
        delay: float = 0.5,
        x_ratio: float = 0.90,
        y_ratio: float = 0.93,
    ) -> None:
        """点击屏幕右下角的返回按钮（公会界面专用）。

        某些界面的返回按钮在右下角而非左上角。

        Args:
            delay: 点击后等待秒数
            x_ratio: 距左边界的比例 (默认 90%)
            y_ratio: 距上边界的比例 (默认 93%)
        """
        w, h = self._device.resolution
        x = int(w * x_ratio)
        y = int(h * y_ratio)
        logger.debug(f"点击右下角返回: ({x}, {y})")
        self._device.tap(x, y, delay=delay)

    def tap_anywhere(self, delay: float = 0.3) -> None:
        """点击屏幕中央（用于消除弹窗/跳过动画）。

        某些弹窗没有关闭按钮，点击任意位置即可消除。
        """
        w, h = self._device.resolution
        self._device.tap(w // 2, h // 2, delay=delay)
        logger.debug("点击屏幕中央消除弹窗")

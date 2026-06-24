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

"""任务基类。

定义所有日常任务的抽象接口和标准生命周期：
    pre_check() → execute() → post_check()

内置重试机制和状态追踪。
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING

from loguru import logger


from core.action import EmergencyStop

if TYPE_CHECKING:
    import numpy as np
    from core.device import Device
    from core.vision import VisionEngine
    from core.action import Action


class TaskResult(Enum):
    """任务执行结果。"""
    SUCCESS = "success"
    FAILED  = "failed"
    RETRY   = "retry"
    SKIPPED = "skipped"


class BaseTask(ABC):
    """所有日常任务的抽象基类。

    子类需要:
    1. 设置 name, priority, timeout 等类变量
    2. 实现 execute() 方法
    3. 可选覆盖 pre_check() / post_check() / on_error()

    Usage:
        class MyTask(BaseTask):
            name = "my_task"
            priority = 5

            def execute(self) -> TaskResult:
                if self.action.click_when_appears("btn_confirm.png"):
                    return TaskResult.SUCCESS
                return TaskResult.FAILED
    """

    # ── 子类覆盖的元数据 ──────────────────────────────

    name: str = "base_task"
    """任务名称，用于日志和配置关联。"""

    priority: int = 0
    """优先级，数值越小越优先执行。"""

    timeout: float = 120.0
    """单次执行的最大时长（秒）。"""

    # ── 初始化 ────────────────────────────────────────

    def __init__(
        self,
        device: "Device",
        vision: "VisionEngine",
        action: "Action" | None = None,
        config: dict | None = None,
    ):
        self._device = device
        self._vision = vision
        self._action = action
        self._config = config or {}

        # 运行时状态
        self._attempt = 0
        self._start_time: float = 0.0

    # ── 属性 ──────────────────────────────────────────

    @property
    def device(self) -> "Device":
        return self._device

    @property
    def vision(self) -> "VisionEngine":
        return self._vision

    @property
    def action(self) -> "Action" | None:
        return self._action

    @property
    def config(self) -> dict:
        return self._config

    @property
    def retry_count(self) -> int:
        """最大重试次数（从配置读取，默认3次）。"""
        return self._config.get("retry_count", 3)

    @property
    def retry_delay(self) -> float:
        """重试延迟秒数（从配置读取，默认2秒）。"""
        return self._config.get("retry_delay", 2.0)

    # ── 生命周期方法 ──────────────────────────────────

    @abstractmethod
    def execute(self) -> TaskResult:
        """子类实现具体任务逻辑。

        Returns:
            TaskResult 表示执行结果。
        """
        ...

    def is_already_done(self) -> bool:
        """检查任务是否已经完成（不应重复执行）。

        子类覆盖此方法，用模板匹配检测"已完成"状态。
        模板统一放在 assets/buttons/ 下。

        默认返回 False（未完成，可执行）。

        Returns:
            True 表示任务已完成，应跳过。
        """
        return False

    def pre_check(self) -> bool:
        """执行前检查。

        默认返回 True。子类可覆盖以实现环境检查，
        如确保当前在主界面。

        Returns:
            True 表示检查通过，可继续执行。
        """
        return True

    def post_check(self) -> bool:
        """执行后验证。

        默认返回 True。子类可覆盖以验证任务结果，
        如检查体力是否正确消耗。

        Returns:
            True 表示验证通过。
        """
        return True

    def on_error(self, error: Exception) -> TaskResult:
        """异常处理回调。

        默认返回 FAILED。子类可覆盖以实现自定义恢复逻辑。

        Returns:
            TaskResult.RETRY 表示需要重试
            TaskResult.FAILED 表示放弃
            TaskResult.SKIPPED 表示跳过
        """
        logger.error(f"[{self.name}] 异常: {error}")
        return TaskResult.FAILED

    # ── 运行入口 ──────────────────────────────────────

    def run(self) -> TaskResult:
        """执行任务（带重试逻辑）。

        这是调度器调用的入口方法。

        Returns:
            最终执行结果
        """
        logger.info(f"[{self.name}] 开始执行 (优先级={self.priority})")
        self._start_time = time.time()

        for attempt in range(self.retry_count + 1):
            self._attempt = attempt
            if attempt > 0:
                delay = self.retry_delay * attempt
                logger.info(f"[{self.name}] 第 {attempt} 次重试 (等待 {delay:.1f}s)")
                time.sleep(delay)

            try:
                # 执行前检查
                if not self.pre_check():
                    logger.warning(f"[{self.name}] 前置检查未通过，跳过")
                    return TaskResult.SKIPPED

                # 已完成检查（避免重复执行）
                if self.is_already_done():
                    logger.info(f"[{self.name}] 检测到已完成，跳过")
                    return TaskResult.SKIPPED

                # 检查超时
                if self._is_timeout():
                    logger.error(f"[{self.name}] 任务超时 ({self.timeout}s)")
                    return TaskResult.FAILED

                # 执行任务
                result = self.execute()

                if result == TaskResult.SUCCESS:
                    # 执行后验证
                    if self.post_check():
                        elapsed = time.time() - self._start_time
                        logger.info(
                            f"[{self.name}] 执行成功 ({elapsed:.1f}s, "
                            f"尝试 {attempt + 1}/{self.retry_count + 1})"
                        )
                        return TaskResult.SUCCESS
                    else:
                        logger.warning(f"[{self.name}] 后置验证未通过")
                        result = TaskResult.RETRY

                if result == TaskResult.RETRY:
                    continue

                if result == TaskResult.FAILED:
                    if attempt < self.retry_count:
                        logger.warning(f"[{self.name}] 执行失败，将重试")
                        continue
                    else:
                        logger.error(f"[{self.name}] 已达最大重试次数，标记失败")
                        return TaskResult.FAILED

                if result == TaskResult.SKIPPED:
                    return TaskResult.SKIPPED

            except EmergencyStop:
                raise  # 直接向上抛出，不重试
            except Exception as e:
                error_result = self.on_error(e)
                if error_result == TaskResult.RETRY and attempt < self.retry_count:
                    continue
                if error_result != TaskResult.RETRY:
                    return error_result

        return TaskResult.FAILED

    def _is_timeout(self) -> bool:
        """检查是否超时。"""
        return (time.time() - self._start_time) > self.timeout

    # ── 辅助方法 ──────────────────────────────────────

    def sleep(self, seconds: float) -> None:
        """等待指定秒数（同时检查超时）。"""
        time.sleep(seconds)

    def screenshot(self) -> "np.ndarray":
        """获取当前截图。"""
        return self._device.screenshot()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(priority={self.priority})"

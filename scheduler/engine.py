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

"""任务调度引擎。

按优先级顺序执行日常任务，支持：
- 循环调度（定时或持续）
- 任务自动发现
- 执行前保活检查 + 弹窗清理
- 任务失败后的恢复处理
- 执行结果汇总
"""

from __future__ import annotations

import importlib
import time
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from config.settings import AppConfig, TaskConfig
from core.action import EmergencyStop
from core.adb_controller import ADBFatalError
from scheduler.recovery import RecoveryManager

if TYPE_CHECKING:
    from core.adb_controller import ADBController
    from core.device import Device
    from core.vision import VisionEngine
    from core.action import Action


class Scheduler:
    """任务调度引擎。

    负责管理任务生命周期：发现 → 排序 → 保活 → 执行 → 汇总。

    Usage:
        scheduler = Scheduler(config, adb, device, vision, action)
        scheduler.run_once()      # 执行一轮
        scheduler.run_loop()      # 持续循环
    """

    def __init__(
        self,
        config: AppConfig,
        adb: "ADBController",
        device: "Device",
        vision: "VisionEngine",
        action: "Action | None" = None,
    ):
        self._config = config
        self._adb = adb
        self._device = device
        self._vision = vision
        self._action = action

        # 初始化恢复管理器
        self._recovery = RecoveryManager(
            adb=adb,
            device=device,
            vision=vision,
            action=action,
            game_package=config.game_package,
            game_activity=config.game_activity,
            assets_dir=config.assets_dir,
            max_restart_count=config.max_restart_count,
            stuck_detection_frames=config.stuck_detection_frames,
        )

        # 自动发现并注册任务
        self._task_registry: dict[str, type] = {}
        self._discover_tasks()

        # 运行状态
        self._stop_flag = False
        self._last_success_time = time.time()

    # ── 任务发现 ──────────────────────────────────────

    def _discover_tasks(self) -> None:
        """自动扫描 tasks/ 目录，发现所有 BaseTask 子类。"""
        tasks_dir = Path(__file__).parent.parent / "tasks"

        # 手动注册已知任务（保证加载顺序明确）
        known_tasks = [
            "daily_signin",
            "daily_quest",
            "collect_mail",
            "friends",
            "events",
            "treasure_hunt",
            "guild",
            "arena",
            "auto_battle",
            "divine_arena",
        ]

        for name in known_tasks:
            try:
                module = importlib.import_module(f"tasks.{name}")
                # 查找模块中的 BaseTask 子类
                from scheduler.base_task import BaseTask
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, BaseTask)
                        and attr is not BaseTask
                        and hasattr(attr, "name")
                    ):
                        self._task_registry[attr.name] = attr
                        logger.debug(f"已注册任务: {attr.name} ({attr_name})")
                        break
            except ImportError:
                # 任务模块不存在，跳过
                logger.debug(f"任务模块不存在: tasks.{name}")
                continue
            except Exception as e:
                logger.warning(f"加载任务模块 tasks.{name} 失败: {e}")
                continue

        logger.info(f"共发现 {len(self._task_registry)} 个任务: "
                    f"{list(self._task_registry.keys())}")

    # ── 单轮执行 ──────────────────────────────────────

    def run_once(self) -> dict[str, str]:
        """执行一轮所有启用的任务。

        执行流程：
        1. 保活检查（游戏是否运行、ADB 是否连接）
        2. 弹窗清理
        3. 卡死检测与恢复
        4. 按优先级顺序执行每个任务
        5. 汇总结果

        Returns:
            {任务名: 结果状态字符串}
        """
        results: dict[str, str] = {}

        # ── 预执行检查 ────────────────────────────────

        # 1. 模拟器存活检测
        if not self._recovery.check_emulator_alive():
            logger.error("模拟器无响应，尝试重连 ADB...")
            if not self._adb.reconnect():
                logger.critical("模拟器不可用，终止本轮")
                return {"_system": "emulator_dead"}

        # 2. 游戏保活
        if not self._recovery.ensure_game_running():
            logger.error("游戏保活失败，尝试紧急重启...")
            if not self._recovery.emergency_restart():
                logger.critical("紧急重启失败，终止本轮")
                return {"_system": "game_not_running"}

        # 3. 弹窗清理（任务执行前清理一次）
        self._recovery.dismiss_popups()

        # 4. 卡死检测
        if not self._recovery.handle_game_stuck():
            logger.warning("画面卡死，尝试紧急重启...")
            if not self._recovery.emergency_restart():
                return {"_system": "stuck_unrecovered"}

        # 5. 网络错误处理
        self._recovery.handle_network_error()

        # ── 获取待执行任务 ──────────────────────────────

        enabled_tasks = sorted(
            [t for t in self._config.tasks if t.enabled],
            key=lambda t: t.priority,
        )

        if not enabled_tasks:
            logger.warning("没有启用的任务")
            return results

        logger.info(
            f"准备执行 {len(enabled_tasks)} 个任务: "
            f"{[t.name for t in enabled_tasks]}"
        )

        # ── 逐个执行任务 ────────────────────────────────

        for task_cfg in enabled_tasks:
            task_cls = self._task_registry.get(task_cfg.name)
            if task_cls is None:
                logger.warning(f"任务 '{task_cfg.name}' 未注册，跳过")
                results[task_cfg.name] = "unregistered"
                continue

            # 每次任务前清理弹窗
            self._recovery.dismiss_popups(max_rounds=1)

            # 紧急停止检测（长耗时任务）
            if task_cfg.name in ("events", "arena", "auto_battle", "treasure_hunt"):
                if self._check_emergency_stop():
                    logger.critical("检测到紧急停止信号，终止本轮所有后续任务")
                    results[task_cfg.name] = "stopped"
                    for remaining in enabled_tasks[enabled_tasks.index(task_cfg) + 1:]:
                        results[remaining.name] = "stopped"
                    break

            # 创建任务实例并执行
            logger.info(f"--- [{task_cfg.name}] 开始 ---")
            task = task_cls(
                device=self._device,
                vision=self._vision,
                action=self._action,
                config=task_cfg.model_dump(),
            )

            try:
                result = task.run()
                results[task_cfg.name] = result.value
            except EmergencyStop:
                logger.critical("紧急停止信号，终止本轮所有任务")
                results[task_cfg.name] = "stopped"
                for remaining in enabled_tasks[enabled_tasks.index(task_cfg) + 1:]:
                    results[remaining.name] = "stopped"
                break
            except (ADBFatalError,):
                logger.critical("ADB 致命错误，终止本轮所有任务")
                results[task_cfg.name] = "fatal"
                for remaining in enabled_tasks[enabled_tasks.index(task_cfg) + 1:]:
                    results[remaining.name] = "stopped"
                raise  # 继续向上传播
            except Exception as e:
                logger.exception(f"任务 [{task_cfg.name}] 抛出未捕获异常: {e}")
                results[task_cfg.name] = "error"

            # 任务失败后的恢复尝试
            if results[task_cfg.name] in ("failed", "error"):
                logger.warning(f"任务 [{task_cfg.name}] 失败，尝试恢复...")
                self._recovery.dismiss_popups()
                self._recovery.handle_game_stuck()

        # ── 汇总 ────────────────────────────────────────

        success_count = sum(1 for v in results.values() if v == "success")
        fail_count = sum(1 for v in results.values() if v in ("failed", "error"))
        skip_count = sum(1 for v in results.values() if v == "skipped")

        logger.info(
            f"本轮完成: {success_count} 成功, {fail_count} 失败, "
            f"{skip_count} 跳过 (共 {len(results)} 个任务)"
        )

        if fail_count == 0:
            self._last_success_time = time.time()
            # 稳定运行，逐步降低重启计数
            self._recovery.reset_restart_count()

        return results

    # ── 循环运行 ──────────────────────────────────────

    def run_loop(self, interval: float | None = None) -> None:
        """持续循环执行任务。

        Args:
            interval: 轮间间隔（秒），None 使用配置文件中的值
        """
        if interval is None:
            interval = self._config.loop_interval

        logger.info(f"调度器进入循环模式 (间隔={interval}s)")

        round_num = 0
        self._stop_flag = False

        while not self._stop_flag:
            round_num += 1
            logger.info(f"\n{'='*50}\n第 {round_num} 轮开始\n{'='*50}")

            try:
                self.run_once()
            except KeyboardInterrupt:
                logger.info("收到中断信号，停止调度器")
                break
            except Exception as e:
                logger.exception(f"第 {round_num} 轮发生严重异常: {e}")
                # 发生严重异常，等待后继续
                time.sleep(5.0)

            logger.info(f"第 {round_num} 轮完成，等待 {interval}s")

            # 分段等待（便于接收停止信号）
            remaining = interval
            while remaining > 0 and not self._stop_flag:
                sleep_time = min(remaining, 5.0)
                time.sleep(sleep_time)
                remaining -= sleep_time

    def _check_emergency_stop(self) -> bool:
        """检测紧急停止信号。

        模板: assets/buttons/btn_emergency_stop.png
        使用较低阈值(0.5)确保不会漏检。
        """
        try:
            screen = self._device.screenshot()
            if self._vision.exists(screen, "buttons/btn_emergency_stop.png", threshold=0.5):
                return True
        except (FileNotFoundError, ValueError):
            pass
        return False

    def stop(self) -> None:
        """请求停止调度器。"""
        logger.info("收到停止请求")
        self._stop_flag = True

    @property
    def last_success_time(self) -> float:
        """上次全部成功的时间戳。"""
        return self._last_success_time

    @property
    def task_count(self) -> int:
        """已注册任务数。"""
        return len(self._task_registry)

    @property
    def registry(self) -> dict[str, type]:
        """任务注册表（只读）。"""
        return dict(self._task_registry)

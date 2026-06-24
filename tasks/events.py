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

"""常驻活动任务。

入口使用绝对坐标。点击参战后立即检测扫荡按钮：
- 扫荡按钮存在 → 进入成功 → 扫荡 → 返回
- 扫荡按钮不存在 → 参战无响应（活动已完成）→ 跳过扫荡、不返回
"""

import time
from scheduler.base_task import BaseTask, TaskResult
from loguru import logger

# 活动入口坐标 (x, y)
EVENT_COORDS = {
    "资源":   (300, 300),
    "活动1":  (300, 400),
    "活动2":  (300, 480),
    "活动3":  (300, 580),
    "生存":   (300, 230),
    "神恩":   (300, 330),
    "元素挑战": (300, 580),
}

SWIPE_START = (300, 580)
SWIPE_END   = (300, 220)
SWIPE_DURATION = 400


class EventsTask(BaseTask):
    name = "events"
    priority = 8
    timeout = 600.0

    def _tap_coord(self, label: str) -> None:
        x, y = EVENT_COORDS[label]
        logger.info(f"[{label}] 坐标点击 ({x}, {y})")
        self.device.tap(x, y)
        self.sleep(2.0)

    def _swipe_up(self) -> None:
        self.device.swipe(
            SWIPE_START[0], SWIPE_START[1],
            SWIPE_END[0],   SWIPE_END[1],
            duration_ms=SWIPE_DURATION,
        )

    # ── 通用扫荡阶段 ──────────────────────────────

    def _do_sweep_phase(self, label: str, coords_key: str, sweep_times: int = 2,
                         done_template: str | None = None) -> None:
        """坐标进入 → 点参战 → 判重 → 扫荡+返回。"""
        self._tap_coord(coords_key)

        if not self.action.click_when_appears("buttons/btn_join.png", timeout=3.0):
            logger.info(f"[{label}] 参战按钮不存在，活动已完成（跳过）")
            return

        self.sleep(2.0)

        # 判重
        if done_template:
            try:
                if self.vision.exists(self.screenshot(), done_template):
                    logger.info(f"[{label}] 已完成")
                    self.device.tap(980, 120)
                    self.sleep(2.0)
                    return
            except (FileNotFoundError, ValueError):
                pass

        if not self.vision.exists(self.screenshot(), "buttons/btn_sweep.png"):
            logger.info(f"[{label}] 扫荡按钮不存在，活动已完成（不扫荡、不返回）")
            return

        for i in range(sweep_times):
            self.action.click_when_appears("buttons/btn_sweep.png", timeout=3.0)
            self.sleep(2.0)

        self.action.tap_back_button()
        self.sleep(2.0)

    # ── 主流程 ────────────────────────────────────

    def execute(self) -> TaskResult:
        phases = self.config.get("params", {}).get("phases", [1, 2, 3, 4, 5, 6, 7])
        run = lambda p: p in phases

        if not self.action.click_when_appears("buttons/btn_events.png", timeout=5.0):
            logger.warning("找不到'活动'入口")
            return TaskResult.FAILED
        self.sleep(2.0)

        # ── 第一页 ──
        if run(1):
            logger.info("=== Phase 1: 资源 ===")
            self._do_sweep_phase("资源", "资源", sweep_times=2,
                                 done_template="buttons/btn_event_done.png")

        if run(2):
            logger.info("=== Phase 2: 活动1 ===")
            self._do_sweep_phase("活动1", "活动1", sweep_times=2,
                                 done_template="buttons/btn_event_done.png")

        if run(3):
            logger.info("=== Phase 3: 活动2 ===")
            self._do_sweep_phase("活动2", "活动2", sweep_times=2)

        if run(4):
            logger.info("=== Phase 4: 活动3 ===")
            self._tap_coord("活动3")

            if not self.action.click_when_appears("buttons/btn_join.png", timeout=3.0):
                logger.info("[活动3] 参战按钮不存在（跳过）")
            else:
                self.sleep(2.0)
                # 判重
                already_done = False
                try:
                    already_done = self.vision.exists(self.screenshot(), "buttons/btn_event_done.png")
                except (FileNotFoundError, ValueError):
                    pass
                if already_done:
                    logger.info("[活动3] 已完成")
                    self.device.tap(980, 120)
                    self.sleep(2.0)
                elif not self.vision.exists(self.screenshot(), "buttons/btn_sweep.png"):
                    logger.info("[活动3] 扫荡按钮不存在，活动已完成（不扫荡、不返回）")
                else:
                    self.action.click_when_appears("buttons/btn_sweep.png", timeout=3.0)
                    self.sleep(2.0)
                    self.action.tap_anywhere()
                    self.sleep(2.0)
                    self.action.click_when_appears("buttons/btn_sweep.png", timeout=3.0)
                    self.sleep(2.0)
                    self.action.tap_anywhere()
                    self.sleep(2.0)
                    self.action.tap_back_button()
                    self.sleep(2.0)

        # ── 上滑 → 第二页 ──
        if any(run(p) for p in [5, 6]):
            self._swipe_up()
            self.sleep(2.0)

        if run(5):
            logger.info("=== Phase 5: 生存 ===")
            if not self.action.click_when_appears("buttons/btn_survival.png", timeout=3.0):
                logger.info("[生存] 入口模板不存在（跳过）")
            else:
                self.sleep(2.0)
                self.action.click_when_appears("buttons/btn_join.png", timeout=3.0)
                self.sleep(2.0)
                if not self.vision.exists(self.screenshot(), "buttons/btn_rush.png"):
                    logger.info("[生存] 突进按钮不存在，活动已完成（不执行、不返回）")
                else:
                    self.action.click_when_appears("buttons/btn_rush.png", timeout=3.0)
                    logger.debug("等待5秒...")
                    time.sleep(5.0)
                    self.action.click_when_appears("buttons/btn_confirm.png", timeout=3.0)
                    self.sleep(2.0)
                    self.action.tap_back_button()
                    self.sleep(2.0)

        if run(6):
            logger.info("=== Phase 6: 神恩 ===")
            if not self.action.click_when_appears("buttons/btn_divine.png", timeout=3.0):
                logger.info("[神恩] 入口模板不存在（跳过）")
            else:
                self.sleep(2.0)
                self.action.click_when_appears("buttons/btn_enter.png", timeout=3.0)
                self.sleep(2.0)
                self.action.click_when_appears("buttons/btn_quick_sacrifice.png", timeout=3.0)
                self.sleep(2.0)
                # 判重（高阈值严格匹配）
                on_sacrifice_screen = False
                try:
                    on_sacrifice_screen = self.vision.exists(
                        self.screenshot(), "buttons/btn_divine_done.png", threshold=0.85
                    )
                except (FileNotFoundError, ValueError):
                    pass
                if on_sacrifice_screen:
                    logger.info("[神恩] 检测到献祭界面，开始献祭")
                    self.action.click_when_appears("buttons/btn_start_sacrifice.png", timeout=3.0)
                    self.sleep(2.0)
                else:
                    logger.info("[神恩] 已完成")
                    self.action.click_when_appears("buttons/btn_close.png", timeout=3.0)
                    self.sleep(2.0)
                self.action.tap_back_button()
                self.sleep(2.0)

        # ── 上滑×3 → 第三页 ──
        if run(7):
            for _ in range(3):
                self._swipe_up()
                self.sleep(2.0)
            logger.info("=== Phase 7: 元素挑战 ===")
            self._do_sweep_phase("元素挑战", "元素挑战", sweep_times=2)

        if any(run(p) for p in [4, 5, 6, 7]):
            self.action.click_when_appears("buttons/btn_close.png", timeout=3.0)
            self.sleep(2.0)

        logger.info("常驻活动完成")
        return TaskResult.SUCCESS

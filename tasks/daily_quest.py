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

"""每日任务 — 主页入口，领取奖励和宝箱。

流程:
1. 确保在主页（btn_home 模板匹配，否则弹窗消除→返回→重试）
2. 点击坐标 (60, 200) 进入每日任务页面
3. 循环匹配"领取"按钮直到连续3次未命中
4. 依次点击4个固定宝箱位置，每次消除弹窗
5. 点击关闭按钮返回主页
"""

from scheduler.base_task import BaseTask, TaskResult
from loguru import logger


class DailyQuestTask(BaseTask):
    name = "daily_quest"
    priority = 2
    timeout = 60.0

    # 主页恢复最大尝试次数
    _HOME_RECOVERY_MAX = 10

    def execute(self) -> TaskResult:
        # ── 第 1 步：确保在主页 ──────────────────────
        if not self._ensure_home():
            logger.error("无法回到主页，放弃执行每日任务")
            return TaskResult.FAILED

        # ── 第 2 步：点击入口坐标进入每日任务页面 ────
        logger.info("进入每日任务页面")
        self.device.tap(60, 200)
        self.sleep(2.0)

        # ── 第 3 步：循环领取奖励 ────────────────────
        self._click_until_consecutive_miss("buttons/btn_daily_claim.png", label="奖励", threshold=0.85)

        # ── 第 4 步：依次点击四个宝箱位置 ────────────
        chest_positions = [
            (333, 205),
            (571, 205),
            (808, 205),
            (1050, 205),
        ]
        for i, (cx, cy) in enumerate(chest_positions, 1):
            logger.debug(f"宝箱 {i}/4: 点击 ({cx}, {cy})")
            self.device.tap(cx, cy)
            self.sleep(0.3)
            self.device.tap(640, 120)  # 消除弹窗
            self.sleep(0.5)
        logger.info("宝箱全部领取完成")

        # ── 第 5 步：关闭每日任务页面 ────────────────
        self.action.click_when_appears("buttons/btn_close.png", timeout=3.0)
        self.sleep(2.0)

        logger.info("每日任务完成")
        return TaskResult.SUCCESS

    # ── 连续未命中循环 ──────────────────────────────

    def _click_until_consecutive_miss(self, template: str, label: str = "", threshold: float | None = None) -> None:
        """循环匹配并点击模板，连续 3 次未命中则视为领完退出。

        每轮：截图 → 匹配 → 命中则点击 → 重置计数
                            → 未命中则计数 +1 → 满 3 次退出
        """
        miss_count = 0
        total_clicks = 0

        while miss_count < 3:
            bbox = self.vision.find(self.screenshot(), template, threshold=threshold)
            if bbox is not None:
                self.device.tap_center(bbox)
                total_clicks += 1
                miss_count = 0
                logger.debug(f"[{label}] 第 {total_clicks} 次点击")
                self.sleep(0.5)
            else:
                miss_count += 1
                logger.debug(f"[{label}] 未命中 {miss_count}/3")
                self.sleep(0.5)

        logger.info(f"[{label}] 领取完成 (共点击 {total_clicks} 次)")

    # ── 主页恢复 ────────────────────────────────────

    def _ensure_home(self) -> bool:
        """确保当前在游戏主页。

        检测 btn_home 模板；若不在主页则：
        1. 优先点 btn_close 消除弹窗
        2. 无弹窗则点左上角返回按钮
        3. 重复直到确认回到主页或达到上限

        Returns:
            True 表示已确认在主页
        """
        for i in range(self._HOME_RECOVERY_MAX):
            if self.vision.exists(self.screenshot(), "buttons/btn_home.png", threshold=0.7):
                logger.debug(f"已确认在主页 (第 {i+1} 次检测)")
                return True

            logger.debug(f"未检测到主页 (第 {i+1}/{self._HOME_RECOVERY_MAX})")

            # 优先尝试关闭弹窗
            if self.action.click_if_exists("buttons/btn_close.png", threshold=0.85):
                logger.debug("检测到弹窗，已点击关闭")
            else:
                # 无弹窗则按返回键
                logger.debug("无弹窗，点击左上角返回")
                self.action.tap_back_button()

            self.sleep(1.5)

        # 最终确认
        if self.vision.exists(self.screenshot(), "buttons/btn_home.png"):
            logger.debug("最后一轮检测：已回到主页")
            return True

        logger.error(f"尝试 {self._HOME_RECOVERY_MAX} 次后仍未回到主页")
        return False

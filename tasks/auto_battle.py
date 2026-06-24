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

"""出战任务 — 精英关卡、英雄之路、冒险。判重统一使用 btn_section_done。"""

import time
from scheduler.base_task import BaseTask, TaskResult
from loguru import logger


class AutoBattleTask(BaseTask):
    name = "auto_battle"
    priority = 25
    timeout = 900.0

    def execute(self) -> TaskResult:
        params = self.config.get("params", {})

        # 读取选项（默认全选）
        run_elite = params.get("elite", True)
        run_hero = params.get("hero_path", True)
        run_adventure = params.get("adventure", True)

        elite_count = params.get("elite_count", 1)
        hero_count = params.get("hero_count", 1)
        adventure_wait = params.get("adventure_wait", 30)

        # 1. 进入副本菜单
        if not self.action.click_when_appears("buttons/btn_quest_menu.png", timeout=5.0):
            logger.warning("找不到副本菜单入口")
            return TaskResult.FAILED
        self.sleep(2.0)

        # 2. 子任务定义: (enabled, 标签, 入口模板, 动作模板, 剩余次数)
        subs = []
        if run_elite:
            subs.append(("精英关卡", "buttons/btn_elite.png", "buttons/btn_auto_battle.png",
                         max(elite_count - 1, 0)))
        if run_hero:
            subs.append(("英雄之路", "buttons/btn_hero_path.png", "buttons/btn_hero_sweep.png",
                         max(hero_count - 1, 0)))
        if run_adventure:
            subs.append(("冒险", "buttons/btn_adventure.png", "buttons/btn_auto_battle.png", 0))

        w, h = self.device.resolution
        left_x, left_y = int(w * 0.2), int(h * 0.5)

        for label, entry_tpl, action_tpl, remaining in subs:
            logger.info(f"--- {label} ---")

            # 点击入口
            self.action.click_when_appears(entry_tpl, timeout=3.0)
            self.sleep(2.0)

            # 执行第1次动作
            self.action.click_when_appears(action_tpl, timeout=3.0)
            self.sleep(2.0)

            # 判重（通用模板）
            if self.vision.exists(self.screenshot(), "buttons/btn_section_done.png"):
                logger.info(f"[{label}] 已完成")
                self.device.tap(left_x, left_y)
                self.sleep(2.0)
                continue  # 不返回，继续下一个子任务

            # 未完成 → 执行剩余次数
            if label == "冒险":
                self._run_adventure(adventure_wait)
            else:
                for i in range(remaining):
                    logger.info(f"[{label}] 第 {i + 2}/{remaining + 1} 次")
                    self.action.click_when_appears(action_tpl, timeout=3.0)
                    time.sleep(1.0)
                    # 每次点击后判重，次数耗尽则跳出
                    if self.vision.exists(self.screenshot(), "buttons/btn_section_done.png"):
                        logger.info(f"[{label}] 次数耗尽")
                        self.device.tap(left_x, left_y)
                        self.sleep(2.0)
                        break

        # 3. 循环结束，统一返回
        self.action.tap_back_button()
        self.sleep(2.0)

        logger.info("出战任务完成")
        return TaskResult.SUCCESS

    def _run_adventure(self, wait_sec: int):
        """冒险：扫荡碎片 → 转生石等待 → 关闭确认。"""
        self.action.click_when_appears("buttons/btn_sweep_fragments.png", timeout=3.0)
        self.sleep(2.0)

        if not self.action.click_when_appears("buttons/btn_rebirth_stone.png", timeout=3.0):
            return

        logger.info(f"转生石扫荡，等待 {wait_sec}s...")
        time.sleep(wait_sec)

        # 关闭转生石页面 — 循环直到模板匹配成功（防止黑屏导致点击失效）
        while True:
            self.device.tap(1025, 145)
            self.sleep(2.0)
            if self.vision.exists(self.screenshot(), "buttons/btn_rebirth_closed.png"):
                logger.info("转生石页面已关闭")
                break
            logger.debug("转生石页面未关闭，重试点击坐标")

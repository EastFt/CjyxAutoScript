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

"""竞技场任务。

直接挑战2场，无需判重。
"""

from scheduler.base_task import BaseTask, TaskResult
from loguru import logger


class ArenaTask(BaseTask):
    name = "arena"
    priority = 20
    timeout = 120.0

    def execute(self) -> TaskResult:
        # 点竞技场
        if not self.action.click_when_appears("buttons/btn_arena.png", timeout=5.0):
            logger.warning("找不到'竞技场'入口")
            return TaskResult.FAILED
        self.sleep(2.0)

        # 打2场
        for battle in range(2):
            logger.info(f"竞技场第 {battle+1}/2 场")
            if not self.action.click_when_appears("buttons/btn_challenge.png", timeout=5.0):
                logger.warning("找不到'挑战'按钮")
                break
            self.sleep(2.0)
            self.action.click_when_appears("buttons/btn_skip.png", timeout=5.0)
            self.sleep(2.0)
            self.action.click_when_appears("buttons/btn_continue.png", timeout=5.0)
            self.sleep(2.0)

        self.action.tap_back_button()
        self.sleep(2.0)
        logger.info("竞技场完成")
        return TaskResult.SUCCESS

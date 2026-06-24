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

"""公会/联盟任务。"""

from scheduler.base_task import BaseTask, TaskResult
from loguru import logger


class GuildTask(BaseTask):
    name = "guild"
    priority = 15
    timeout = 90.0

    def execute(self) -> TaskResult:
        # 点社交
        if not self.action.click_when_appears("buttons/btn_social.png", timeout=5.0):
            logger.warning("找不到'社交'入口")
            return TaskResult.FAILED
        self.sleep(2.0)

        # 点联盟
        if not self.action.click_when_appears("buttons/btn_alliance.png", timeout=3.0):
            logger.warning("找不到'联盟'标签")
            return TaskResult.FAILED
        self.sleep(2.0)

        # ── 捐献（仅一次）───────────────────────────
        if not self.action.click_when_appears("buttons/btn_donate.png", timeout=3.0):
            logger.warning("找不到'联盟捐献'")
        else:
            self.sleep(2.0)
            self.action.click_when_appears("buttons/btn_max1.png", timeout=2.0)
            self.sleep(2.0)
            self.action.click_when_appears("buttons/btn_confirm1.png", timeout=2.0)
            self.sleep(2.0)
            self.action.click_when_appears("buttons/btn_close.png", timeout=3.0)
            self.sleep(2.0)

        # 返回
        self.device.tap(1220, 660)
        self.sleep(2.0)

        logger.info("公会任务完成")
        return TaskResult.SUCCESS

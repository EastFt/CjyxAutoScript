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

"""好友互动任务。"""

from scheduler.base_task import BaseTask, TaskResult
from loguru import logger


class FriendsTask(BaseTask):
    name = "friends"
    priority = 5
    timeout = 20.0

    def execute(self) -> TaskResult:
        # 点社交
        if not self.action.click_when_appears("buttons/btn_social.png", timeout=5.0):
            logger.warning("找不到'社交'入口")
            return TaskResult.FAILED
        self.sleep(2.0)

        # 点好友
        if not self.action.click_when_appears("buttons/btn_friends_tab.png", timeout=3.0):
            logger.warning("找不到'好友'标签")
            return TaskResult.FAILED
        self.sleep(2.0)

        # 点赠送
        sent = self.action.click_when_appears("buttons/btn_send.png", timeout=3.0)
        if sent:
            logger.info("已赠送友情点")
        else:
            logger.info("无可赠送或已赠送")
        self.sleep(2.0)

        # 点关闭
        self.action.click_when_appears("buttons/btn_close.png", timeout=3.0)
        self.sleep(2.0)

        logger.info("好友互动完成")
        return TaskResult.SUCCESS

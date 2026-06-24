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

"""领取邮件任务。

流程:
1. 社交 → 信息 → 一键领取
2. 点击屏幕左侧消除弹窗
3. 模板检测 btn_mail_remaining.png → 还有邮件则继续领取
4. 全部领取完毕 → 左上角返回
"""

from scheduler.base_task import BaseTask, TaskResult
from loguru import logger


class CollectMailTask(BaseTask):
    name = "collect_mail"
    priority = 3
    timeout = 20.0

    def execute(self) -> TaskResult:
        # 点社交
        if not self.action.click_when_appears("buttons/btn_social.png", timeout=5.0):
            logger.warning("找不到'社交'入口")
            return TaskResult.FAILED
        self.sleep(2.0)

        # 点信息
        if not self.action.click_when_appears("buttons/btn_messages.png", timeout=3.0):
            logger.warning("找不到'信息'标签")
            return TaskResult.FAILED
        self.sleep(2.0)

        # 循环领取：领取 → 消弹窗 → 判重 → 继续/结束
        w, h = self.device.resolution
        left_x, left_y = int(w * 0.2), int(h * 0.5)

        while True:
            self.action.click_when_appears("buttons/btn_claim_all.png", timeout=3.0)
            self.sleep(2.0)

            # 点击屏幕左侧消除弹窗
            self.device.tap(left_x, left_y)
            self.sleep(2.0)

            # 检测是否还有剩余邮件
            if self.vision.exists(self.screenshot(), "buttons/btn_mail_remaining.png"):
                logger.info("还有剩余邮件，继续领取")
            else:
                logger.info("邮件已全部领取")
                break

        # 左上角返回
        self.action.tap_back_button()
        self.sleep(2.0)

        logger.info("邮件领取完成")
        return TaskResult.SUCCESS

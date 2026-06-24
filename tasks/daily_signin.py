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

"""每日签到任务。

流程:
1. 点福利 → 点签到页面
2. 模板检测 btn_signin_done.png → 已签到则跳过
3. 进入VIP礼包中心 → 模板检测 btn_claim_done.png → 已领则跳过
4. 点关闭
"""

from scheduler.base_task import BaseTask, TaskResult
from loguru import logger


class DailySignInTask(BaseTask):
    name = "daily_signin"
    priority = 1
    timeout = 30.0

    def execute(self) -> TaskResult:
        # 步骤1: 点福利
        if not self.action.click_when_appears("buttons/btn_welfare.png", timeout=5.0):
            logger.warning("找不到'福利'入口")
            return TaskResult.FAILED
        self.sleep(2.0)

        # 步骤2: 点签到页面
        if not self.action.click_when_appears("buttons/btn_signin_tab.png", timeout=3.0):
            logger.warning("找不到'签到页面'")
            return TaskResult.FAILED
        self.sleep(2.0)

        # 步骤3: 检测签到按钮是否存在，存在则点击，不存在=已完成
        if self.vision.exists(self.screenshot(), "buttons/btn_signin.png", threshold=0.8):
            self.action.click_when_appears("buttons/btn_signin.png", timeout=3.0)
            self.sleep(2.0)
        else:
            logger.info("模板匹配：签到已完成，跳过签到按钮")

        # 步骤4: 进入VIP礼包中心
        if not self.action.click_when_appears("buttons/btn_vip_gift.png", timeout=3.0):
            logger.debug("无VIP专属礼包入口")
            self.action.click_when_appears("buttons/btn_close.png", timeout=3.0)
            self.sleep(2.0)
            logger.info("每日签到完成（无VIP礼包）")
            return TaskResult.SUCCESS

        self.sleep(2.0)

        # 步骤5: 在VIP页面判定是否已领奖
        claim_done = False
        try:
            if self.vision.exists(self.screenshot(), "buttons/btn_claim_done.png"):
                logger.info("模板匹配：VIP已领奖，跳过领取")
                claim_done = True
        except (FileNotFoundError, ValueError):
            pass

        if not claim_done:
            self.action.click_when_appears("buttons/btn_claim.png", timeout=3.0)
            self.sleep(2.0)

        # 步骤6: 点关闭
        self.action.click_when_appears("buttons/btn_close.png", timeout=3.0)
        self.sleep(2.0)

        logger.info("每日签到完成")
        return TaskResult.SUCCESS

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

"""夺宝奇兵 — 限时活动任务。

流程:
1. 确保在主页（btn_home 模板匹配）
2. 点击"夺宝奇兵"入口 → 验证刷新按钮确认进入成功
3. 循环 N 次（默认10，可选1-50）：
   - 点击刷新
   - 匹配"夺宝钻石"：
      命中 → 进入购买内循环：
        3c-Ⅰ. 点击最近"立即夺宝"（延迟 0.1s，加载极短）
        3c-Ⅱ. 点击"购买十次"
        3c-Ⅲ. 检测 btn_section_done：
               匹配到 → 购买失败，点 (641,146) 消弹窗，终止内循环
               未匹配 → 购买成功，计数 +1
        3c-Ⅳ. 再次匹配"夺宝钻石"：
               命中 → 回到 3c-Ⅰ 继续买
               未命中 → 终止内循环
      未命中 → 等30秒→继续下一轮
4. 点击关闭返回主页
"""

from scheduler.base_task import BaseTask, TaskResult
from loguru import logger


class TreasureHuntTask(BaseTask):
    name = "treasure_hunt"
    priority = 12
    timeout = 900.0

    _HOME_RECOVERY_MAX = 10
    _ENTRY_RETRY_MAX = 5
    _ROI = (0, 0, 1140, 650)  # 活动页面匹配区域

    def execute(self) -> TaskResult:
        # ── 第 1 步：确保在主页 ──────────────────────
        if not self._ensure_home():
            logger.error("无法回到主页，放弃执行夺宝奇兵")
            return TaskResult.FAILED

        # ── 第 2 步：进入夺宝奇兵 ────────────────────
        if not self._enter_treasure_hunt():
            logger.error("无法进入夺宝奇兵")
            return TaskResult.FAILED

        # ── 第 3 步：主循环（成功购买 N 次才退出）──────
        buy_count = self.config.get("params", {}).get("buy_count", 10)
        logger.info(f"夺宝奇兵 目标购买 {buy_count} 次")

        success = 0
        while success < buy_count:
            logger.info(f"=== 夺宝奇兵 已完成 {success}/{buy_count}，继续尝试 ===")

            # 3a. 点击刷新
            if not self.action.click_when_appears("buttons/btn_refresh.png", timeout=5.0, threshold=0.75, roi=self._ROI):
                logger.warning("找不到刷新按钮，尝试重新进入活动")
                if not self._enter_treasure_hunt():
                    return TaskResult.FAILED
                # 重新进入后再试一次刷新
                if not self.action.click_when_appears("buttons/btn_refresh.png", timeout=5.0, threshold=0.75, roi=self._ROI):
                    logger.error("重新进入后仍找不到刷新按钮")
                    return TaskResult.FAILED
            self.sleep(2.0)

            # 3b. 匹配夺宝钻石
            diamond_bbox = self.vision.find(self.screenshot(), "buttons/btn_treasure_diamond.png", threshold=0.75, roi=self._ROI)
            if diamond_bbox is None:
                logger.info("未找到钻石，等待 30 秒后重新刷新...")
                self.sleep(30.0)
                continue

            # ══════ 3c. 钻石匹配成功 → 进入购买内循环 ══════
            while True:
                # 3c-Ⅰ. 点击最近的"立即夺宝"（延迟 0.1s，加载极短）
                now_bboxes = self.vision.find_all(self.screenshot(), "buttons/btn_treasure_now.png", threshold=0.75, roi=self._ROI)
                if not now_bboxes:
                    logger.warning("找不到'立即夺宝'按钮，退出购买内循环")
                    break

                nearest = self._find_nearest(diamond_bbox, now_bboxes)
                self.device.tap_center(nearest)
                self.sleep(0.1)

                # 3c-Ⅱ. 点击"购买十次"
                if not self.action.click_when_appears("buttons/btn_buy_ten.png", timeout=5.0, threshold=0.9, roi=self._ROI):
                    logger.warning("找不到'购买十次'按钮，退出购买内循环")
                    break

                # 3c-Ⅲ. 检测 btn_section_done（仅匹配 1 次）
                if self.vision.exists(self.screenshot(), "buttons/btn_section_done.png", threshold=0.75, roi=self._ROI):
                    # 购买失败（已买完/条件不满足）
                    logger.info("检测到 section_done，购买失败，消除弹窗")
                    self.device.tap(641, 146)
                    self.sleep(0.3)
                    break

                # 未匹配 → 购买成功
                success += 1
                logger.info(f"购买成功！({success}/{buy_count})")

                if success >= buy_count:
                    break

                # 3c-Ⅳ. 再次匹配夺宝钻石（继续买下一个）
                diamond_bbox = self.vision.find(self.screenshot(), "buttons/btn_treasure_diamond.png", threshold=0.75, roi=self._ROI)
                if diamond_bbox is None:
                    logger.info("本轮钻石已买完")
                    break
                # 找到了 → 回到 3c-Ⅰ 继续买

            # ── 内循环结束，等待 30 秒后下一轮刷新 ──
            if success < buy_count:
                logger.info("等待 30 秒后刷新下一轮...")
                self.sleep(30.0)

        # ── 第 4 步：关闭返回主页 ────────────────────
        self.action.click_when_appears("buttons/btn_close.png", timeout=5.0)
        self.sleep(2.0)

        logger.info("夺宝奇兵完成")
        return TaskResult.SUCCESS

    # ── 进入活动 ────────────────────────────────────

    def _enter_treasure_hunt(self) -> bool:
        """点击夺宝奇兵入口并验证进入成功（刷新按钮存在）。

        Returns:
            True 表示已成功进入活动页面
        """
        for i in range(self._ENTRY_RETRY_MAX):
            logger.info(f"尝试进入夺宝奇兵 (第 {i+1}/{self._ENTRY_RETRY_MAX})")

            # 点击入口
            if not self.action.click_when_appears("buttons/btn_treasure_hunt.png", timeout=5.0, threshold=0.75):
                logger.warning("找不到'夺宝奇兵'入口，尝试回到主页再试")
                if not self._ensure_home():
                    return False
                continue

            self.sleep(2.0)

            # 验证进入成功
            if self.vision.exists(self.screenshot(), "buttons/btn_refresh.png", threshold=0.75, roi=self._ROI):
                logger.info("成功进入夺宝奇兵")
                return True

            logger.warning("未检测到刷新按钮，返回主页重试")
            self.action.tap_back_button()
            self.sleep(1.0)
            if not self._ensure_home():
                return False

        logger.error(f"尝试 {self._ENTRY_RETRY_MAX} 次后仍无法进入夺宝奇兵")
        return False

    # ── 主页恢复 ────────────────────────────────────

    def _ensure_home(self) -> bool:
        """确保当前在游戏主页。

        检测 btn_home 模板；若不在主页则：
        1. 优先点 btn_close 消除弹窗
        2. 无弹窗则点左上角返回按钮
        3. 重复直到确认回到主页或达到上限
        """
        for i in range(self._HOME_RECOVERY_MAX):
            if self.vision.exists(self.screenshot(), "buttons/btn_home.png", threshold=0.7):
                logger.debug(f"已确认在主页 (第 {i+1} 次检测)")
                return True

            logger.debug(f"未检测到主页 (第 {i+1}/{self._HOME_RECOVERY_MAX})")

            if self.action.click_if_exists("buttons/btn_close.png", threshold=0.85):
                logger.debug("检测到弹窗，已点击关闭")
            else:
                logger.debug("无弹窗，点击左上角返回")
                self.action.tap_back_button()

            self.sleep(1.5)

        # 最终确认
        if self.vision.exists(self.screenshot(), "buttons/btn_home.png"):
            logger.debug("最后一轮检测：已回到主页")
            return True

        logger.error(f"尝试 {self._HOME_RECOVERY_MAX} 次后仍未回到主页")
        return False

    # ── 距离计算 ────────────────────────────────────

    @staticmethod
    def _find_nearest(target_bbox, candidate_bboxes):
        """从候选框中找到距离目标框中心最近的一个。

        Args:
            target_bbox: (left, top, right, bottom)
            candidate_bboxes: list of (left, top, right, bottom)

        Returns:
            最近的候选框
        """
        tx = (target_bbox[0] + target_bbox[2]) / 2
        ty = (target_bbox[1] + target_bbox[3]) / 2

        best = None
        best_dist = float("inf")
        for bbox in candidate_bboxes:
            cx = (bbox[0] + bbox[2]) / 2
            cy = (bbox[1] + bbox[3]) / 2
            dist = (cx - tx) ** 2 + (cy - ty) ** 2
            if dist < best_dist:
                best_dist = dist
                best = bbox
        return best

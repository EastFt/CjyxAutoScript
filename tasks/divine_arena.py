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

"""神域竞技场任务 — 三大星域战场循环挑战。"""

from scheduler.base_task import BaseTask, TaskResult
from loguru import logger


class DivineArenaTask(BaseTask):
    name = "divine_arena"
    priority = 30
    timeout = 1800.0

    # 三个星域战场: (名称, 入口坐标, 配置key前缀)
    BATTLEFIELDS = [
        ("皮尔米特", (300, 650), "pirmin"),
        ("乌尔伦",   (650, 650), "wulun"),
        ("哈托莫",   (960, 650), "hatomo"),
    ]

    # 未来任务2：神域十二宫
    # 未来任务3：神域争霸赛
    # 未来任务4：星际拓荒

    # ── 主入口 ──────────────────────────────────────

    def execute(self) -> TaskResult:
        params = self.config.get("params", {})

        # 1. 进入神域主页
        self.device.tap(658, 61)
        self.sleep(2.0)

        # 2. 进入星域竞技场
        self.device.tap(550, 200)
        self.sleep(2.0)

        # 3. 依次处理三个战场（各自独立配置）
        for name, (bx, by), key in self.BATTLEFIELDS:
            enabled = params.get(f"{key}_enabled", True)
            rounds = params.get(f"{key}_rounds", 10)
            if enabled:
                self._process_battlefield(name, bx, by, rounds)

        # 4. 返回神域主页 → 返回游戏主界面
        self.action.tap_back_button()
        self.sleep(2.0)
        self.action.tap_back_button()
        self.sleep(2.0)

        logger.info("神域竞技场任务完成")
        return TaskResult.SUCCESS

    # ── 战场循环 ────────────────────────────────────

    def _process_battlefield(self, name: str, entry_x: int, entry_y: int, rounds: int):
        """执行单个星域战场的 N 轮匹配循环。

        Args:
            name: 星域名称（日志用）
            entry_x, entry_y: 战场入口坐标
            rounds: 循环次数
        """
        # 进入战场
        self.device.tap(entry_x, entry_y)
        self.sleep(2.0)

        for i in range(rounds):
            # 开始匹配
            self.device.tap(1170, 660)
            self.sleep(6.0)

            # 识别 skip（最多尝试 3 次）
            for attempt in range(3):
                bbox = self.vision.find(
                    self.screenshot(), "buttons/btn_skip.png", threshold=0.75
                )
                if bbox is not None:
                    self.device.tap_center(bbox)
                    self.sleep(1.0)
                    self.device.tap(640, 360)  # 消除结算弹窗
                    self.sleep(1.0)
                    break
                else:
                    if attempt < 2:
                        self.sleep(2.0)
            else:
                # 3 次均未找到 skip
                self.device.tap(1200, 650)
                self.sleep(0.5)
                self.device.tap(1200, 650)
                self.sleep(1.0)

            logger.info(f"{name} 第 {i+1} 轮完成")

        # 返回星域竞技场主页
        self.action.tap_back_button()
        self.sleep(2.0)

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

"""OCR 文字识别模块。

封装 EasyOCR 用于识别游戏界面中的文字信息，
如体力值、金币数量、任务描述等。

支持按 ROI 区域限定搜索范围以提升精度和速度。
"""

from __future__ import annotations

import re

import numpy as np
from loguru import logger


class OCREngine:
    """文字识别封装。

    默认使用 EasyOCR，支持中英文混合识别。
    采用懒加载策略，首次调用时才初始化模型（模型较大，约 100-300MB）。

    Usage:
        ocr = OCREngine(languages=["ch_sim", "en"])
        results = ocr.recognize(screenshot, roi=(100, 200, 400, 80))
        number = ocr.read_number(screenshot, roi=(100, 200, 400, 80))
    """

    def __init__(
        self,
        languages: list[str] | None = None,
        gpu: bool = True,
    ):
        """
        Args:
            languages: 识别语言列表。默认 ["ch_sim", "en"]
            gpu: 是否使用 GPU 加速
        """
        self._languages = languages or ["ch_sim", "en"]
        self._gpu = gpu
        self._reader = None
        logger.debug(f"OCREngine 已创建 (语言={self._languages}, GPU={gpu})")

    @property
    def is_ready(self) -> bool:
        """OCR 模型是否已加载。"""
        return self._reader is not None

    def _ensure_reader(self) -> None:
        """懒加载 OCR 模型。"""
        if self._reader is not None:
            return

        logger.info(f"正在加载 OCR 模型 (语言: {self._languages})...")
        try:
            import easyocr
            self._reader = easyocr.Reader(
                self._languages,
                gpu=self._gpu,
            )
            logger.info("OCR 模型加载完成")
        except ImportError:
            logger.error("EasyOCR 未安装。请运行: pip install easyocr")
            raise
        except Exception as e:
            logger.error(f"OCR 模型加载失败: {e}")
            raise

    # ── 文字识别 ──────────────────────────────────────

    def recognize(
        self,
        screenshot: np.ndarray,
        roi: tuple | None = None,
    ) -> list[dict]:
        """识别截图中的文字。

        Args:
            screenshot: BGR 格式截图 (numpy array)
            roi: 搜索区域 (left, top, right, bottom)，None 表示全图

        Returns:
            识别结果列表，按阅读顺序排列:
            [{
                "text": str,          # 识别文字
                "bbox": (l,t,r,b),    # 边界框（全图坐标）
                "confidence": float,  # 置信度 0~1
            }, ...]
        """
        self._ensure_reader()

        # ROI 裁剪
        image = screenshot
        offset_x, offset_y = 0, 0
        if roi is not None:
            l, t, r, b = roi
            image = screenshot[t:b, l:r]
            offset_x, offset_y = l, t

        try:
            raw_results = self._reader.readtext(image)
        except Exception as e:
            logger.error(f"OCR 识别异常: {e}")
            return []

        # 格式化结果，将坐标转换回全图坐标
        results = []
        for bbox, text, confidence in raw_results:
            # bbox: [[x1,y1], [x2,y2], [x3,y3], [x4,y4]] (四点)
            xs = [p[0] for p in bbox]
            ys = [p[1] for p in bbox]

            l = int(min(xs)) + offset_x
            t = int(min(ys)) + offset_y
            r = int(max(xs)) + offset_x
            b = int(max(ys)) + offset_y

            results.append({
                "text": text.strip(),
                "bbox": (l, t, r, b),
                "confidence": float(confidence),
            })

        logger.debug(f"OCR 识别到 {len(results)} 个文字区域")
        return results

    # ── 文字查找 ──────────────────────────────────────

    def find_text(
        self,
        screenshot: np.ndarray,
        target: str,
        roi: tuple | None = None,
        exact: bool = False,
    ) -> tuple[int, int, int, int] | None:
        """查找包含指定文字的区域。

        Args:
            screenshot: 截图
            target: 要查找的文字
            roi: 搜索区域
            exact: True 表示精确匹配，False 表示包含即可

        Returns:
            第一个匹配区域的 bbox (left, top, right, bottom)，未找到返回 None
        """
        results = self.recognize(screenshot, roi)

        target_lower = target.lower()
        for r in results:
            text_lower = r["text"].lower()
            if exact and text_lower == target_lower:
                logger.debug(f"精确匹配文字: '{target}' @ {r['bbox']}")
                return r["bbox"]
            if not exact and target_lower in text_lower:
                logger.debug(f"包含匹配文字: '{r['text']}' 包含 '{target}' @ {r['bbox']}")
                return r["bbox"]

        logger.debug(f"未找到文字: '{target}'")
        return None

    def find_all_text(
        self,
        screenshot: np.ndarray,
        target: str,
        roi: tuple | None = None,
    ) -> list[tuple[int, int, int, int]]:
        """查找所有包含指定文字的区域。

        Returns:
            匹配区域的 bbox 列表
        """
        results = self.recognize(screenshot, roi)
        target_lower = target.lower()

        matches = [
            r["bbox"]
            for r in results
            if target_lower in r["text"].lower()
        ]
        logger.debug(f"找到 {len(matches)} 处 '{target}'")
        return matches

    # ── 数字读取 ──────────────────────────────────────

    def read_number(
        self,
        screenshot: np.ndarray,
        roi: tuple,
    ) -> int | None:
        """读取 ROI 区域内的数字。

        适用于读取体力值、金币数、等级等纯数字显示。

        Args:
            screenshot: 截图
            roi: 数字所在区域 (left, top, right, bottom)

        Returns:
            解析后的整数，识别失败返回 None
        """
        results = self.recognize(screenshot, roi)

        for r in results:
            # 提取数字（支持逗号分隔和负号）
            nums = re.findall(r"-?\d[\d,]*", r["text"])
            if nums:
                # 取第一个数字，去除逗号
                value_str = nums[0].replace(",", "")
                try:
                    value = int(value_str)
                    logger.debug(f"读取数字: {value} (原始文字: '{r['text']}')")
                    return value
                except ValueError:
                    continue

        logger.debug(f"ROI 内未找到数字: {roi}")
        return None

    def read_text(
        self,
        screenshot: np.ndarray,
        roi: tuple,
    ) -> str | None:
        """读取 ROI 区域内的第一段文字。

        Args:
            screenshot: 截图
            roi: 文字区域

        Returns:
            识别到的文字，未找到返回 None
        """
        results = self.recognize(screenshot, roi)
        if results:
            text = results[0]["text"]
            logger.debug(f"读取文字: '{text}'")
            return text
        return None

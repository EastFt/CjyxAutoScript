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

"""图像识别引擎。

提供模板匹配和特征匹配两种识别方式，
支持 ROI 限定搜索区域、多帧确认、轮询等待等功能。
"""

from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np
from loguru import logger


def _ensure_grayscale(img: np.ndarray) -> np.ndarray:
    """确保图像为灰度格式。"""
    if img.ndim == 3:
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return img


class VisionEngine:
    """图像识别引擎。

    双层架构：
    1. 模板匹配 (TM_CCOEFF_NORMED) — 主力，快速且对光照鲁棒
    2. SIFT 特征匹配 — 兜底，抗缩放/旋转/部分遮挡

    Usage:
        vision = VisionEngine(assets_dir="./assets")
        bbox = vision.find(screenshot, "buttons/btn_battle.png")
        if bbox:
            device.tap_center(bbox)
    """

    def __init__(
        self,
        assets_dir: str = "./assets",
        threshold: float = 0.75,
    ):
        self._assets_dir = Path(assets_dir)
        self._threshold = threshold
        logger.debug(f"VisionEngine 阈值={threshold}")
        # 模板缓存: path -> (template_gray, template_w, template_h)
        self._template_cache: dict[str, np.ndarray] = {}

        # 初始化 SIFT 检测器
        try:
            self._sift = cv2.SIFT_create()
            # FLANN 匹配器参数
            index_params = dict(algorithm=1, trees=5)  # KD-tree
            search_params = dict(checks=50)
            self._flann = cv2.FlannBasedMatcher(index_params, search_params)
            self._sift_available = True
        except Exception:
            logger.warning("SIFT 不可用，特征匹配功能将被禁用")
            self._sift_available = False

    # ── 模板加载与缓存 ────────────────────────────────

    def _resolve_path(self, template_path: str) -> Path:
        """解析模板路径。

        支持:
        - 相对路径: "buttons/btn_battle.png" → assets/buttons/btn_battle.png
        - 绝对路径: 直接使用
        """
        p = Path(template_path)
        if p.is_absolute():
            return p
        return self._assets_dir / template_path

    def _load_template(self, template_path: str) -> np.ndarray:
        """加载模板图像（带缓存）。"""
        if template_path in self._template_cache:
            return self._template_cache[template_path]

        full_path = self._resolve_path(template_path)
        if not full_path.exists():
            raise FileNotFoundError(f"模板文件不存在: {full_path}")

        template = cv2.imread(str(full_path), cv2.IMREAD_COLOR)
        if template is None:
            raise ValueError(f"无法读取模板图像: {full_path}")

        template_gray = _ensure_grayscale(template)
        self._template_cache[template_path] = template_gray
        logger.debug(f"模板已加载: {template_path} ({template_gray.shape[1]}x{template_gray.shape[0]})")
        return template_gray

    def clear_cache(self) -> None:
        """清空模板缓存。"""
        self._template_cache.clear()

    # ── 模板匹配 ──────────────────────────────────────

    def find(
        self,
        screenshot: np.ndarray,
        template_path: str,
        roi: tuple[int, int, int, int] | None = None,
        threshold: float | None = None,
    ) -> tuple[int, int, int, int] | None:
        """在截图中查找模板（多尺度），返回 (left, top, right, bottom) 或 None。

        自动在多个缩放尺度上尝试匹配，适配模板与截图分辨率不一致的情况。
        尺度范围: 0.5x ~ 1.5x，共 11 级。

        Args:
            screenshot: 截图 (BGR 或灰度)
            template_path: 模板路径
            roi: 搜索区域 (left, top, right, bottom)，None 表示全图搜索
            threshold: 匹配置信度阈值，None 使用默认值

        Returns:
            匹配区域的 bbox，未找到返回 None
        """
        thresh = threshold if threshold is not None else self._threshold
        template = self._load_template(template_path)
        screen_gray = _ensure_grayscale(screenshot)

        # ROI 裁剪
        offset_x = 0
        offset_y = 0
        if roi is not None:
            l, t, r, b = roi
            screen_gray = screen_gray[t:b, l:r]
            offset_x, offset_y = l, t

        s_h, s_w = screen_gray.shape[:2]
        t_h, t_w = template.shape[:2]

        # 多尺度匹配
        scales = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5]
        best_val = -1.0
        best_loc = None
        best_scale = 1.0
        best_size = (t_w, t_h)

        for scale in scales:
            new_w = int(t_w * scale)
            new_h = int(t_h * scale)

            # 跳过太大或太小的模板
            if new_w < 5 or new_h < 5:
                continue
            if new_w > s_w or new_h > s_h:
                continue

            scaled_template = cv2.resize(template, (new_w, new_h))
            result = cv2.matchTemplate(
                screen_gray, scaled_template, cv2.TM_CCOEFF_NORMED
            )
            _, max_val, _, max_loc = cv2.minMaxLoc(result)

            if max_val > best_val:
                best_val = max_val
                best_loc = max_loc
                best_scale = scale
                best_size = (new_w, new_h)

        if best_val >= thresh and best_loc is not None:
            left = best_loc[0] + offset_x
            top = best_loc[1] + offset_y
            right = left + best_size[0]
            bottom = top + best_size[1]
            logger.debug(
                f"模板匹配成功: {template_path} "
                f"@ ({left},{top})-({right},{bottom}) "
                f"尺度={best_scale:.1f}x 置信度={best_val:.3f}"
            )
            return (left, top, right, bottom)

        logger.warning(
            f"模板未匹配: {template_path} "
            f"(最佳置信度={best_val:.3f}@尺度{best_scale:.1f}x, 阈值={thresh})"
        )
        return None

    def find_all(
        self,
        screenshot: np.ndarray,
        template_path: str,
        roi: tuple[int, int, int, int] | None = None,
        threshold: float | None = None,
    ) -> list[tuple[int, int, int, int]]:
        """查找截图中所有匹配的模板位置。

        Returns:
            匹配区域列表，按置信度从高到低排序
        """
        thresh = threshold if threshold is not None else self._threshold
        template = self._load_template(template_path)
        screen_gray = _ensure_grayscale(screenshot)

        if roi is not None:
            l, t, r, b = roi
            screen_gray = screen_gray[t:b, l:r]

        t_h, t_w = template.shape[:2]
        s_h, s_w = screen_gray.shape[:2]
        if t_h > s_h or t_w > s_w:
            return []

        result = cv2.matchTemplate(screen_gray, template, cv2.TM_CCOEFF_NORMED)

        # 找到所有超过阈值的位置
        locations = np.where(result >= thresh)
        offset_x = roi[0] if roi else 0
        offset_y = roi[1] if roi else 0

        # 按置信度排序并去重（NMS）
        matches = []
        for pt in zip(*locations[::-1]):  # (x, y)
            confidence = result[pt[1], pt[0]]
            left = pt[0] + offset_x
            top = pt[1] + offset_y
            matches.append(((left, top, left + t_w, top + t_h), confidence))

        # 按置信度降序排列
        matches.sort(key=lambda x: x[1], reverse=True)

        # 简单 NMS：过滤重叠的匹配
        filtered = []
        for bbox, conf in matches:
            if not any(_iou(bbox, fb) > 0.5 for fb in filtered):
                filtered.append(bbox)

        logger.debug(f"找到 {len(filtered)} 个 '{template_path}' 匹配")
        return filtered

    def exists(
        self,
        screenshot: np.ndarray,
        template_path: str,
        roi: tuple[int, int, int, int] | None = None,
        threshold: float | None = None,
    ) -> bool:
        """检查模板是否存在于截图中。"""
        return self.find(screenshot, template_path, roi, threshold) is not None

    # ── 轮询等待 ──────────────────────────────────────

    def wait_until(
        self,
        fetch_screenshot,
        template_path: str,
        timeout: float = 10.0,
        interval: float = 0.5,
        roi: tuple[int, int, int, int] | None = None,
        threshold: float | None = None,
    ) -> tuple[int, int, int, int] | None:
        """轮询等待直到元素出现。

        Args:
            fetch_screenshot: 截图获取函数 callable() -> np.ndarray
            template_path: 模板路径
            timeout: 超时秒数
            interval: 轮询间隔秒数
            roi: 搜索区域
            threshold: 置信度阈值

        Returns:
            元素的 bbox，超时返回 None
        """
        logger.debug(f"等待元素出现: {template_path} (timeout={timeout}s)")
        start = time.time()

        while time.time() - start < timeout:
            screen = fetch_screenshot()
            bbox = self.find(screen, template_path, roi, threshold)
            if bbox is not None:
                elapsed = time.time() - start
                logger.debug(f"元素已出现: {template_path} ({elapsed:.2f}s)")
                return bbox
            time.sleep(interval)

        logger.warning(f"等待元素超时: {template_path} ({timeout}s)")
        return None

    def wait_until_gone(
        self,
        fetch_screenshot,
        template_path: str,
        timeout: float = 10.0,
        interval: float = 0.5,
        roi: tuple[int, int, int, int] | None = None,
        threshold: float | None = None,
    ) -> bool:
        """轮询等待直到元素消失。

        Returns:
            True 表示元素已消失，False 表示超时
        """
        logger.debug(f"等待元素消失: {template_path} (timeout={timeout}s)")
        start = time.time()

        while time.time() - start < timeout:
            screen = fetch_screenshot()
            if not self.exists(screen, template_path, roi, threshold):
                elapsed = time.time() - start
                logger.debug(f"元素已消失: {template_path} ({elapsed:.2f}s)")
                return True
            time.sleep(interval)

        logger.warning(f"等待元素消失超时: {template_path} ({timeout}s)")
        return False

    # ── 特征匹配兜底 ──────────────────────────────────

    def find_feature(
        self,
        screenshot: np.ndarray,
        template_path: str,
        min_matches: int = 15,
    ) -> tuple[int, int, int, int] | None:
        """使用 SIFT 特征匹配查找模板（抗缩放/旋转/遮挡）。

        Args:
            screenshot: 截图
            template_path: 模板路径
            min_matches: 最少匹配点数

        Returns:
            bbox 或 None
        """
        if not self._sift_available:
            logger.warning("SIFT 不可用，跳过特征匹配")
            return None

        template = self._load_template(template_path)
        screen_gray = _ensure_grayscale(screenshot)

        # 检测关键点和描述符
        kp1, des1 = self._sift.detectAndCompute(template, None)
        kp2, des2 = self._sift.detectAndCompute(screen_gray, None)

        if des1 is None or des2 is None or len(des1) < 2 or len(des2) < 2:
            return None

        # FLANN 匹配
        matches = self._flann.knnMatch(des1, des2, k=2)

        # Lowe's ratio test
        good = []
        for match_pair in matches:
            if len(match_pair) == 2:
                m, n = match_pair
                if m.distance < 0.7 * n.distance:
                    good.append(m)

        if len(good) < min_matches:
            logger.debug(
                f"特征匹配不足: {template_path} ({len(good)}/{min_matches})"
            )
            return None

        # 计算单应性矩阵
        src_pts = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)

        M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
        if M is None:
            return None

        # 变换模板边界得到目标区域
        h, w = template.shape[:2]
        corners = np.float32([[0, 0], [0, h - 1], [w - 1, h - 1], [w - 1, 0]]).reshape(-1, 1, 2)
        transformed = cv2.perspectiveTransform(corners, M)

        x_min = int(min(transformed[:, 0, 0]))
        y_min = int(min(transformed[:, 0, 1]))
        x_max = int(max(transformed[:, 0, 0]))
        y_max = int(max(transformed[:, 0, 1]))

        inliers = mask.sum() if mask is not None else 0
        logger.debug(
            f"特征匹配成功: {template_path} ({len(good)} 匹配, {inliers} inliers)"
        )
        return (x_min, y_min, x_max, y_max)

    def __repr__(self) -> str:
        return f"VisionEngine(assets={self._assets_dir}, threshold={self._threshold})"


def _iou(box1: tuple, box2: tuple) -> float:
    """计算两个 bbox 的 IoU。"""
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])

    if x2 <= x1 or y2 <= y1:
        return 0.0

    intersection = (x2 - x1) * (y2 - y1)
    area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])

    return intersection / (area1 + area2 - intersection)

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

"""日志系统 — 基于 loguru 的结构化日志。

提供控制台彩色输出 + 按日期轮转的文件日志。
"""

import sys
from pathlib import Path

from loguru import logger


def setup_logger(
    log_dir: str = "./logs",
    level: str = "INFO",
    rotation: str = "10 MB",
    retention: str = "7 days",
) -> None:
    """初始化日志系统。

    Args:
        log_dir: 日志文件目录
        level: 日志级别 (DEBUG/INFO/WARNING/ERROR/CRITICAL)
        rotation: 日志轮转大小或时间
        retention: 日志保留时长
    """
    # 移除默认 handler
    logger.remove()

    # 控制台输出（彩色）
    logger.add(
        sys.stdout,
        level=level,
        colorize=True,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
    )

    # 确保日志目录存在
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # 文件输出（按日期轮转）
    logger.add(
        log_path / "bot_{time:YYYY-MM-DD}.log",
        level="DEBUG",
        rotation=rotation,
        retention=retention,
        encoding="utf-8",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
            "{name}:{function}:{line} | {message}"
        ),
    )

    # 错误日志单独文件
    logger.add(
        log_path / "error_{time:YYYY-MM-DD}.log",
        level="ERROR",
        rotation=rotation,
        retention=retention,
        encoding="utf-8",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
            "{name}:{function}:{line} | {message}\n{exception}"
        ),
    )

    logger.info(f"日志系统已初始化，级别={level}，目录={log_dir}")


__all__ = ["logger", "setup_logger"]

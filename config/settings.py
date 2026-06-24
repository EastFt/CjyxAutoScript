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

"""Pydantic v2 配置模型。

定义 ADB 连接参数、任务配置和应用全局设置的结构，
支持从 YAML 文件加载并自动校验类型。
"""

from __future__ import annotations

from typing import Any
from enum import Enum

from pydantic import BaseModel, Field


class ScreenshotMethod(str, Enum):
    """截图方式。"""
    RAW = "raw"   # exec-out screencap (BGRA raw)，速度快
    PNG = "png"   # screencap -p (PNG)，兼容性好


class ADBConfig(BaseModel):
    """ADB 连接配置。"""
    device_addr: str = Field(
        default="auto",
        description="设备地址。'auto' 表示自动检测，也可手动指定如 '127.0.0.1:16384'"
    )
    adb_path: str = Field(
        default="auto",
        description="ADB 可执行文件路径。'auto' 表示自动查找"
    )
    screenshot_method: ScreenshotMethod = Field(
        default=ScreenshotMethod.RAW,
        description="截图方式: raw(快3倍) 或 png(兼容性好)"
    )
    connect_timeout: float = Field(
        default=10.0,
        description="ADB 连接超时（秒）"
    )


class TaskConfig(BaseModel):
    """单个任务的配置。"""
    name: str = Field(description="任务名称，对应 tasks/ 下的模块名")
    enabled: bool = Field(default=True, description="是否启用此任务")
    priority: int = Field(default=0, description="优先级，数值越小越先执行")
    retry_count: int = Field(default=3, description="失败重试次数")
    retry_delay: float = Field(default=2.0, description="重试间隔（秒）")
    timeout: float = Field(default=120.0, description="单任务最大执行时间（秒）")
    schedule: str | None = Field(
        default=None,
        description="cron 表达式定时触发，None 表示每次循环都执行"
    )
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="任务特定参数（如副本名称、重复次数等）"
    )


class AppConfig(BaseModel):
    """应用全局配置。"""
    adb: ADBConfig = Field(default_factory=ADBConfig)
    tasks: list[TaskConfig] = Field(default_factory=list)
    global_retry: int = Field(default=3, description="全局默认重试次数")
    screenshot_interval: float = Field(default=0.5, description="截图间隔（秒）")
    loop_interval: float = Field(default=60.0, description="主循环间隔（秒）")
    log_level: str = Field(default="INFO", description="日志级别")
    log_dir: str = Field(default="./logs", description="日志目录")
    assets_dir: str = Field(default="./assets", description="图像模板资源目录")
    game_package: str = Field(
        default="",
        description="游戏包名（用于保活检测和重启）"
    )
    game_activity: str = Field(
        default="",
        description="游戏启动 Activity（用于自动启动游戏）"
    )
    max_restart_count: int = Field(default=3, description="最大连续重启次数")
    stuck_detection_frames: int = Field(
        default=5, description="卡死判定所需连续相同帧数"
    )

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

"""路径解析工具 — 兼容源码运行和 PyInstaller 打包后的 exe。"""

import sys
from pathlib import Path


def base_dir() -> Path:
    """返回项目根目录。

    源码运行时 = 项目根目录
    exe 运行时   = 临时解压目录 _MEIPASS（资源目录）
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后
        return Path(sys._MEIPASS)
    return Path(__file__).parent.parent


def exe_dir() -> Path:
    """返回 exe 文件所在目录（用于读写外部文件：config.yaml、logs、adb）。"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent


def asset_path(relative: str) -> Path:
    """返回资源文件路径（图片模板等）。"""
    return base_dir() / relative

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

"""MuMu 模拟器 ADB 端口自动检测。

支持的 MuMu 版本:
- MuMu 12: 默认端口 16384，多开实例以 32 为步长递增 (16384, 16416, 16448...)
- MuMu 6:  默认端口 7555 或 21503

检测策略（按优先级）:
1. 扫描已知端口范围
2. 尝试连接并检查设备名是否包含 'mumu'
"""

import subprocess
import sys
from pathlib import Path

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# MuMu 12 端口范围
MUMU12_PORT_START = 16384
MUMU12_PORT_END = 16512
MUMU12_PORT_STEP = 32

# MuMu 6 常见端口
MUMU6_PORTS = [7555, 21503, 21513]

# MuMu 模拟器常见安装路径
MUMU_INSTALL_PATHS = [
    r"D:\Program Files\MuMu\MuMuPlayer-12.0",
    r"D:\Program Files\Netease\MuMuPlayer-12.0",
    r"C:\Program Files\MuMu\MuMuPlayer-12.0",
    r"C:\Program Files\Netease\MuMuPlayer-12.0",
    r"D:\MuMu\MuMuPlayer-12.0",
]


def find_adb_executable() -> str | None:
    """查找 ADB 可执行文件路径。

    搜索顺序:
    1. 系统 PATH 中的 adb
    2. MuMu 模拟器自带的 adb
    """
    # 1. 检查系统 PATH
    try:
        result = subprocess.run(
            ["where", "adb"] if sys.platform == "win32" else ["which", "adb"],
            capture_output=True, text=True, timeout=5,
            creationflags=_CREATE_NO_WINDOW,
        )
        if result.returncode == 0 and result.stdout.strip():
            adb_path = result.stdout.strip().split("\n")[0].strip()
            # 验证可执行
            verify = subprocess.run(
                [adb_path, "version"], capture_output=True, timeout=5,
                creationflags=_CREATE_NO_WINDOW,
            )
            if verify.returncode == 0:
                return adb_path
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # 2. 搜索 MuMu 安装目录中的 adb
    for base in MUMU_INSTALL_PATHS:
        for root, dirs, files in Path(base).rglob("adb.exe"):
            if root.name == "adb.exe":
                return str(root)
        # 也检查非 exe 后缀
        for root, dirs, files in Path(base).rglob("adb"):
            if root.is_file():
                return str(root)

    return None


def _check_port(host: str, port: int, adb_path: str = "adb") -> str | None:
    """尝试连接指定端口并验证是否为 MuMu 设备。

    Returns:
        设备序列号 (如 '127.0.0.1:16384') 或 None
    """
    addr = f"{host}:{port}"
    try:
        # 尝试连接
        subprocess.run(
            [adb_path, "connect", addr],
            capture_output=True, timeout=5,
            creationflags=_CREATE_NO_WINDOW,
        )
        # 检查设备列表
        result = subprocess.run(
            [adb_path, "devices"],
            capture_output=True, text=True, timeout=5,
            creationflags=_CREATE_NO_WINDOW,
        )
        for line in result.stdout.strip().split("\n")[1:]:
            if addr in line and "device" in line:
                # 进一步验证是否为 MuMu 设备
                prop_result = subprocess.run(
                    [adb_path, "-s", addr, "shell", "getprop", "ro.product.manufacturer"],
                    capture_output=True, text=True, timeout=5,
                    creationflags=_CREATE_NO_WINDOW,
                )
                manufacturer = prop_result.stdout.strip().lower()
                # MuMu 设备通常 manufacturer 包含 netease 或 mumu
                if "netease" in manufacturer or "mumu" in manufacturer or "android" in manufacturer:
                    return addr
                # 如果无法获取 manufacturer，但能连接且有 device 状态，也接受
                return addr
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def detect_mumu_device(adb_path: str = "adb") -> str | None:
    """自动检测 MuMu 模拟器的 ADB 设备地址。

    Returns:
        设备序列号字符串 (如 '127.0.0.1:16384')，未找到返回 None
    """
    host = "127.0.0.1"

    # 1. 扫描 MuMu 12 端口范围
    for port in range(MUMU12_PORT_START, MUMU12_PORT_END + 1, MUMU12_PORT_STEP):
        addr = _check_port(host, port, adb_path)
        if addr:
            return addr

    # 2. 检查 MuMu 6 常见端口
    for port in MUMU6_PORTS:
        addr = _check_port(host, port, adb_path)
        if addr:
            return addr

    return None


def list_all_devices(adb_path: str = "adb") -> list[str]:
    """列出所有已连接的 ADB 设备（不过滤制造商）。

    执行 adb devices，返回所有状态为 'device' 的设备 ID。
    不过滤任何 IP 格式（支持 127.0.0.1、192.168.x.x、10.0.x.x 等）。

    Args:
        adb_path: ADB 可执行文件路径

    Returns:
        设备 ID 列表

    Raises:
        RuntimeError: 未找到任何设备
    """
    from core.adb_controller import ADBController
    return ADBController.list_devices(adb_path)


def get_adb_path() -> str:
    """获取 ADB 可执行文件路径，找不到则返回 'adb'（依赖 PATH）。"""
    found = find_adb_executable()
    return found if found else "adb"

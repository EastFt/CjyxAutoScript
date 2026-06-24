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

"""ADB 连接管理器。

封装 adb connect/disconnect/shell 等原始命令，
是整个系统与模拟器通信的唯一入口。
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from loguru import logger

# Windows: 隐藏 subprocess 弹出的命令行窗口
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


class ADBConnectionError(Exception):
    """ADB 连接异常。"""
    pass


class ADBCommandError(Exception):
    """ADB 命令执行异常。"""
    pass


class ADBFatalError(Exception):
    """ADB 连续失败超过阈值，终止所有任务。"""
    pass


class ADBController:
    """ADB 连接管理与原始命令发送。

    Usage:
        adb = ADBController("127.0.0.1:16384")
        adb.connect()
        output = adb.shell("wm size")
        screenshot_bytes = adb.exec_out("screencap")
    """

    def __init__(
        self,
        device_addr: str = "127.0.0.1:16384",
        adb_path: str = "adb",
        connect_timeout: float = 10.0,
    ):
        self._device_addr = device_addr
        self._adb_path = adb_path
        self._connect_timeout = connect_timeout
        self._connected = False
        self._consecutive_failures = 0
        self._max_consecutive_failures = 10

    # ── 连接管理 ──────────────────────────────────────

    @property
    def device_addr(self) -> str:
        return self._device_addr

    @property
    def adb_path(self) -> str:
        return self._adb_path

    @property
    def is_connected(self) -> bool:
        return self._connected

    @staticmethod
    def list_devices(adb_path: str = "adb") -> list[str]:
        """列出所有已连接的 ADB 设备。

        执行 adb devices，解析输出，返回所有状态为 'device' 的设备 ID。
        不过滤任何 IP 格式（支持 127.0.0.1、192.168.x.x、10.0.x.x 等）。

        Args:
            adb_path: ADB 可执行文件路径

        Returns:
            设备 ID 列表（如 ['127.0.0.1:16384', '192.168.175.46:5555']）

        Raises:
            RuntimeError: 未找到任何设备，或 ADB 不可用
        """
        try:
            result = subprocess.run(
                [adb_path, "devices"],
                capture_output=True, text=True, timeout=5,
                creationflags=_CREATE_NO_WINDOW,
            )
        except FileNotFoundError:
            raise RuntimeError(
                f"找不到 ADB 可执行文件: {adb_path}。"
                f"请确保 Android Platform Tools 已安装并加入 PATH。"
            )

        devices: list[str] = []
        lines = result.stdout.strip().split("\n")[1:]  # 跳过首行 "List of devices attached"
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # 只保留状态为 'device' 的行（排除 'offline'、'unauthorized' 等）
            if "\tdevice" in line and "offline" not in line:
                device_id = line.split("\t")[0].strip()
                if device_id:
                    devices.append(device_id)

        if not devices:
            raise RuntimeError("未找到任何 ADB 设备，请检查模拟器是否开启")

        return devices

    def connect(self) -> bool:
        """连接到设备。

        支持 auto 模式：当 device_addr 为 'auto' 时，
        自动执行 adb devices 获取设备列表，选取第一个设备连接。

        Returns:
            True 表示连接成功或已连接
        """
        if self._connected:
            return True

        # ── auto 模式：自动检测设备 ──
        if self._device_addr == "auto":
            devices = self.list_devices(self._adb_path)
            self._device_addr = devices[0]
            logger.info(f"自动检测到设备: {self._device_addr}")

        logger.info(f"正在连接 ADB 设备: {self._device_addr}")

        try:
            result = subprocess.run(
                [self._adb_path, "connect", self._device_addr],
                capture_output=True, text=True, timeout=self._connect_timeout,
                creationflags=_CREATE_NO_WINDOW,
            )
            output = result.stdout.strip().lower()

            # 检查连接结果
            if "connected" in output or "already connected" in output:
                # 验证设备状态
                if self._verify_device():
                    self._connected = True
                    logger.info(f"ADB 设备已连接: {self._device_addr}")
                    return True

            logger.error(f"ADB 连接失败: {output}")
            return False

        except subprocess.TimeoutExpired:
            logger.error(f"ADB 连接超时 ({self._connect_timeout}s)")
            return False
        except FileNotFoundError:
            logger.error(
                f"找不到 ADB 可执行文件: {self._adb_path}。"
                f"请确保 Android Platform Tools 已安装并加入 PATH。"
            )
            return False

    def disconnect(self) -> None:
        """断开设备连接。"""
        if not self._connected:
            return
        try:
            subprocess.run(
                [self._adb_path, "disconnect", self._device_addr],
                capture_output=True, timeout=5,
                creationflags=_CREATE_NO_WINDOW,
            )
        except Exception:
            pass
        finally:
            self._connected = False
            logger.info(f"ADB 设备已断开: {self._device_addr}")

    def kill_server(self) -> None:
        """终止 ADB 服务进程，清理所有残留连接。"""
        try:
            subprocess.run(
                [self._adb_path, "kill-server"],
                capture_output=True, timeout=5,
                creationflags=_CREATE_NO_WINDOW,
            )
            logger.info("ADB 服务已终止")
        except Exception:
            pass
        self._connected = False

    def _check_fatal(self):
        if self._consecutive_failures >= self._max_consecutive_failures:
            raise ADBFatalError(
                f"ADB 连续失败 {self._consecutive_failures} 次，终止所有任务"
            )

    def reset_failure_count(self):
        """重置连续失败计数。"""
        self._consecutive_failures = 0

    def reconnect(self) -> bool:
        """重连设备。"""
        self.disconnect()
        time.sleep(1.0)
        return self.connect()

    def _verify_device(self) -> bool:
        """验证设备在线且可通信。"""
        try:
            result = subprocess.run(
                [self._adb_path, "devices"],
                capture_output=True, text=True, timeout=5,
                creationflags=_CREATE_NO_WINDOW,
            )
            for line in result.stdout.strip().split("\n")[1:]:
                if self._device_addr in line and "\tdevice" in line:
                    return True
            return False
        except Exception:
            return False

    # ── 命令执行 ──────────────────────────────────────

    def shell(self, cmd: str, timeout: float = 10.0) -> str:
        """执行 adb shell 命令并返回 stdout 文本。

        Args:
            cmd: shell 命令字符串
            timeout: 超时秒数

        Returns:
            命令输出文本（已去除尾部空白）

        Raises:
            ADBConnectionError: 设备未连接
            ADBCommandError: 命令执行失败
        """
        if not self._connected:
            raise ADBConnectionError("设备未连接，请先调用 connect()")

        full_cmd = [self._adb_path, "-s", self._device_addr, "shell", cmd]
        logger.debug(f"shell: {cmd}")

        try:
            result = subprocess.run(
                full_cmd,
                capture_output=True, text=True, timeout=timeout,
                creationflags=_CREATE_NO_WINDOW,
            )
            self._consecutive_failures = 0  # 成功则重置
            if result.returncode != 0:
                stderr = result.stderr.strip()
                if stderr:
                    logger.warning(f"shell 命令返回非零: {cmd} -> {stderr}")
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            self._consecutive_failures += 1
            self._check_fatal()
            raise ADBCommandError(f"shell 命令超时 ({timeout}s): {cmd}")
        except Exception:
            self._consecutive_failures += 1
            self._check_fatal()
            raise

    def shell_bytes(self, cmd: str, timeout: float = 10.0) -> bytes:
        """执行 adb shell 命令并返回原始字节。

        用于获取截图等二进制数据。

        Raises:
            ADBConnectionError: 设备未连接
            ADBCommandError: 命令执行失败
        """
        if not self._connected:
            raise ADBConnectionError("设备未连接，请先调用 connect()")

        full_cmd = [self._adb_path, "-s", self._device_addr, "shell", cmd]
        logger.debug(f"shell (bytes): {cmd}")

        try:
            result = subprocess.run(
                full_cmd,
                capture_output=True, timeout=timeout,
                creationflags=_CREATE_NO_WINDOW,
            )
            self._consecutive_failures = 0
            if result.returncode != 0:
                stderr = result.stderr.decode(errors="ignore").strip()
                if stderr:
                    logger.warning(f"shell 命令返回非零: {cmd} -> {stderr}")
            return result.stdout
        except subprocess.TimeoutExpired:
            self._consecutive_failures += 1
            self._check_fatal()
            raise ADBCommandError(f"shell 命令超时 ({timeout}s): {cmd}")
        except Exception:
            self._consecutive_failures += 1
            self._check_fatal()
            raise

    def exec_out(self, cmd: str, timeout: float = 10.0) -> bytes:
        """执行 adb exec-out 命令并返回原始字节。

        exec-out 不经过 PTY，适合获取截图等二进制数据。

        Raises:
            ADBConnectionError: 设备未连接
            ADBCommandError: 命令执行失败
        """
        if not self._connected:
            raise ADBConnectionError("设备未连接，请先调用 connect()")

        full_cmd = [self._adb_path, "-s", self._device_addr, "exec-out", cmd]
        logger.debug(f"exec-out: {cmd}")

        try:
            result = subprocess.run(
                full_cmd,
                capture_output=True, timeout=timeout,
                creationflags=_CREATE_NO_WINDOW,
            )
            self._consecutive_failures = 0
            if result.returncode != 0:
                stderr = result.stderr.decode(errors="ignore").strip()
                if stderr:
                    logger.warning(f"exec-out 命令返回非零: {cmd} -> {stderr}")
            return result.stdout
        except subprocess.TimeoutExpired:
            self._consecutive_failures += 1
            self._check_fatal()
            raise ADBCommandError(f"exec-out 命令超时 ({timeout}s): {cmd}")
        except Exception:
            self._consecutive_failures += 1
            self._check_fatal()
            raise

    # ── 便捷方法 ──────────────────────────────────────

    def tap(self, x: int, y: int) -> None:
        """点击屏幕坐标。"""
        self.shell(f"input tap {x} {y}")

    def swipe(
        self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300
    ) -> None:
        """滑动屏幕。"""
        self.shell(f"input swipe {x1} {y1} {x2} {y2} {duration_ms}")

    def press_key(self, keycode: int) -> None:
        """发送按键事件。"""
        self.shell(f"input keyevent {keycode}")

    def press_back(self) -> None:
        """按下返回键 (KEYCODE_BACK = 4)。"""
        self.press_key(4)

    def press_home(self) -> None:
        """按下 Home 键 (KEYCODE_HOME = 3)。"""
        self.press_key(3)

    def get_resolution(self) -> tuple[int, int]:
        """获取设备屏幕分辨率 (宽, 高)。"""
        output = self.shell("wm size")
        # 格式: Physical size: 1280x720
        size_str = output.split(":")[-1].strip()
        w, h = size_str.split("x")
        return int(w), int(h)

    def start_app(self, package: str, activity: str | None = None) -> None:
        """启动应用。"""
        if activity:
            cmd = f"am start -n {package}/{activity}"
        else:
            cmd = f"monkey -p {package} -c android.intent.category.LAUNCHER 1"
        self.shell(cmd)
        logger.info(f"已启动应用: {package}")

    def stop_app(self, package: str) -> None:
        """强制停止应用。"""
        self.shell(f"am force-stop {package}")
        logger.info(f"已停止应用: {package}")

    def app_is_running(self, package: str) -> bool:
        """检查应用是否在运行。"""
        output = self.shell(f"pidof {package}")
        return bool(output) and "not found" not in output.lower()

    def __repr__(self) -> str:
        status = "connected" if self._connected else "disconnected"
        return f"ADBController({self._device_addr}, {status})"

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

# 卡牌游戏日常任务自动化脚本
# MuMu 模拟器 + ADB + OpenCV 图像识别
#
# Usage:
#   python main.py                # 运行一轮日常任务
#   python main.py --check        # 环境诊断
#   python main.py --loop         # 持续循环运行
#   python main.py --config path  # 指定配置文件

import argparse
import sys
import time
from pathlib import Path

import yaml
from loguru import logger

from config.settings import AppConfig
from utils.logger import setup_logger
from utils.mumu_detector import detect_mumu_device, get_adb_path


def load_config(config_path: str) -> AppConfig:
    """从 YAML 文件加载配置。"""
    path = Path(config_path)
    if not path.exists():
        logger.warning(f"配置文件不存在: {path}，使用默认配置")
        return AppConfig()

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    return AppConfig(**data)


def init_adb(config: AppConfig):
    """初始化 ADB 控制器。"""
    from core.adb_controller import ADBController

    # 确定 ADB 路径
    adb_path = config.adb.adb_path
    if adb_path == "auto":
        adb_path = get_adb_path()
        logger.info(f"自动检测 ADB 路径: {adb_path}")

    # 确定设备地址
    device_addr = config.adb.device_addr
    if device_addr == "auto":
        detected = detect_mumu_device(adb_path)
        if detected:
            device_addr = detected
            logger.info(f"自动检测 MuMu 设备: {device_addr}")
        else:
            logger.info(
                "MuMu 专有端口未发现设备，将尝试 adb devices 通用检测"
            )
            # 不返回 None —— 交给 ADBController.connect() 做通用设备检测

    adb = ADBController(
        device_addr=device_addr,
        adb_path=adb_path,
        connect_timeout=config.adb.connect_timeout,
    )

    if not adb.connect():
        logger.error(f"无法连接到设备: {device_addr}")
        return None

    return adb


def run_check(adb) -> bool:
    """运行环境诊断。"""
    logger.info("=" * 50)
    logger.info("环境诊断")
    logger.info("=" * 50)

    all_ok = True

    # 1. ADB 连接
    logger.info(f"ADB 已连接: {adb.is_connected}")

    # 2. 分辨率
    try:
        w, h = adb.get_resolution()
        logger.info(f"屏幕分辨率: {w}x{h}（模板应为 1280x720 或相近比例）")
    except Exception as e:
        logger.error(f"获取分辨率失败: {e}")
        all_ok = False

    # 3. 检查图像模板目录
    assets_dir = Path("./assets")
    for subdir in ["buttons", "screens", "popups"]:
        d = assets_dir / subdir
        png_files = list(d.glob("*.png")) if d.exists() else []
        if not png_files:
            logger.warning(f"图像模板目录为空: {d} (请截取游戏界面模板)")
        else:
            logger.info(f"模板目录 {subdir}: {len(png_files)} 个文件")

    # 4. OpenCV 版本
    try:
        import cv2
        logger.info(f"OpenCV 版本: {cv2.__version__}")
    except ImportError:
        logger.error("OpenCV 未安装")
        all_ok = False

    # 5. NumPy
    try:
        import numpy as np
        logger.info(f"NumPy 版本: {np.__version__}")
    except ImportError:
        logger.error("NumPy 未安装")
        all_ok = False

    # 6. 其他检查通过

    logger.info("=" * 50)
    if all_ok:
        logger.info("环境诊断完成，基础检查通过")
    else:
        logger.warning("环境诊断完成，存在警告项")
    return all_ok


def build_runtime(config: AppConfig, adb):
    """构建运行时组件：Device, Vision, Action, Scheduler。"""

    from core.device import Device
    from core.vision import VisionEngine
    from core.action import Action
    from scheduler.engine import Scheduler

    device = Device(adb)
    vision = VisionEngine(assets_dir=config.assets_dir)
    action = Action(device, vision)

    scheduler = Scheduler(
        config=config,
        adb=adb,
        device=device,
        vision=vision,
        action=action,
    )

    logger.info(f"设备分辨率: {device.resolution}")
    logger.info(f"图像模板目录: {config.assets_dir}")
    logger.info(f"已注册 {scheduler.task_count} 个任务")

    return device, vision, action, scheduler


def main():
    parser = argparse.ArgumentParser(
        description="卡牌游戏日常任务自动化脚本"
    )
    parser.add_argument(
        "--config", "-c",
        default="config.yaml",
        help="配置文件路径 (默认: config.yaml)"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="运行环境诊断"
    )
    parser.add_argument(
        "--loop", "-l",
        action="store_true",
        help="持续循环运行"
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=None,
        help="循环间隔秒数 (覆盖配置文件)"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="执行一轮后退出"
    )
    args = parser.parse_args()

    # 加载配置
    config = load_config(args.config)

    # 初始化日志
    setup_logger(log_dir=config.log_dir, level=config.log_level)
    logger.info("=" * 50)
    logger.info("卡牌游戏日常任务自动化脚本 启动")
    logger.info("=" * 50)

    # 初始化 ADB
    adb = init_adb(config)
    if adb is None:
        logger.error("ADB 初始化失败，退出")
        sys.exit(1)

    try:
        # 环境诊断模式
        if args.check:
            run_check(adb)
            return

        # 构建运行时
        _, _, _, scheduler = build_runtime(config, adb)

        # 单次执行模式
        if args.once:
            results = scheduler.run_once()
            success = sum(1 for v in results.values() if v == "success")
            fail = sum(1 for v in results.values() if v in ("failed", "error"))
            skip = sum(1 for v in results.values() if v == "skipped")
            logger.info(f"任务完成: {success} 成功, {fail} 失败, {skip} 跳过")
            return

        # 默认：执行一轮
        # （如果指定了 --loop 则持续循环）
        if args.loop:
            interval = args.interval if args.interval is not None else config.loop_interval
            scheduler.run_loop(interval=interval)
        else:
            # 无参数默认执行一轮
            results = scheduler.run_once()
            success = sum(1 for v in results.values() if v == "success")
            fail = sum(1 for v in results.values() if v in ("failed", "error"))
            skip = sum(1 for v in results.values() if v == "skipped")
            logger.info(f"任务完成: {success} 成功, {fail} 失败, {skip} 跳过")

    except KeyboardInterrupt:
        logger.info("用户中断，退出")
    finally:
        adb.disconnect()
        logger.info("脚本已退出")


if __name__ == "__main__":
    main()

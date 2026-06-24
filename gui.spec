# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec — 卡牌游戏日常任务自动化 GUI
=================================================
生成: pyinstaller gui.spec

资源: assets/**/*.png    → exe 内置
外部: config.yaml        → exe 同目录（用户可编辑）
      logs/              → exe 同目录
      platform-tools/    → exe 同目录（含 adb.exe）
"""

import sys
from pathlib import Path

_project_root = Path(SPECPATH)  # spec 文件所在目录 = 项目根目录

# ── 收集 assets/ 下所有 PNG ──────────────────────────
assets = []
_assets_dir = _project_root / "assets"
for p in _assets_dir.rglob("*.png"):
    # 保持目录结构
    dest = str(p.parent.relative_to(_project_root))
    assets.append((str(p), dest))

print(f"[spec] Collected {len(assets)} assets from assets/")

a = Analysis(
    ['gui.py'],
    pathex=[str(_project_root)],
    binaries=[],
    datas=assets,
    hiddenimports=[
        'yaml',
        'numpy',
        'cv2',
        'PIL',
        'PIL.Image',
        'PIL.ImageDraw',
        'PIL.ImageTk',
        'loguru',
        'core',
        'core.adb_controller',
        'core.device',
        'core.vision',
        'core.action',
        'core.ocr',
        'scheduler',
        'scheduler.base_task',
        'scheduler.engine',
        'scheduler.recovery',
        'tasks',
        'tasks.daily_signin',
        'tasks.collect_mail',
        'tasks.friends',
        'tasks.events',
        'tasks.guild',
        'tasks.arena',
        'tasks.auto_battle',
        'config',
        'config.settings',
        'utils',
        'utils.logger',
        'utils.mumu_detector',
        'utils.paths',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='I\'m Yours',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(_assets_dir / "icon.png"),
)

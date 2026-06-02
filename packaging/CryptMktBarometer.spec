# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 规格文件 — 单文件 Windows exe
# 用法（在项目根目录）：
#   pyinstaller packaging\CryptMktBarometer.spec --noconfirm

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

# SPECPATH = packaging/ 目录；项目根目录为其上一级
ROOT = Path(SPECPATH).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

block_cipher = None

hiddenimports = [
    *collect_submodules("apscheduler"),
    *collect_submodules("feedparser"),
    *collect_submodules("tzdata"),
    "flask",
    "jinja2.ext",
    "yaml",
    "sqlite3",
    "requests",
    "certifi",
    "charset_normalizer",
    "idna",
    "urllib3",
    "pystray",
    "PIL",
    "PIL._imagingtk",
    "PIL._tkinter_finder",
    "scoring.engine",
    "scoring.macro_score",
    "scoring.regulation_score",
    "scoring.funding_score",
    "scoring.fundamentals_score",
    "collectors.fetch_runner",
    "collectors.news_collect",
    "collectors.news_display",
    "collectors.news_localize",
    "collectors.news_categories",
    "collectors.price_ticker",
    "weight_optimizer",
    "floating_dashboard",
    "floating_integration",
    "tkinter",
    "_tkinter",
]

datas = [
    (str(ROOT / "app" / "templates"), "app/templates"),
    (str(ROOT / "static"), "static"),
    (str(ROOT / "config" / "config.example.yaml"), "config"),
    (str(ROOT / "packaging" / "icon.ico"), "packaging"),
]

a = Analysis(
    [str(ROOT / "desktop_launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "numpy", "pandas", "pytest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="CryptMktBarometer",
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
    icon=str(ROOT / "packaging" / "icon.ico"),
)

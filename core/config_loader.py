"""
配置加载模块
从 config/config.yaml 读取运行参数与 API 密钥。
"""

from pathlib import Path
from typing import Any

import yaml

# 项目根目录（core 的上级）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"
EXAMPLE_CONFIG_PATH = PROJECT_ROOT / "config" / "config.example.yaml"

_config_cache: dict[str, Any] | None = None


def get_config_path() -> Path:
    """返回实际使用的配置文件路径。"""
    if DEFAULT_CONFIG_PATH.exists():
        return DEFAULT_CONFIG_PATH
    if EXAMPLE_CONFIG_PATH.exists():
        return EXAMPLE_CONFIG_PATH
    raise FileNotFoundError(
        f"未找到配置文件，请将 {EXAMPLE_CONFIG_PATH.name} 复制为 config.yaml"
    )


def load_config(reload: bool = False) -> dict[str, Any]:
    """
    加载 YAML 配置，带内存缓存。
    :param reload: 为 True 时强制重新读取磁盘
    """
    global _config_cache
    if _config_cache is not None and not reload:
        return _config_cache

    path = get_config_path()
    with open(path, encoding="utf-8") as f:
        _config_cache = yaml.safe_load(f) or {}

    return _config_cache


def get_nested(cfg: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """按层级键安全取值，例如 get_nested(cfg, 'web', 'port')"""
    cur: Any = cfg
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur

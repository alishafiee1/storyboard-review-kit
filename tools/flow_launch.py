# -*- coding: utf-8 -*-
"""Chrome orchestration for Flow automation.

Detects or spawns Google Chrome with remote debugging on port 9222
and a dedicated user profile. Configurable via environment variables
and kit-config.json.
"""
import json
import os
import shutil
import socket
import subprocess

DEFAULT_CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DEFAULT_PROFILE_DIR = r"C:\Users\alish\flow-chrome-profile"
DEBUG_PORT = 9222

FALLBACK_EXE_LIST = [
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
    "chrome",
    "chrome.exe",
]


def is_port_open(host: str = "127.0.0.1", port: int = DEBUG_PORT, timeout: float = 0.5) -> bool:
    """Check if TCP port accepts connections."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def load_kit_config(project_dir: str = None) -> dict:
    """Load kit-config.json from project root."""
    root = project_dir or "."
    cfg_path = os.path.join(root, "kit-config.json")
    if os.path.isfile(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}
    return {}


def resolve_profile_dir(project_dir: str = None, env: dict = None) -> str:
    """Resolve Chrome profile directory.

    Priority:
    1. Env: FLOW_CHROME_PROFILE
    2. kit-config.json: flow_chrome_profile
    3. Default: C:\\Users\\alish\\flow-chrome-profile
    """
    environ = env if env is not None else os.environ
    if "FLOW_CHROME_PROFILE" in environ and environ["FLOW_CHROME_PROFILE"]:
        return environ["FLOW_CHROME_PROFILE"]

    cfg = load_kit_config(project_dir)
    if cfg.get("flow_chrome_profile"):
        return str(cfg["flow_chrome_profile"])

    return DEFAULT_PROFILE_DIR


def resolve_chrome_path(project_dir: str = None, env: dict = None, file_checker=None) -> str:
    """Resolve Google Chrome executable.

    Priority:
    1. Env: FLOW_CHROME_PATH
    2. kit-config.json: flow_chrome_path
    3. Default: C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe
    4. Fallbacks in order:
       - C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe
       - %LOCALAPPDATA%\\Google\\Chrome\\Application\\chrome.exe
       - shutil.which("chrome")
       - shutil.which("chrome.exe")
       - platform fallbacks (google-chrome, chromium)
    """
    is_file = file_checker or os.path.isfile
    environ = env if env is not None else os.environ

    # 1. Env override
    if "FLOW_CHROME_PATH" in environ and environ["FLOW_CHROME_PATH"]:
        return environ["FLOW_CHROME_PATH"]

    # 2. Config override
    cfg = load_kit_config(project_dir)
    if cfg.get("flow_chrome_path"):
        return str(cfg["flow_chrome_path"])

    # 3. Default path
    if is_file(DEFAULT_CHROME_EXE):
        return DEFAULT_CHROME_EXE

    # 4. Fallbacks in order
    for fb in FALLBACK_EXE_LIST:
        expanded = os.path.expandvars(fb)
        if ("\\" in expanded or "/" in expanded) and is_file(expanded):
            return expanded
        which_path = shutil.which(fb)
        if which_path and is_file(which_path):
            return which_path

    # Extra unix fallbacks if running in linux/mac sandbox
    for extra in ("google-chrome", "chromium", "chromium-browser", "google-chrome-stable"):
        which_extra = shutil.which(extra)
        if which_extra and is_file(which_extra):
            return which_extra

    return None


def launch_chrome(
    chrome_path: str = None,
    profile_path: str = None,
    port_checker=None,
    spawner=None,
    file_checker=None,
    project_dir: str = None,
    env: dict = None,
) -> dict:
    """Launch Chrome with remote debugging on port 9222 and dedicated profile.

    Returns dict with result status and details. Never raises or crashes server.
    """
    check_port = port_checker or is_port_open
    if check_port(port=DEBUG_PORT):
        return {
            "ok": True,
            "already_connected": True,
            "port": DEBUG_PORT,
            "message": f"Chrome is already running and listening on port {DEBUG_PORT}.",
        }

    # Resolve executable
    exe = chrome_path or resolve_chrome_path(project_dir=project_dir, env=env, file_checker=file_checker)
    if not exe:
        return {
            "ok": False,
            "error": "مسیر فایل اجرایی کروم پیدا نشد. لطفاً کروم را نصب کرده یا مسیر آن را در FLOW_CHROME_PATH تنظیم کنید.",
            "port": DEBUG_PORT,
        }

    # Resolve profile
    profile = profile_path or resolve_profile_dir(project_dir=project_dir, env=env)

    # Spawn command
    cmd = [
        exe,
        f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={profile}",
    ]

    spawn_fn = spawner or (lambda c: subprocess.Popen(c))
    try:
        spawn_fn(cmd)
        return {
            "ok": True,
            "spawned": True,
            "exe": exe,
            "profile": profile,
            "port": DEBUG_PORT,
            "message": f"Chrome launched on port {DEBUG_PORT} with profile {profile}.",
        }
    except Exception as e:
        return {
            "ok": False,
            "error": f"خطا در اجرای مرورگر کروم: {e}",
            "port": DEBUG_PORT,
        }

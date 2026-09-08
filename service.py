import pyperclip
import psutil
import os
import subprocess
import winreg
import comtypes
from pycaw.pycaw import AudioUtilities, IAudioMeterInformation
from pycaw.constants import AudioSessionState
from app_logging import log_error, log_info, log_warning

COMMON_MEDIA_PLAYERS = {
    'cloudmusic.exe',
    'qqmusic.exe',
    'spotify.exe',
    'foobar2000.exe',
    'yesplaymusic.exe',
    'kgma.exe',
    'kugou.exe',
    'kwmusic.exe',
    'kwmusic_main.exe'
}

def getClipContent():
    content = pyperclip.paste()
    return content

def is_media_player_running():
    """Check if any common media player is running"""
    try:
        for proc in psutil.process_iter(['name']):
            try:
                process_name = proc.info.get('name')
                if process_name and process_name.lower() in COMMON_MEDIA_PLAYERS:
                    # print(f"Found running player: {proc.info['name']}")
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
    except Exception as e:
        log_error(f"service.is_media_player_running failed: {e}")
        
    return False

def is_media_playing():
    """Check if any common media player is actually playing audio"""
    # Initialize COM (safe to call multiple times per thread)
    try:
        comtypes.CoInitialize()
    except:
        pass

    try:
        sessions = AudioUtilities.GetAllSessions()
        for session in sessions:
            process = session.Process
            if not process:
                continue

            try:
                name = process.name().lower()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                # 播放器刚退出时音频会话可能短暂残留，这里直接忽略即可。
                continue

            if name in COMMON_MEDIA_PLAYERS and session.State == AudioSessionState.Active:
                # 用峰值音量确认是否真的在出声，避免暂停后仍被系统短暂标记为活跃。
                try:
                    meter = session._ctl.QueryInterface(IAudioMeterInformation)
                    if meter.GetPeakValue() > 0:
                        return True
                except Exception:
                    # 如果拿不到峰值信息，则回退到会话状态判断，避免误判为未播放。
                    return True
    except Exception as e:
        log_error(f"service.is_media_playing failed: {e}")
    finally:
        # Uninitialize COM
        try:
            comtypes.CoUninitialize()
        except:
            pass
        
    return False

def get_protocol_executable(protocol):
    """Get executable path associated with a protocol from Registry"""
    try:
        # Protocol name usually matches the scheme, e.g. "qqmusic"
        key_path = f"{protocol}\\shell\\open\\command"
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, key_path) as key:
            command, _ = winreg.QueryValueEx(key, "")
            # Command is usually like: "C:\Path\To\App.exe" "%1"
            return _extract_path_from_command(command)
    except Exception:
        return None

def get_app_path(app_name):
    """Get executable path from App Paths registry key"""
    try:
        # HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\QQMusic.exe
        key_path = f"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\{app_name}"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
            path, _ = winreg.QueryValueEx(key, "")
            return path
    except Exception:
        try:
            # Try HKCU as well
            key_path = f"Software\\Microsoft\\Windows\\CurrentVersion\\App Paths\\{app_name}"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                path, _ = winreg.QueryValueEx(key, "")
                return path
        except Exception:
            return None

def get_uninstall_path(app_id):
    """Get install location from Uninstall registry key"""
    uninstall_paths = [
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
    ]
    
    roots = [
        (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_READ | winreg.KEY_WOW64_64KEY),
        (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_READ | winreg.KEY_WOW64_32KEY),
        (winreg.HKEY_CURRENT_USER, winreg.KEY_READ)
    ]

    for root, flags in roots:
        for base_path in uninstall_paths:
            # HKCU doesn't usually use WOW6432Node, but simple loop is fine
            if root == winreg.HKEY_CURRENT_USER and "WOW6432Node" in base_path:
                continue
                
            try:
                key_path = f"{base_path}\\{app_id}"
                with winreg.OpenKey(root, key_path, 0, flags) as key:
                    try:
                        path, _ = winreg.QueryValueEx(key, "InstallLocation")
                        return path
                    except FileNotFoundError:
                        pass
            except Exception:
                pass
    return None

def _extract_path_from_command(command):
    # Handle quoted path
    if command.startswith('"'):
        end_quote = command.find('"', 1)
        if end_quote != -1:
            return command[1:end_quote]
    
    # Handle unquoted path
    lower_cmd = command.lower()
    if ".exe" in lower_cmd:
        end_index = lower_cmd.find(".exe") + 4
        return command[:end_index]
        
    return command

def launch_default_media_player():
    """Try to launch a media player if none is running"""
    log_info("未检测到正在运行的播放器，开始尝试自动启动")
    
    # Priority list of players (Protocol, AppExeName, Readable Name, UninstallKeyID)
    players = [
        ("qqmusic", "QQMusic.exe", "QQ Music", "QQMusic"),
        ("orpheus", "cloudmusic.exe", "Netease Cloud Music", "CloudMusic"),
        ("spotify", "Spotify.exe", "Spotify", "Spotify"),
        ("kugou", "KuGou.exe", "KuGou Music", "KuGou"),
        ("kwmusic", "KwMusic.exe", "Kuwo Music", "kwmusic")
    ]
    
    # Strategy 1: Check App Paths (Most reliable for standard installed apps)
    for proto, exe_name, name, app_id in players:
        path = get_app_path(exe_name)
        if path and os.path.exists(path):
            log_info(f"通过 App Paths 找到 {name}：{path}")
            try:
                subprocess.Popen(path)
                return True
            except Exception as e:
                log_error(f"service.launch_default_media_player app paths failed for {name}: {e}")

    # Strategy 2: Check Uninstall Registry (Reliable for custom install locations)
    for proto, exe_name, name, app_id in players:
        install_loc = get_uninstall_path(app_id)
        if install_loc:
            # InstallLocation is usually a directory
            exe_path = os.path.join(install_loc, exe_name)
            if os.path.exists(exe_path):
                log_info(f"通过卸载信息找到 {name}：{exe_path}")
                try:
                    subprocess.Popen(exe_path)
                    return True
                except Exception as e:
                    log_error(f"service.launch_default_media_player uninstall registry failed for {name}: {e}")

    # Strategy 3: Registry Protocol Check
    for proto, exe_name, name, app_id in players:
        exe_path = get_protocol_executable(proto)
        if exe_path and os.path.exists(exe_path):
            log_info(f"通过协议注册表找到 {name}：{exe_path}")
            try:
                subprocess.Popen(exe_path)
                return True
            except Exception as e:
                log_error(f"service.launch_default_media_player protocol registry failed for {name}: {e}")

    # Strategy 4: Common Paths Fallback
    paths = [
        r"C:\Program Files (x86)\Tencent\QQMusic\QQMusic.exe",
        r"C:\Program Files\Tencent\QQMusic\QQMusic.exe",
        r"D:\Program Files (x86)\Tencent\QQMusic\QQMusic.exe",
        r"D:\Program Files\Tencent\QQMusic\QQMusic.exe",
        r"C:\Program Files (x86)\Netease\CloudMusic\cloudmusic.exe",
        r"D:\Program Files (x86)\Netease\CloudMusic\cloudmusic.exe"
    ]
    
    for path in paths:
        if os.path.exists(path):
            log_info(f"通过兜底路径启动播放器：{path}")
            try:
                subprocess.Popen(path)
                return True
            except Exception as e:
                log_error(f"service.launch_default_media_player fallback path failed for {path}: {e}")
    
    log_warning("未找到任何可用的已安装播放器")
    log_error("service.launch_default_media_player failed to find any installed media player")
    return False

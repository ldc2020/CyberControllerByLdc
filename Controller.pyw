import ctypes
import json
import os
import sys
import threading
import time
import traceback

import keyboard
import pyautogui
import win32api
import win32con
import win32event
import win32gui
import winerror
from PIL import Image, ImageDraw
from win32com.client import Dispatch

from TcpServer import TcpServer
from KeyboardListener import KeyboardListener
from service import *
from ComputerMonitor import ComputerMonitor
from SystemMonitor import SystemMonitor
from screen_shot import ScreenCapture
from CommandMessage import CommandMessage
from KeyboardManager import *
from app_logging import (
    APP_ERROR_LOG_FILE,
    APP_RUNTIME_LOG_FILE,
    SYSTEM_MONITOR_ERROR_LOG_FILE,
    ensure_error_log_files,
    get_current_log_level,
    install_error_hooks,
    log_debug,
    log_error,
    log_info,
    log_warning,
    set_current_log_level,
)

APP_NAME = "ldc小助手"
APP_ID = "LDC.CyberController.Helper"
MUTEX_NAME = "Local\\LDC_XiaoZhuShou_SingleInstance"
TRAY_EVENT_ID = win32con.WM_APP + 1
TRAY_MENU_OPEN_START = 1001
TRAY_MENU_VIEW_ERROR_LOG = 1002
TRAY_MENU_VIEW_RUNTIME_LOG = 1003
TRAY_MENU_LOG_LEVEL_DEBUG = 1004
TRAY_MENU_LOG_LEVEL_INFO = 1005
TRAY_MENU_LOG_LEVEL_WARNING = 1006
TRAY_MENU_LOG_LEVEL_ERROR = 1007
TRAY_MENU_EXIT = 1008

TRAY_LOG_LEVEL_MENU_ITEMS = {
    TRAY_MENU_LOG_LEVEL_DEBUG: "DEBUG",
    TRAY_MENU_LOG_LEVEL_INFO: "INFO",
    TRAY_MENU_LOG_LEVEL_WARNING: "WARNING",
    TRAY_MENU_LOG_LEVEL_ERROR: "ERROR",
}

app_mutex = None
tray_icon = None
app_exiting = False
base_dir = os.path.dirname(os.path.abspath(__file__))


def show_startup_error(message):
    """启动阶段出现致命问题时给用户明确提示，避免看起来像被直接杀掉。"""
    try:
        win32api.MessageBox(0, message, APP_NAME, win32con.MB_ICONERROR | win32con.MB_OK)
    except Exception:
        log_error(message)


def open_error_log():
    """优先打开有内容的错误日志，保证托盘按钮能直接定位到问题文件。"""
    ensure_error_log_files()
    target_log_file = APP_ERROR_LOG_FILE
    if os.path.exists(SYSTEM_MONITOR_ERROR_LOG_FILE) and os.path.getsize(APP_ERROR_LOG_FILE) == 0:
        target_log_file = SYSTEM_MONITOR_ERROR_LOG_FILE
    try:
        os.startfile(target_log_file)
    except Exception as e:
        log_error(f"Open error log failed: {e}")
        try:
            os.startfile(base_dir)
        except Exception:
            pass


def open_runtime_log():
    """打开运行日志，便于观察当前生效日志级别下的实时流程。"""
    ensure_error_log_files()
    try:
        os.startfile(APP_RUNTIME_LOG_FILE)
    except Exception as e:
        log_error(f"Open runtime log failed: {e}")
        try:
            os.startfile(base_dir)
        except Exception:
            pass


def set_app_identity():
    """设置应用身份，方便托盘与开始菜单统一显示为 ldc小助手。"""
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception as e:
        log_error(f"Set AppUserModelID failed: {e}")


def ensure_single_instance():
    """通过系统互斥锁确保同一时间只能运行一个 ldc小助手。"""
    global app_mutex
    app_mutex = win32event.CreateMutex(None, False, MUTEX_NAME)
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        win32api.MessageBox(0, f"{APP_NAME} 已经在运行。", APP_NAME, win32con.MB_ICONINFORMATION)
        sys.exit(0)


def ensure_app_icon():
    """生成托盘和开始菜单共用图标，避免没有独立软件标识。"""
    icon_path = os.path.join(base_dir, "ldc_helper.ico")
    if os.path.exists(icon_path):
        return icon_path

    # 用项目内生成的 ico 作为统一标识，这样托盘和快捷方式都能复用同一张图。
    image = Image.new("RGBA", (256, 256), (47, 86, 233, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((16, 16, 240, 240), radius=48, fill=(47, 86, 233, 255))
    draw.rounded_rectangle((40, 40, 216, 216), radius=36, outline=(255, 255, 255, 255), width=10)
    draw.text((58, 92), "LDC", fill=(255, 255, 255, 255))
    image.save(icon_path, format="ICO")
    return icon_path


def ensure_start_menu_shortcut(icon_path):
    """在开始菜单创建快捷方式，方便用户固定到开始菜单或搜索启动。"""
    start_menu_dir = os.path.join(os.environ["APPDATA"], "Microsoft", "Windows", "Start Menu", "Programs")
    shortcut_path = os.path.join(start_menu_dir, f"{APP_NAME}.lnk")
    pythonw_path = os.path.join(base_dir, ".venv", "Scripts", "pythonw.exe")

    if not os.path.exists(pythonw_path):
        pythonw_path = sys.executable

    # 已存在可用快捷方式时直接复用，避免被系统锁定时反复写入报错。
    if os.path.exists(shortcut_path):
        return start_menu_dir

    try:
        os.makedirs(start_menu_dir, exist_ok=True)
        shortcut = Dispatch("WScript.Shell").CreateShortcut(shortcut_path)
        shortcut.TargetPath = pythonw_path
        shortcut.Arguments = f'"{os.path.abspath(__file__)}"'
        shortcut.WorkingDirectory = base_dir
        shortcut.IconLocation = icon_path
        shortcut.Description = f"{APP_NAME} 托盘服务"
        shortcut.Save()
    except Exception as e:
        log_error(f"Create start menu shortcut failed: {e}")

    return start_menu_dir


class TrayIcon:
    """使用原生 Win32 托盘图标承载后台服务入口，避免额外依赖。"""

    def __init__(self, icon_path, start_menu_dir, exit_callback):
        self.icon_path = icon_path
        self.start_menu_dir = start_menu_dir
        self.exit_callback = exit_callback
        self.hwnd = None
        self.hicon = None
        self.class_name = "LdcXiaoZhuShouTrayWindow"

    def start(self):
        """在独立线程中运行托盘消息循环，避免阻塞主程序。"""
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        """通知托盘线程退出，并清理系统托盘图标。"""
        if self.hwnd:
            win32gui.PostMessage(self.hwnd, win32con.WM_CLOSE, 0, 0)

    def _run(self):
        """创建隐藏窗口并挂接托盘消息，供右键菜单使用。"""
        message_map = {
            TRAY_EVENT_ID: self._on_tray_event,
            win32con.WM_COMMAND: self._on_command,
            win32con.WM_DESTROY: self._on_destroy,
        }

        window_class = win32gui.WNDCLASS()
        window_class.hInstance = win32api.GetModuleHandle(None)
        window_class.lpszClassName = self.class_name
        window_class.lpfnWndProc = message_map

        try:
            win32gui.RegisterClass(window_class)
        except win32gui.error:
            pass

        self.hwnd = win32gui.CreateWindow(
            self.class_name,
            APP_NAME,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            window_class.hInstance,
            None,
        )

        self._create_tray_icon()
        win32gui.PumpMessages()

    def _create_tray_icon(self):
        """创建系统托盘图标，让后台服务有可见入口。"""
        if os.path.exists(self.icon_path):
            self.hicon = win32gui.LoadImage(
                0,
                self.icon_path,
                win32con.IMAGE_ICON,
                0,
                0,
                win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE,
            )
        else:
            self.hicon = win32gui.LoadIcon(0, win32con.IDI_APPLICATION)

        notify_id = (
            self.hwnd,
            0,
            win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP,
            TRAY_EVENT_ID,
            self.hicon,
            APP_NAME,
        )
        win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, notify_id)

    def _show_menu(self):
        """右键菜单提供常用入口，方便调试和运维。"""
        menu = win32gui.CreatePopupMenu()
        log_level_menu = win32gui.CreatePopupMenu()
        current_log_level = get_current_log_level()

        for command_id, level in TRAY_LOG_LEVEL_MENU_ITEMS.items():
            menu_flags = win32con.MF_STRING
            if level == current_log_level:
                menu_flags |= win32con.MF_CHECKED
            win32gui.AppendMenu(log_level_menu, menu_flags, command_id, level)

        win32gui.AppendMenu(menu, win32con.MF_STRING, TRAY_MENU_OPEN_START, "打开开始菜单目录")
        win32gui.AppendMenu(menu, win32con.MF_STRING, TRAY_MENU_VIEW_ERROR_LOG, "查看错误日志")
        win32gui.AppendMenu(menu, win32con.MF_STRING, TRAY_MENU_VIEW_RUNTIME_LOG, "查看运行日志")
        win32gui.AppendMenu(menu, win32con.MF_POPUP, log_level_menu, "日志级别")
        win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, "")
        win32gui.AppendMenu(menu, win32con.MF_STRING, TRAY_MENU_EXIT, "退出 ldc小助手")

        win32gui.SetForegroundWindow(self.hwnd)
        position = win32gui.GetCursorPos()
        win32gui.TrackPopupMenu(menu, win32con.TPM_LEFTALIGN, position[0], position[1], 0, self.hwnd, None)
        win32gui.PostMessage(self.hwnd, win32con.WM_NULL, 0, 0)

    def _on_tray_event(self, hwnd, msg, wparam, lparam):
        """统一处理托盘鼠标事件，保持交互简单稳定。"""
        if lparam in (win32con.WM_LBUTTONUP, win32con.WM_RBUTTONUP, win32con.WM_LBUTTONDBLCLK):
            self._show_menu()
        return 0

    def _on_command(self, hwnd, msg, wparam, lparam):
        """处理托盘菜单命令，避免把退出逻辑塞进消息循环。"""
        command_id = wparam & 0xFFFF
        if command_id == TRAY_MENU_OPEN_START:
            try:
                os.startfile(self.start_menu_dir)
            except Exception as e:
                log_error(f"Open start menu folder failed: {e}")
        elif command_id == TRAY_MENU_VIEW_ERROR_LOG:
            open_error_log()
        elif command_id == TRAY_MENU_VIEW_RUNTIME_LOG:
            open_runtime_log()
        elif command_id in TRAY_LOG_LEVEL_MENU_ITEMS:
            target_level = TRAY_LOG_LEVEL_MENU_ITEMS[command_id]
            applied_level = set_current_log_level(target_level)
            self._show_balloon("日志级别已生效", f"当前级别：{applied_level}")
        elif command_id == TRAY_MENU_EXIT:
            threading.Thread(target=self.exit_callback, daemon=True).start()
        return 0

    def _show_balloon(self, title, message):
        """通过托盘气泡提示反馈关键操作结果，避免打断当前使用。"""
        if not self.hwnd:
            return
        try:
            info_flag = getattr(win32gui, "NIIF_INFO", 1)
            notify_id = (
                self.hwnd,
                0,
                win32gui.NIF_INFO,
                TRAY_EVENT_ID,
                self.hicon,
                APP_NAME,
                message,
                1500,
                title,
                info_flag,
            )
            win32gui.Shell_NotifyIcon(win32gui.NIM_MODIFY, notify_id)
        except Exception as e:
            log_warning(f"Show tray balloon failed: {e}")

    def _on_destroy(self, hwnd, msg, wparam, lparam):
        """删除托盘图标，避免程序退出后残留空白图标。"""
        win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, (self.hwnd, 0))
        win32gui.PostQuitMessage(0)
        return 0


def delayed_play(delay=5):
    """等待播放器启动完成后再发送播放键，避免刚拉起时命令丢失。"""
    log_info(f"等待播放器初始化，延迟 {delay} 秒后执行播放命令")
    time.sleep(delay)
    log_info("开始执行延迟播放命令")
    pyautogui.press("playpause")


def on_message_received(data):
    """处理手机端发来的指令，当前主要包含媒体控制和脚本执行。"""
    log_debug(f"收到客户端数据：{data}")
    try:
        command_message = json.loads(data)

        if "command" in command_message:
            cmd = command_message["command"]
            msg = command_message.get("message", "")

            if cmd == 6:
                log_info(f"收到媒体控制命令：{msg}")
                if msg == "START":
                    if not is_media_player_running():
                        if launch_default_media_player():
                            threading.Thread(target=delayed_play, args=(8,), daemon=True).start()
                    else:
                        if not is_media_playing():
                            pyautogui.press("playpause")
                        else:
                            log_info("播放器已经处于播放状态，本次 START 命令已忽略")
                elif msg == "STOP":
                    if is_media_playing():
                        pyautogui.press("playpause")
                elif msg == "PREV":
                    pyautogui.press("prevtrack")
                elif msg == "NEXT":
                    pyautogui.press("nexttrack")
                elif msg == "VOL_UP":
                    pyautogui.press("volumeup")
                elif msg == "VOL_DOWN":
                    pyautogui.press("volumedown")
                return

        if "script" in command_message:
            script = command_message["script"]
            params = command_message.get("params")
            log_info("收到远程脚本执行请求")
            exec(script)
    except Exception as e:
        log_error(f"Error executing script/command: {e}")


def on_screen_locked():
    """锁屏时向手机端发送状态，保证远端能感知当前电脑状态。"""
    log_info("检测到系统锁屏")
    data = json.dumps({"command": 2, "message": ""})
    log_debug(f"发送锁屏状态：{data}")
    tcpServer.send_text(data)


def on_screen_unlocked():
    """解锁时恢复状态同步，便于手机端更新界面。"""
    log_info("检测到系统解锁")
    data = json.dumps({"command": 3, "message": ""})
    log_debug(f"发送解锁状态：{data}")
    tcpServer.send_text(data)


def on_tcp_connected():
    """新连接建立后补齐监控组件，避免客户端重连后状态丢失。"""
    log_info("客户端已连接，开始同步监控状态")
    if not computerMonitor.started:
        computerMonitor.start()
    systemMonitor.start()


def onTrans():
    """把本机剪贴板内容同步给手机端。"""
    log_info("触发剪贴板同步")
    content = getClipContent()
    text = json.dumps({"command": 1, "message": content})
    tcpServer.send_text(text)


def onRecordStart():
    """开始录音时通知手机端更新状态。"""
    log_info("开始录音")
    text = json.dumps({"command": 100, "message": "开始录音"})
    log_debug(f"发送录音开始状态：{text}")
    tcpServer.send_text(text)


def onRecordEnd():
    """结束录音时通知手机端回收录音状态。"""
    log_info("结束录音")
    text = json.dumps({"command": 101, "message": "结束录音"})
    log_debug(f"发送录音结束状态：{text}")
    tcpServer.send_text(text)


def stop_app():
    """集中处理退出逻辑，确保托盘退出时不会留下后台线程。"""
    global app_exiting
    if app_exiting:
        return
    app_exiting = True
    log_info(f"{APP_NAME} 开始退出")

    try:
        keyboard.unhook_all()
    except Exception as e:
        log_error(f"Keyboard cleanup failed: {e}")

    try:
        systemMonitor.stop()
    except Exception as e:
        log_error(f"System monitor stop failed: {e}")

    try:
        tcpServer.stop()
    except Exception as e:
        log_error(f"TCP server stop failed: {e}")

    try:
        if tray_icon:
            tray_icon.stop()
    except Exception as e:
        log_error(f"Tray stop failed: {e}")

    try:
        screenCapture.root.after(0, screenCapture.root.quit)
    except Exception:
        os._exit(0)


ensure_single_instance()
ensure_error_log_files()
sys.excepthook = install_error_hooks()
set_app_identity()
icon_path = ensure_app_icon()
start_menu_dir = ensure_start_menu_shortcut(icon_path)

computerMonitor = ComputerMonitor(on_screen_locked, on_screen_unlocked)
tcpServer = TcpServer()
systemMonitor = SystemMonitor(tcpServer)
keyboardListener = KeyboardListener(tcpServer)
screenCapture = ScreenCapture()

tcpServer.set_receive_listener(on_message_received)
tcpServer.connected_listener = on_tcp_connected
keyboardListener.set_screen_capture(screenCapture)

tray_icon = TrayIcon(icon_path, start_menu_dir, stop_app)
tray_icon.start()
log_info("托盘服务已启动")

try:
    tcpServer.start()
except Exception as e:
    error_message = (
        f"{APP_NAME} 启动失败，TCP 服务无法监听 {tcpServer.port} 端口。\n\n"
        f"错误信息：{e}\n\n"
        f"这通常是因为端口被占用，或当前环境不允许绑定该端口。"
    )
    log_error(f"TCP server startup failed: {e}\n{traceback.format_exc()}")
    show_startup_error(error_message)
    stop_app()
    sys.exit(1)

keyboardListener.listen_keyboard(onTrans, onRecordStart, onRecordEnd)
log_info("键盘监听已启动")
try:
    screenCapture.run_forever()
except Exception as e:
    log_error(f"Main loop exited unexpectedly: {e}\n{traceback.format_exc()}")
    stop_app()
    raise

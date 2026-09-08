import threading
import win32gui
import win32ts
from app_logging import log_error, log_info

# 显式定义常量，避免不同环境下 win32 模块暴露不一致。
WM_WTSSESSION_CHANGE = 0x02B1
WTS_SESSION_LOCK = 0x7
WTS_SESSION_UNLOCK = 0x8


class ComputerMonitor:
    def __init__(self, lock_callback, unlock_callback=None):
        self.lock_callback = lock_callback
        self.unlock_callback = unlock_callback
        self.started = False
        self.hwnd = None

    def _create_hidden_window(self):
        wc = win32gui.WNDCLASS()
        wc.lpfnWndProc = self._wnd_proc
        wc.lpszClassName = "CyberControllerMonitor"
        wc.hInstance = win32gui.GetModuleHandle(None)

        try:
            win32gui.RegisterClass(wc)
        except Exception:
            # 类可能在热加载后已存在，这里直接复用即可。
            pass

        self.hwnd = win32gui.CreateWindow(
            "CyberControllerMonitor",
            "CyberMonitor",
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            wc.hInstance,
            None,
        )

        try:
            win32ts.WTSRegisterSessionNotification(self.hwnd, win32ts.NOTIFY_FOR_THIS_SESSION)
        except Exception as e:
            log_error(f"ComputerMonitor register session notification failed: {e}")
            raise

        win32gui.PumpMessages()

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_WTSSESSION_CHANGE:
            if wparam == WTS_SESSION_LOCK:
                log_info("收到系统锁屏事件")
                if self.lock_callback:
                    threading.Thread(target=self.lock_callback, daemon=True).start()
            elif wparam == WTS_SESSION_UNLOCK:
                log_info("收到系统解锁事件")
                if self.unlock_callback:
                    threading.Thread(target=self.unlock_callback, daemon=True).start()

        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    def start(self):
        if self.started:
            return
        self.started = True
        monitor_thread = threading.Thread(target=self._create_hidden_window, daemon=True)
        monitor_thread.start()
        log_info("系统锁屏监控已启动")

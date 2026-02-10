import threading
import win32con
import win32gui
import win32ts
import time

# Define Win32 Constants explicitly to avoid AttributeError
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
			class_atom = win32gui.RegisterClass(wc)
		except Exception:
			# Class might already be registered if we reload
			pass
		
		self.hwnd = win32gui.CreateWindow(
			"CyberControllerMonitor", 
			"CyberMonitor", 
			0, 0, 0, 0, 0, 0, 0, 
			wc.hInstance, 
			None
		)
		
		# Register for Session Notifications (Lock/Unlock)
		win32ts.WTSRegisterSessionNotification(self.hwnd, win32ts.NOTIFY_FOR_THIS_SESSION)
		
		# Pump messages to keep the window alive and processing events
		win32gui.PumpMessages()

	def _wnd_proc(self, hwnd, msg, wparam, lparam):
		if msg == WM_WTSSESSION_CHANGE:
			if wparam == WTS_SESSION_LOCK:
				print("System Locked Detected (Win32 Event)")
				if self.lock_callback:
					# Run callback in a separate thread to not block the message loop
					threading.Thread(target=self.lock_callback).start()
			elif wparam == WTS_SESSION_UNLOCK:
				print("System Unlocked")
				if self.unlock_callback:
					threading.Thread(target=self.unlock_callback).start()
		
		return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

	def start(self):
		if self.started:
			return
		self.started = True
		# Win32 message loop must run in its own thread
		monitor_thread = threading.Thread(target=self._create_hidden_window, args=())
		monitor_thread.daemon = True
		monitor_thread.start()
		print("Win32 Event Monitor Started")

import io
import time

import keyboard

from app_logging import log_debug, log_info, log_warning


class KeyboardListener:
    def __init__(self, tcpServer):
        self.tcpServer = tcpServer
        self.t = 0
        self.c = 0
        self.key_state_map = {}
        self.screen_capture = None
        self.callback = None
        self.on_record_start = None
        self.on_record_end = None
        self.recording = False

    def set_screen_capture(self, screen_capture):
        self.screen_capture = screen_capture

    def listen_keyboard(self, callback, on_record_start=None, on_record_end=None):
        self.callback = callback
        self.on_record_start = on_record_start
        self.on_record_end = on_record_end
        self.recording = False
        keyboard.hook(self.onKeyEvent)

    def onImgCapture(self, pic):
        img_byte_arr = io.BytesIO()
        pic.save(img_byte_arr, format="JPEG")
        bytes_data = img_byte_arr.getvalue()
        self.tcpServer.send_img(bytes_data)
        if self.screen_capture:
            self.screen_capture.trigger_toast("截图已发送至手机")

    def isCtrlHolding(self):
        return (
            ("ctrl" in self.key_state_map and self.key_state_map["ctrl"] == "down")
            or ("left ctrl" in self.key_state_map and self.key_state_map["left ctrl"] == "down")
            or ("right ctrl" in self.key_state_map and self.key_state_map["right ctrl"] == "down")
        )

    def isAltHolding(self):
        return (
            ("alt" in self.key_state_map and self.key_state_map["alt"] == "down")
            or ("left alt" in self.key_state_map and self.key_state_map["left alt"] == "down")
            or ("right alt" in self.key_state_map and self.key_state_map["right alt"] == "down")
        )

    def isKeyHolding(self, key):
        return key in self.key_state_map and self.key_state_map[key] == "down"

    def onKeyEvent(self, key):
        key_name = (key.name or "").lower()
        self.key_state_map[key_name] = key.event_type

        if self.isAltHolding() and key.event_type == "down" and key_name == "a":
            if self.screen_capture:
                self.screen_capture.trigger_capture(self.onImgCapture)
            else:
                log_warning("截图模块尚未初始化，忽略本次 Alt + A 操作")

        if key.event_type == "down" and key_name == "c" and self.isCtrlHolding():
            if self.t == 0:
                self.t = time.time()
                self.c += 1
                log_debug(f"检测到 Ctrl + C 连击第 {self.c} 次，等待下一次输入")
                return

            if time.time() - self.t < 0.5:
                self.t = time.time()
                self.c += 1
                log_debug(f"检测到 Ctrl + C 连击第 {self.c} 次，继续等待")
            else:
                self.c = 0
                self.t = 0
                log_debug("Ctrl + C 连击超时，已重置计数")

            if self.c >= 2:
                self.c = 0
                log_info("检测到快捷复制操作，准备同步剪贴板")
                if self.callback:
                    self.callback()

        if key_name == "space":
            if key.event_type == "down" and self.isCtrlHolding():
                if not self.recording:
                    self.recording = True
                    log_info("检测到 Ctrl + Space，开始录音")
                    if self.on_record_start:
                        self.on_record_start()
            elif key.event_type == "up":
                if self.recording:
                    self.recording = False
                    log_info("检测到 Space 松开，结束录音")
                    if self.on_record_end:
                        self.on_record_end()

        if "ctrl" in key_name and key.event_type == "up" and self.recording:
            self.recording = False
            log_info("检测到 Ctrl 松开，结束录音")
            if self.on_record_end:
                self.on_record_end()

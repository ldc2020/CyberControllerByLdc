# -*- coding:utf-8 -*-
import tkinter
import os
import ctypes
from PIL import Image, ImageTk
from time import sleep
import mss
import mss.tools
from app_logging import log_debug, log_error, log_info, log_warning

class ScreenCapture:
    def __init__(self):
        # 尝试启用 Per-Monitor DPI Aware V2
        # 这种模式下，我们直接操作物理像素，避免了系统缩放带来的模糊和尺寸问题
        self.dpi_level = 0
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2) # 2 = PROCESS_PER_MONITOR_DPI_AWARE
            log_debug("SetProcessDpiAwareness(2) 调用成功")
            self.dpi_level = 2
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
                log_debug("SetProcessDPIAware() 调用成功")
                self.dpi_level = 1
            except Exception as e:
                log_warning(f"DPI 感知初始化失败：{e}")

        # 初始化 Tkinter root 但立即隐藏
        self.root = tkinter.Tk()
        self.root.withdraw()
        
        # 配置缩放因子
        if self.dpi_level == 2:
            # Per-Monitor 模式下，强制 Tkinter 使用 1.0 缩放，直接对应物理像素
            self.root.call('tk', 'scaling', 1.0)
            self.scale_factor = 1.0
        elif self.dpi_level == 1:
            # System Aware 模式下，获取系统缩放比例
            self.scale_factor = self.get_system_scale()
        else:
            self.scale_factor = 1.0

        log_debug(f"DPI 初始化完成，级别={self.dpi_level}，缩放因子={self.scale_factor}")

        self.sel = False
        self.callback = None
        self.lastDraw = None
        self.top = None
        
        # 绑定自定义事件以从主线程触发捕获
        self.root.bind('<<StartCapture>>', self._start_capture_main_thread)
        self.is_capturing = False

    def get_system_scale(self):
        """获取主显示器的系统缩放比例"""
        try:
            hDC = ctypes.windll.user32.GetDC(0)
            dpi_x = ctypes.windll.gdi32.GetDeviceCaps(hDC, 88) # LOGPIXELSX
            ctypes.windll.user32.ReleaseDC(0, hDC)
            return dpi_x / 96.0
        except Exception as e:
            log_warning(f"获取系统缩放比例失败：{e}")
            return 1.0

    def run_forever(self):
        """Run the main Tkinter loop. This blocks."""
        self.root.mainloop()

    def trigger_capture(self, callback):
        """Thread-safe method to trigger screenshot from another thread."""
        if self.is_capturing:
            log_debug("截图流程仍在进行中，忽略重复触发")
            return
        self.callback = callback
        self.root.event_generate('<<StartCapture>>', when='tail')

    def _start_capture_main_thread(self, event):
        """Actual start method running on main thread."""
        self.is_capturing = True
        self.start()

    def destroy_overlay(self):
        # 仅关闭覆盖窗口，保持 root 存活
        self.is_capturing = False
        if self.top:
            self.top.destroy()
            self.top = None

    def get_mouse_pos(self):
        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
        pt = POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y

    def start(self):
        # 使用 mss 进行可靠的多显示器捕获
        try:
            with mss.mss() as sct:
                # 获取鼠标位置
                mx, my = self.get_mouse_pos()
                
                # 查找鼠标所在的监视器
                target_mon = None
                
                # sct.monitors[0] 是所有监视器的组合
                # sct.monitors[1:] 是单个监视器
                for mon in sct.monitors[1:]:
                    # 检查鼠标是否在此监视器的范围内
                    # mon 字典包含: left, top, width, height
                    if (mon['left'] <= mx < mon['left'] + mon['width']) and \
                       (mon['top'] <= my < mon['top'] + mon['height']):
                        target_mon = mon
                        break
                
                # 如果未找到，则回退到主监视器（通常是索引 1）
                if not target_mon:
                    log_warning("鼠标未命中任何显示器区域，回退到主显示器")
                    target_mon = sct.monitors[1]
                
                tl = target_mon['left']
                tt = target_mon['top']
                width = target_mon['width']
                height = target_mon['height']
                
                log_debug(f"鼠标位置：({mx}, {my})")
                log_debug(f"目标显示器：{target_mon}")
                log_debug(f"物理像素几何信息：{width}x{height}+{tl}+{tt}")
                
                # 仅捕获目标监视器 (物理像素)
                sct_img = sct.grab(target_mon)
                
                # 转换为 PIL Image (mss 返回 BGRA, PIL 需要 RGB)
                self.image = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

                # 计算窗口几何数据
                # 如果是 PMv2 (Level 2)，我们直接使用物理像素，scale_factor 为 1.0
                # 如果是 System Aware (Level 1)，我们需要除以系统缩放比例转换为逻辑像素
                
                scale = self.scale_factor
                
                l_tl = int(tl / scale)
                l_tt = int(tt / scale)
                l_width = int(width / scale)
                l_height = int(height / scale)
                
                log_debug(f"截图窗口几何信息：{l_width}x{l_height}+{l_tl}+{l_tt}，缩放={scale}")

                # 创建覆盖仅目标监视器的 Toplevel 窗口
                self.top = tkinter.Toplevel(self.root)
                self.top.withdraw() # 初始隐藏
                self.top.overrideredirect(True) # 移除窗口装饰
                self.top.attributes('-topmost', True) # 保持窗口在最顶层
                self.top.attributes('-alpha', 1.0) # 确保不透明

                # 初始几何设置
                geo_str = f"{l_width}x{l_height}+{l_tl}+{l_tt}"
                self.top.geometry(geo_str)

                # 使用 Windows API 强制窗口位置
                try:
                    self.top.deiconify() # 显示窗口
                    self.top.update() # 强制完全更新以确保 HWND 有效
                    hwnd = self.top.winfo_id()
                    
                    # 定义 argtypes 以确保参数传递正确
                    SetWindowPos = ctypes.windll.user32.SetWindowPos
                    SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
                    SetWindowPos.restype = ctypes.c_bool
                    
                    HWND_TOPMOST = ctypes.c_void_p(-1)
                    SWP_SHOWWINDOW = 0x0040
                    
                    # 在 PMv2 模式下，SetWindowPos 期望物理坐标
                    # 在 System Aware 模式下，SetWindowPos 期望逻辑坐标
                    # 我们的 l_tl, l_tt 等变量已经根据模式处理过了
                    ret = SetWindowPos(ctypes.c_void_p(hwnd), HWND_TOPMOST, 
                                 l_tl, l_tt, 
                                 l_width, l_height, 
                                 SWP_SHOWWINDOW)
                    if not ret:
                         err = ctypes.windll.kernel32.GetLastError()
                         log_warning(f"SetWindowPos 调用失败，错误码：{err}")
                         # 如果 SetWindowPos 失败，回退到 geometry
                         self.top.geometry(geo_str)
                    else:
                         log_debug("SetWindowPos 调用成功")
                         
                except Exception as e:
                    log_warning(f"SetWindowPos 调用异常：{e}")
                    self.top.geometry(geo_str)

                self.top.focus_force() # 确保窗口获得焦点以进行关键事件

                # 图像处理
                # 如果 scale != 1.0 (即 System Aware 模式)，我们需要 resize 图片以匹配逻辑窗口
                # 如果 scale == 1.0 (即 PMv2 模式)，我们直接显示原图
                if abs(scale - 1.0) > 0.01:
                     self.photo_image = self.image.resize((l_width, l_height), Image.Resampling.LANCZOS)
                else:
                     self.photo_image = self.image

                self.photo = ImageTk.PhotoImage(self.photo_image)

                # 创建 Canvas
                self.canvas = tkinter.Canvas(self.top, bg='black', width=l_width, height=l_height, highlightthickness=0)
                
                self.canvas.create_image(0, 0, anchor=tkinter.NW, image=self.photo)
                self.canvas.pack(fill=tkinter.BOTH, expand=tkinter.YES)

                # 选择变量
                self.X = tkinter.IntVar(value=0)
                self.Y = tkinter.IntVar(value=0)
                
                # 绑定鼠标事件
                self.canvas.bind('<Button-1>', self.onLeftButtonDown)
                self.canvas.bind('<B1-Motion>', self.onLeftButtonMove)
                self.canvas.bind('<ButtonRelease-1>', self.onLeftButtonUp)
                
                # 绑定退出键（右键单击和 Escape）
                self.top.bind('<Button-3>', lambda e: self.destroy_overlay())
                self.top.bind('<Escape>', lambda e: self.destroy_overlay())

        except Exception as e:
            log_error(f"启动截图流程失败：{e}")
            self.is_capturing = False

    def onLeftButtonDown(self, event):
        self.X.set(event.x)
        self.Y.set(event.y)
        self.sel = True

    def onLeftButtonMove(self, event):
        if not self.sel:
            return
        
        # Delete previous rectangle
        if self.lastDraw:
            try:
                self.canvas.delete(self.lastDraw)
            except Exception:
                pass
        
        # Draw new rectangle
        self.lastDraw = self.canvas.create_rectangle(self.X.get(), self.Y.get(), event.x, event.y, outline='red', width=2)

    def onLeftButtonUp(self, event):
        self.sel = False
        if self.lastDraw:
            try:
                self.canvas.delete(self.lastDraw)
            except Exception:
                pass
            self.lastDraw = None

        # Calculate selection coordinates
        x1, x2 = sorted([self.X.get(), event.x])
        y1, y2 = sorted([self.Y.get(), event.y])

        # Ignore accidental small clicks
        if (x2 - x1) < 5 or (y2 - y1) < 5:
            return

        # Crop the image
        # Note: Since we use DPI awareness, event coordinates should map 1:1 to image coordinates
        pic = self.image.crop((x1, y1, x2, y2))
        
        # Call callback and destroy overlay
        if self.callback:
            self.callback(pic)
        
        self.destroy_overlay()

    def trigger_toast(self, message):
        log_info(f"提示消息：{message}")

    def are_capture(self, callback):
        # Deprecated: kept for compatibility if needed, but should use trigger_capture + run_forever pattern
        self.trigger_capture(callback)

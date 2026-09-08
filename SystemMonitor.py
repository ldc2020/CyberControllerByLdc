import threading
import time
import json
import psutil
import sys
import comtypes
from service import is_media_player_running, is_media_playing
from app_logging import log_system_monitor_error

class SystemMonitor:
    """
    Monitor system resources (CPU, Memory, Network) and send updates to the TCP server.
    """
    def __init__(self, tcp_server):
        """
        Initialize the SystemMonitor.
        
        Args:
            tcp_server: Instance of TcpServer to send data through.
        """
        self.tcp_server = tcp_server
        self.running = False
        self.thread = None
        self.media_player_was_running = False

    def start(self):
        """
        Start the monitoring thread.
        """
        if self.thread and self.thread.is_alive():
            return
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop)
        self.thread.daemon = True
        self.thread.start()
        # self._log("System Monitor Started")

    def stop(self):
        """
        Stop the monitoring thread.
        """
        self.running = False
        try:
            if self.thread and self.thread.is_alive():
                self.thread.join(timeout=2)
        except Exception:
            pass
        self.thread = None

    def _log_error(self, message):
        """
        Write errors to a file for debugging in pythonw mode.
        """
        log_system_monitor_error(message)
            
    def _monitor_loop(self):
        """
        Loop to gather system stats and send them every second.
        """
        try:
            # Initialize COM for this thread (Required for pycaw)
            try:
                comtypes.CoInitialize()
            except Exception as e:
                self._log_error(f"Failed to initialize COM: {e}")

            # Initialize network counters
            last_net = psutil.net_io_counters()
            last_time = time.time()

            while self.running:
                try:
                    # Get CPU percentage. interval=1 blocks for 1 second, providing our timing.
                    cpu_percent = psutil.cpu_percent(interval=1)

                    # Get Memory percentage
                    memory_percent = psutil.virtual_memory().percent

                    # Get Network IO
                    current_net = psutil.net_io_counters()
                    current_time = time.time()

                    time_delta = current_time - last_time
                    if time_delta <= 0:
                        time_delta = 1 # Avoid division by zero

                    bytes_sent = current_net.bytes_sent - last_net.bytes_sent
                    bytes_recv = current_net.bytes_recv - last_net.bytes_recv

                    # Calculate speed in Bytes/s
                    upload_speed = int(bytes_sent / time_delta)
                    download_speed = int(bytes_recv / time_delta)

                    # Update last values
                    last_net = current_net
                    last_time = current_time

                    # 先判断播放器进程是否还存在，避免刚退出时继续做播放态探测而刷错误日志。
                    process_running = False
                    try:
                        process_running = is_media_player_running()
                        if self.media_player_was_running and not process_running:
                            # Player was running, now closed -> Send signal
                            stop_msg = json.dumps({
                                "command": 7,
                                "message": "STOPPED"
                            })
                            self.tcp_server.send_text(stop_msg)

                        self.media_player_was_running = process_running
                    except Exception as e:
                        self._log_error(f"Error checking media process: {e}")

                    # Check actual playback status (for monitoring)
                    is_playing = False
                    if process_running:
                        try:
                            is_playing = is_media_playing()
                        except Exception as e:
                            self._log_error(f"Error checking playback status: {e}")

                    # Construct data payload
                    data = {
                        "cpu": cpu_percent,
                        "memory": memory_percent,
                        "upload_speed": upload_speed,
                        "download_speed": download_speed,
                        "media_running": is_playing
                    }

                    # Wrap in command structure (Command 102 for System Stats)
                    message = json.dumps({
                        "command": 102,
                        "message": data
                    })

                    # Send data if a client is connected
                    # Check if clientSocket exists and is open (basic check, send_text handles errors)
                    if hasattr(self.tcp_server, 'clientSocket') and self.tcp_server.clientSocket:
                         self.tcp_server.send_text(message)

                except Exception as e:
                    self._log_error(f"Error in SystemMonitor loop: {e}")
                    # Don't crash the thread, just wait a bit and retry
                    time.sleep(1)
        finally:
            self.running = False
            self.thread = None
            try:
                comtypes.CoUninitialize()
            except:
                pass

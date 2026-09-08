import os
import socket
import threading
import json
from app_logging import log_debug, log_error, log_info, log_warning

class TcpServer:
    def __init__(self):
        self.port=self._resolve_port()#设置端口
        self.HEAD_LEN=8
        self.bind_ip = "0.0.0.0"
        self.tcpServerSocket=None
        self.connected_listener = None
        self.receive_listener = None
        self.clientSocket = None
        self.server_threading = None
        self.running = False

    def set_receive_listener(self,receive_listener):
        self.receive_listener = receive_listener

    def _resolve_port(self):
        """优先读取环境变量，其次使用避开系统保留范围的默认端口。"""
        raw_port = os.environ.get("LDC_HELPER_PORT", "2333")
        try:
            port = int(raw_port)
            if 1 <= port <= 65535:
                return port
        except (TypeError, ValueError):
            pass
        log_error(f"Invalid LDC_HELPER_PORT: {raw_port}, fallback to 2333")
        return 2333

    def _close_client_socket(self):
        """关闭当前客户端连接，避免断开重连时残留旧 socket。"""
        if self.clientSocket:
            try:
                self.clientSocket.close()
            except OSError:
                pass
            self.clientSocket = None

    def _recv_exact(self, size):
        """按指定长度读取数据，避免 TCP 分包导致读取不完整。"""
        chunks = []
        remaining = size
        while self.running and remaining > 0:
            chunk = self.clientSocket.recv(remaining)
            if not chunk:
                return b""
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _create_server_socket(self):
        """延迟创建并绑定监听 socket，避免构造阶段异常直接杀掉整个进程。"""
        sock = socket.socket()
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((self.bind_ip, self.port))
            sock.listen(5)
        except OSError:
            sock.close()
            raise
        self.tcpServerSocket = sock
        log_info(f"TCP 服务开始监听，地址 {self.bind_ip}:{self.port}")

    def server(self):
        while self.running:
            log_debug("TCP 服务正在等待客户端连接")
            try:
                self.clientSocket, addr = self.tcpServerSocket.accept()
            except OSError as e:
                if self.running:
                    log_error(f"TcpServer accept failed: {e}")
                break
            log_info(f"客户端已连接：{addr}")
            if self.connected_listener:
                try:
                    self.connected_listener()
                except Exception as e:
                    log_error(f"TcpServer connected_listener failed: {e}")

            while self.running:
                try:
                    head_data=self._recv_exact(self.HEAD_LEN)
                    if not len(head_data)==8:
                        if head_data:
                            log_warning(f"TcpServer bad package head: {head_data}")
                        else:
                            log_info("客户端已主动断开连接")
                        break
                    body_len = self.get_length_from_head_data(head_data)
                    body_data = self._recv_exact(body_len)
                    if not body_len==len(body_data):
                        log_warning(f"TcpServer bad package body length: expected={body_len}, actual={len(body_data)}")
                        break
                    data_type = self.get_type_from_head_data(head_data)

                    if data_type == 1:#test/json data
                        text = body_data.decode()
                        log_debug(f"收到文本数据：{text}")
                        if not text:
                            break
                        if self.receive_listener:
                            try:
                                self.receive_listener(text)
                            except Exception as e:
                                log_error(f"TcpServer receive_listener failed: {e}")
                    elif data_type == 2:#image data
                        pass

                except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, OSError) as e:
                    if self.running:
                        log_warning(f"TcpServer connection error: {e}")
                    break

            self._close_client_socket()

        try:
            if self.tcpServerSocket:
                self.tcpServerSocket.close()
        except OSError:
            pass
        self.tcpServerSocket = None

    def get_length_from_head_data(self,head_data):
        if(not len(head_data)==8):
            return
        ch1 = head_data[4] & 0x00FF;
        ch2 = head_data[5] & 0x00FF;
        ch3 = head_data[6] & 0x00FF;
        ch4 = head_data[7] & 0x00FF;
        return ((ch1 << 24) + (ch2 << 16) + (ch3 << 8) + (ch4 << 0));

    def get_type_from_head_data(self,head_data):
        if(not len(head_data)==8):
            return
        ch1 = head_data[0] & 0x00FF;
        ch2 = head_data[1] & 0x00FF;
        ch3 = head_data[2] & 0x00FF;
        ch4 = head_data[3] & 0x00FF;
        return ((ch1 << 24) + (ch2 << 16) + (ch3 << 8) + (ch4 << 0));


    def start(self): 
        """启动服务线程；如果已在运行则直接复用当前实例。"""
        if self.server_threading and self.server_threading.is_alive():
            return True
        self._create_server_socket()
        self.running = True
        self.server_threading = threading.Thread(target=self.server, args=())
        self.server_threading.daemon = True
        self.server_threading.start()
        return True

    def restart(self):
        """仅关闭当前连接，让监听线程自动回到等待连接状态。"""
        self._close_client_socket()

    def stop(self):
        """停止监听并关闭所有 socket，供托盘退出时安全清理。"""
        self.running = False
        self._close_client_socket()
        try:
            if self.tcpServerSocket:
                self.tcpServerSocket.close()
        except OSError:
            pass
        self.tcpServerSocket = None

    def send_data(self, data):
        if not self.clientSocket:
            return
        try:
            self.clientSocket.send(data)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, OSError) as e:
            log_warning(f"TcpServer send failed: {e}")
            self.restart()
    def send_img(self, bytes_data):
        data = self.wrapper_data(2,bytes_data)
        self.send_data(data)
  
    def send_text(self, text):
        data = self.wrapper_data(1,text.encode())
        self.send_data(data)
    
    def wrapper_data(self,data_type,body_data):
        # Reduced logging for performance and cleanliness
        # print("data_type:",data_type)
        # print("body_data len:",len(body_data))


        type_bytes=data_type.to_bytes(4,'big')
        # print("type_bytes:",type_bytes)
        body_len = len(body_data)

        body_len_bytes = body_len.to_bytes(4,'big')
        # print("body_len_bytes:",body_len_bytes)

        head_data = type_bytes + body_len_bytes
        # print("head_data:",head_data)

        data = head_data+body_data
        return data

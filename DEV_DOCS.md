# 开发文档

## 更新日志

- **2026-08-09**:
  - **修复 ldc小助手 启动即退出问题**:
    - 排查确认 Windows 当前将 `2233` 划入了 TCP 排除端口范围 `2194-2293`，导致服务端在启动阶段绑定端口时直接报 `WinError 10013`。
    - `TcpServer.py` 调整为延迟创建监听 socket，避免在构造函数阶段因为端口绑定失败直接退出进程。
    - 默认监听端口改为 `2333`，避开当前系统保留端口范围。
    - 新增环境变量 `LDC_HELPER_PORT`，允许按需覆盖监听端口，便于和手机端保持一致。
    - `Controller.pyw` 启动阶段新增错误提示与异常日志，端口绑定失败时会明确弹窗，而不是看起来像“启动后被杀掉”。
    - `SystemMonitor.py` 修复重复启动监控线程的问题，避免长时间运行后出现 `can't start new thread`。

- **2026-02-04**:
  - **新增 ldc小助手 托盘化入口**:
    - 将 `Controller.pyw` 包装为单实例后台小程序，应用名称统一显示为 `ldc小助手`。
    - 启动时自动创建托盘图标，右键可打开开始菜单目录、查看错误日志或退出程序。
    - 启动时自动生成开始菜单快捷方式 `ldc小助手.lnk`，便于搜索启动和手动固定到开始菜单。
    - 新增单实例互斥锁，重复点击启动入口时不会再创建第二个后台实例。
    - 运行时会自动生成 `ldc_helper.ico` 作为托盘和开始菜单共用图标。
    - 新增应用级错误日志 `ldc_helper_error.log`，并保留 `monitor_error.log` 作为系统监控模块错误日志。
    - 持久化日志按 `error` 级别记录，普通运行信息仍通过控制台输出，不写入日志文件。
    - 新增共享日志模块 `app_logging.py`，统一接管 `Controller.pyw`、`TcpServer.py`、`ComputerMonitor.py`、`service.py` 和 `SystemMonitor.py` 的错误日志写入。
  - **优化服务退出与重连稳定性**:
    - 重构 `TcpServer.py` 的连接循环，断开连接后不再重复拉起监听线程，而是回到等待连接状态。
    - 新增 `stop()` 与 socket 清理逻辑，便于托盘退出时安全结束后台服务。
    - 新增定长接收逻辑，避免 TCP 分包导致包头/包体读取不完整。
  - **优化截屏翻译功能**:
    - **多显示器智能支持**: 实现了基于鼠标位置的屏幕检测。
      - 当鼠标位于主屏时，截屏窗口仅在主屏弹出。
      - 当鼠标位于副屏时，截屏窗口仅在副屏弹出。
      - 避免了跨屏幕的大白框遮挡，提升了多屏协作体验。
    - **DPI 缩放与定位修复**: 
      - **DPI 适配策略**: 从 `SetProcessDpiAwarenessContext(-4)` 调整为 `SetProcessDpiAwareness(2)`，彻底解决了副屏截图缩放/模糊问题。
      - **定位增强**: 引入 `geometry` 预定位机制，解决了副屏截图偶发跳回主屏的问题。
    - **快捷键变更**: 截屏触发快捷键由 `Caps Lock + A` 变更为 `Alt + A`。
    - **交互优化**: 修复了截屏窗口卡死、无法退出的问题（增加了 `trigger_toast` 避免崩溃）。现在可以通过右键点击或按下 `Esc` 键退出截屏模式。
    - **代码规范**: 完成了核心模块的中文注释覆盖。
  - **新增多媒体控制功能**:
    - 支持通过 TCP 指令控制音乐播放器。
    - 指令格式: `{"command": 6, "message": "ACTION"}`
    - 支持的动作: `START` (播放/暂停), `STOP` (停止), `PREV` (上一首), `NEXT` (下一首), `VOL_UP` (音量+), `VOL_DOWN` (音量-)。
    - **智能启动策略**: 当发送 `START` 且无播放器运行时，系统会自动扫描注册表（App Paths/Uninstall Keys）查找并启动 QQ 音乐、网易云音乐等，并在 8 秒后自动开始播放。
    - **状态反馈**: 当媒体播放器被关闭时，自动向手机端发送通知 `{"command": 7, "message": "STOPPED"}`。
  - **修复语音输入问题**:
    - 修复了手机端语音输入文字无法在电脑端光标处上屏的问题。
    - 解决方案：采用“剪贴板 + Ctrl+V”模拟粘贴的方式，完美支持中文及特殊字符输入。
  - **系统稳定性**:
    - 修复了 `start_server.vbs` 在后台运行时因 `sys.stdout` 不可用导致的崩溃问题。
    - 修复了 `Tkinter` 线程安全问题（"main thread is not in main loop"），重构了 `ScreenCapture` 类的事件处理机制。

- **2026-02-01**:
  - **新增系统监控功能**:
    - 实时获取 CPU 使用率、内存使用率、网络上传/下载速率、媒体播放器状态。
    - 实现秒级更新，并通过 TCP 发送到客户端。
    - 数据格式：`{"command": 102, "message": {"cpu": 25.5, "memory": 60.2, "upload_speed": 1024, "download_speed": 2048, "media_running": true}}` (速率单位: Bytes/s)
    - **字段说明**: `media_running` 仅在检测到播放器**正在播放**音频时为 `true`，暂停或关闭时均为 `false`。
    - 新增依赖 `psutil`, `pycaw`, `comtypes`。

- **2026-01-30**:
  - **新增按键监听功能 (Alt + .)**：
    - 在 `KeyboardListener.py` 中实现了对 `Alt + .` 组合键的监听。
    - **按下**时：发送 `{"command": 100, "message": "开始录音"}`
    - **松开**时：发送 `{"command": 101, "message": "结束录音"}`
    - 包含状态保护，防止按住不放时重复触发“开始录音”。
  - **新增开机启动支持**：
    - 优化 `start_server.vbs`：增加了路径自适应功能，无论从哪里调用都能正确定位到 `cybercontroller.bat`。
    - 自动配置：通过 PowerShell 命令在“启动”文件夹中创建了快捷方式 `CyberController.lnk`。
  - **新增键盘控制功能**：
    - 优化 `KeyboardManager.py`：新增 `press_hotkey(*keys)` 函数，方便发送组合键（如 `Alt+.`）。
  - 修复 `ComputerMonitor.py` 在后台运行时反复弹窗的问题。
    - 原因：`subprocess.check_output` 调用 `TASKLIST` 命令时，默认会创建控制台窗口。在 `pythonw.exe` 模式下，这会导致每隔 2 秒闪烁一次黑框。
    - 修复：添加了 `creationflags=0x08000000` (CREATE_NO_WINDOW) 参数，禁止创建子进程窗口。
  - 新增 `start_server.vbs` 启动脚本。
    - 功能：彻底隐藏启动时的控制台窗口。双击 `start_server.vbs` 即可无声无息地启动服务。

- **2026-01-29**:
  - 修复 `cybercontroller.bat` 启动失效问题。
    - 原因：原脚本使用了全局 `pythonw`，导致缺少依赖。
    - 修复：修改脚本以强制使用项目内的虚拟环境 (`.\.venv\Scripts\pythonw.exe`)。
    - 优化：同步更新了 `Controller.pyw` 确保代码一致。
  - 修复 `Controller.py` 启动崩溃问题。
    - 修改 `TcpServer.py`: 优化 IP 获取逻辑，避免因网络环境不同导致的 `IndexError: list index out of range`。现在会自动获取本机有效 IP 或回退到 `0.0.0.0`。
  - 修复 `ModuleNotFoundError: No module named 'win32api'` 错误。
    - 新增依赖: `pywin32` (用于Windows API调用)
  - 修复 `ModuleNotFoundError: No module named 'PIL'` 错误。
    - 新增依赖: `Pillow` (用于图像处理/截图功能)
    - 新增依赖: `pyautogui` (用于屏幕控制功能)
  - 已生成 `requirements.txt` 以管理项目依赖

## 远程控制指令参考

### 指令参考
服务端支持接收以下 JSON 格式指令（通过 TCP 发送）：
- `{"script": "python_code", "params": [...]}`: 执行任意 Python 代码
- `{"command": 1, "message": "content"}`: 剪贴板内容同步
- `{"command": 6, "message": "START"}`: 媒体控制 (START/STOP/PREV/NEXT/VOL_UP/VOL_DOWN)
- `{"command": 7, "message": "STOPPED"}`: 媒体播放器已关闭 (服务端 -> 客户端)
- `{"command": 100, "message": "开始录音"}`: 按下 Ctrl+Space 发送
- `{"command": 101, "message": "结束录音"}`: 松开 Ctrl+Space 发送

### 7. 开发注意事项
- **Controller.pyw 同步**: 修改 `Controller.py` 后，请务必同步更新 `Controller.pyw`，因为 bat 脚本默认运行的是 `.pyw` 文件（无控制台窗口模式）。
- **管理员权限**: 键盘监控功能需要管理员权限运行。
- **日志**: 为了保持整洁，已移除了 TcpServer 中详细的数据包日志。

### 8. 发送键盘组合键 (如 Ctrl + Space)
使用 `KeyboardManager.press_hotkey('ctrl', 'space')` 可以模拟发送组合键。

### 9. 监控键盘组合键 (Ctrl + Space)
在 `KeyboardListener.py` 中实现了对 `Ctrl + Space` 的监听逻辑：
- 按下时触发 `onRecordStart` 回调
- 松开时触发 `onRecordEnd` 回调
- 安全机制：如果 `Ctrl` 键提前松开，也会触发结束回调。

由于 `Controller.py` 支持执行远程 Python 脚本，你可以通过发送 JSON 指令来模拟按键。

**方法 1：使用 `KeyboardManager` (推荐，底层 API)**

发送以下 JSON 数据包：
```json
{
  "script": "press_hotkey('alt', '.')",
  "params": null
}
```
*注：`press_hotkey` 是本次更新新增的便捷函数。*

**方法 2：使用 `pyautogui` (跨平台库)**

```json
{
  "script": "pyautogui.hotkey('alt', '.')",
  "params": null
}
```

## 环境配置与故障排除

### 常见错误：ModuleNotFoundError

如果你遇到 `ModuleNotFoundError: No module named 'keyboard'` 或 `win32api` 等类似错误，通常是因为你的运行环境与项目依赖环境不一致。

**解决方案：**

1.  **确保激活了虚拟环境**：
    在终端中，确保你看到了 `(.venv)` 前缀。如果未激活，请运行：
    ```powershell
    # Windows
    .\.venv\Scripts\activate
    ```
    *注意：在 IDE 中，如果你之前已经打开了终端，新安装的依赖可能不会立即生效，或者环境变量未更新。尝试**关闭并重新打开终端**。*

2.  **安装依赖**：
    确保所有依赖都已安装到当前环境中：
    ```bash
    pip install -r requirements.txt
    ```

3.  **检查 Python 解释器**：
    如果你在 IDE (如 VS Code/Trae) 中运行，请确保右下角或命令面板中选择的 Python 解释器是项目目录下的 `.venv` 环境，而不是全局 Python。

### 运行问题：程序无反应或报错

1.  **管理员权限 (重要!)**：
    本项目使用了 `keyboard` 库来监听全局键盘事件。在 Windows 上，这通常需要**管理员权限**。
    *   如果你的 IDE 没有以管理员身份运行，程序可能会启动失败，或者无法捕获按键。
    *   **尝试方法**：右键点击 IDE 图标 -> "以管理员身份运行"，然后再运行代码。

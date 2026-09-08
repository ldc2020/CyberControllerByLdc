# CyberControllerServer

这是一个运行在 Windows 上的本地辅助服务，负责接收手机端指令并执行剪贴板同步、媒体控制、系统监控、键盘监听和截图等能力。

## 运行方式

推荐使用以下任一方式启动：

```powershell
.\start_server.vbs
```

或在终端中直接运行，便于查看调试输出：

```powershell
.\.venv\Scripts\python.exe .\Controller.pyw
```

## 日志说明

- `ldc_helper_runtime.log`：统一运行日志，支持 `DEBUG / INFO / WARNING / ERROR`
- `ldc_helper_error.log`：主程序错误日志
- `monitor_error.log`：系统监控线程错误日志
- 所有日志均采用“最新在最上面”的写入方式

如果需要查看普通调试输出，可以直接打开 `ldc_helper_runtime.log`。如果使用终端运行 `Controller.pyw`，日志也会同步输出到控制台。

### 热更新日志级别

程序运行中可通过托盘菜单直接切换日志级别，无需重启：

- 右键托盘图标
- 鼠标悬停到“日志级别”
- 点击 `DEBUG / INFO / WARNING / ERROR`
- 点击后立即生效，并弹出托盘提示

支持的级别有：

- `DEBUG`
- `INFO`
- `WARNING`
- `ERROR`

程序会每秒检查一次配置变更，保存文件后即可生效。

## 本次修复

2026-09-08：

- 修复播放器关闭后 `ldc_helper_error.log` 持续刷 `process no longer exists` 的问题
- 在系统监控中增加短路判断：播放器进程不存在时，不再继续执行播放状态检测
- 在音频会话遍历中忽略播放器刚退出时的瞬时进程失效异常，避免把预期内状态抖动记成错误
- 新增统一运行日志 `ldc_helper_runtime.log`
- 新增托盘二级菜单日志级别切换，运行中调整级别无需重启程序
- 托盘菜单新增“查看运行日志”入口，并移除手动修改日志配置的操作入口

## 依赖安装

```powershell
pip install -r .\requirements.txt
```

import json
import os
import sys
import threading
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_RUNTIME_LOG_FILE = os.path.join(BASE_DIR, "ldc_helper_runtime.log")
APP_ERROR_LOG_FILE = os.path.join(BASE_DIR, "ldc_helper_error.log")
SYSTEM_MONITOR_ERROR_LOG_FILE = os.path.join(BASE_DIR, "monitor_error.log")
LOG_CONFIG_FILE = os.path.join(BASE_DIR, "log_config.json")
MAX_LOG_LINES = 50000
DEFAULT_LOG_LEVEL = "ERROR"
LOG_LEVEL_PRIORITY = {
    "DEBUG": 10,
    "INFO": 20,
    "WARNING": 30,
    "ERROR": 40,
}
CONFIG_CHECK_INTERVAL_SECONDS = 1
LOG_WRITE_LOCK = threading.Lock()
LOG_CONFIG_LOCK = threading.Lock()
_current_log_level = DEFAULT_LOG_LEVEL
_last_config_check_at = 0.0
_last_config_mtime = None


def _normalize_log_level(level):
    """把外部传入的日志级别规整成受支持的标准值。"""
    normalized_level = str(level or "").strip().upper()
    return normalized_level if normalized_level in LOG_LEVEL_PRIORITY else DEFAULT_LOG_LEVEL


def _build_log_lines(level, message):
    """统一生成带时间戳和级别前缀的日志行。"""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    message_lines = str(message).splitlines() or [""]
    return [f"[{timestamp}] {level} {line}\n" for line in message_lines]


def _write_log_file(file_path, level, message):
    """把日志写入指定文件，采用最新日志置顶的方式，便于直接打开定位。"""
    try:
        entry_lines = _build_log_lines(level, message)
        with LOG_WRITE_LOCK:
            existing_lines = []
            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8") as log_file:
                    existing_lines = log_file.readlines()
            merged_lines = (entry_lines + existing_lines)[:MAX_LOG_LINES]
            with open(file_path, "w", encoding="utf-8") as log_file:
                log_file.writelines(merged_lines)
    except Exception:
        pass


def _emit_console(level, message):
    """在有控制台时同步输出，兼容 python.exe 调试模式。"""
    try:
        console = getattr(sys, "stdout", None) or getattr(sys, "__stdout__", None)
        if not console:
            return
        for line in _build_log_lines(level, message):
            console.write(line)
        console.flush()
    except Exception:
        pass


def _read_log_level_from_config():
    """从配置文件读取日志级别，缺失或非法时回退到默认值。"""
    try:
        with open(LOG_CONFIG_FILE, "r", encoding="utf-8") as config_file:
            config_data = json.load(config_file)
        return _normalize_log_level(config_data.get("log_level"))
    except Exception:
        return DEFAULT_LOG_LEVEL


def _persist_log_level(level):
    """把当前日志级别写回配置文件，保证下次启动仍能沿用。"""
    try:
        config_data = {
            "log_level": _normalize_log_level(level)
        }
        with open(LOG_CONFIG_FILE, "w", encoding="utf-8") as config_file:
            json.dump(config_data, config_file, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _refresh_log_level_if_needed(force=False):
    """按固定检查间隔热加载日志级别配置，避免每次写日志都频繁读文件。"""
    global _current_log_level, _last_config_check_at, _last_config_mtime

    current_time = time.monotonic()
    if not force and current_time - _last_config_check_at < CONFIG_CHECK_INTERVAL_SECONDS:
        return _current_log_level

    with LOG_CONFIG_LOCK:
        current_time = time.monotonic()
        if not force and current_time - _last_config_check_at < CONFIG_CHECK_INTERVAL_SECONDS:
            return _current_log_level

        _last_config_check_at = current_time
        current_mtime = os.path.getmtime(LOG_CONFIG_FILE) if os.path.exists(LOG_CONFIG_FILE) else None
        if not force and current_mtime == _last_config_mtime:
            return _current_log_level

        previous_level = _current_log_level
        _current_log_level = _read_log_level_from_config()
        _last_config_mtime = current_mtime

        if previous_level != _current_log_level:
            change_message = f"日志级别已热更新为 {_current_log_level}"
            _write_log_file(APP_RUNTIME_LOG_FILE, "INFO", change_message)
            _emit_console("INFO", change_message)

        return _current_log_level


def _should_write_runtime_log(level):
    """根据当前热加载后的日志级别，判断是否需要写入运行日志。"""
    active_level = _refresh_log_level_if_needed()
    return LOG_LEVEL_PRIORITY[level] >= LOG_LEVEL_PRIORITY[active_level]


def _log_runtime(level, message):
    """写运行日志，并在有控制台时同步输出。"""
    if _should_write_runtime_log(level):
        _write_log_file(APP_RUNTIME_LOG_FILE, level, message)
        _emit_console(level, message)


def log_debug(message):
    """记录调试级别日志，适合排查流程细节。"""
    _log_runtime("DEBUG", message)


def log_info(message):
    """记录信息级别日志，适合记录关键流程状态。"""
    _log_runtime("INFO", message)


def log_warning(message):
    """记录警告级别日志，适合记录可恢复异常和边界情况。"""
    _log_runtime("WARNING", message)


def log_error(message):
    """记录主程序和通用模块错误日志，同时进入运行日志。"""
    _write_log_file(APP_ERROR_LOG_FILE, "ERROR", message)
    _log_runtime("ERROR", message)


def log_system_monitor_error(message):
    """记录系统监控专用错误日志，同时进入运行日志便于统一排查。"""
    _write_log_file(SYSTEM_MONITOR_ERROR_LOG_FILE, "ERROR", message)
    _log_runtime("ERROR", message)


def get_current_log_level():
    """获取当前生效的日志级别，供界面或调试逻辑展示。"""
    return _refresh_log_level_if_needed()


def set_current_log_level(level):
    """立即切换日志级别并持久化配置，供托盘菜单等交互入口调用。"""
    global _current_log_level, _last_config_check_at, _last_config_mtime

    ensure_log_config_file()
    normalized_level = _normalize_log_level(level)

    with LOG_CONFIG_LOCK:
        previous_level = _current_log_level
        persisted = _persist_log_level(normalized_level)
        _current_log_level = normalized_level
        _last_config_check_at = time.monotonic()
        _last_config_mtime = os.path.getmtime(LOG_CONFIG_FILE) if os.path.exists(LOG_CONFIG_FILE) else None

    if previous_level != normalized_level:
        change_message = f"日志级别已切换为 {normalized_level}"
        _write_log_file(APP_RUNTIME_LOG_FILE, "INFO", change_message)
        _emit_console("INFO", change_message)

    if not persisted:
        log_error(f"Persist log level failed, fallback to in-memory level: {normalized_level}")

    return normalized_level


def ensure_log_config_file():
    """提前生成日志配置文件，便于运行中直接修改日志级别。"""
    if os.path.exists(LOG_CONFIG_FILE):
        return
    try:
        config_data = {
            "log_level": DEFAULT_LOG_LEVEL
        }
        with open(LOG_CONFIG_FILE, "w", encoding="utf-8") as config_file:
            json.dump(config_data, config_file, ensure_ascii=False, indent=2)
    except Exception:
        pass


def ensure_error_log_files():
    """提前创建日志相关文件，确保托盘菜单和热更新配置都可直接使用。"""
    for file_path in (APP_ERROR_LOG_FILE, SYSTEM_MONITOR_ERROR_LOG_FILE, APP_RUNTIME_LOG_FILE):
        if not os.path.exists(file_path):
            try:
                with open(file_path, "w", encoding="utf-8") as log_file:
                    log_file.write("")
            except Exception:
                pass
    ensure_log_config_file()
    _refresh_log_level_if_needed(force=True)


def install_error_hooks():
    """注册全局异常钩子，让 pythonw 模式下的未捕获异常也能落盘。"""
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            return
        log_error(f"Unhandled exception: {exc_value}")

    def handle_thread_exception(args):
        log_error(f"Unhandled thread exception: {args.exc_value}")

    threading.excepthook = handle_thread_exception
    return handle_exception

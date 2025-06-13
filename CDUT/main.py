"""
Program for HAB Transceiver.

This program is used to turn a MicroPython board into a smart
Configurable Data Transfer Unit for HC-12 transceiver module. 

It provides Transparent Data Bridge, Runtime AT Command Control,
Persistent Configuration and Automatic Mode Switching.

Author: BG7ZDQ
Date: 2025/06/12 
Version: 0.0.1 
LICENSE: GNU General Public License v3.0
"""

import sys
import time
import select
from machine import UART, Pin

""" 参数定义 """
# 允许的波特率与信道
VALID_BAUD_RATES = {2400, 9600, 38400, 115200}
VALID_CHANNELS = {f"{i:03d}" for i in range(1, 17)}

# AT 参数定义
AT_MODE_ENTRY_DELAY_S = 0.05  # 进入AT模式需要的稳定时间
AT_MODE_EXIT_DELAY_S = 0.1    # 退出AT模式后模块重启时间
AT_CMD_INTERVAL_S = 0.1       # 发送AT指令后的等待时间

# 硬件引脚定义
CTRL_PIN = Pin(6, Pin.OUT)
UART_TX_PIN = Pin(4)
UART_RX_PIN = Pin(5)
UART_ID = 1

# AT指令模式固定通信参数
AT_MODE_BAUD_RATE = 9600

# 配置文件名
CONFIG_FILE = "config.ini"

# 运行状态
state = True

""" 函数定义 """
# 验证波特率是否有效
def is_valid_baud(baud):
    return baud in VALID_BAUD_RATES

# 验证信道是否有效
def is_valid_channel(chan):
    return chan in VALID_CHANNELS

# 从 config.ini 读取配置
def read_config():
    baud = None
    chan = None
    valid = True

    try:
        # 读取配置文件
        with open(CONFIG_FILE, "r") as f:
            for line in f:
                line = line.strip()

                # 处理 baud 参数
                if line.startswith("baud="):
                    # 提取并验证波特率是否有效
                    try:
                        val = int(line.split("=")[1])
                        if is_valid_baud(val):
                            baud = val
                        else:
                            valid = False
                    # 解析失败也视为无效
                    except ValueError:
                        valid = False

                # 处理 chan 参数
                elif line.startswith("chan="):
                    try:
                        val = line.split("=")[1]
                        if is_valid_channel(val):
                            chan = val
                        else:
                            valid = False
                    # 解析失败也视为无效
                    except ValueError:
                        valid = False

    # 异常处理
    except OSError:
        # 配置文件不存在，提示并写入默认值
        usb_log("** [注意] 未找到配置文件，将使用默认配置 **")
        baud = 9600
        chan = "004"
        update_config(baud, chan)
        return baud, chan

    # 其他读取错误
    except Exception as e:
        usb_log(f"** [错误] 配置文件读取失败: {e} **")
        baud = 9600
        chan = "004"
        update_config(baud, chan)
        return baud, chan

    # 如果文件存在但参数非法或缺失，仍使用默认值并写回文件
    if not valid or baud is None or chan is None:
        usb_log("** [错误] 配置文件参数无效，将使用默认配置 **")
        baud = 9600
        chan = "004"
        update_config(baud, chan)

    return baud, chan

# 更新 config.ini 文件
def update_config(baud=None, chan=None):
    config = {}
    changed = False

    try:
        with open(CONFIG_FILE, "r") as f:
            for line in f:
                if '=' in line:
                    k, v = line.strip().split('=', 1)
                    config[k] = v

    # 配置文件不存在，忽略并初始化 config
    except OSError:
        config = {}
        changed = True

    # 判断是否需要更新波特率，仅在值变化时更新
    if baud is not None and is_valid_baud(baud):
        if config.get("baud") != str(baud):
            config["baud"] = str(baud)
            changed = True

    # 判断是否需要更新信道,，仅在值变化时更新
    if chan is not None and is_valid_channel(chan):
        if config.get("chan") != chan:
            config["chan"] = chan
            changed = True

    # 若配置未变，则无需写入文件
    if not changed:
        return

    # 尝试写回配置文件
    try:
        with open(CONFIG_FILE, "w") as f:
            for k, v in config.items():
                f.write(f"{k}={v}\n")
    except OSError as e:
        usb_log(f"** [错误] 配置文件更新失败: {e} **")


# 初始化/重新初始化 UART
def init_uart(baud):
    return UART(UART_ID, baudrate=baud, tx=UART_TX_PIN, rx=UART_RX_PIN, rxbuf=256)

# 向USB串口写入原始二进制数据
def usb_raw(data):
    if isinstance(data, bytearray):
        data = bytes(data)
    elif not isinstance(data, bytes):
        raise TypeError("** [错误] RAW 函数需要字节或字节数组 **")
    sys.stdout.buffer.write(data)

# 向USB串口写入 UTF-8 编码的调试或提示信息
def usb_log(message):
    if not isinstance(message, bytes):
        message = str(message).encode("utf-8")
    sys.stdout.buffer.write(message)

# 进入AT指令模式
def enter_at_mode():
    CTRL_PIN.value(0)
    time.sleep(AT_MODE_ENTRY_DELAY_S)

# 退出AT指令模式
def exit_at_mode():
    CTRL_PIN.value(1)
    time.sleep(AT_MODE_EXIT_DELAY_S)

# 发送AT指令并读取响应
def send_at_command(uart, cmd, response_timeout=300):
    if uart.any():
        uart.read() # 清空缓存
    
    uart.write(cmd.encode() if isinstance(cmd, str) else cmd)
    time.sleep(AT_CMD_INTERVAL_S)
    
    response = b''
    start_time = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start_time) < response_timeout:
        if uart.any():
            response += uart.read()
        
    if response.strip():
        display_response = response.strip().replace(b'\r\n', b' ').replace(b'\n', b' ')
        usb_log(f"** {display_response} **")
    return response

# 解析来自USB的AT指令并更新配置
def parse_at_command_and_update_config(cmd_bytes):
    try:
        try:
            # 按 ASCII 字符进行解码
            text = cmd_bytes.decode("ASCII")
        except UnicodeDecodeError:
            usb_log("** [错误] 解码失败：指令包含非 ASCII 字符 **")
            return False, None, None

        # 去除字符串两端的空白、回车、换行等字符
        clean_text = text.strip()

        # 使用清理后的指令进行解析
        if not clean_text.startswith("AT+"):
            # 对于不以 AT+ 开头的指令，视为透明数据
            return False, None, None
        
        # 处理波特率指令
        if clean_text.startswith("AT+B"):
            val_str = clean_text[4:]
            baud = int(val_str)  # 这里现在是 int('9600')，可以正常工作
            if is_valid_baud(baud):
                update_config(baud=baud)
                return True, "baud", baud
            else:
                usb_log(f"** [错误] 波特率值无效: {baud} **")
                return False, None, None

        # 处理信道指令
        elif clean_text.startswith("AT+C"):
            chan = clean_text[4:]
            if is_valid_channel(chan):
                update_config(chan=chan)
                return True, "chan", chan
            else:
                usb_log(f"** [错误] 信道值无效: {chan} **")
                return False, None, None
                
        # 处理退出指令
        elif clean_text == "AT+EXIT":
            global state
            state = False
            usb_log("** [注意] 收发信机受控退出运行 **")
            return False, None, None
        
        # 其他有效但非配置的AT指令
        else:
            usb_log(f"** [注意] 非配置的AT指令: {clean_text} **")
            return False, None, None

    except (ValueError, IndexError) as e:
        usb_log(f"** [错误] 指令格式错误或参数无效: {e} **")
        return False, None, None
    except Exception as e:
        # 捕获其他所有意外错误
        usb_log(f"** [严重错误] 解析时发生意外: {e} **")
        return False, None, None

# 在运行时处理AT指令
def handle_runtime_at_command(uart_obj, cmd_bytes):
    is_valid, param_type, value = parse_at_command_and_update_config(cmd_bytes)
    
    if not is_valid:
        return uart_obj
        
    usb_log(f"** [注意] 已将 {param_type} 设置为 {value} **")
    uart_obj.deinit()

    enter_at_mode()
    at_uart = init_uart(AT_MODE_BAUD_RATE)
    send_at_command(at_uart, cmd_bytes.decode().strip() + '\r\n')
    send_at_command(at_uart, "AT+RX\r\n")
    at_uart.deinit()
    exit_at_mode()
    
    new_baud, _ = read_config()
    new_uart = init_uart(new_baud)
    
    usb_log(f"** [注意] 已退出命令模式，现在以{new_baud} bps 运行 **")
    return new_uart

# 从 USB 串口非阻塞地读取一行字节数据
def usb_readline_bytes():
    line = b''
    # 进行非阻塞检查
    while poll.poll(0):
        # 直接从 buffer 读取字节
        char_byte = sys.stdin.buffer.read(1)
        if char_byte:
            line += char_byte
            if char_byte == b'\n':
                break
        # 无字可读时退出
        else:
            break
    return line


""" 上电初始化 """
enter_at_mode()

usb_log("** [调试] 收发信机正在初始化... **")
target_baud, target_chan = read_config()

uart1 = init_uart(AT_MODE_BAUD_RATE)

usb_log(f"** [调试] 波特率将设置为 {target_baud} **")
send_at_command(uart1, f"AT+B{target_baud}\r\n")
usb_log(f"** [调试] 信道将设置为 {target_chan} **")
send_at_command(uart1, f"AT+C{target_chan}\r\n")
usb_log("** [调试] 正在读取最终信息... **")
send_at_command(uart1, "AT+RX\r\n")

uart1.deinit()
exit_at_mode()

uart1 = init_uart(target_baud)
usb_log("** [调试] 初始化完成 **")


""" 轮询逻辑 """
# 仅使用 poll 监控 sys.stdin，以规避固件Bug
poll = select.poll()
poll.register(sys.stdin, select.POLLIN)

# 分配缓冲区
buf = bytearray(256)

while state:
    try:
        # 优先处理来自无线模块的数据
        try:
            if uart1 and hasattr(uart1, "readinto") and uart1.any():
                n = uart1.readinto(buf)
                if n is not None and n > 0:
                    usb_raw(buf[:n])
        except Exception as e:
            usb_log(f"** [错误] 处理来自无线模块的数据时发生错误：{repr(e)} **\n")

        # 然后处理来自USB的数据
        usb_line = usb_readline_bytes()
        if usb_line:
            # 检查是否为AT指令
            if usb_line.strip().upper().startswith(b'AT+'):
                # 调用修改后的AT指令处理函数
                uart1 = handle_runtime_at_command(uart1, usb_line)
            else:
                # 作为透明数据直接转发
                try:
                    uart1.write(usb_line)
                except Exception as e:
                    usb_log(f"** [错误] 转发时发生错误：{e} **")

    # 其他情况处理
    except KeyboardInterrupt:
        break
    except Exception as e:
        usb_log(f"** [错误] 轮询逻辑发生错误：{e} **")
        time.sleep(1)

""" 程序退出清理 """
uart1.deinit()
CTRL_PIN.value(1)
usb_log("** [提示] 程序终止 **")
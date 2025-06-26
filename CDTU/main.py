"""
Program for HAB Transceiver.

This program is used to turn a MicroPython board into a smart
Configurable Data Transfer Unit for HC-12 transceiver module. 

It provides Transparent Data Bridge, Runtime AT Command Control,
Persistent Configuration and Automatic Mode Switching.

Author: BG7ZDQ
Date: 2025/06/27 
Version: 0.0.2 
LICENSE: GNU General Public License v3.0
"""

import sys
import time
import select
import neopixel
from machine import UART, Pin

""" 参数定义 """
# 允许的波特率与信道号
# 此处挑选效率最高的选项，同时确保处于业余无线电频段
VALID_BAUD = {2400, 9600, 38400, 115200}
VALID_CHAN = {f"{i:03d}" for i in range(1, 17)}

# AT 参数定义
AT_MODE_ENTRY_DELAY_S = 0.05  # 进入AT模式需要的稳定时间
AT_MODE_EXIT_DELAY_S = 0.1    # 退出AT模式后模块重启时间
AT_CMD_INTERVAL_S = 0.1       # 发送AT指令后所需等待时间

# 硬件引脚定义
CTRL_PIN = Pin(6, Pin.OUT)
UART_TX_PIN = Pin(4)
UART_RX_PIN = Pin(5)
UART_ID = 1

# LED 颜色定义 (R, G, B)
COLOR_STANDBY = (16, 0, 0)  # 待机 - 红色
COLOR_USB_RX = (0, 16, 0)   # 收到上位机(USB)数据 - 绿色
COLOR_UART_RX = (0, 0, 16)  # 收到串口(无线模块)数据 - 蓝色

# 配置文件名
CONFIG_FILE = "config.ini"

# 上电时进入AT指令模式的固定通信参数
POWER_ON_AT_MODE_BAUD_RATE = 9600

# 当前模块的运行波特率
current_baud_rate = 0 

# 运行状态
state = True


""" LED 状态控制器定义 """
class StatusLED:
    def __init__(self, pin, flash_duration_ms=10):
        self.np = neopixel.NeoPixel(Pin(pin), 1)
        self.flash_duration_ms = flash_duration_ms
        
        # 记录上次颜色改变的时间戳
        self.last_change_time = 0
        self.is_flashing = False

        # 设置初始待机颜色
        self.set_color(COLOR_STANDBY)

    def set_color(self, color):
        """直接设置LED颜色"""
        self.np[0] = color
        self.np.write()

    def trigger_flash(self, flash_color):
        """触发一次指定颜色的闪烁"""
        self.set_color(flash_color)
        self.last_change_time = time.ticks_ms()
        self.is_flashing = True

    def update(self):
        """在主循环中不断调用此方法来更新LED状态"""
        # 仅当LED处于闪烁状态时才需要检查
        if self.is_flashing:
            # 如果距离上次闪烁已经超过了设定的时间
            if time.ticks_diff(time.ticks_ms(), self.last_change_time) > self.flash_duration_ms:
                self.set_color(COLOR_STANDBY)
                self.is_flashing = False
                
""" 函数定义 """
# 验证波特率是否有效
def is_valid_baud(baud):
    return baud in VALID_BAUD

# 验证信道号是否有效
def is_valid_chan(chan):
    return chan in VALID_CHAN

# 从 config.ini 读取配置
def read_config():
    default_baud = 9600
    default_chan = "006"

    try:
        # 打开配置文件
        with open(CONFIG_FILE, "r") as f:
            config_data = {}
            # 设置配置格式
            for line in f:
                if '=' in line:
                    key, value = line.strip().split('=', 1)
                    config_data[key] = value

            # 读取字段值
            baud_str = config_data.get("baud")
            chan_str = config_data.get("chan")
            baud = int(baud_str) if baud_str else None
            chan = str(chan_str) if chan_str else None
            
            # 验证读取到的值
            if baud and is_valid_baud(baud) and chan and is_valid_chan(chan):
                return baud, chan
            else:
                raise ValueError("Invalid config parameters")

    # 处理文件不存在或内容无效的情况
    except (OSError, ValueError) as e:
        if isinstance(e, OSError):
            usb_log("** [注意] 配置文件未找到，将使用默认配置 **\n")
        else:
            usb_log("** [错误] 配置文件值无效，将使用默认配置 **\n")
        
        update_config(default_baud, default_chan)
        return default_baud, default_chan
    # 处理其他异常错误
    except Exception as e:
        usb_log(f"** [错误] 配置文件读取异常，将使用默认配置: {e} **\n")
        return default_baud, default_chan

# 更新 config.ini 文件
def update_config(baud=None, chan=None):
    config = {}
    changed = False

    # 读取先前的配置
    try:
        with open(CONFIG_FILE, "r") as f:
            for line in f:
                if '=' in line:
                    k, v = line.strip().split('=', 1)
                    config[k] = v

    # 配置文件不存在
    except OSError:
        config = {}
        changed = True

    # 判断是否需要更新波特率
    if baud is not None and is_valid_baud(baud):
        if config.get("baud") != str(baud):
            config["baud"] = str(baud)
            changed = True

    # 判断是否需要更新信道号
    if chan is not None and is_valid_chan(chan):
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
        usb_log(f"** [错误] 配置文件更新失败: {e} **\n")


# 初始化/重新初始化 UART
def init_uart(baud):
    try:
        return UART(UART_ID, baudrate=baud, tx=UART_TX_PIN, rx=UART_RX_PIN, rxbuf=256)
    except Exception as e:
        usb_log(f"** [错误] 初始化 UART 时出错: {e} **\n")
        return None

# 向USB串口写入原始二进制数据
def usb_raw(data):
    if isinstance(data, bytearray):
        data = bytes(data)
    elif not isinstance(data, bytes):
        raise TypeError("** [错误] RAW 函数需要字节或字节数组 **\n")
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
def send_at_command(uart, cmd, response_timeout=300, silent=False):
    while uart.any():
        uart.read()
    
    uart.write(cmd.encode() if isinstance(cmd, str) else cmd)
    time.sleep(AT_CMD_INTERVAL_S)
    
    response = b''
    start_time = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start_time) < response_timeout:
        data = uart.read()
        if data:
            response += data
    
    if not silent and response.strip():
        display_response = response.strip().replace(b'\r\n', b' ').replace(b'\n', b' ')
        usb_log(f"** {display_response} **\n")

    return response

# 探测 AT 模式的正确波特率
def find_at_baud_rate(last_known_baud,silent=False):
    
    # 定义波特率尝试列表
    baud_rates_to_try = list(dict.fromkeys([last_known_baud] + sorted(list(VALID_BAUD) + [POWER_ON_AT_MODE_BAUD_RATE])))
    
    # 尝试进行探测
    for baud in baud_rates_to_try:
        uart = init_uart(baud)
        
        # 首先确保 uart 对象被成功创建
        if uart: 
            response = send_at_command(uart, "AT\r\n", response_timeout=200, silent=True)
            
            # 然后判断 response 是否有效且正确
            if response and response.strip().endswith(b'OK'):
                return uart  # 成功，直接返回，不关闭串口
            else:
                uart.deinit() # 失败，关闭这个没用的串口，继续下一次循环

    # 如果所有尝试都失败了
    usb_log("** [错误] 无法与模块建立AT通信 **\n")
    return init_uart(POWER_ON_AT_MODE_BAUD_RATE)

# 解析来自USB的AT指令并更新配置
def parse_usb_command(cmd_bytes):
    try:
        # 按 ASCII 编码尝试解码指令
        try:
            text = cmd_bytes.decode("ASCII")
        except UnicodeDecodeError:
            usb_log("** [错误] 解码失败：指令包含非 ASCII 字符 **\n")
            return "error", None, None

        # 去除字符串两端的非预期字符
        clean_text = text.strip()
        
        # 处理波特率指令
        if clean_text.startswith("AT+B"):
            val_str = clean_text[4:]
            baud = int(val_str)
            # 验证有效性然后交付处理
            if is_valid_baud(baud):
                return "config", "baud", baud
            else:
                usb_log(f"** [错误] 波特率无效: {baud} **\n")
                return "error", "InvalidBaud", baud

        # 处理信道指令
        elif clean_text.startswith("AT+C"):
            val_str = clean_text[4:]
            # 验证有效性然后交付处理
            if is_valid_chan(val_str):
                return "config", "chan", val_str
            else:
                usb_log(f"** [错误] 信道号无效: {val_str} **\n")
                return "error", "InvalidChannel", val_str
                
        # 处理退出指令
        elif clean_text == "AT+EXIT":
            return "control", "exit", None
        
        # 处理查询指令
        elif clean_text.startswith(("AT+R")):
            return "query", clean_text, None
        
        # 处理其他非配置的AT指令
        else:
            usb_log(f"** [注意] 未知指令: {clean_text} **\n")
            return "unknown", clean_text, None

    # 格式错误异常处理
    except (ValueError, IndexError) as e:
        return "error", "FormatError", str(e)
    # 捕获其他所有意外错误
    except Exception as e:
        return "error", "Exception", str(e)

# 在运行时处理AT指令
def execute_at_command(cmd_bytes, uart_obj):

    # 进行解析然后获取信息
    global current_baud_rate, state
    cmd_type, param, value = parse_usb_command(cmd_bytes)

    # 如果解析发生错误
    if cmd_type == "error":
        usb_log(f"** [错误] 指令处理失败：{param} - {value}**\n")
        return uart_obj

    # 如果收到退出指令
    elif cmd_type == "control" and param == "exit":
        state = False
        usb_log("** [注意] 收发信机受控退出运行 **\n")
        return uart_obj

    # 如果收到配置指令
    elif cmd_type == "config":
        enter_at_mode()
        at_uart = find_at_baud_rate(current_baud_rate, True)
        if param == "baud":
            response = send_at_command(at_uart, f"AT+B{value}\r\n")
        elif param == "chan":
            response = send_at_command(at_uart, f"AT+C{value}\r\n")
        
        # 销毁临时uart对象
        if at_uart:
            at_uart.deinit()
            
        exit_at_mode()

        # 更新配置信息
        if b"OK" in response:
            update_config(**{param: value})
            usb_log(f"** [注意] 参数 {param} 已设置为 {value} **\n")
            current_baud_rate = value if param == "baud" else current_baud_rate

        # 重载 UART 配置
        new_uart = init_uart(current_baud_rate)
        return new_uart
    
    # 如果收到查询指令
    elif cmd_type == "query":
        enter_at_mode()
        at_uart = find_at_baud_rate(current_baud_rate,True)
        send_at_command(at_uart, param + '\r\n')
        exit_at_mode()

        # 销毁临时uart对象
        if at_uart:
            at_uart.deinit()
        
        # 重新初始化主串口，并返回新的对象
        new_uart = init_uart(current_baud_rate)
        return new_uart

    # 其他类型信息
    else:
        return uart_obj

# 从 USB 串口非阻塞地读取一行字节数据
def usb_readline_bytes(maxlen=256):
    line = b''
    # 进行非阻塞检查
    while poll.poll(0):
        # 直接从 buffer 读取字节
        char_byte = sys.stdin.buffer.read(1)
        if char_byte:
            line += char_byte
            if char_byte == b'\n' or  len(line) >= maxlen:
                break
        # 无字可读时退出
        else:
            break
    return line


""" 上电初始化 """
# 工作指示灯
led = StatusLED(pin = 16)

# 留出给设备管理器识别的空当
time.sleep(2)

# 读取配置，了解模块上次运行的状态
target_baud, target_chan = read_config()
current_baud_rate = target_baud

# 进入 AT 模式
enter_at_mode()

# 自动探测并找到正确的AT通信波特率，返回一个可用的 uart 对象
at_serial = find_at_baud_rate(target_baud,True)

# 使用探测成功的 uart 对象来发送配置指令
usb_log(f"** [调试] 波特率将设置为 {target_baud} **\n")
send_at_command(at_serial, f"AT+B{target_baud}\r\n")
usb_log(f"** [调试] 信道号将设置为 {target_chan} **\n")
send_at_command(at_serial, f"AT+C{target_chan}\r\n")
usb_log("** [调试] 读取最终设置... **\n")
send_at_command(at_serial, "AT+RX\r\n")

# 退出 AT 模式
exit_at_mode()
at_serial.deinit()

# 初始化用于透明传输的串口，并更新全局波特率变量
serial = init_uart(target_baud)
current_baud_rate = target_baud

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
            if serial and hasattr(serial, "readinto") and serial.any():
                n = serial.readinto(buf)
                if n is not None and n > 0:
                    usb_raw(buf[:n])
                    # 更新指示灯状态
                    led.trigger_flash(COLOR_UART_RX)
        except Exception as e:
            usb_log(f"** [错误] 处理来自无线模块的数据时发生错误：{repr(e)} **\n")

        # 然后处理来自USB的数据
        usb_line = usb_readline_bytes()
        if usb_line:
            # 更新指示灯状态
            led.trigger_flash(COLOR_USB_RX)
            # 检查是否为AT指令
            if usb_line.strip().upper().startswith(b'AT+'):
                # 调用修改后的AT指令处理函数
                serial = execute_at_command(usb_line, serial)
            else:
                # 作为透明数据直接转发
                try:
                    serial.write(usb_line)
                except Exception as e:
                    usb_log(f"** [错误] 转发时发生错误：{e} **\n")

    # 其他情况处理
    except KeyboardInterrupt:
        break
    except Exception as e:
        usb_log(f"** [错误] 轮询逻辑发生错误：{e} **\n")
        time.sleep(1)
        
    # 更新 LED 状态
    led.update()

""" 程序退出清理 """
if serial:
    serial.deinit()
poll.unregister(sys.stdin)
CTRL_PIN.value(1)
led.set_color((0,0,0))
usb_log("** [提示] 程序终止 **\n")
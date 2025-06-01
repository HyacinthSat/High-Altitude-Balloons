"""
GUI program for Balloon Ground Station.

This program is a graphical user interface implemented using PyQt,
It connects to and manages the receiver serial port to acquire telemetry and image data from high-altitude balloons.
The program real-time parses and displays the balloon's GPS information, integrates map tracking, and features SSDV image downlink capabilities,
providing a comprehensive ground monitoring and data visualization solution for HAB missions.

Author: BG7ZDQ
Date: 2025/05/25
Version: 0.0.1
LICENSE: GNU General Public License v3.0
"""

import re
import os
import sys
import serial
import subprocess
from serial.tools import list_ports
from configparser import RawConfigParser
from PyQt6.QtGui import QIcon, QPixmap, QColor
from datetime import datetime, timedelta, timezone
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import Qt, QUrl, QTimer, QTime, QThread, pyqtSignal
from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QPushButton, QPlainTextEdit, QMessageBox, QComboBox, QLineEdit, QFormLayout, QHeaderView, QTableWidget, QVBoxLayout, QTableWidgetItem, QAbstractItemView
from PyQt6.QtCore import QTimer, QTime, Qt

# 禁用 GPU 加速
os.environ['QTWEBENGINE_CHROMIUM_FLAGS'] = '--disable-gpu --disable-software-rasterizer'

# 组件样式
tip_style = 'color: #3063AB; font-family: 微软雅黑; font: 10pt;'
common_style = 'color: #555555; font-family: 微软雅黑; font: bold 12pt;'
grid_style = 'color: #3063AB; font-family: 微软雅黑; font: bold 12pt; border: none;'
title_style = 'color: #3063AB; font-family: 微软雅黑; font: bold 12pt; border: none;'
callsign_style = 'color: #3063AB; font-family: 微软雅黑; font: bold 16pt; border: none;'
Common_button_style = 'QPushButton {background-color: #3498db; color: #ffffff; border-radius: 5px; padding: 6px; font-size: 12px;} QPushButton:hover {background-color: #2980b9;} QPushButton:pressed {background-color: #21618c;}'
TextEdit_style = 'QPlainTextEdit {background-color: #FFFFFF; color: #3063AB; border: 1px solid #3498db; border-radius: 5px; padding: 1px; font-family: 微软雅黑; font-size: 12px;}'
ComboBox_style = 'QComboBox {background-color: #ffffff; border: 1px solid #3498db; border-radius: 3px; padding: 2px; min-width: 6em; font: bold 10pt "微软雅黑"; color: #3063AB;}QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 20px; border-left: 1px solid #3498db;}QComboBox::down-arrow { image: url(UI/arrow.svg); width: 10px; height: 10px;}QComboBox QAbstractItemView { background: #ffffff; selection-background-color: #89CFF0; selection-color: #000000; border: 1px solid #3498db; outline: 0; font: 10pt "微软雅黑";}'
LineEdit_style = 'QLineEdit { background-color: #FFFFFF; color: #3063AB; border: 1px solid #3498db; border-radius: 5px; padding: 1px; font-family: 微软雅黑; font-size: 12px; }'
frame_style = 'border: 1px solid #AAAAAA; border-radius: 4px;;'

# 处理配置文件
config = RawConfigParser()
config.optionxform = str
config.read("config.ini")

# 程序主窗口
class GUI(QWidget):

    # 向 QSO 窗口发送数据
    rx_message = pyqtSignal(str, str, str, str, str, str)

    # 设置窗口与程序图标
    def __init__(self):
        super().__init__()

        # 窗口属性
        icon = QIcon('UI/logo.ico')
        self.setWindowIcon(icon)
        self.resize(800, 510)
        self.setFixedSize(800, 510)
        self.setWindowTitle('气球地面站：The Ground Station Software of HAB')
        self.setStyleSheet('QWidget { background-color: rgb(223,237,249); }')

        self.SET_window = None
        self.QSO_window = None 
        self.Radio_Serial_Thread = None
 

        # 地面站信息
        try:
            self.callsign = config.get("GroundStation", "Callsign")
            self.local_lat = config.getfloat("GroundStation", "Latitude")
            self.local_lng = config.getfloat("GroundStation", "Longitude")
            self.local_alt = config.getfloat("GroundStation", "Altitude")
        except Exception as e:
            QMessageBox.warning(self, "提示", f"请重设地面站信息：{e}")
            # 提供默认值以防止崩溃
            self.callsign = ""
            self.local_lat = 0
            self.local_lng = 0
            self.local_alt = 0

        # 气球信息
        self.balloon_lat = 0
        self.balloon_lng = 0
        self.balloon_alt = 0
        self.balloon_time = "2025-05-25T00:00:00Z"

        # 图像编号
        self.filename  = ''
        self.img_num   = -1
        self.frame_num = 1

        # 退出标记位
        self._quitting_for_restart = False

        # 设置主程序图标
        global waiting, correct, warning, error, data, hourglass, camera, img, geo
        waiting = QPixmap('UI/waiting.svg')
        correct = QPixmap('UI/correct.svg')
        warning = QPixmap('UI/warning.svg')
        error = QPixmap('UI/error.svg')
        data = QPixmap('UI/data.svg')
        hourglass = QPixmap('UI/hourglass.svg')
        camera = QPixmap('UI/camera.svg')
        img = QPixmap('UI/image.svg')
        geo = QPixmap('UI/geo.svg')

        # 数据缓存
        self.buffer = bytearray()

        self.UI()

    # 主窗口
    def UI(self):

        '''左栏'''
        # 接收机端口选择部分
        self.Radio_COM_status = QLabel(self)
        self.Radio_COM_status.setPixmap(waiting)
        self.Radio_COM_status.move(40, 28)

        self.Receiver_COM_label = QLabel(self)
        self.Receiver_COM_label.setText("接收机端口：")
        self.Receiver_COM_label.move(65, 25)
        self.Receiver_COM_label.setStyleSheet(title_style)

        self.Radio_COM_Combo = QComboBox(self)
        self.Radio_COM_Combo.addItems([])
        self.Radio_COM_Combo.setGeometry(165, 21, 120, 30)
        self.Radio_COM_Combo.setStyleSheet(ComboBox_style)

        self.Radio_COM_button = QPushButton("连接", self)
        self.Radio_COM_button.setGeometry(300, 21, 50, 27)
        self.Radio_COM_button.setStyleSheet(Common_button_style)
        self.Radio_COM_button.clicked.connect(self.Connect_Radio_COM)

        # 旋转器端口选择部分
        self.Rotator_COM_status = QLabel(self)
        self.Rotator_COM_status.setPixmap(waiting)
        self.Rotator_COM_status.move(40, 63)

        self.Rotator_COM_label = QLabel(self)
        self.Rotator_COM_label.setText("旋转器端口：")
        self.Rotator_COM_label.move(65, 60)
        self.Rotator_COM_label.setStyleSheet(title_style)

        self.Rotator_COM_Combo = QComboBox(self)
        self.Rotator_COM_Combo.addItems([])
        self.Rotator_COM_Combo.setGeometry(165, 56, 120, 30)
        self.Rotator_COM_Combo.setStyleSheet(ComboBox_style)

        self.Rotator_COM_button = QPushButton("连接", self)
        self.Rotator_COM_button.setGeometry(300, 56, 50, 27)
        self.Rotator_COM_button.setStyleSheet(Common_button_style)
        self.Rotator_COM_button.clicked.connect(self.Connect_Rotator_COM)

        # GPS 数据
        self.GPS_status = QLabel(self)
        self.GPS_status.setPixmap(geo)
        self.GPS_status.move(40, 103)

        self.GPS_label = QLabel(self)
        self.GPS_label.setText("GPS 数据：尚无")
        self.GPS_label.move(65, 100)
        self.GPS_label.setStyleSheet(title_style)

        # 轨迹地图嵌入
        self.map_view = QWebEngineView(self)
        self.map_view.setGeometry(40, 130, 320, 240)
        self.map_view.setUrl(QUrl("http://hab.satellites.ac.cn/map"))

        self.GPS_LAT_label = QLabel(self)
        self.GPS_LAT_label.setText("经度: ")
        self.GPS_LAT_label.move(40, 390)
        self.GPS_LAT_label.setStyleSheet(title_style)

        self.GPS_LAT_NUM = QLabel(self)
        self.GPS_LAT_NUM.setText("")
        self.GPS_LAT_NUM.move(85, 390)
        self.GPS_LAT_NUM.setStyleSheet(title_style)

        self.GPS_LON_label = QLabel(self)
        self.GPS_LON_label.setText("纬度：")
        self.GPS_LON_label.move(200, 390)
        self.GPS_LON_label.setStyleSheet(title_style)

        self.GPS_LON_NUM = QLabel(self)
        self.GPS_LON_NUM.setText("")
        self.GPS_LON_NUM.move(245, 390)
        self.GPS_LON_NUM.setStyleSheet(title_style)

        self.GPS_ALT_label = QLabel(self)
        self.GPS_ALT_label.setText("高度：")
        self.GPS_ALT_label.move(40, 415)
        self.GPS_ALT_label.setStyleSheet(title_style)

        self.GPS_ALT_NUM = QLabel(self)
        self.GPS_ALT_NUM.setText("")
        self.GPS_ALT_NUM.move(85, 415)
        self.GPS_ALT_NUM.setStyleSheet(title_style)

        self.GPS_SPD_label = QLabel(self)
        self.GPS_SPD_label.setText("速度：")
        self.GPS_SPD_label.move(200, 415)
        self.GPS_SPD_label.setStyleSheet(title_style)

        self.GPS_SPD_NUM = QLabel(self)
        self.GPS_SPD_NUM.setText("")
        self.GPS_SPD_NUM.move(245, 415)
        self.GPS_SPD_NUM.setStyleSheet(title_style)

        self.GPS_SATS_label = QLabel(self)
        self.GPS_SATS_label.setText("卫星数: ")
        self.GPS_SATS_label.move(200, 440)
        self.GPS_SATS_label.setStyleSheet(title_style)

        self.GPS_SATS_NUM = QLabel(self)
        self.GPS_SATS_NUM.setText("")
        self.GPS_SATS_NUM.move(260, 440)
        self.GPS_SATS_NUM.setStyleSheet(title_style)

        self.GPS_heading_label = QLabel(self)
        self.GPS_heading_label.setText("航向角: ")
        self.GPS_heading_label.move(40, 440)
        self.GPS_heading_label.setStyleSheet(title_style)

        self.GPS_heading_NUM = QLabel(self)
        self.GPS_heading_NUM.setText("")
        self.GPS_heading_NUM.move(100, 440)
        self.GPS_heading_NUM.setStyleSheet(title_style)

        self.rotator_az_label = QLabel(self)
        self.rotator_az_label.setText("方位角：")
        self.rotator_az_label.move(40, 465)
        self.rotator_az_label.setStyleSheet(title_style)

        self.rotator_az_NUM = QLabel(self)
        self.rotator_az_NUM.setText("")
        self.rotator_az_NUM.move(100, 465)
        self.rotator_az_NUM.setStyleSheet(title_style)

        self.rotator_el_label = QLabel(self)
        self.rotator_el_label.setText("俯仰角：")
        self.rotator_el_label.move(200, 465)
        self.rotator_el_label.setStyleSheet(title_style)

        self.rotator_el_NUM = QLabel(self)
        self.rotator_el_NUM.setText("")
        self.rotator_el_NUM.move(260, 465)
        self.rotator_el_NUM.setStyleSheet(title_style)
        '''右栏'''
        # 系统状态指示
        self.Data_status_label = QLabel(self)
        self.Data_status_label.setText("数传:")
        self.Data_status_label.move(420, 25)
        self.Data_status_label.setStyleSheet(title_style)

        self.Data_status_icon = QLabel(self)
        self.Data_status_icon.setPixmap(waiting)
        self.Data_status_icon.move(465, 28)

        self.Camera_status_label = QLabel(self)
        self.Camera_status_label.setText("相机:")
        self.Camera_status_label.move(500, 25)
        self.Camera_status_label.setStyleSheet(title_style)

        self.Camera_status_icon = QLabel(self)
        self.Camera_status_icon.setPixmap(waiting)
        self.Camera_status_icon.move(545, 28)

        self.GPS_status_label = QLabel(self)
        self.GPS_status_label.setText("定位:")
        self.GPS_status_label.move(580, 25)
        self.GPS_status_label.setStyleSheet(title_style)

        self.GPS_status_icon = QLabel(self)
        self.GPS_status_icon.setPixmap(waiting)
        self.GPS_status_icon.move(625, 28)

        self.init_status_label = QLabel(self)
        self.init_status_label.setText("自检:")
        self.init_status_label.move(660, 25)
        self.init_status_label.setStyleSheet(title_style)

        self.init_status_icon = QLabel(self)
        self.init_status_icon.setPixmap(waiting)
        self.init_status_icon.move(705, 28)

        # 帧类型指示器
        self.Frame_type_icon = QLabel(self)
        self.Frame_type_icon.setPixmap(data)
        self.Frame_type_icon.move(420, 63)

        self.Frame_type_label = QLabel(self)
        self.Frame_type_label.setText("当前帧类型：")
        self.Frame_type_label.move(445, 60)
        self.Frame_type_label.setStyleSheet(title_style)

        self.Frame_type_output = QLabel(self)
        self.Frame_type_output.setText("暂无有效帧")
        self.Frame_type_output.move(545, 60)
        self.Frame_type_output.setStyleSheet(common_style)
    
        # 图片接收
        self.SSDV_icon = QLabel(self)
        self.SSDV_icon.setPixmap(img)
        self.SSDV_icon.move(420, 103)

        self.SSDV_label = QLabel(self)
        self.SSDV_label.setText("图像回传：")
        self.SSDV_label.move(445, 100)
        self.SSDV_label.setStyleSheet(title_style)

        # SSDV 接收框
        self.SSDV_IMG = QLabel(self)
        self.SSDV_IMG.setPixmap(QPixmap("UI/SSDV.jpeg").scaled(320, 240, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.SSDV_IMG.setFixedSize(320, 240)
        self.SSDV_IMG.move(420, 130)

        self.DEBUG_INFO_label = QLabel(self)
        self.DEBUG_INFO_label.setText("调试信息：")
        self.DEBUG_INFO_label.move(420, 390)
        self.DEBUG_INFO_label.setStyleSheet(title_style)

        self.SET_button = QPushButton("设置", self)
        self.SET_button.setGeometry(500, 387, 50, 27)
        self.SET_button.setStyleSheet(Common_button_style)
        self.SET_button.clicked.connect(self.SET)

        self.QSO_button = QPushButton("通信", self)
        self.QSO_button.setGeometry(560, 387, 50, 27)
        self.QSO_button.setStyleSheet(Common_button_style)
        self.QSO_button.clicked.connect(self.QSO)

        self.DEBUG_output = QPlainTextEdit(self)
        self.DEBUG_output.setReadOnly(True)
        self.DEBUG_output.setGeometry(420, 420, 330, 65)
        self.DEBUG_output.setStyleSheet(TextEdit_style)

        # 串口刷新定时器
        self.Update_COM_Info()
        self.serial_timer = QTimer(self)
        self.serial_timer.timeout.connect(self.Update_COM_Info)
        self.serial_timer.start(200)

    # 向调试信息框写入信息
    def debug_info(self, text):
        time = datetime.now().strftime("%H:%M:%S")
        self.DEBUG_output.appendPlainText(f"{time} {text}")
        print(text)

    # 处理收发信机的串口数据
    def Handle_Radio_Serial_Data(self, data: bytes):
        self.buffer.extend(data)

        while True:
            # 优先尝试提取 ASCII
            if self.Try_Extract_ASCII():
                continue
            # 然后提取 SSDV
            if self.try_extract_ssdv():
                continue
            break

    # 使用正则表达式提取 ASCII 帧信息
    def Try_Extract_ASCII(self) -> bool:
        current_buffer_bytes = bytes(self.buffer)
        changed = False

        # 找出所有完整的 ASCII 帧
        for match in re.finditer(rb"\*\*(.+?)\*\*", current_buffer_bytes, re.DOTALL):
            ascii_raw = match.group(0)

            try:
                ascii_text = ascii_raw.decode("ascii", errors="strict").strip("* ").strip()
            except UnicodeDecodeError:
                print(f"[警告] ASCII解码失败: {ascii_raw}")
                continue
            
            # 数传状态正常，将 ASCII 数据发送到处理函数
            self.Data_status_icon.setPixmap(correct)
            self.Processing_ASCII_Data(ascii_text)
            changed = True

        # 如果有匹配，清除 buffer 直到最后一个匹配结束位置
        if changed:
            last_match = list(re.finditer(rb"\*\*(.+?)\*\*", current_buffer_bytes, re.DOTALL))[-1]
            self.buffer = self.buffer[last_match.end():]
            return True
        else:
            return False
        
    # 处理非图像 ASCII 数据
    def Processing_ASCII_Data(self, text):

        # 记录日志
        print(f"ASCII帧：{text}")
        time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open("log.txt", "a") as f:
            f.write(f"{time}    {text}\n")

        # 处理 $$ 开头的遥测数据
        # $$CALLSIGN,Frame_Counter,HH:MM:SS,latitude,longitude,altitude,speed,sats,heading
        if text.startswith("$$"):
            self.Frame_type_output.setText(f"GPS 数据遥测帧")
            self.Frame_type_output.adjustSize()
            try:
                fields = text[2:].split(",")
                if len(fields) >= 9:
                    self.balloon_time = fields[2]
                    self.balloon_lat = float(fields[3])
                    self.balloon_lng = float(fields[4])
                    self.balloon_alt = float(fields[5])
                    self.balloon_spd = float(fields[6])
                    self.balloon_sats = int(fields[7])
                    self.balloon_heading = float(fields[8])
                    
                    # 更新地图
                    self.update_map_position()
                    self.debug_info(f"GPS 数据已更新")

                    # 更新标签显示
                    self.GPS_status_icon.setPixmap(correct)
                    self.GPS_label.setText(f"GPS 数据：就绪")
                    self.GPS_label.adjustSize()
                    self.GPS_LAT_NUM.setText(f"{self.balloon_lat:.6f}")
                    self.GPS_LAT_NUM.adjustSize()
                    self.GPS_LON_NUM.setText(f"{self.balloon_lng:.6f}")
                    self.GPS_LON_NUM.adjustSize()
                    self.GPS_ALT_NUM.setText(f"{self.balloon_alt:.2f} m")
                    self.GPS_ALT_NUM.adjustSize()
                    self.GPS_SPD_NUM.setText(f"{self.balloon_spd:.2f} m/s")
                    self.GPS_SPD_NUM.adjustSize()
                    self.GPS_SATS_NUM.setText(f"{self.balloon_sats}")
                    self.GPS_SATS_NUM.adjustSize()
                    self.GPS_heading_NUM.setText(f"{self.balloon_heading:.2f}")
                    self.GPS_heading_NUM.adjustSize()
                    self.rotator_az_NUM.setText("---.--")
                    self.rotator_az_NUM.adjustSize()
                    self.rotator_el_NUM.setText("---.--")
                    self.rotator_el_NUM.adjustSize()

                    # 获取现在的时间并将其格式化
                    now_utc = datetime.now(timezone.utc)
                    adjusted_time = now_utc + timedelta(seconds=30)
                    formatted = adjusted_time.strftime('%Y-%m-%dT%H:%M:%S') + 'Z'

                    # 调用 SondeHub API接口
                    # sondehub_dev.exe <上传者呼号> <接收时间> <球上时间> <经度> <纬度> <高度> <航向角> <GPS卫星数> <地面站经度> <地面站纬度> <地面站高度>
                    try:
                        subprocess.Popen(["./sondehub", f"{self.callsign}", f"{formatted}", f"{self.balloon_time}", f"{self.balloon_lng}", f"{self.balloon_lat}", f"{self.balloon_alt}", f"{self.balloon_heading}", f"{self.balloon_sats}", f"{self.local_lng}", f"{self.local_lat}", f"{self.local_alt}"])
                    except Exception as e:
                        self.debug_info(f"SondeHub上传失败: {e}")
                        return False
                    return

                else:
                    self.debug_info("遥测数据字段不足，解析失败")
            except Exception as e:
                self.debug_info(f"遥测数据解析出错：{e}")
            return
        
        # 处理 ## 开头的中继数据帧
        # ##RELAY,ToCall,FmCall,Grid,INFO
        elif text.startswith("##"):
            self.Frame_type_output.setText("中继数据帧")
            self.Frame_type_output.adjustSize()

            try:
                fields = text[2:].split(",", maxsplit=4)
                if len(fields) >= 5:
                    to_call = fields[1]
                    fm_call = fields[2]
                    grid    = fields[3]
                    info    = fields[4]

                    # 获取格式化的接收时间并通过信号槽输入QSO窗口
                    time_str = datetime.now().strftime("%H:%M:%S")
                    self.rx_message.emit(time_str, fm_call, to_call, grid, info, "Balloon")
                    return
                else:
                    self.debug_info("中继数据字段不足，解析失败")
            except Exception as e:
                self.debug_info(f"中继数据解析出错：{e}")
            return

        # 启动阶段
        if "Booting" in text:
             self.init_status_icon.setPixmap(hourglass)
             self.debug_info("正在启动...")
        elif "Calibrate Failed" in text:
            self.Camera_status_icon.setPixmap(error)
            self.debug_info("相机初始化失败！")
        elif "Calibrating camera" in text:
            self.Camera_status_icon.setPixmap(hourglass)
            self.debug_info("相机初始化成功，开始校准！")
        elif "Camera Calibrate" in text:
            self.Camera_status_icon.setPixmap(correct)
            self.debug_info("相机校准完成！")
        elif "GPS Initializing!" in text:
            self.GPS_status_icon.setPixmap(hourglass)
            self.debug_info("GPS初始化中...")
        elif "GPS init Completed" in text:
            self.GPS_status_icon.setPixmap(correct)
            self.debug_info("GPS初始化完成！")
        elif "GPS init Falied" in text:
            self.GPS_status_icon.setPixmap(error)
            self.debug_info("GPS初始化失败！")
        elif "Init Done" in text:
             self.init_status_icon.setPixmap(correct)
             self.debug_info("初始化全部完成！")
        elif "SSDV Encoding: image" in text:
            self.debug_info(f"正在编码第 {self.img_num + 1} 张图片")
        elif "SSDV End" in text:
            self.debug_info(f"第 {self.img_num} 张图片接收完成")
            self.debug_info(f"共收到 {self.frame_num} 帧")
        else:
            self.debug_info(f"收到信息：{text}")

    # 提取 SSDV 数据
    def try_extract_ssdv(self) -> bool:
        
        # 定义帧信息并寻找帧头
        header = b"\x55\x67\xB9\xD9\x5B\x2F"
        frame_len = 256
        start = self.buffer.find(header)

        # 首先判断是否为完整帧再进行提取
        if start == -1 or len(self.buffer) - start < frame_len: return False
        frame = self.buffer[start:start + frame_len]

        # 接收到SSDV数据包证明摄像头工作正常，初始化正常
        self.Camera_status_icon.setPixmap(correct)
        self.init_status_icon.setPixmap(correct)

        # 提取图像编号并检查是否变化
        try:
            current_img_num = frame[6]
            if current_img_num != self.img_num or self.img_num == -1:
                self.img_num = current_img_num
                time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                self.filename = f"{time}"
                self.frame_num = 1
        except:
            print("图像编号提取失败")
            self.buffer = self.buffer[start + frame_len:]
            return False
        
        # 累计帧计数
        self.Frame_type_output.setText(f"SSDV 图像数据帧 {self.frame_num}")
        self.Frame_type_output.adjustSize()
        self.frame_num += 1

        # 确保 'dat' 文件夹存在并将接收到的数据进行存储
        os.makedirs("dat", exist_ok=True)
        dat_filepath = f"dat/{self.filename}.dat"
        try:
            with open(dat_filepath, "ab") as f:
                f.write(frame)
        except IOError as e:
            self.debug_info(f"写入 SSDV 数据失败: {e}")
            return False

        # 调用 SSDV 解码器解调存储的 dat 文件
        try:
            result = subprocess.run(["./ssdv", "-d", f"dat/{self.filename}.dat", f"{self.filename}.jpg"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if result.returncode != 0:
                raise RuntimeError("SSDV 解码器返回码非 0")
        except Exception as e:
            self.debug_info(f"SSDV 解码失败: {e}")
            self.buffer = self.buffer[start + frame_len:]
            return False

        # 确认文件存在再加载图像
        if os.path.exists(f"{self.filename}.jpg"):
            self.SSDV_IMG.setPixmap(QPixmap(f"{self.filename}.jpg").scaled(320, 240, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            self.SSDV_IMG.repaint()

        # 从缓冲区移除已处理数据
        self.buffer = self.buffer[start + frame_len:]
        return True
    
    # 管理收发信机串口连接
    def Connect_Radio_COM(self):
        port_name = self.Radio_COM_Combo.currentData()
        if self.Radio_COM_button.text() == "连接":
            if not port_name:
                self.Radio_COM_status.setPixmap(warning)
                QMessageBox.warning(self, "警告：串口无效", "未连接有效串口")
                return

            # 启动串口处理线程，并绑定接收和断开信号的槽函数
            self.Radio_Serial_Thread = SerialConnection(port_name, baudrate=9600)
            self.Radio_Serial_Thread.data_received.connect(self.Handle_Radio_Serial_Data)
            self.Radio_Serial_Thread.disconnected.connect(self.Radio_Disconnected)
            self.Radio_Serial_Thread.start()

            # 检查是否已经成功连接
            if self.Radio_Serial_Thread and self.Radio_Serial_Thread.isRunning():
                self.Radio_COM_status.setPixmap(correct)
                self.Radio_COM_button.setText("断开")
                print(f"接收机串口已连接：{port_name}")
                self.debug_info(f"接收机串口已连接：{port_name}")

        else:
            if self.Radio_Serial_Thread:
                self.Radio_Serial_Thread.stop()

            # 手动断开时，也应该确保UI状态正确更新
            self.Radio_COM_status.setPixmap(waiting)
            self.Radio_COM_button.setText("连接")

            # 确保线程对象被清理
            if self.Radio_Serial_Thread:
                 self.Radio_Serial_Thread = None
            self.debug_info("接收机串口已断开")

    # 处理收发信机串口意外断开时的情况
    def Radio_Disconnected(self):
        self.Radio_COM_status.setPixmap(warning)
        self.Radio_COM_button.setText("连接")
        if self.Radio_Serial_Thread:
            self.Radio_Serial_Thread.stop()
            self.Radio_Serial_Thread = None
        self.debug_info("接收机串口已断开")
        QMessageBox.warning(self, "警告：串口连接失败", "接收机串口连接失败或已断开。")

    # 发送数据到收发信机串口
    def Send_Data_to_Radio(self, data_to_send: str):
        # 检查收发信机串口是否打开
        if self.Radio_Serial_Thread and self.Radio_Serial_Thread.isRunning():
            self.Radio_Serial_Thread.send_data(data_to_send.encode('ascii'))
        else:
            self.debug_info("接收机串口未连接或未运行，无法发送数据。")
            QMessageBox.warning(self, "发送失败", "接收机串口未连接或未运行。")

    # 连接天线旋转器串口
    def Connect_Rotator_COM(self):
        self.debug_info("旋转器功能尚未实现")
        if (self.local_alt == 0 and self.local_lat == 0 and self.local_lng == 0):
            self.debug_info("请先输入本地经纬度")
            self.SET()
            return

    # 刷新系统中所有可用串口信息，并更新到下拉框中
    def Update_COM_Info(self):
        ports = list_ports.comports()
        current_ports = [(p.device, p.description) for p in ports]

        # 初始化缓存（首次调用）
        if not hasattr(self, 'port_list_cache'):
            self.port_list_cache = []
            self.Radio_COM_Combo.addItem("尚未选择", userData=None)
            self.Rotator_COM_Combo.addItem("尚未选择", userData=None)

        # 检查是否有变化，如果没有变化则跳过刷新
        if current_ports == self.port_list_cache: return
        self.port_list_cache = current_ports

        # 记录之前已选中的串口
        Radio_Selected = self.Radio_COM_Combo.currentData()
        Rotator_Selected = self.Rotator_COM_Combo.currentData()

        # 将当前系统可用的串口设备填入 UI 中的两个下拉框
        self.Radio_COM_Combo.blockSignals(True)
        self.Rotator_COM_Combo.blockSignals(True)
        self.Radio_COM_Combo.clear()
        self.Rotator_COM_Combo.clear()
        self.Radio_COM_Combo.addItem("尚未选择", userData=None)
        self.Rotator_COM_Combo.addItem("尚未选择", userData=None)

        for name, desc in current_ports:
            self.Radio_COM_Combo.addItem(name, userData=name)
            idx_r = self.Radio_COM_Combo.count() - 1
            self.Radio_COM_Combo.setItemData(idx_r, desc, Qt.ItemDataRole.ToolTipRole)
    
            self.Rotator_COM_Combo.addItem(name, userData=name)
            idx_ro = self.Rotator_COM_Combo.count() - 1
            self.Rotator_COM_Combo.setItemData(idx_ro, desc, Qt.ItemDataRole.ToolTipRole)
    
        # 检查已经连接的收发信机串口是否仍然可用
        Found_Radio = any(p[0] == Radio_Selected for p in current_ports)
        if Found_Radio:
            idx = self.Radio_COM_Combo.findData(Radio_Selected)
            self.Radio_COM_Combo.setCurrentIndex(idx)
        else:
            self.Radio_COM_Combo.setCurrentIndex(0)
            if Radio_Selected is not None:
                self.Radio_COM_status.setPixmap(error)
                QMessageBox.warning(self, "警告：串口断开", f"收发信机串口 {Radio_Selected} 已断开。")
    
        # 检查已经连接的旋转器串口是否仍然可用
        Found_Rotator = any(p[0] == Rotator_Selected for p in current_ports)
        if Found_Rotator:
            idx = self.Rotator_COM_Combo.findData(Rotator_Selected)
            self.Rotator_COM_Combo.setCurrentIndex(idx)
        else:
            self.Rotator_COM_Combo.setCurrentIndex(0)
            if Rotator_Selected is not None:
                self.Rotator_COM_status.setPixmap(error)
                QMessageBox.warning(self, "警告：串口断开", f"旋转器串口 {Rotator_Selected} 已断开。")
    
        self.Radio_COM_Combo.blockSignals(False)
        self.Rotator_COM_Combo.blockSignals(False)

    # 更新气球在地图中的位置
    def update_map_position(self):
        js_code = f"updatePosition({self.balloon_lat}, {self.balloon_lng}, {self.local_lat}, {self.local_lng});"
        self.map_view.page().runJavaScript(js_code)

    # 启动设置窗口
    def SET(self):
        if self.SET_window is None:
            self.SET_window = SET_Windows(self.callsign, self.local_lat, self.local_lng, self.local_alt) 
            self.SET_window.coords_updated.connect(self.update_local_coords)
        self.SET_window.show()

    # 更新地面站信息
    def update_local_coords(self, Callsign, lat, lng, alt):
        
        # 检查是否有实际变化
        if self.callsign != Callsign or self.local_lat != lat or self.local_lng != lng or self.local_alt != alt:
            self.callsign = Callsign
            self.local_lat = lat
            self.local_lng = lng
            self.local_alt = alt
            self.debug_info(f"地面站信息已更改")

            # 更新配置文件
            try:
                if not config.has_section("GroundStation"):
                    config.add_section("GroundStation")
                config.set("GroundStation", "Callsign", self.callsign)
                config.set("GroundStation", "Latitude", str(self.local_lat))
                config.set("GroundStation", "Longitude", str(self.local_lng))
                config.set("GroundStation", "Altitude", str(self.local_alt))

                with open("config.ini", "w") as configfile:
                    config.write(configfile)

            except Exception as e:
                self.debug_info(f"配置文件写入错误: {e}")
                QMessageBox.critical(self, "错误", f"存储信息到配置文件失败！\n{e}")

            self.restart_application()

    # 重启应用程序
    def restart_application(self):

        self.debug_info("正在重启应用程序...")

        # 重设标记位
        self._quitting_for_restart = True

        # 停止所有子线程
        if self.Radio_Serial_Thread:
            self.Radio_Serial_Thread.stop()
            self.Radio_Serial_Thread.wait()
        
        # 关闭所有窗口
        QApplication.closeAllWindows()

        try:
            current_script_path = os.path.abspath(sys.argv[0]) 
            # 构建新的命令行参数列表
            command = [sys.executable, current_script_path] + sys.argv[1:]

            QApplication.closeAllWindows()
            
            # 使用 Popen 在后台启动新进程
            subprocess.Popen(command)
            
        except Exception as e:
            self.debug_info(f"重启失败: {e}")
            QMessageBox.critical(self, "重启失败", f"程序重启时发生错误：{e}")
        
        # 无论重启是否成功，最后都退出当前进程
        sys.exit(0)

    # 启动 QSO 窗口
    def QSO(self):
        if self.Radio_Serial_Thread and self.Radio_Serial_Thread.serial and self.Radio_Serial_Thread.serial.is_open:
            if self.QSO_window is None:
                self.QSO_window = QSO_Windows(self.callsign, self.local_lat, self.local_lng)
                self.QSO_window.tx_message.connect(self.Send_Data_to_Radio)
                self.rx_message.connect(self.QSO_window.add_info_table_row)
            self.QSO_window.show()
        else:
            QMessageBox.warning(self, "警告", "接收机串口未连接，请先连接接收机串口。")

    # 主窗口关闭事件处理
    def closeEvent(self, event):

         # 如果是为重启而退出，直接接受事件
        if self._quitting_for_restart:
            event.accept()
            return

        warn = QMessageBox.question(self, "提示", "是否确定要退出程序？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if warn == QMessageBox.StandardButton.Yes:
            QApplication.closeAllWindows()
            event.accept()
        else:
            event.ignore()

# 串口连接线程
class SerialConnection(QThread):

    # 发送信号
    data_received = pyqtSignal(bytes)
    disconnected = pyqtSignal()

    def __init__(self, port_name, baudrate=9600):
        super().__init__()
        self.port_name = port_name
        self.baudrate = baudrate
        self._running = True
        self.serial = None
        self._send_queue = []

    # 打开串口并读取数据
    def run(self):
        # 尝试打开串口
        try:
            self.serial = serial.Serial(self.port_name, self.baudrate, timeout=1)
        except serial.SerialException as e:
            print(f"[错误] 串口打开失败：{e}")
            self.disconnected.emit()
            return

        while self._running:
            try:
                # 读取数据
                if self.serial.in_waiting:
                    data = self.serial.read(self.serial.in_waiting)
                    self.data_received.emit(data)

                # 发送数据
                if self._send_queue:
                    data_to_send = self._send_queue.pop(0)
                    self.serial.write(data_to_send)
                    QThread.msleep(25)

            except serial.SerialException as e:
                print(f"[错误] 串口异常断开：{e}")
                self._running = False
                if self.serial and self.serial.is_open:
                    self.serial.close()
                self.serial = None
                self.disconnected.emit()
                break
            except Exception as e:
                print(f"[错误] 串口操作异常：{e}")
                continue

    # 发送数据
    def send_data(self, data: bytes):
        self._send_queue.append(data)

    # 停止线程
    def stop(self):
        self._running = False
        if self.serial and self.serial.is_open:
            self.serial.close()
        self.quit()
        self.wait()

# 设置窗口
class SET_Windows(QWidget):
    # 定义一个信号，用于在坐标和呼号更新后发射给主窗口
    coords_updated = pyqtSignal(str, float, float, float)

    def __init__(self, callsign, current_lat, current_lng, current_alt):
        super().__init__()

        # 窗口属性
        icon = QIcon('UI/logo.ico')
        self.setWindowIcon(icon)
        self.resize(200, 250)
        self.setFixedSize(220, 280) # 适当调整窗口大小以容纳新的输入框
        self.setWindowTitle('设置')
        self.setStyleSheet('QWidget { background-color: rgb(223,237,249); }')

        # 存储先前的呼号和经纬度信息
        self.current_callsign = callsign
        self.current_lat = current_lat
        self.current_lng = current_lng
        self.current_alt = current_alt

        self.init_ui()

    def init_ui(self):
        layout = QFormLayout()

        # 呼号输入框
        self.callsign_input = QLineEdit(self)
        self.callsign_input.setStyleSheet(LineEdit_style)
        self.callsign_input.setText(self.current_callsign)
        layout.addRow("地面站呼号:", self.callsign_input)

        self.lat_input = QLineEdit(self)
        self.lat_input.setStyleSheet(LineEdit_style)
        self.lat_input.setText(str(self.current_lat))
        layout.addRow("地面站纬度:", self.lat_input)

        self.lng_input = QLineEdit(self)
        self.lng_input.setStyleSheet(LineEdit_style)
        self.lng_input.setText(str(self.current_lng))
        layout.addRow("地面站经度:", self.lng_input)

        self.alt_input = QLineEdit(self)
        self.alt_input.setStyleSheet(LineEdit_style)
        self.alt_input.setText(str(self.current_alt))
        layout.addRow("地面站高度:", self.alt_input)

        self.save_button = QPushButton("保存", self)
        self.save_button.setStyleSheet(Common_button_style)
        self.save_button.clicked.connect(self.save_coords)
        layout.addRow(self.save_button)

        self.setLayout(layout)

    # 保存呼号和坐标
    def save_coords(self):
        try:
            new_callsign = self.callsign_input.text().strip()
            new_lat = float(self.lat_input.text())
            new_lng = float(self.lng_input.text())
            new_alt = float(self.alt_input.text())

            # 验证呼号是否为空
            if not new_callsign:
                QMessageBox.warning(self, "输入错误", "呼号不能为空。")
                return

            # 验证经纬度范围
            if not (-90 <= new_lat <= 90):
                QMessageBox.warning(self, "输入错误", "纬度必须在 -90 到 90 之间。")
                return
            if not (-180 <= new_lng <= 180):
                QMessageBox.warning(self, "输入错误", "经度必须在 -180 到 180 之间。")
                return
            if not (-12263 <= new_alt <= 8848.86):
                QMessageBox.warning(self, "输入错误", "高度必须在 -12263 到 8848.86 之间。")
                return

            # 更新当前呼号和坐标
            self.current_callsign = new_callsign
            self.current_lat = new_lat
            self.current_lng = new_lng
            self.current_alt = new_alt
            
            # 发射信号，通知主窗口更新呼号和坐标
            self.coords_updated.emit(self.current_callsign, self.current_lat, self.current_lng, self.current_alt)
            # 保存后关闭设置窗口
            self.close()

        except ValueError:
            QMessageBox.warning(self, "输入错误", "请确保经度、纬度、高度输入为有效的数字。")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存时发生未知错误: {e}")

# 信息发送窗口
class QSO_Windows(QWidget):
    # 定义一个信号，用于发射时向主窗口传输拼装好的信息
    tx_message = pyqtSignal(str)

    def __init__(self, callsign, current_lat, current_lng):
        super().__init__()

        # 窗口属性
        icon = QIcon('UI/logo.ico')
        self.setWindowIcon(icon)
        self.resize(800, 510)
        self.setFixedSize(800, 510)
        self.setWindowTitle('数字通信试验')
        self.setStyleSheet('QWidget { background-color: rgb(223,237,249); }')

        # 存储传入的参数
        self.callsign = callsign
        self.current_lat = current_lat
        self.current_lng = current_lng
        self.grid = self.latlng_to_maiden(self.current_lat, self.current_lng)

        # 构建信息用的参数
        self.ToCallSign = "CQ"
        self.ToMSG = "Test"

        # 拼装后的信息
        self.TofullMSG = ""

        # 统计信息
        self.rx_count = 0
        self.tx_count = 0
        self.QSO_count = 0
        self.qso_callsigns = set()

        # 初始化UI
        self.init_ui()

    def init_ui(self):

        # 信息发送区
        self.send_info_frame = QWidget(self)
        self.send_info_frame.setGeometry(30, 25, 290, 100)
        self.send_info_frame.setStyleSheet(frame_style)

        self.Callsign_label = QLabel(self)
        self.Callsign_label.setText("信息发送")
        self.Callsign_label.move(35, 30)
        self.Callsign_label.setStyleSheet(tip_style)

        self.Callsign_label = QLabel(self)
        self.Callsign_label.setText("呼号：")
        self.Callsign_label.move(40, 60)
        self.Callsign_label.setStyleSheet(title_style)

        self.Callsign_input = QLineEdit(self)
        self.Callsign_input.setStyleSheet(LineEdit_style)
        self.Callsign_input.move(100, 60)
        self.Callsign_input.setText(str(self.ToCallSign))
        
        self.MSG_label = QLabel(self)
        self.MSG_label.setText("信息：")
        self.MSG_label.move(40, 90)
        self.MSG_label.setStyleSheet(title_style)

        self.MSG_input = QLineEdit(self)
        self.MSG_input.setStyleSheet(LineEdit_style)
        self.MSG_input.move(100, 90)
        self.MSG_input.setText(self.ToMSG)

        self.TX_button = QPushButton("发送信息", self)
        self.TX_button.setGeometry(225, 62, 80, 50)
        self.TX_button.setStyleSheet(Common_button_style)
        self.TX_button.clicked.connect(self.TX)

        self.cooldown_ms = 300
        self.send_timer = QTimer()
        self.send_timer.setSingleShot(True)
        self.send_timer.timeout.connect(self.unlock_send_button)

        # 信息统计区
        self.count_frame = QWidget(self)
        self.count_frame.setGeometry(330, 25, 160, 100)
        self.count_frame.setStyleSheet(frame_style)

        self.rx_count_label = QLabel(self)
        self.rx_count_label.setText("接收计数：")
        self.rx_count_label.move(340, 40)
        self.rx_count_label.setStyleSheet(title_style)

        self.rx_count_num = QLabel(self)
        self.rx_count_num.setText(str(self.rx_count))
        self.rx_count_num.move(420, 40)
        self.rx_count_num.setStyleSheet(title_style)

        self.tx_count_label = QLabel(self)
        self.tx_count_label.setText("发送计数：")
        self.tx_count_label.move(340, 65)
        self.tx_count_label.setStyleSheet(title_style)

        self.tx_count_num = QLabel(self)
        self.tx_count_num.setText(str(self.tx_count))
        self.tx_count_num.move(420, 65)
        self.tx_count_num.setStyleSheet(title_style)

        self.QSO_count_label = QLabel(self)
        self.QSO_count_label.setText("通联计数：")
        self.QSO_count_label.move(340, 90)
        self.QSO_count_label.setStyleSheet(title_style)

        self.QSO_count_num = QLabel(self)
        self.QSO_count_num.setText(str(self.QSO_count))
        self.QSO_count_num.move(420, 90)
        self.QSO_count_num.setStyleSheet(title_style)

        # 台站信息区
        self.station_info_frame = QWidget(self)
        self.station_info_frame.setGeometry(510, 25, 250, 100)
        self.station_info_frame.setStyleSheet(frame_style)
        
        self.station_info_label = QLabel(self)
        self.station_info_label.setText("站点信息")
        self.station_info_label.move(515, 30)
        self.station_info_label.setStyleSheet(tip_style)

        self.My_Callsign_label = QLabel(self.station_info_frame)
        self.My_Callsign_label.setText(self.callsign)
        self.My_Callsign_label.setGeometry(10, 25, 230, 30)
        self.My_Callsign_label.setStyleSheet(callsign_style)
        self.My_Callsign_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.My_grid_label = QLabel(self.station_info_frame)
        self.My_grid_label.setText(self.grid)
        self.My_grid_label.setGeometry(10, 55, 230, 30)
        self.My_grid_label.setStyleSheet(grid_style)
        self.My_grid_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 通联信息区
        self.info_frame = QWidget(self)
        self.info_frame.setGeometry(30, 150, 460, 320)
        self.info_frame.setStyleSheet(frame_style)

        info_layout = QVBoxLayout(self.info_frame)
        info_layout.setContentsMargins(5, 5, 5, 5)
        self.info_table = QTableWidget(self.info_frame)

        # 设置列数和列头标签
        self.info_table.setColumnCount(4)
        self.info_table.setHorizontalHeaderLabels(["  时间  ", "  源站呼号  ", "  目标呼号  ", "信息"])
        self.info_table.horizontalHeader().setStyleSheet(title_style)

        # 设置列宽自适应填充可用空间
        self.info_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.info_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.info_table.verticalHeader().setDefaultSectionSize(20)

        # 隐藏行号，设置表格的网格线颜色
        self.info_table.verticalHeader().setVisible(False)
        self.info_table.setStyleSheet("QTableWidget { gridline-color: #DDDDDD; }")

        # 禁用编辑和选中
        self.info_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.info_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        info_layout.addWidget(self.info_table)

        # 当单元格被双击时，触发 fill_callsign_from_table 方法
        self.info_table.cellDoubleClicked.connect(self.fill_callsign_from_table)

        # 实时时钟
        self.clock_label = QLabel(self)
        self.clock_label.setGeometry(510, 150, 250, 60)
        self.clock_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.clock_label.setStyleSheet('color: #3063AB; font-family: 微软雅黑; font: bold 30pt; border: none;')

        # 定时更新时间
        self.timer = QTimer(self)
        self.timer.timeout.connect(lambda: self.clock_label.setText(QTime.currentTime().toString("HH:mm:ss")))
        self.timer.start(1000)

        # 初始显示
        self.clock_label.setText(QTime.currentTime().toString("HH:mm:ss"))

        # QSO 信息区
        self.info_QSO_frame = QWidget(self)
        self.info_QSO_frame.setGeometry(510, 220, 250, 250)
        self.info_QSO_frame.setStyleSheet(frame_style)

        QSO_info_layout = QVBoxLayout(self.info_QSO_frame)
        QSO_info_layout.setContentsMargins(5, 5, 5, 5)
        self.QSO_info_table = QTableWidget(self.info_QSO_frame)

        # 设置列数和列头标签
        self.QSO_info_table.setColumnCount(3)
        self.QSO_info_table.setHorizontalHeaderLabels(["   时间   ", "  呼号  ", "  网格  "])
        self.QSO_info_table.horizontalHeader().setStyleSheet(title_style)

        # 设置列宽自适应填充可用空间
        self.QSO_info_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        # 隐藏行号，设置表格的网格线颜色
        self.QSO_info_table.verticalHeader().setVisible(False)
        self.QSO_info_table.setStyleSheet("QTableWidget { gridline-color: #DDDDDD; }")

        # 禁用编辑和选中
        self.QSO_info_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.QSO_info_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        QSO_info_layout.addWidget(self.QSO_info_table)

    # 格式：“##ToCall,FmCall,Gird,INFO\n”
    def TX(self):

        # 发送冷却时间
        if not self.TX_button.isEnabled():
            return  # 冷却中，不发送

        # 计数
        self.tx_count += 1
        self.tx_count_num.setText(str(self.tx_count))
        self.tx_count_num.adjustSize()

        # 获取目标呼号和消息
        to_call = self.Callsign_input.text().strip().upper()
        msg = self.MSG_input.text().strip()

        # 校验输入
        if not to_call or not msg:
            QMessageBox.warning(self, "输入错误", "目标呼号和信息不能为空。")
            return
        elif to_call == self.callsign:
            QMessageBox.warning(self, "输入错误", "不能给自己发送消息。")
            return

        # 当前时间
        current_time = datetime.now().strftime("%H:%M:%S")

        # 构建消息字符串：##ToCall,FmCall,Grid,INFO\n
        # 调试版本
        # full_msg = f"** ##RELAY,{to_call},{self.callsign},{self.grid},{msg} **"
        full_msg = f"##{to_call},{self.callsign},{self.grid},{msg}\n"

        # 保存完整消息
        self.TofullMSG = full_msg

        # 发射信号并将发送的消息放入表格
        self.tx_message.emit(full_msg)
        self.add_info_table_row(current_time, self.callsign, to_call, self.grid, msg, "Ground")

        # 禁用发射按钮避免过频繁发射
        self.TX_button.setEnabled(False)
        self.send_timer.start(self.cooldown_ms)

    # 解锁按钮
    def unlock_send_button(self):
        self.TX_button.setEnabled(True)

    # 添加数据到通联信息表格(此函数同时从串口线程读取数据)
    def add_info_table_row(self, time_str, source_call, target_call, grid, message, program):

        # 计数
        self.rx_count += 1

        # 直接使用 self.info_table 访问表格实例
        row_position = self.info_table.rowCount()
        self.info_table.insertRow(row_position)

        # 时间
        item_time = QTableWidgetItem(time_str)
        item_time.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        self.info_table.setItem(row_position, 0, item_time)

        # 源站呼号
        item_source_call = QTableWidgetItem(source_call)
        item_source_call.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        self.info_table.setItem(row_position, 1, item_source_call)

        # 目标呼号
        item_target_call = QTableWidgetItem(target_call)
        item_target_call.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        self.info_table.setItem(row_position, 2, item_target_call)

        # 信息
        item_message = QTableWidgetItem(f"{grid},{message}")
        item_message.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.info_table.setItem(row_position, 3, item_message)

        # 将自己发送的消息颜色设置为#FFA07A
        if source_call == self.callsign and program == "Ground":
            self.rx_count -= 1
            for col in range(self.info_table.columnCount()):
                item = self.info_table.item(row_position, col)
                if item:
                    item.setBackground(QColor("#FFA07A"))
        # 从气球上转发回来的自己的消息
        elif source_call == self.callsign and program == "Balloon":
            for col in range(self.info_table.columnCount()):
                item = self.info_table.item(row_position, col)
                if item:
                    item.setBackground(QColor("#FFE4EA"))
        # 将发给我的消息设置为#00BFFF
        elif target_call == self.callsign:
            for col in range(self.info_table.columnCount()):
                item = self.info_table.item(row_position, col)
                if item:
                    item.setBackground(QColor("#00BFFF"))
                if "73" in message:
                    self.add_qso_table_row(source_call, grid)
        #将他人的CQ设置为#EE82EE
        elif target_call == "CQ":
            for col in range(self.info_table.columnCount()):
                item = self.info_table.item(row_position, col)
                if item:
                    item.setBackground(QColor("#EE82EE"))
        # 其他普通消息设置为#FFFFFF
        else:
            for col in range(self.info_table.columnCount()):
                item = self.info_table.item(row_position, col)
                if item:
                    item.setBackground(QColor("#FFFFFF"))

        # 信息滚动
        scrollbar = self.info_table.verticalScrollBar()
        at_bottom = scrollbar.value() == scrollbar.maximum()
        if at_bottom:
            self.info_table.scrollToBottom()

        # 更新计数
        self.rx_count_num.setText(str(self.rx_count))
        self.rx_count_num.adjustSize()

    # 添加 QSO 表格行
    def add_qso_table_row(self, source_call, grid):

        # 如果已经记录过该呼号则跳过
        if source_call in self.qso_callsigns:
            return

        # 添加到已记录集合
        self.qso_callsigns.add(source_call)

        # 计数
        self.QSO_count += 1
        self.QSO_count_num.setText(str(self.QSO_count))
        self.QSO_count_num.adjustSize()

        # 插入表格行
        row_position = self.QSO_info_table.rowCount()
        self.QSO_info_table.insertRow(row_position)

        # 时间
        item_time = QTableWidgetItem(datetime.now().strftime("%H:%M:%S")) 
        item_time.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        self.QSO_info_table.setItem(row_position, 0, item_time)

        # 对方呼号
        item_source_call = QTableWidgetItem(source_call)
        item_source_call.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        self.QSO_info_table.setItem(row_position, 1, item_source_call)

        # 网格
        item_grid = QTableWidgetItem(grid)
        item_grid.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        self.QSO_info_table.setItem(row_position, 2, item_grid)

        # 滚动到底部
        scrollbar = self.QSO_info_table.verticalScrollBar()
        at_bottom = scrollbar.value() == scrollbar.maximum()
        if at_bottom:
            self.QSO_info_table.scrollToBottom()

    # 双击表格行时，将该行的“源站呼号”自动填充到呼号输入框。
    def fill_callsign_from_table(self, row):

        # 获取源呼号和目标呼号
        FmCallsign = self.info_table.item(row, 1).text()
        ToCallsign = self.info_table.item(row, 2).text()
        MSG = self.info_table.item(row, 3).text()

        # 当对方在CQ时，回复73,QSL?
        if (FmCallsign != self.callsign and ToCallsign == "CQ"):
            self.Callsign_input.setText(FmCallsign)
            self.MSG_input.setText("73")
        # 当对方回复我的CQ时(即73,QSL?)，回复RR73 QSL.
        elif (FmCallsign != self.callsign and ToCallsign == self.callsign and len(MSG) > 6 and MSG.endswith(",73")):
            self.Callsign_input.setText(FmCallsign)
            self.MSG_input.setText("RR73")
        else:
            if FmCallsign != self.callsign:
                self.Callsign_input.setText(FmCallsign)

    # 经纬度转梅登黑德网格
    def latlng_to_maiden(self, lat, lon):
        lat += 90
        lon += 180
        return (
            f"{chr(int(lon // 20) + 65)}{chr(int(lat // 10) + 65)}"
            f"{int((lon % 20) // 2)}{int(lat % 10)}"
            f"{chr(int((lon % 2) * 12) + 97)}{chr(int((lat % 1) * 24) + 97)}"
        )

# 主事件
if __name__ == '__main__':
    app = QApplication(sys.argv)
    GUI = GUI()
    GUI.show()
    sys.exit(app.exec())
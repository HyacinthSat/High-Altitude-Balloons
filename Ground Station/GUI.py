# -*- coding: utf-8 -*-

"""
GUI program for Balloon Ground Station.

This program is a graphical user interface implemented using PyQt,
It connects to and manages the receiver serial port to acquire telemetry and image data from high-altitude balloons.
The program real-time parses and displays the balloon's GPS information, integrates map tracking, and features SSDV image downlink capabilities,
providing a comprehensive ground monitoring and data visualization solution for HAB missions.

Author: BG7ZDQ
Date: 2025/06/12
Version: 0.1.0
LICENSE: GNU General Public License v3.0
"""

import re
import os
import sys
import serial
import subprocess
import numpy as np
from serial.tools import list_ports
from datetime import datetime, timezone
from configparser import RawConfigParser
from PyQt6.QtGui import QIcon, QPixmap, QColor
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import Qt, QUrl, QTimer, QTime, QThread, pyqtSignal
from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QPushButton, QPlainTextEdit, QMessageBox, QComboBox, QLineEdit, QFormLayout, QHeaderView, QTableWidget, QVBoxLayout, QTableWidgetItem, QAbstractItemView, QDialog, QTabWidget, QHBoxLayout, QFileDialog

# 禁用 GPU 加速
os.environ['QTWEBENGINE_CHROMIUM_FLAGS'] = '--disable-gpu --disable-software-rasterizer'

# 全局组件样式
tip_text_style = 'color: #3063AB; font-family: 微软雅黑; font: 10pt; border: none;'
callsign_style = 'color: #3063AB; font-family: 微软雅黑; font: bold 16pt; border: none;'
primary_text_style = 'color: #3063AB; font-family: 微软雅黑; font: bold 12pt; border: none;'
secondary_text_style = 'color: #555555; font-family: 微软雅黑; font: bold 12pt; border: none;'

qso_frame_style = 'border: 1px solid #AAAAAA; border-radius: 4px;'
debug_box_style = 'QPlainTextEdit { background-color: #FFFFFF; color: #3063AB; border: 1px solid #3498db; border-radius: 5px; padding: 1px; font-family: 微软雅黑; font-size: 12px;}'
combo_box_style = 'QComboBox { background-color: #ffffff; border: 1px solid #3498db; border-radius: 3px; padding: 2px; min-width: 6em; font: bold 10pt "微软雅黑"; color: #3063AB;} QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 20px; border-left: 1px solid #3498db;}QComboBox::down-arrow { image: url(UI/arrow.svg); width: 10px; height: 10px;} QComboBox QAbstractItemView { background: #ffffff; selection-background-color: #89CFF0; selection-color: #000000; border: 1px solid #3498db; outline: 0; font: 10pt "微软雅黑";}'
input_box_style = 'QLineEdit { background-color: #FFFFFF; color: #3063AB; border: 1px solid #3498db; border-radius: 5px; padding: 1px; font-family: 微软雅黑; font-size: 12px; } QPlainTextEdit { background-color: #FFFFFF; color: #3063AB; border: 1px solid #3498db; border-radius: 5px; padding: 1px; font-family: 微软雅黑; font-size: 12px; } QLineEdit:disabled {background-color: #F0F0F0; color: #000000; border: 1px solid #888888;}'
common_button_style = 'QPushButton { background-color: #3498db; color: #ffffff; border-radius: 5px; padding: 6px; font-size: 12px;} QPushButton:hover {background-color: #2980b9;} QPushButton:pressed {background-color: #21618c;}'

# 处理配置文件
config = RawConfigParser()
config.optionxform = str
config.read("config.ini")

# 检查配置文件是否存在且包含必要信息
def is_config_valid():
    try:
        config.read('config.ini')
        config.get("GroundStation", "Callsign")
        config.getfloat("GroundStation", "Latitude")
        config.getfloat("GroundStation", "Longitude")
        config.getfloat("GroundStation", "Altitude")
        return True
    except Exception:
        return False

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

        # 线程占位符
        self.SET_window = None
        self.QSO_window = None
        self.decoder_thread = None
        self.Command_window = None
        self.Radio_Serial_Thread = None

        # 气球信息
        self.balloon_lat = 0
        self.balloon_lng = 0
        self.balloon_alt = 0
        self.balloon_time = "2025-05-25T00:00:00Z"

        # 旋转器信息
        self.Rotator_AZ = 00.00
        self.Rotator_EL = 00.00

        # 图像编号
        self.filename  = ''
        self.img_num   = -1
        self.frame_num = 1

        # 设置可复用的状态图标
        global standby, success, warning, failure, pending
        standby = QPixmap('UI/standby.svg')
        success = QPixmap('UI/success.svg')
        warning = QPixmap('UI/warning.svg')
        failure = QPixmap('UI/failure.svg')
        pending = QPixmap('UI/pending.svg')

        # 状态码翻译与处理字典
        self.status_code_map = {
            # --- 系统级状态码 (0x10xx) ---
            0x1000: ("[正常] 正在启动..."  , "init", pending),
            0x1001: ("[正常] 系统初始化完成", "init", success),
            0x1002: ("[错误] 系统初始化失败", "init", failure),
            0x1003: ("[注意] 系统将受控重启", "init", warning),
            0x1004: ("[注意] 处于开发者模式",  None , None),
            0x1005: ("[警告] 中继功能已限流", "data", warning),

            # --- 摄像头状态码 (0x20xx) ---
            0x2000: ("[正常] 相机初始化开始", "camera", pending),
            0x2001: ("[正常] 相机初始化成功", "camera", success),
            0x2002: ("[错误] 相机初始化失败", "camera", failure),
            0x2003: ("[正常] 相机开始校准"  , "camera", pending),
            0x2004: ("[正常] 相机校准成功"  , "camera", success),
            0x2005: ("[错误] 相机校准失败"  , "camera", failure),
            0x2006: ("[警告] 图像获取失败"  , "camera", failure),
            0x2007: ("[正常] 相机配置成功"  , "camera", success),
            0x2008: ("[警告] 相机配置失败"  , "camera", failure),
            0x2009: ("[注意] 相机参数重置"  , "camera", success),
            0x200A: ("[错误] 相机重置失败"  , "camera", failure),
            
            # --- GPS 状态码 (0x30xx) ---
            0x3000: ("[正常] GPS 初始化开始", "gps", pending),
            0x3001: ("[正常] GPS 初始化成功", "gps", success),
            0x3002: ("[错误] GPS 初始化超时", "gps", failure),

            # --- SSDV 状态码 (0x40xx) ---
            0x4000: ("[正常] 图像编码开始", "data", pending),
            0x4001: ("[正常] 图像发送完毕", "data", success),
            0x4002: ("[错误] 图像编码错误", "data", failure),
            0x4003: ("[警告] 图像缓冲区满", "data", warning),

            # --- 指令应答 (0x50xx, 0x51xx) ---
            # NACK
            0x5000: ("[拒绝] 命令密码错误", None, None),
            0x5001: ("[拒绝] 指令格式错误", None, None),
            0x5002: ("[拒绝] 指令缺少参数", None, None),
            0x5003: ("[拒绝] 指令类型无效", None, None),
            0x5004: ("[拒绝] 查询目标无效", None, None),
            0x5005: ("[拒绝] 控制目标无效", None, None),
            0x5006: ("[拒绝] 设置目标无效", None, None),
            0x5007: ("[拒绝] 图传任务正忙", None, None),
            0x5008: ("[拒绝] 图像质量无效", None, None),
            0x5009: ("[拒绝] 图像质量过高", None, None),
            0x500A: ("[拒绝] 编码质量无效", None, None),
            0x500B: ("[拒绝] 图传周期无效", None, None),
            0x5016: ("[拒绝] 图传模式无效", None, None),
            0x5017: ("[拒绝] 图传预设无效", None, None),
            # CTL ACK
            0x500C: ("[应答] 中继功能已开启", None, None),
            0x500D: ("[应答] 中继功能已关闭", None, None),
            0x500E: ("[应答] 图传功能已开启", None, None),
            0x500F: ("[应答] 图传功能已关闭", None, None),
            # SET ACK
            0x5010: ("[应答] 图传模式已设置", None, None),
            0x5011: ("[应答] 图传质量已设置", None, None),
            0x5012: ("[应答] 图传周期已设置", None, None),
            0x5013: ("[应答] 图像尺寸已设置", None, None),
            0x5014: ("[应答] 图像质量已设置", None, None),
            0x5015: ("[应答] 图传预设已设置", None, None),
            # GET ACK
            0x5100: ("[查询] 中继状态", None, None),
            0x5101: ("[查询] 图传状态", None, None),
            0x5102: ("[查询] 图传模式", None, None),
            0x5103: ("[查询] 图传质量", None, None),
            0x5104: ("[查询] 图传周期", None, None),
            0x5105: ("[查询] 图像尺寸", None, None),
            0x5106: ("[查询] 图像质量", None, None),
            
            # --- 传感器状态码 (0x60xx) ---
            0x6000: ("[错误] 电压采样失败", "data", failure),
        }

        # 翻译枚举定义
        self.CAM_SIZE_MAP = {
            "14": "FHD  (1920x1080)",
            "12": "SXGA (1280x1024)",
            "10": "XGA  (1024x768)",
            "8" : "VGA  (640x480)",
            "5" : "QVGA (320x240)",
        }
        self.SSDV_TYPE_MAP = {
            "0": "FEC",
            "1": "NOFEC",
        }
        self.ESP_ERR_MAP = {
            "0":     "OK",
            "1":     "FAIL",
            "257":   "ERR_NO_MEM",
            "258":   "ERR_INVALID_ARG",
            "259":   "ERR_INVALID_STATE",
            "260":   "ERR_INVALID_SIZE",
            "261":   "ERR_NOT_FOUND",
            "262":   "ERR_NOT_SUPPORTED",
            "263":   "ERR_TIMEOUT",
            # --- 摄像头相关错误码 (基于 0x20000) ---
            "131073": "ERR_CAMERA_NOT_DETECTED",
            "131074": "ERR_CAMERA_FAILED_TO_SET_FRAME_SIZE",
            "131075": "ERR_CAMERA_FAILED_TO_INIT",
            "131076": "ERR_CAMERA_FAILED_TO_GET_FB",
        }

        # 定义串口数据缓存区 (接收) 
        self.rx_buffer = bytearray()

        # 绘制UI
        self.UI()

        # 然后检查配置
        if not is_config_valid():
            # 配置无效，弹出设置窗口让用户设置
            QMessageBox.information(self, "欢迎", "首次运行，请先设置地面站信息。")
            
            # 打开设置窗口
            self.SET_window = SET_Windows("", 0.0, 0.0, 0.0)
            self.SET_window.settings_saved.connect(self.update_ground_station_settings)
            
            # 以模态方式执行对话框
            result = self.SET_window.exec()

            # 检查用户是否完成了保存
            if result == QDialog.DialogCode.Accepted:
                config.read('config.ini')
                self.callsign = config.get("GroundStation", "Callsign")
                self.local_lat = config.getfloat("GroundStation", "Latitude")
                self.local_lng = config.getfloat("GroundStation", "Longitude")
                self.local_alt = config.getfloat("GroundStation", "Altitude")
                self.debug_info("首次设置成功。")
            else:
                QMessageBox.warning(self, "提示", "未完成基本设置，程序将退出。")
                sys.exit(1)
                return
        else:
            # 配置有效，加载信息
            self.callsign = config.get("GroundStation", "Callsign")
            self.local_lat = config.getfloat("GroundStation", "Latitude")
            self.local_lng = config.getfloat("GroundStation", "Longitude")
            self.local_alt = config.getfloat("GroundStation", "Altitude")

    # 主窗口
    def UI(self):

        '''左栏'''
        # 接收机端口选择部分
        self.Radio_COM_status = QLabel(self)
        self.Radio_COM_status.setPixmap(standby)
        self.Radio_COM_status.move(40, 28)

        self.Receiver_COM_label = QLabel(self)
        self.Receiver_COM_label.setText("接收机端口：")
        self.Receiver_COM_label.move(65, 25)
        self.Receiver_COM_label.setStyleSheet(primary_text_style)

        self.Radio_COM_Combo = QComboBox(self)
        self.Radio_COM_Combo.addItems([])
        self.Radio_COM_Combo.setGeometry(165, 21, 120, 30)
        self.Radio_COM_Combo.setStyleSheet(combo_box_style)

        self.Radio_COM_button = QPushButton("连接", self)
        self.Radio_COM_button.setGeometry(300, 21, 50, 27)
        self.Radio_COM_button.setStyleSheet(common_button_style)
        self.Radio_COM_button.clicked.connect(self.Connect_Radio_COM)

        # 旋转器端口选择部分
        self.Rotator_COM_status = QLabel(self)
        self.Rotator_COM_status.setPixmap(standby)
        self.Rotator_COM_status.move(40, 63)

        self.Rotator_COM_label = QLabel(self)
        self.Rotator_COM_label.setText("旋转器端口：")
        self.Rotator_COM_label.move(65, 60)
        self.Rotator_COM_label.setStyleSheet(primary_text_style)

        self.Rotator_COM_Combo = QComboBox(self)
        self.Rotator_COM_Combo.addItems([])
        self.Rotator_COM_Combo.setGeometry(165, 56, 120, 30)
        self.Rotator_COM_Combo.setStyleSheet(combo_box_style)

        self.Rotator_COM_button = QPushButton("连接", self)
        self.Rotator_COM_button.setGeometry(300, 56, 50, 27)
        self.Rotator_COM_button.setStyleSheet(common_button_style)
        self.Rotator_COM_button.clicked.connect(self.Connect_Rotator_COM)

        # GPS 数据
        self.GPS_status = QLabel(self)
        self.GPS_status.setPixmap(QPixmap('UI/geo.svg'))
        self.GPS_status.move(40, 103)

        self.GPS_label = QLabel(self)
        self.GPS_label.setText("GPS 数据：尚无")
        self.GPS_label.move(65, 100)
        self.GPS_label.setStyleSheet(primary_text_style)

        # 轨迹地图嵌入
        self.map_view = QWebEngineView(self)
        self.map_view.setGeometry(40, 130, 320, 240)
        self.map_view.setUrl(QUrl("http://hab.satellites.ac.cn/map"))

        self.GPS_LAT_label = QLabel(self)
        self.GPS_LAT_label.setText("经度: ")
        self.GPS_LAT_label.move(40, 390)
        self.GPS_LAT_label.setStyleSheet(primary_text_style)

        self.GPS_LAT_NUM = QLabel(self)
        self.GPS_LAT_NUM.setText("")
        self.GPS_LAT_NUM.move(85, 390)
        self.GPS_LAT_NUM.setStyleSheet(primary_text_style)

        self.GPS_LON_label = QLabel(self)
        self.GPS_LON_label.setText("纬度：")
        self.GPS_LON_label.move(200, 390)
        self.GPS_LON_label.setStyleSheet(primary_text_style)

        self.GPS_LON_NUM = QLabel(self)
        self.GPS_LON_NUM.setText("")
        self.GPS_LON_NUM.move(245, 390)
        self.GPS_LON_NUM.setStyleSheet(primary_text_style)

        self.GPS_ALT_label = QLabel(self)
        self.GPS_ALT_label.setText("高度：")
        self.GPS_ALT_label.move(40, 415)
        self.GPS_ALT_label.setStyleSheet(primary_text_style)

        self.GPS_ALT_NUM = QLabel(self)
        self.GPS_ALT_NUM.setText("")
        self.GPS_ALT_NUM.move(85, 415)
        self.GPS_ALT_NUM.setStyleSheet(primary_text_style)

        self.GPS_SPD_label = QLabel(self)
        self.GPS_SPD_label.setText("速度：")
        self.GPS_SPD_label.move(200, 415)
        self.GPS_SPD_label.setStyleSheet(primary_text_style)

        self.GPS_SPD_NUM = QLabel(self)
        self.GPS_SPD_NUM.setText("")
        self.GPS_SPD_NUM.move(245, 415)
        self.GPS_SPD_NUM.setStyleSheet(primary_text_style)

        self.GPS_SATS_label = QLabel(self)
        self.GPS_SATS_label.setText("卫星数: ")
        self.GPS_SATS_label.move(200, 440)
        self.GPS_SATS_label.setStyleSheet(primary_text_style)

        self.GPS_SATS_NUM = QLabel(self)
        self.GPS_SATS_NUM.setText("")
        self.GPS_SATS_NUM.move(260, 440)
        self.GPS_SATS_NUM.setStyleSheet(primary_text_style)

        self.GPS_heading_label = QLabel(self)
        self.GPS_heading_label.setText("航向角: ")
        self.GPS_heading_label.move(40, 440)
        self.GPS_heading_label.setStyleSheet(primary_text_style)

        self.GPS_heading_NUM = QLabel(self)
        self.GPS_heading_NUM.setText("")
        self.GPS_heading_NUM.move(100, 440)
        self.GPS_heading_NUM.setStyleSheet(primary_text_style)

        self.rotator_az_label = QLabel(self)
        self.rotator_az_label.setText("方位角：")
        self.rotator_az_label.move(40, 465)
        self.rotator_az_label.setStyleSheet(primary_text_style)

        self.rotator_az_NUM = QLabel(self)
        self.rotator_az_NUM.setText("")
        self.rotator_az_NUM.move(100, 465)
        self.rotator_az_NUM.setStyleSheet(primary_text_style)

        self.rotator_el_label = QLabel(self)
        self.rotator_el_label.setText("俯仰角：")
        self.rotator_el_label.move(200, 465)
        self.rotator_el_label.setStyleSheet(primary_text_style)

        self.rotator_el_NUM = QLabel(self)
        self.rotator_el_NUM.setText("")
        self.rotator_el_NUM.move(260, 465)
        self.rotator_el_NUM.setStyleSheet(primary_text_style)
        
        '''右栏'''
        # 系统状态指示
        self.Data_status_label = QLabel(self)
        self.Data_status_label.setText("数传:")
        self.Data_status_label.move(420, 25)
        self.Data_status_label.setStyleSheet(primary_text_style)

        self.Data_status_icon = QLabel(self)
        self.Data_status_icon.setPixmap(standby)
        self.Data_status_icon.move(465, 28)

        self.Camera_status_label = QLabel(self)
        self.Camera_status_label.setText("相机:")
        self.Camera_status_label.move(500, 25)
        self.Camera_status_label.setStyleSheet(primary_text_style)

        self.Camera_status_icon = QLabel(self)
        self.Camera_status_icon.setPixmap(standby)
        self.Camera_status_icon.move(545, 28)

        self.GPS_status_label = QLabel(self)
        self.GPS_status_label.setText("定位:")
        self.GPS_status_label.move(580, 25)
        self.GPS_status_label.setStyleSheet(primary_text_style)

        self.GPS_status_icon = QLabel(self)
        self.GPS_status_icon.setPixmap(standby)
        self.GPS_status_icon.move(625, 28)

        self.init_status_label = QLabel(self)
        self.init_status_label.setText("自检:")
        self.init_status_label.move(660, 25)
        self.init_status_label.setStyleSheet(primary_text_style)

        self.init_status_icon = QLabel(self)
        self.init_status_icon.setPixmap(standby)
        self.init_status_icon.move(705, 28)

        # 帧类型指示器
        self.Frame_type_icon = QLabel(self)
        self.Frame_type_icon.setPixmap(QPixmap('UI/data.svg'))
        self.Frame_type_icon.move(420, 63)

        self.Frame_type_label = QLabel(self)
        self.Frame_type_label.setText("当前帧类型：")
        self.Frame_type_label.move(445, 60)
        self.Frame_type_label.setStyleSheet(primary_text_style)

        self.Frame_type_output = QLabel(self)
        self.Frame_type_output.setText("暂无有效帧")
        self.Frame_type_output.move(545, 60)
        self.Frame_type_output.setStyleSheet(secondary_text_style)
    
        # 图片接收
        self.SSDV_icon = QLabel(self)
        self.SSDV_icon.setPixmap(QPixmap('UI/image.svg'))
        self.SSDV_icon.move(420, 103)

        self.SSDV_label = QLabel(self)
        self.SSDV_label.setText("图像回传：")
        self.SSDV_label.move(445, 100)
        self.SSDV_label.setStyleSheet(primary_text_style)

        self.SSDV_name_output = QLabel(self)
        self.SSDV_name_output.setText("尚无有效图像")
        self.SSDV_name_output.move(525, 100)
        self.SSDV_name_output.setStyleSheet(primary_text_style)

        # SSDV 接收框
        self.SSDV_IMG = QLabel(self)
        self.SSDV_IMG.setPixmap(QPixmap("UI/SSDV.jpeg").scaled(320, 240, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.SSDV_IMG.setFixedSize(320, 240)
        self.SSDV_IMG.move(420, 130)

        self.DEBUG_INFO_label = QLabel(self)
        self.DEBUG_INFO_label.setText("调试信息：")
        self.DEBUG_INFO_label.move(420, 390)
        self.DEBUG_INFO_label.setStyleSheet(primary_text_style)

        self.SET_button = QPushButton("设置", self)
        self.SET_button.setGeometry(500, 387, 50, 27)
        self.SET_button.setStyleSheet(common_button_style)
        self.SET_button.clicked.connect(self.SET)

        self.QSO_button = QPushButton("通信", self)
        self.QSO_button.setGeometry(560, 387, 50, 27)
        self.QSO_button.setStyleSheet(common_button_style)
        self.QSO_button.clicked.connect(self.QSO)

        self.Command_button = QPushButton("命令", self)
        self.Command_button.setGeometry(620, 387, 50, 27)
        self.Command_button.setStyleSheet(common_button_style)
        self.Command_button.clicked.connect(self.Command)

        self.DEBUG_output = QPlainTextEdit(self)
        self.DEBUG_output.setReadOnly(True)
        self.DEBUG_output.setGeometry(420, 420, 330, 65)
        self.DEBUG_output.setStyleSheet(debug_box_style)

        # 串口刷新定时器
        self.Update_COM_Info()
        self.serial_timer = QTimer(self)
        self.serial_timer.timeout.connect(self.Update_COM_Info)
        self.serial_timer.start(500)

    # 向调试信息框写入信息
    def debug_info(self, text):
        time = datetime.now().strftime("%H:%M:%S")
        self.DEBUG_output.appendPlainText(f"{time} {text}")
        print(text)

    # 处理收发信机的串口数据
    def Handle_Radio_Serial_Data(self, data: bytes):
        self.rx_buffer.extend(data)

        # 只要缓冲区内容在一次完整的处理循环中发生了变化，就持续循环
        while True:
            buffer_changed_this_cycle = False

            # 先检测清理所有前导噪声
            if self.discard_leading_garbage():
                buffer_changed_this_cycle = True

            # 然后循环提取所有完整的 SSDV 帧
            while self.try_extract_ssdv():
                buffer_changed_this_cycle = True

            # 循环提取所有完整的文本帧
            if self.Try_Extract_Text():
                buffer_changed_this_cycle = True
            
            # 如果经过一整轮的清理、SSDV提取、文本提取后，缓冲区没有任何变化，
            # 说明剩下的都是不完整的数据帧，应该跳出循环，等待更多新数据进来。
            if not buffer_changed_this_cycle:
                break
    
    # 清除缓冲区的噪声数据
    def discard_leading_garbage(self) -> bool:
        
        # 定义所有已知有效数据包的头部
        known_headers = [
            b"\x55\x67",  # SSDV NOFEC 模式
            b"\x55\x66",  # SSDV 正常模式
            b"**"         # 文本模式
        ]

        # 如果缓冲区为空，则无需操作
        if not self.rx_buffer:
            return False

        # 寻找第一个出现的有效包头的位置
        first_valid_pos = -1
        for header in known_headers:
            pos = self.rx_buffer.find(header)
            if pos != -1:
                if first_valid_pos == -1 or pos < first_valid_pos:
                    first_valid_pos = pos
        
        # 情况一：缓冲区中存在至少一个有效包头
        if first_valid_pos != -1:
            if first_valid_pos > 0:
                # self.debug_info(f"检测并丢弃 {first_valid_pos} 字节的无效数据。")
                self.rx_buffer = self.rx_buffer[first_valid_pos:]
                return True
            else:
                return False

        # 情况二：缓冲区超长但找不到任何有效的包头时，清空缓冲区
        else:
            if len(self.rx_buffer) > 512:
                self.debug_info(f"已清空 {len(self.rx_buffer)} 字节噪声。")
                self.rx_buffer.clear()
                return True
            return False

    # 使用正则表达式提取文本帧信息
    def Try_Extract_Text(self) -> bool:
        current_buffer_str = bytes(self.rx_buffer)
        original_len = len(current_buffer_str)
        
        # 使用 re.sub 来替换所有文本帧匹配项
        def process_and_remove(match):
            Text_raw = match.group(0)
            try:
                Text_text = Text_raw.decode("utf-8", errors="strict").strip("* ").strip()
                # 数传状态正常，将文本数据发送到处理函数
                self.Data_status_icon.setPixmap(success)
                self.Processing_Text_Data(Text_text)
            except UnicodeDecodeError:
                print(f"[警告] 文本解码失败: {Text_raw}")
            
            # 返回空字节串，相当于从原字符串中删除此匹配项
            return b""

        # 查找所有匹配项，并用 process_and_remove 函数的返回值替换
        modified_buffer_str = re.sub(rb"\*\*(.+?)\*\*", process_and_remove, current_buffer_str)

        if len(modified_buffer_str) < original_len:
            self.rx_buffer = bytearray(modified_buffer_str)
            return True
        else:
            return False
        
    # 处理非图像文本数据
    def Processing_Text_Data(self, text):

        # 记录日志
        print(f"文本帧：{text}")
        time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open("log.txt", "a", encoding="utf-8") as f:
            f.write(f"{time}    « {text}\n")

        # 处理 $$ 开头的遥测数据
        # $$CALLSIGN,Frame_Counter,HH:MM:SS,latitude,longitude,altitude,speed,sats,heading
        if text.startswith("$$"):
            try:
                fields = text[2:].strip().split(",")
                if len(fields) == 12:
                    balloon_callsign = fields[0]                # 气球呼号
                    telemetry_counter = fields[1]               # 帧计数
                    self.balloon_time = fields[2]               # 球上时间
                    new_balloon_lat = float(fields[3])          # 气球纬度
                    new_balloon_lng = float(fields[4])          # 气球经度
                    new_balloon_alt = float(fields[5])          # 气球高度
                    self.balloon_spd = float(fields[6])         # 气球速度
                    self.balloon_sats = int(fields[7])          # 卫星数量
                    self.balloon_heading = float(fields[8])     # 气球航向
                    self.balloon_temprature = float(fields[9])  # 球上温度
                    self.balloon_voltage = float(fields[10])    # 球上电压
                    self.gps_validity = fields[11]              # 定位状态
                else:
                    self.debug_info(f"[警告] 遥测数据格式错误: {text}")
                    return
            except Exception as e:
                self.debug_info(f"遥测数据解析出错：{e}")
                return
            
            # 更新 UI 显示
            self.Frame_type_output.setText(f"基本遥测帧 {telemetry_counter}")
            self.Frame_type_output.adjustSize()

            # GPS 有效性检查
            if self.gps_validity == "A":
                self.debug_info(f"遥测数据已更新")
                # 控制旋转器
                self.Rotator_AZ, self.Rotator_EL = self.calculate_az_el(new_balloon_lat, new_balloon_lng, new_balloon_alt)
                # 更新数值
                self.balloon_lat = new_balloon_lat
                self.balloon_lng = new_balloon_lng
                self.balloon_alt = new_balloon_alt
                # 更新标签显示
                self.GPS_status_icon.setPixmap(success)
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
                self.rotator_az_NUM.setText(f"{self.Rotator_AZ:.2f}")
                self.rotator_az_NUM.adjustSize()
                self.rotator_el_NUM.setText(f"{self.Rotator_EL:.2f}")
                self.rotator_el_NUM.adjustSize()

                # 更新地图显示
                self.update_map_position()
            else:
                self.GPS_status_icon.setPixmap(failure)
                self.debug_info(f"[注意] GPS 数据无效")
                # 更新标签
                self.GPS_label.setText(f"GPS 数据：无效")
                self.GPS_label.adjustSize()

            # 获取现在的时间并将其格式化
            time_received = datetime.now(timezone.utc)
            time_received = time_received.strftime('%Y-%m-%dT%H:%M:%S') + 'Z'

            # 调用 SondeHub API接口
            try:
                command_args = [
                    "./sondehub",
                    f"{self.callsign}",            # 上传者呼号
                    f"{time_received}",            # 接收时间
                    f"{balloon_callsign}",         # 气球呼号
                    f"{self.balloon_time}",        # 球上时间
                    f"{new_balloon_lng}",          # 气球经度
                    f"{new_balloon_lat}",          # 气球纬度
                    f"{new_balloon_alt}",          # 气球高度 
                    f"{self.balloon_heading}",     # 气球航向
                    f"{self.balloon_spd}",         # 气球速度 
                    f"{self.balloon_sats}",        # 卫星数量
                    f"{self.balloon_temprature}",  # 球上温度
                    f"{self.balloon_voltage}",     # 球上电压
                    f"{self.local_lng}",           # 地面站经度
                    f"{self.local_lat}",           # 地面站纬度
                    f"{self.local_alt}",           # 地面站高度
                    "normal"                       # 开发状态
                ]
                subprocess.Popen(command_args)
            except Exception as e:
                self.debug_info(f"SondeHub上传失败: {e}")
                return False
            
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

        # 处理系统状态码 (Code: 0xXXXX)
        elif text.startswith("Code:"):
            self.Frame_type_output.setText(f"状态提示帧")
            self.Frame_type_output.adjustSize()
            
            # 使用正则表达式解析状态码和可选的Payload
            match = re.search(r"Code: 0x([0-9A-Fa-f]{4})(?:, Info: (.*))?", text)
            if not match:
                return

            # 提取状态码和 Payload
            status_code_hex = match.group(1)
            payload_hex = match.group(2)
            status_code = int(status_code_hex, 16)

            # 从字典中查找对应的处理信息
            if status_code in self.status_code_map:
                prompt, icon_category, icon = self.status_code_map[status_code]
                
                # 调用翻译函数，构造并显示调试信息
                debug_message = f"{prompt}"
                if payload_hex:
                    translated_payload = self.translate_payload(status_code, payload_hex)
                    debug_message += f": {translated_payload}"
                
                self.debug_info(debug_message)

                # 更新对应的状态图标
                if icon_category and icon:
                    if icon_category == "init":
                        self.init_status_icon.setPixmap(icon)
                    elif icon_category == "camera":
                        self.Camera_status_icon.setPixmap(icon)
                    elif icon_category == "gps":
                        self.GPS_status_icon.setPixmap(icon)
                    elif icon_category == "data":
                        self.Data_status_icon.setPixmap(icon)
            else:
                self.debug_info(f"收到未知状态码: 0x{status_code_hex.upper()}")
            return
        
        # 对于不符合任何已知格式的文本，直接显示
        else:
            self.debug_info(f"{text}")


    # 提取 SSDV 数据
    def try_extract_ssdv(self) -> bool:
        
        # 定义帧信息并寻找帧头
        header1 = b"\x55\x67" # NOFEC模式
        header2 = b"\x55\x66" # 正常模式
        frame_len = 256
        start = self.rx_buffer.find(header1)
        if start == -1: start = self.rx_buffer.find(header2)

        # 首先判断是否为完整帧再进行提取
        if start == -1 or len(self.rx_buffer) - start < frame_len: return False
        frame = self.rx_buffer[start:start + frame_len]

        # 接收到SSDV数据包证明数传正常，摄像头工作正常，初始化正常
        self.Data_status_icon.setPixmap(success)
        self.Camera_status_icon.setPixmap(success)
        self.init_status_icon.setPixmap(success)

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
            self.rx_buffer = self.rx_buffer[start + frame_len:]
            return False
        
        # 累计帧计数
        self.Frame_type_output.setText(f"SSDV 图像数据帧 {self.frame_num}")
        self.Frame_type_output.adjustSize()
        self.frame_num += 1

        # 图像文件名
        self.SSDV_name_output.setText(f"{self.filename}")
        self.SSDV_name_output.adjustSize()
        
        # 确保 'dat' 文件夹存在并将接收到的数据进行存储
        os.makedirs("dat", exist_ok=True)
        dat_filepath = f"dat/{self.filename}.dat"
        try:
            with open(dat_filepath, "ab") as f:
                f.write(frame)
        except IOError as e:
            self.debug_info(f"写入 SSDV 数据失败: {e}")
            return False

        # 启动一个工作线程来解码 SSDV，避免阻塞 UI
        output_jpg_path = f"{self.filename}.jpg"
        self.decoder_thread = SsdvDecoderThread(dat_filepath, output_jpg_path, self)
        
        # 连接解码完成信号到处理结果的槽
        self.decoder_thread.decoding_finished.connect(self.on_decoding_finished)
        
        # 连接日志信号到显示调试信息的槽
        self.decoder_thread.log_message.connect(self.debug_info)
        
        # 确保线程结束后能被Qt安全地回收内存
        self.decoder_thread.finished.connect(self.decoder_thread.deleteLater) 
        self.decoder_thread.start()

        # 从缓冲区移除已处理数据
        self.rx_buffer = self.rx_buffer[start + frame_len:]
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
            self.Radio_Serial_Thread.connection_failed.connect(self.on_connection_failed)
            self.Radio_Serial_Thread.start()

            # 检查是否已经成功连接
            if self.Radio_Serial_Thread and self.Radio_Serial_Thread.isRunning():
                self.Radio_COM_status.setPixmap(success)
                self.Radio_COM_button.setText("断开")
                print(f"接收机串口已连接：{port_name}")
                self.debug_info(f"接收机串口已连接：{port_name}")

        else:
            if self.Radio_Serial_Thread:
                self.Radio_Serial_Thread.stop()

            # 手动断开时，也应该确保 UI 状态正确更新
            self.Radio_COM_status.setPixmap(standby)
            self.Radio_COM_button.setText("连接")

            # 确保线程对象被清理
            if self.Radio_Serial_Thread:
                 self.Radio_Serial_Thread = None
            self.debug_info("接收机串口已断开")

    # 串口连接失败时的处理
    def on_connection_failed(self, error_message):
        self.Radio_COM_status.setPixmap(warning)
        self.Radio_COM_button.setText("连接")
        QMessageBox.warning(self, "警告：串口连接失败", error_message)

    # 处理收发信机串口意外断开时的情况
    def Radio_Disconnected(self):
        self.Radio_COM_status.setPixmap(warning)
        self.Radio_COM_button.setText("连接")
        self.debug_info("接收机串口已断开")
        QMessageBox.warning(self, "警告：串口意外断开", "接收机串口已断开，请检查连接。")
        if self.Radio_Serial_Thread:
            self.Radio_Serial_Thread.stop()
            self.Radio_Serial_Thread = None

    # 发送数据到收发信机串口
    def Send_Data_to_Radio(self, data_to_send: str):
        # 检查收发信机串口是否打开
        if self.Radio_Serial_Thread and self.Radio_Serial_Thread.isRunning():
            try:
                self.Radio_Serial_Thread.send_data(data_to_send.encode('utf-8'))
            except Exception as e:
                print(f"数据编码发送时发生错误: {e}")

            # 记录发送的数据到日志文件
            time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open("log.txt", "a", encoding="utf-8") as f:
                f.write(f"{time}    » {data_to_send}")
        else:
            self.debug_info("接收机串口未连接或未运行，无法发送数据。")
            QMessageBox.warning(self, "发送失败", "接收机串口未连接或未运行。")

    # 连接天线旋转器串口
    def Connect_Rotator_COM(self):
        QMessageBox.warning(self, "警告", "天线旋转器功能尚未实现")
        self.debug_info("旋转器功能尚未实现")

    # 刷新系统中所有可用串口信息，并更新到下拉框中
    def Update_COM_Info(self):
        ports = list_ports.comports()
        current_ports = [(p.device, p.description) for p in ports]

        # 初始化缓存 (首次调用) 
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
            # 检查收发信机串口是否仍然连接
            is_connected = self.Radio_Serial_Thread is not None and self.Radio_Serial_Thread.isRunning()
            if Radio_Selected is not None and is_connected:
                self.Radio_COM_status.setPixmap(failure)
                QMessageBox.warning(self, "警告：串口断开", f"收发信机串口 {Radio_Selected} 已断开。")
                # 如果线程还在，但物理上断开了，应该调用断开函数来清理状态
                if self.Radio_Serial_Thread:
                    self.Radio_Serial_Thread.stop()
                    self.Radio_Disconnected()
    
        # 检查已经连接的旋转器串口是否仍然可用
        Found_Rotator = any(p[0] == Rotator_Selected for p in current_ports)
        if Found_Rotator:
            idx = self.Rotator_COM_Combo.findData(Rotator_Selected)
            self.Rotator_COM_Combo.setCurrentIndex(idx)
    
        self.Radio_COM_Combo.blockSignals(False)
        self.Rotator_COM_Combo.blockSignals(False)

    # 以 WGS-84 坐标系为基准，根据地面站与气球的经纬度和高度计算方位角与俯仰角
    def calculate_az_el(self, new_balloon_lat, new_balloon_lng, new_balloon_alt):

        # 从大地坐标系转换为地心固连坐标系
        def geodetic_to_ecef(lat_deg, lon_deg, alt_m):
            a = 6378137.0
            f = 1 / 298.257223563
            e2 = f * (2 - f)

            lat = np.radians(lat_deg)
            lon = np.radians(lon_deg)

            N = a / np.sqrt(1 - e2 * np.sin(lat)**2)
            x = (N + alt_m) * np.cos(lat) * np.cos(lon)
            y = (N + alt_m) * np.cos(lat) * np.sin(lon)
            z = (N * (1 - e2) + alt_m) * np.sin(lat)

            return np.array([x, y, z])

        # 将 ECEF 向量转换为 ENU 向量
        def ecef_to_enu(ecef_balloon, ecef_local, lat_deg, lon_deg):
            lat = np.radians(lat_deg)
            lon = np.radians(lon_deg)

            dx = ecef_balloon - ecef_local

            slat = np.sin(lat)
            clat = np.cos(lat)
            slon = np.sin(lon)
            clon = np.cos(lon)

            # 构建旋转矩阵，从 ECEF 坐标系旋转到 ENU 坐标系
            R = np.array([
                [-slon       ,  clon       , 0   ],
                [-clon * slat, -slon * slat, clat],
                [ clon * clat,  slon * clat, slat]
            ])

            return R @ dx

        # 将 ENU 向量转换为方位角与俯仰角
        def enu_to_az_el(enu):
            east, north, up = enu
            az = np.degrees(np.arctan2(east, north)) % 360
            hor_dist = np.sqrt(east**2 + north**2)
            el = np.degrees(np.arctan2(up, hor_dist))
            return az, el

        # 计算两个角度的有符号最小差值
        def angle_diff_sign(a, b):
            diff = (a - b + 180) % 360 - 180
            return diff
            
        # 环绕角平滑滤波 (AZ)
        # AZ 轴受到的主要影响为平面差距过小以及定位数据错误带来的剧烈变化
        def angle_smooth(old_angle, new_angle, current_elevation, alpha=0.3):
            # 天顶奇点判断：如果俯仰角高于85度，说明天线几乎垂直向上，此时方位角极不稳定，直接返回旧的角度，冻结方位角转动。
            if current_elevation > 85.0:
                return old_angle

            # GPS数据跳变过滤
            if abs(self.balloon_lat - new_balloon_lat) > 0.01 or abs(self.balloon_lng - new_balloon_lng) > 0.01:
                return old_angle
            
            # 标准平滑处理
            diff = angle_diff_sign(new_angle, old_angle)
            smoothed = (old_angle + alpha * diff) % 360
            return smoothed

        # 线性角平滑滤波 (EL)
        # EL 轴受到的影响主要为定位数据错误带来的剧烈变化
        def linear_smooth(old_val, new_val, alpha=0.5):                
            # 仅在高度数据发生巨大跳变时才拒绝更新
            if abs(self.balloon_alt - new_balloon_alt) > 200:
                return old_val
            
            # 对所有有效数据进行平滑处理
            return alpha * new_val + (1 - alpha) * old_val
        
        # 无论如何，先计算出原始的方位角和俯仰角
        ecef_local = geodetic_to_ecef(self.local_lat, self.local_lng, self.local_alt)
        ecef_balloon = geodetic_to_ecef(new_balloon_lat, new_balloon_lng, new_balloon_alt)
        enu = ecef_to_enu(ecef_balloon, ecef_local, self.local_lat, self.local_lng)
        azimuth, elevation = enu_to_az_el(enu)

        # 只有当目标出现在地平线1度以上时才启动跟踪。
        if elevation > 1.0:
            # 传入当前计算出的俯仰角用于天顶判断
            azimuth_smoothed = angle_smooth(self.Rotator_AZ, azimuth, elevation)
            elevation_smoothed = linear_smooth(self.Rotator_EL, elevation)
            return azimuth_smoothed, elevation_smoothed
        
        # 如果目标在地平线以下，则旋转器按兵不动，保持零位
        else:
            # 如果旋转器当前不在待命位置，则命令其进入待命位置
            if self.Rotator_AZ != 0.00 or self.Rotator_EL != 00.00:
                return 0.00, 00.00
            # 如果已经在待命位置，就保持不动
            else:
                return self.Rotator_AZ, self.Rotator_EL

    # 更新气球在地图中的位置
    def update_map_position(self):
        js_code = f"updatePosition({self.balloon_lat}, {self.balloon_lng}, {self.local_lat}, {self.local_lng});"
        self.map_view.page().runJavaScript(js_code)

    # 枚举值翻译函数
    def translate_payload(self, status_code, payload):
        
        # 处理摄像头尺寸相关的状态码
        if status_code in [0x5104, 0x5013]:
            return self.CAM_SIZE_MAP.get(payload, payload)
            
        # 处理SSDV类型相关的状态码
        elif status_code in [0x5102, 0x5010]:
            return self.SSDV_TYPE_MAP.get(payload, payload)
        
        # 对于布尔值 ON/OFF 的翻译
        elif status_code in [0x5100, 0x5101]:
             return "ON" if payload == "1" else "OFF"
        
        # 处理 SSDV 图像 ID 的格式化
        elif status_code in [0x4000, 0x4001]: # SSDV_ENCODE_START, SSDV_ENCODE_END
            # 使用 zfill(3) 将数字字符串格式化为3位，不足则补零
            return payload.zfill(3)
        
        # 翻译各种失败状态码
        # CAM_INIT_FAIL, CAM_RECONFIG_FAIL, CAM_RESTORE_DEFAULT_FAIL, CAM_CALIBRATE_FAIL
        # CAM_CAPTURE_FAIL, SSDV_ENCODE_ERROR, ADC_SAMPLE_FAIL
        elif status_code in [0x2002, 0x2009, 0x200B, 0x2005, 0x2006,0x4002,0x6000 ]:
            error_name = self.ESP_ERR_MAP.get(payload, f"信息码: {payload}")
            return {error_name}
             
        # 如果没有匹配的翻译规则，直接返回原始的payload
        else:
            return payload

    # SSDV 解码线程完成后的槽函数，此函数在主线程中被调用，可以安全地更新UI。
    def on_decoding_finished(self, jpg_filepath):

        # 检查解码是否成功
        if jpg_filepath and os.path.exists(jpg_filepath):
            pixmap = QPixmap(jpg_filepath)
            # 检查文件是否可被 QPixmap 加载
            if not pixmap.isNull():
                self.SSDV_IMG.setPixmap(pixmap.scaled(320, 240, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                self.SSDV_IMG.repaint()
            else:
                print(f"解码文件 {os.path.basename(jpg_filepath)} 已生成但无法加载。")
        else:
            self.debug_info(f"SSDV 图像解码失败。")

    # QSO类的槽函数，用于更新配置
    def update_ground_station_settings(self, new_callsign, new_lat, new_lng, new_alt):

        # 更新主窗口的内部变量
        self.callsign = new_callsign
        self.local_lat = new_lat
        self.local_lng = new_lng
        self.local_alt = new_alt

        # 更新配置文件中的信息
        if not config.has_section("GroundStation"):
            config.add_section("GroundStation")

        config.set("GroundStation", "Callsign", new_callsign)
        config.set("GroundStation", "Latitude", str(new_lat))
        config.set("GroundStation", "Longitude", str(new_lng))
        config.set("GroundStation", "Altitude", str(new_alt))

        with open("config.ini", "w") as configfile:
            config.write(configfile)

        # 如果 QSO 窗口已打开，更新它的信息
        if self.QSO_window:
            self.QSO_window.update_station_info(self.callsign, self.local_lat, self.local_lng)

        # 进行提示
        self.debug_info("地面站信息已更新")

    # 启动设置窗口
    def SET(self):
        if self.SET_window is None:
            try:
                self.SET_window = SET_Windows(self.callsign, self.local_lat, self.local_lng, self.local_alt) 
            except:
                self.SET_window = SET_Windows("", "", "", "")

            # 连接信号到槽函数
            self.SET_window.settings_saved.connect(self.update_ground_station_settings)

        self.SET_window.show()

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

    # 启动命令窗口
    def Command(self):
        if self.Radio_Serial_Thread and self.Radio_Serial_Thread.serial and self.Radio_Serial_Thread.serial.is_open:
            if self.Command_window is None:
                self.Command_window = Command_Windows(main_window=self)
                self.Command_window.tx_message.connect(self.Send_Data_to_Radio)
            self.Command_window.show()
        else:
            QMessageBox.warning(self, "警告", "接收机串口未连接，请先连接接收机串口。")

    # 主窗口关闭事件处理
    def closeEvent(self, event):

        warn = QMessageBox.question(self, "提示", "是否确定要退出程序？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if warn == QMessageBox.StandardButton.Yes:
            QApplication.closeAllWindows()
            event.accept()
        else:
            event.ignore()

# 设置窗口
class SET_Windows(QDialog):
    # 定义一个信号，传递呼号、纬度、经度、高度
    settings_saved = pyqtSignal(str, float, float, float)

    def __init__(self, callsign, current_lat, current_lng, current_alt):
        super().__init__()

        # 窗口属性
        icon = QIcon('UI/logo.ico')
        self.setWindowIcon(icon)
        self.resize(200, 250)
        self.setFixedSize(220, 280)
        self.setWindowTitle('设置')
        self.setStyleSheet('QWidget { background-color: rgb(223,237,249); }')
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

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
        self.callsign_input.setStyleSheet(input_box_style)
        self.callsign_input.setText(self.current_callsign)
        layout.addRow("地面站呼号:", self.callsign_input)

        self.lat_input = QLineEdit(self)
        self.lat_input.setStyleSheet(input_box_style)
        self.lat_input.setText(str(self.current_lat))
        layout.addRow("地面站纬度:", self.lat_input)

        self.lng_input = QLineEdit(self)
        self.lng_input.setStyleSheet(input_box_style)
        self.lng_input.setText(str(self.current_lng))
        layout.addRow("地面站经度:", self.lng_input)

        self.alt_input = QLineEdit(self)
        self.alt_input.setStyleSheet(input_box_style)
        self.alt_input.setText(str(self.current_alt))
        layout.addRow("地面站高度:", self.alt_input)

        self.save_button = QPushButton("保存", self)
        self.save_button.setStyleSheet(common_button_style)
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

            # 发射信号，将新配置传递出去
            self.settings_saved.emit(new_callsign, new_lat, new_lng, new_alt)

            self.accept()

        except ValueError:
            QMessageBox.warning(self, "输入错误", "请确保经度、纬度、高度输入为有效的数字。")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存时发生未知错误: {e}")

    # 当窗口关闭处理
    def closeEvent(self, event):
        self.reject()
        event.accept()

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
        self.ToMSG = ""

        # 拼装后的信息
        self.TofullMSG = ""

        # 初始化统计信息
        self.rx_count = 0
        self.tx_count = 0
        self.QSO_count = 0
        self.qso_callsigns = set()

        # 防止在程序自动滚动时触发 handle_scroll 逻辑
        self.is_auto_scrolling = False 

        # 初始化UI
        self.init_ui()

    def init_ui(self):

        # 信息发送区
        self.send_info_frame = QWidget(self)
        self.send_info_frame.setGeometry(30, 25, 290, 100)
        self.send_info_frame.setStyleSheet(qso_frame_style)

        self.Callsign_label = QLabel(self)
        self.Callsign_label.setText("信息发送")
        self.Callsign_label.move(35, 30)
        self.Callsign_label.setStyleSheet(tip_text_style)

        self.Callsign_label = QLabel(self)
        self.Callsign_label.setText("呼号：")
        self.Callsign_label.move(40, 60)
        self.Callsign_label.setStyleSheet(primary_text_style)

        self.Callsign_input = QLineEdit(self)
        self.Callsign_input.setStyleSheet(input_box_style)
        self.Callsign_input.move(100, 60)
        self.Callsign_input.setText(str(self.ToCallSign))
        
        self.MSG_label = QLabel(self)
        self.MSG_label.setText("信息：")
        self.MSG_label.move(40, 90)
        self.MSG_label.setStyleSheet(primary_text_style)

        self.MSG_input = QLineEdit(self)
        self.MSG_input.setStyleSheet(input_box_style)
        self.MSG_input.move(100, 90)
        self.MSG_input.setText(self.ToMSG)

        self.TX_button = QPushButton("发送信息", self)
        self.TX_button.setGeometry(225, 62, 80, 50)
        self.TX_button.setStyleSheet(common_button_style)
        self.TX_button.clicked.connect(self.TX)

        self.cooldown_ms = 300
        self.send_timer = QTimer()
        self.send_timer.setSingleShot(True)
        self.send_timer.timeout.connect(self.unlock_send_button)

        # 信息统计区
        self.count_frame = QWidget(self)
        self.count_frame.setGeometry(330, 25, 160, 100)
        self.count_frame.setStyleSheet(qso_frame_style)

        self.rx_count_label = QLabel(self)
        self.rx_count_label.setText("接收计数：")
        self.rx_count_label.move(340, 40)
        self.rx_count_label.setStyleSheet(primary_text_style)

        self.rx_count_num = QLabel(self)
        self.rx_count_num.setText(str(self.rx_count))
        self.rx_count_num.move(420, 40)
        self.rx_count_num.setStyleSheet(primary_text_style)

        self.tx_count_label = QLabel(self)
        self.tx_count_label.setText("发送计数：")
        self.tx_count_label.move(340, 65)
        self.tx_count_label.setStyleSheet(primary_text_style)

        self.tx_count_num = QLabel(self)
        self.tx_count_num.setText(str(self.tx_count))
        self.tx_count_num.move(420, 65)
        self.tx_count_num.setStyleSheet(primary_text_style)

        self.QSO_count_label = QLabel(self)
        self.QSO_count_label.setText("通联计数：")
        self.QSO_count_label.move(340, 90)
        self.QSO_count_label.setStyleSheet(primary_text_style)

        self.QSO_count_num = QLabel(self)
        self.QSO_count_num.setText(str(self.QSO_count))
        self.QSO_count_num.move(420, 90)
        self.QSO_count_num.setStyleSheet(primary_text_style)

        # 台站信息区
        self.station_info_frame = QWidget(self)
        self.station_info_frame.setGeometry(510, 25, 250, 100)
        self.station_info_frame.setStyleSheet(qso_frame_style)
        
        self.station_info_label = QLabel(self)
        self.station_info_label.setText("站点信息")
        self.station_info_label.move(515, 30)
        self.station_info_label.setStyleSheet(tip_text_style)

        self.My_Callsign_label = QLabel(self.station_info_frame)
        self.My_Callsign_label.setText(self.callsign)
        self.My_Callsign_label.setGeometry(10, 25, 230, 30)
        self.My_Callsign_label.setStyleSheet(callsign_style)
        self.My_Callsign_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.My_grid_label = QLabel(self.station_info_frame)
        self.My_grid_label.setText(self.grid)
        self.My_grid_label.setGeometry(10, 55, 230, 30)
        self.My_grid_label.setStyleSheet(primary_text_style)
        self.My_grid_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 通联信息区
        self.info_frame = QWidget(self)
        self.info_frame.setGeometry(30, 150, 460, 320)
        self.info_frame.setStyleSheet(qso_frame_style)

        info_layout = QVBoxLayout(self.info_frame)
        info_layout.setContentsMargins(5, 5, 5, 5)
        self.info_table = QTableWidget(self.info_frame)

        # 设置列数和列头标签
        self.info_table.setColumnCount(4)
        self.info_table.setHorizontalHeaderLabels(["  时间  ", "  源站呼号  ", "  目标呼号  ", "信息"])
        self.info_table.horizontalHeader().setStyleSheet(primary_text_style)

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

        # 创建“滚动到底部”按钮，初始时隐藏
        self.scrollToBottomButton = QPushButton(" ▼ ", self.info_frame)
        self.scrollToBottomButton.hide() 
        self.scrollToBottomButton.setStyleSheet(common_button_style)
        self.scrollToBottomButton.setGeometry(400, 280, 30, 23)

        # 连接点击事件
        self.scrollToBottomButton.clicked.connect(self.on_scroll_button_clicked)

        # 监听滚动条的动作，以便在用户手动滚动时隐藏按钮
        self.info_table.verticalScrollBar().actionTriggered.connect(self.handle_scroll)

        # 当单元格被双击时，触发 fill_callsign_from_table 方法
        self.info_table.cellDoubleClicked.connect(self.fill_callsign_from_table)

        # 实时时钟
        self.clock_label = QLabel(self)
        self.clock_label.setGeometry(490, 150, 250, 60)
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
        self.info_QSO_frame.setStyleSheet(qso_frame_style)

        QSO_info_layout = QVBoxLayout(self.info_QSO_frame)
        QSO_info_layout.setContentsMargins(5, 5, 5, 5)
        self.QSO_info_table = QTableWidget(self.info_QSO_frame)

        # 设置列数和列头标签
        self.QSO_info_table.setColumnCount(3)
        self.QSO_info_table.setHorizontalHeaderLabels(["   时间   ", "  呼号  ", "  网格  "])
        self.QSO_info_table.horizontalHeader().setStyleSheet(primary_text_style)

        # 设置列宽自适应填充可用空间
        self.QSO_info_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        # 隐藏行号，设置表格的网格线颜色
        self.QSO_info_table.verticalHeader().setVisible(False)
        self.QSO_info_table.setStyleSheet("QTableWidget { gridline-color: #DDDDDD; }")

        # 禁用编辑和选中
        self.QSO_info_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.QSO_info_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        QSO_info_layout.addWidget(self.QSO_info_table)

    def update_station_info(self, callsign, lat, lng):
        self.callsign = callsign
        self.current_lat = lat
        self.current_lng = lng
        self.grid = self.latlng_to_maiden(self.current_lat, self.current_lng)
        
        # 更新UI上的显示
        self.My_Callsign_label.setText(self.callsign)
        self.My_grid_label.setText(self.grid)

    # 格式：“##ToCall,FmCall,Gird,INFO\n”
    def TX(self):

        # 发送冷却时间
        if not self.TX_button.isEnabled():
            return  # 冷却中，不发送

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
        
        # 计数
        self.tx_count += 1
        self.tx_count_num.setText(str(self.tx_count))
        self.tx_count_num.adjustSize()

        # 当前时间
        current_time = datetime.now().strftime("%H:%M:%S")

        # 构建消息字符串：##ToCall,FmCall,Grid,INFO\n
        # 调试版本 full_msg = f"** ##RELAY,{to_call},{self.callsign},{self.grid},{msg} **"
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

        scrollbar = self.info_table.verticalScrollBar()
        is_at_bottom = scrollbar.value() >= scrollbar.maximum() - 5

        # 计数器
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
        item_message = QTableWidgetItem(f"{grid}, {message}")
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

        # 根据位置决定是自动滚动还是显示按钮
        if is_at_bottom:
            self.is_auto_scrolling = True
            self.info_table.scrollToBottom()
        else:
            self.scrollToBottomButton.show()
            self.scrollToBottomButton.raise_()

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

    # 快捷按钮逻辑
    def handle_scroll(self):
        # 如果是程序自动滚动到底部，则不作处理
        if self.is_auto_scrolling:
            self.is_auto_scrolling = False
            return

        scrollbar = self.info_table.verticalScrollBar()

        # 如果用户手动滚动到了底部，隐藏提示按钮
        if scrollbar.value() >= scrollbar.maximum() - 5:
            self.scrollToBottomButton.hide()

    def on_scroll_button_clicked(self):
        # 当用户点击滚动按钮时，自动滚动到表格底部
        self.info_table.scrollToBottom()
        self.scrollToBottomButton.hide()

    # 经纬度转梅登黑德网格
    def latlng_to_maiden(self, lat, lon):
        lat += 90
        lon += 180
        return (
            f"{chr(int(lon // 20) + 65)}{chr(int(lat // 10) + 65)}"
            f"{int((lon % 20) // 2)}{int(lat % 10)}"
            f"{chr(int((lon % 2) * 12) + 97)}{chr(int((lat % 1) * 24) + 97)}"
        )

# 命令窗口
class Command_Windows(QWidget):

    # 定义一个信号，用于发送消息
    tx_message = pyqtSignal(str)
    

    # 定义窗口基本信息
    def __init__(self, main_window=None):
        super().__init__()

        self.main_window = main_window

        icon = QIcon('UI/logo.ico')
        self.setWindowIcon(icon)
        self.resize(400, 260)
        self.setFixedSize(400, 260)
        self.setWindowTitle('命令发送')
        self.setStyleSheet('QWidget { background-color: rgb(223,237,249); font-size: 13px; }')
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        # 尝试从配置文件读取密码文件路径
        self.password = ""
        self.password_file = config.get("GroundStation", "CommandPasswordFile", fallback="") 
        self.load_password_from_file()

        # 定义可用的命令及其会话框表现
        self.commands = {
            ' 开启中继 (CTL,RELAY,ON)'  : ('CTL,RELAY,ON', False),
            ' 关闭中继 (CTL,RELAY,OFF)' : ('CTL,RELAY,OFF', False),
            ' 开启图传 (CTL,SSDV,ON)'   : ('CTL,SSDV,ON', False),
            ' 关闭图传 (CTL,SSDV,OFF)'  : ('CTL,SSDV,OFF', False),
            ' 重启系统 (CTL,SYS,REBOOT)': ('CTL,SYS,REBOOT', False),
            ' 设置图传模式 (SET,SSDV_TYPE)'   : ('SET,SSDV_TYPE', True),
            ' 设置图传质量 (SET,SSDV_QUALITY)': ('SET,SSDV_QUALITY', True),
            ' 设置图传周期 (SET,SSDV_CYCLE)'  : ('SET,SSDV_CYCLE', True),
            ' 设置图传预设 (SET,SSDV_PRESET)' : ('SET,SSDV_PRESET', True),
            ' 设置图像尺寸 (SET,CAM_SIZE)'    : ('SET,CAM_SIZE', True),
            ' 设置图像质量 (SET,CAM_QUALITY)' : ('SET,CAM_QUALITY', True),
            ' 查询中继状态 (GET,RELAY)' : ('GET,RELAY', False),
            ' 查询图传状态 (GET,SSDV)'  : ('GET,SSDV', False),
            ' 查询相机参数 (GET,CAM)'   : ('GET,CAM', False),
        }

        self.init_ui()

    # 初始化主UI布局，主要是创建和设置选项卡
    def init_ui(self):
        main_layout = QVBoxLayout(self)

        tabs = QTabWidget()
        self.tab_structured = QWidget()
        self.tab_freeform = QWidget()
        tabs.addTab(self.tab_structured, "预设命令")
        tabs.addTab(self.tab_freeform, "自由命令")

        self.init_structured_tab()
        self.init_freeform_tab()
        main_layout.addWidget(tabs)
        self.setLayout(main_layout)

    # 初始化预设命令选项卡
    def init_structured_tab(self):

        # 使用 QVBoxLayout 使内容垂直居中
        page_layout = QVBoxLayout(self.tab_structured)
        page_layout.setContentsMargins(15, 20, 15, 15)

        # 创建一个容器Widget来承载QFormLayout
        form_widget = QWidget()
        layout = QFormLayout(form_widget)
        layout.setVerticalSpacing(15)

        # 预设命令下拉栏
        self.cmd_combo = QComboBox()
        self.cmd_combo.setFixedHeight(28)
        self.cmd_combo.setStyleSheet(combo_box_style)

        # 预设命令参数框
        self.value_input = QLineEdit()
        self.value_input.setFixedHeight(28)
        self.value_input.setStyleSheet(input_box_style)
        self.value_input.setPlaceholderText(" 请在此输入参数...")

        # 密码文件选择
        self.pwd_file_input = QLineEdit(self)
        self.pwd_file_input.setFixedHeight(28)
        self.pwd_file_input.setStyleSheet(input_box_style)
        self.pwd_file_input.setReadOnly(True)
        self.pwd_file_input.setText(os.path.basename(self.password_file) if self.password_file else "")
        
        self.select_pwd_file_button = QPushButton("选择", self)
        self.select_pwd_file_button.setFixedHeight(28)
        self.select_pwd_file_button.setFixedWidth(50)
        self.select_pwd_file_button.setStyleSheet(common_button_style)
        self.select_pwd_file_button.clicked.connect(self.select_password_file)

        # 创建一个水平布局来放置密码文件路径显示和选择按钮
        pwd_file_layout = QHBoxLayout()
        pwd_file_layout.addWidget(self.pwd_file_input)
        pwd_file_layout.addWidget(self.select_pwd_file_button)
        pwd_file_layout.setSpacing(10)

        # 预设命令发送按钮
        send_button = QPushButton("发送", self)
        send_button.setStyleSheet(common_button_style)
        send_button.setFixedHeight(32)
        send_button.setFixedWidth(100)

        for display_text, (command, has_value) in self.commands.items():
            self.cmd_combo.addItem(display_text, userData=(command, has_value))
            if not command:
                index = self.cmd_combo.count() - 1
                self.cmd_combo.model().item(index).setEnabled(False)

        layout.addRow("选择命令: ", self.cmd_combo)
        layout.addRow("输入参数: ", self.value_input)
        layout.addRow("密码文件:", pwd_file_layout)
        
        # 为按钮创建一个水平布局，使其右对齐
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(send_button)

        # 添加弹性伸缩实现垂直居中
        page_layout.addStretch()
        page_layout.addWidget(form_widget)
        page_layout.addLayout(button_layout)
        page_layout.addStretch()

        self.cmd_combo.currentIndexChanged.connect(self.on_command_change)
        send_button.clicked.connect(self.send_structured_command)
        self.on_command_change(0)

    # 初始化自由命令选项卡，提供一个多行文本框，用于输入任意格式的信息
    def init_freeform_tab(self):

        # 使用 QVBoxLayout 使内容垂直居中
        layout = QVBoxLayout(self.tab_freeform)
        layout.setContentsMargins(15, 20, 15, 15)
        layout.setSpacing(10)

        # 提示文字
        info_label = QLabel("请输入自由命令：")
        info_label.setStyleSheet("font-size: 13px;")

        # 自由命令输入框
        self.freeform_input = QPlainTextEdit()
        self.freeform_input.setStyleSheet(input_box_style)
        self.freeform_input.setPlaceholderText("例如：@@CTL,RELAY,ON")

        # 自由命令发送按钮
        send_button = QPushButton("发送", self)
        send_button.setFixedHeight(32)
        send_button.setFixedWidth(100)
        send_button.setStyleSheet(common_button_style)
        send_button.clicked.connect(self.send_freeform_command)

        # 添加控件到布局
        layout.addWidget(info_label)
        layout.addWidget(self.freeform_input)
        layout.addWidget(send_button, alignment=Qt.AlignmentFlag.AlignRight)

    # 根据预设参数处理“输入参数”文本框的可用性
    def on_command_change(self, index):

        # 通过索引获取存储在item中的用户数据 (command, has_value)
        _, has_value = self.cmd_combo.itemData(index)
        # 根据has_value的值，启用或禁用参数输入框
        self.value_input.setEnabled(has_value)
        self.value_input.setPlaceholderText("请在此输入参数...")
        # 如果命令不需要参数，为防止混淆，清空输入框
        if not has_value:
            self.value_input.clear()
            self.value_input.setPlaceholderText("该命令无需参数。")

    # 从密码文件加载密码
    def load_password_from_file(self):
        # 如果密码文件存在，则尝试读取密码
        if self.password_file and os.path.exists(self.password_file):
            try:
                with open(self.password_file, 'r', encoding='utf-8') as f:
                    self.password = f.readline().strip()
                if self.password:
                    self.main_window.debug_info(f"[成功] 已加载密码文件")
                else:
                    self.main_window.debug_info(f"[警告] 命令密码文件为空")
            except Exception as e:
                self.main_window.debug_info(f"[错误] 读取命令密码文件失败: {e}")
                self.password = ""
        else:
            self.main_window.debug_info("[警告] 命令密码文件不存在")
            self.password = ""

    # 发送预设的结构化命令
    def send_structured_command(self):
        index = self.cmd_combo.currentIndex()
        command, has_value = self.cmd_combo.itemData(index)

        # 如果没有选择命令，直接返回
        if not command:
            return

        # 如果没有密码，直接拒绝发送并给出警告
        if not self.password:
            QMessageBox.warning(self, "警告", "命令密码文件不存在")
            return

        # 如果命令需要参数，检查输入框是否为空
        value = self.value_input.text().strip()
        if has_value and not value:
            QMessageBox.warning(self, "警告", "该命令需要输入参数值。")
            return

        # 无论是否有参数，都附加密码
        if has_value:
            full_command = f"@@{command},{value},{self.password}\n"
        else:
            full_command = f"@@{command},{self.password}\n"
        self.tx_message.emit(full_command)

    # 发送自由命令
    def send_freeform_command(self):
        command_text = self.freeform_input.toPlainText().strip()
        if not command_text:
            QMessageBox.warning(self, "警告", "发送的命令不能为空。")
            return

        self.tx_message.emit(command_text + '\n')

    # 选择密码文件并更新配置文件
    def select_password_file(self):
        file_dialog = QFileDialog(self)
        file_path, _ = file_dialog.getOpenFileName(self, "选择密码文件", "", "密码文件 (*.pwd);;所有文件 (*)")
        if file_path:
            self.password_file = file_path
            self.pwd_file_input.setText(os.path.basename(file_path)) 
            self.load_password_from_file() # 重新加载密码

            # 保存到配置文件
            if not config.has_section("GroundStation"):
                config.add_section("GroundStation")
            config.set("GroundStation", "CommandPasswordFile", file_path)
            with open("config.ini", "w") as configfile:
                config.write(configfile)
            
            self.main_window.debug_info(f"命令密码已选择")

# 串口连接线程
class SerialConnection(QThread):

    # 发送信号
    data_received = pyqtSignal(bytes)
    disconnected = pyqtSignal()
    connection_failed = pyqtSignal(str)

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
            self.serial.dtr = False
            self.serial.rts = False
        except serial.SerialException as e:
            error_message = f"打开串口 {self.port_name} 失败: \n{e}"
            print(f"[错误] {error_message}")
            # 发射带错误信息的信号
            self.connection_failed.emit(error_message)
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

# SSDV 解码工作线程，避免阻塞主线程。
class SsdvDecoderThread(QThread):

    # 定义信号，解码完成后发射，参数为解码后的 jpg 文件路径
    decoding_finished = pyqtSignal(str)

    # 定义信号，解码过程中发射，参数为日志信息
    log_message = pyqtSignal(str)

    def __init__(self, dat_filepath, jpg_filepath, parent=None):
        super().__init__(parent)
        self.dat_filepath = dat_filepath
        self.jpg_filepath = jpg_filepath

    def run(self):
        try:
            # 调用解码程序
            subprocess.run(
                ["./ssdv", "-d", self.dat_filepath, self.jpg_filepath],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True
            )

            self.decoding_finished.emit(self.jpg_filepath)

        except subprocess.CalledProcessError:
            self.log_message.emit("[错误] SSDV解码失败，程序返回错误。")
            self.decoding_finished.emit("")
        except Exception as e:
            self.log_message.emit(f"[错误] SSDV解码线程出现未知异常: {e}")
            self.decoding_finished.emit("")

# 主事件
if __name__ == '__main__':

    app = QApplication(sys.argv)

    # 获取程序所在目录
    base_dir = os.path.dirname(os.path.abspath(sys.argv[0]))

    # 依赖程序检查
    dependencies = ['ssdv.exe', 'sondehub.exe']
    missing_files = []

    for dep in dependencies:
        dep_path = os.path.join(base_dir, dep)
        if not os.path.exists(dep_path):
            missing_files.append(dep_path)

    if missing_files:
        missing_str = "\n".join(missing_files)
        QMessageBox.critical(None, "依赖文件缺失", f"程序无法启动，缺少以下关键文件：\n{missing_str}")
        sys.exit(1)

    # 启动主窗口
    main_window = GUI()
    main_window.show()

sys.exit(app.exec())
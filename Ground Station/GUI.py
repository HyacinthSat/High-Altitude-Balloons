"""
GUI program for Balloon Ground Station.

This program is a graphical user interface implemented using PyQt, 
mainly used to obtain software running parameters.

Author: BG7ZDQ
Date: 2025/05/20
Version: 0.0.0 formal_edition
LICENSE: GNU General Public License v3.0
"""

import re
import os
import sys
import serial
import subprocess
from datetime import datetime
from serial.tools import list_ports
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import Qt, QUrl, QTimer, QThread, pyqtSignal
from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QPushButton, QPlainTextEdit, QMessageBox, QComboBox

# 禁用 GPU 加速
os.environ['QTWEBENGINE_CHROMIUM_FLAGS'] = '--disable-gpu --disable-software-rasterizer'

# 组件样式
title_style = 'color: #3063AB; font-family: 微软雅黑; font: bold 12pt;'
common_style = 'color: #555555; font-family: 微软雅黑; font: bold 12pt;'
Common_button_style = 'QPushButton {background-color: #3498db; color: #ffffff; border-radius: 5px; padding: 6px; font-size: 12px;} QPushButton:hover {background-color: #2980b9;} QPushButton:pressed {background-color: #21618c;}'
TextEdit_style = 'QPlainTextEdit {background-color: #FFFFFF; color: #3063AB; border: 1px solid #3498db; border-radius: 5px; padding: 1px; font-family: 微软雅黑; font-size: 12px;}'
ComboBox_style = '''QComboBox {background-color: #ffffff; border: 1px solid #3498db; border-radius: 3px; padding: 2px; min-width: 6em; font: bold 10pt "微软雅黑"; color: #3063AB;}QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 20px; border-left: 1px solid #3498db;}QComboBox::down-arrow { image: url(UI/arrow.svg); width: 10px; height: 10px;}QComboBox QAbstractItemView { background: #ffffff; selection-background-color: #89CFF0; selection-color: #000000; border: 1px solid #3498db; outline: 0; font: 10pt "微软雅黑";}'''

# 程序主窗口
class GUI(QWidget):

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

        self.receiver_serial_thread = None

        # 地面站位置
        self.local_lat = 0
        self.local_lng = 0
        self.local_alt = 0

        # 气球位置
        self.balloon_lat = 0
        self.balloon_lng = 0
        self.balloon_alt = 0

        # 图像编号
        self.img_num = -1
        self.frame_num = 1

        # 当前文件名
        self.filename = ''

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
        self.Receiver_COM_status = QLabel(self)
        self.Receiver_COM_status.setPixmap(waiting)
        self.Receiver_COM_status.move(40, 28)

        self.Receiver_COM_label = QLabel(self)
        self.Receiver_COM_label.setText("接收机端口：")
        self.Receiver_COM_label.move(65, 25)
        self.Receiver_COM_label.setStyleSheet(title_style)

        self.Receiver_COM_combo = QComboBox(self)
        self.Receiver_COM_combo.addItems([])
        self.Receiver_COM_combo.setGeometry(165, 21, 120, 30)
        self.Receiver_COM_combo.setStyleSheet(ComboBox_style)

        self.Receiver_COM_button = QPushButton("连接", self)
        self.Receiver_COM_button.setGeometry(300, 21, 50, 27)
        self.Receiver_COM_button.setStyleSheet(Common_button_style)
        self.Receiver_COM_button.clicked.connect(self.Connect_receiver_COM)

        # 旋转器端口选择部分
        self.Rotator_COM_status = QLabel(self)
        self.Rotator_COM_status.setPixmap(waiting)
        self.Rotator_COM_status.move(40, 63)

        self.Rotator_COM_label = QLabel(self)
        self.Rotator_COM_label.setText("旋转器端口：")
        self.Rotator_COM_label.move(65, 60)
        self.Rotator_COM_label.setStyleSheet(title_style)

        self.Rotator_COM_combo = QComboBox(self)
        self.Rotator_COM_combo.addItems([])
        self.Rotator_COM_combo.setGeometry(165, 56, 120, 30)
        self.Rotator_COM_combo.setStyleSheet(ComboBox_style)

        self.Rotator_COM_button = QPushButton("连接", self)
        self.Rotator_COM_button.setGeometry(300, 56, 50, 27)
        self.Rotator_COM_button.setStyleSheet(Common_button_style)
        self.Rotator_COM_button.clicked.connect(self.Connect_rotator_COM)

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
        self.map_view.setUrl(QUrl("https://hab.satellites.ac.cn/map"))

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

        self.DEBUG_output = QPlainTextEdit(self)
        self.DEBUG_output.setReadOnly(True)
        self.DEBUG_output.setGeometry(420, 415, 330, 70)
        self.DEBUG_output.setStyleSheet(TextEdit_style)

        # 串口刷新定时器
        self.update_serial_ports()
        self.serial_timer = QTimer(self)
        self.serial_timer.timeout.connect(self.update_serial_ports)
        self.serial_timer.start(200)

    # 调试信息框
    def debug_info(self, text):
        time = datetime.now().strftime("%H:%M:%S")
        self.DEBUG_output.appendPlainText(f"{time} {text}")
        print(text)

    # 连接接收机串口
    def Connect_receiver_COM(self):
        port_name = self.Receiver_COM_combo.currentData()
        if self.Receiver_COM_button.text() == "连接":
            if not port_name:
                self.Receiver_COM_status.setPixmap(warning)
                QMessageBox.warning(self, "警告：串口无效", "未连接有效串口")
                return

            self.receiver_serial_thread = SerialReader(port_name, baudrate=9600)
            self.receiver_serial_thread.data_received.connect(self.handle_serial_data)
            self.receiver_serial_thread.disconnected.connect(self.on_serial_disconnected) # 添加这行连接
            self.receiver_serial_thread.start()

            if self.receiver_serial_thread and self.receiver_serial_thread.isRunning(): # 简单的检查
                self.Receiver_COM_status.setPixmap(correct)
                self.Receiver_COM_button.setText("断开")
                print(f"接收机串口已连接：{port_name}")
                self.debug_info(f"接收机串口已连接：{port_name}")

        else:
            if self.receiver_serial_thread:
                self.receiver_serial_thread.stop()

            # 手动断开时，也应该确保UI状态正确更新
            self.Receiver_COM_status.setPixmap(waiting)
            self.Receiver_COM_button.setText("连接")
            if self.receiver_serial_thread: # 确保线程对象被清理
                 self.receiver_serial_thread = None
            self.debug_info("接收机串口已断开")

    # 串口断开处理
    def on_serial_disconnected(self):
        self.Receiver_COM_status.setPixmap(warning)
        self.Receiver_COM_button.setText("连接")
        self.receiver_serial_thread = None
        self.serial_connected = False

    # 处理遥测数据
    def processing_telemetry_data(self, text):

        # 记录日志
        print(f"ASCII帧：{text}")
        time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open("log.txt", "a") as f:
            f.write(f"{time}    {text}\n")

        # 处理 $$ 开头的遥测数据
        if text.startswith("$$"):
            self.Frame_type_output.setText(f"GPS 数据帧")
            self.Frame_type_output.adjustSize()
            try:
                fields = text[2:].split(",")
                if len(fields) >= 6:
                    self.balloon_lat = float(fields[0])
                    self.balloon_lng = float(fields[1])
                    self.balloon_alt = float(fields[2])
                    self.balloon_spd = float(fields[3])
                    self.balloon_sats = int(fields[4])
                    self.balloon_heading = float(fields[5])

                    # 更新地图
                    self.update_map_position()
                    self.debug_info(f"GPS 数据已更新")

                    # 更新标签显示
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

                    return
                else:
                    self.debug_info("遥测数据字段不足，解析失败")
            except Exception as e:
                self.debug_info(f"遥测数据解析出错：{e}")
            return
    
        self.Frame_type_output.setText(f"状态指示帧")
        self.Frame_type_output.adjustSize()

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
            self.debug_info(f"第 {self.img_num} 张图片编码完成")
        else:
            self.debug_info(f"收到信息：{text}")

    # 处理串口数据
    def handle_serial_data(self, data: bytes):
        self.buffer.extend(data)

        while True:
            # 优先尝试提取 ASCII
            if self.try_extract_ascii():
                continue
            # 然后提取 SSDV
            if self.try_extract_ssdv():
                continue
            break

    # 使用正则表达式提取 ASCII 帧信息
    def try_extract_ascii(self) -> bool:
        current_buffer_bytes = bytes(self.buffer)
        changed = False

        # 使用 finditer 找出所有完整的 ASCII 帧
        for match in re.finditer(rb"\*\*(.+?)\*\*", current_buffer_bytes, re.DOTALL):
            ascii_raw = match.group(0)

            try:
                ascii_text = ascii_raw.decode("ascii", errors="strict").strip("* ").strip()
            except UnicodeDecodeError:
                print(f"[警告] ASCII解码失败: {ascii_raw}")
                continue
            
            self.Data_status_icon.setPixmap(correct)
            self.processing_telemetry_data(ascii_text)
            changed = True

        # 如果有匹配，清除 buffer 直到最后一个匹配结束位置
        if changed:
            last_match = list(re.finditer(rb"\*\*(.+?)\*\*", current_buffer_bytes, re.DOTALL))[-1]
            self.buffer = self.buffer[last_match.end():]
            return True
        else:
            return False

    # 提取 SSDV 数据
    def try_extract_ssdv(self) -> bool:
        header = b"\x55\x67\xB9\xD9\x5B\x2F"
        frame_len = 256

        # 寻找帧头
        start = self.buffer.find(header)

        # 不足一个完整帧
        if start == -1 or len(self.buffer) - start < frame_len:
            return False

        # 提取帧
        frame = self.buffer[start:start + frame_len]

        # 检查图像编号是否变化
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

        # 确保 'dat' 文件夹存在
        os.makedirs("dat", exist_ok=True)

        # 追加到 .dat 文件
        dat_filepath = f"dat/{self.filename}.dat"
        try:
            with open(dat_filepath, "ab") as f:
                f.write(frame)
        except IOError as e:
            self.debug_info(f"写入 SSDV 数据失败: {e}")
            return False

        # 调用 SSDV 解码器
        try:
            result = subprocess.run(["./ssdv", "-d", f"dat/{self.filename}.dat", f"{self.filename}.jpg"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if result.returncode != 0:
                raise RuntimeError("SSDV 解码器返回码非 0")
        except Exception as e:
            self.debug_info(f"SSDV 解码失败: {e}")
            self.buffer = self.buffer[start + frame_len:]
            return False

        # 加载图像，确认文件存在
        if os.path.exists(f"{self.filename}.jpg"):
            self.SSDV_IMG.setPixmap(QPixmap(f"{self.filename}.jpg").scaled(320, 240, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            self.SSDV_IMG.repaint()

        # 移除已处理数据
        self.buffer = self.buffer[start + frame_len:]
        return True

    # 连接旋转器串口
    def Connect_rotator_COM(self):
        self.debug_info("旋转器功能尚未实现")

    # 刷新串口信息
    def update_serial_ports(self):
        ports = list_ports.comports()
        current_ports = [(p.device, p.description) for p in ports]

        # 初始化缓存（首次调用）
        if not hasattr(self, 'port_list_cache'):
            self.port_list_cache = []
            self.Receiver_COM_combo.addItem("尚未选择", userData=None)
            self.Rotator_COM_combo.addItem("尚未选择", userData=None)

        if current_ports == self.port_list_cache:
            return  # 没有变化，跳过刷新

        self.port_list_cache = current_ports  # 更新缓存

        # 记录旧的选中串口
        receiver_selected = self.Receiver_COM_combo.currentData()
        rotator_selected = self.Rotator_COM_combo.currentData()

        self.Receiver_COM_combo.blockSignals(True)
        self.Rotator_COM_combo.blockSignals(True)
        self.Receiver_COM_combo.clear()
        self.Rotator_COM_combo.clear()
        self.Receiver_COM_combo.addItem("尚未选择", userData=None)
        self.Rotator_COM_combo.addItem("尚未选择", userData=None)

        for name, desc in current_ports:
            self.Receiver_COM_combo.addItem(name, userData=name)
            idx_r = self.Receiver_COM_combo.count() - 1
            self.Receiver_COM_combo.setItemData(idx_r, desc, Qt.ItemDataRole.ToolTipRole)
    
            self.Rotator_COM_combo.addItem(name, userData=name)
            idx_ro = self.Rotator_COM_combo.count() - 1
            self.Rotator_COM_combo.setItemData(idx_ro, desc, Qt.ItemDataRole.ToolTipRole)
    
        # 还原 Receiver 选中项
        found_receiver = any(p[0] == receiver_selected for p in current_ports)
        if found_receiver:
            idx = self.Receiver_COM_combo.findData(receiver_selected)
            self.Receiver_COM_combo.setCurrentIndex(idx)
        else:
            self.Receiver_COM_combo.setCurrentIndex(0)
            if receiver_selected is not None:
                self.Receiver_COM_status.setPixmap(error)
                QMessageBox.warning(self, "警告：串口断开", f"接收机串口 {receiver_selected} 已断开。")
    
        # 还原 Rotator 选中项
        found_rotator = any(p[0] == rotator_selected for p in current_ports)
        if found_rotator:
            idx = self.Rotator_COM_combo.findData(rotator_selected)
            self.Rotator_COM_combo.setCurrentIndex(idx)
        else:
            self.Rotator_COM_combo.setCurrentIndex(0)
            if rotator_selected is not None:
                self.Rotator_COM_status.setPixmap(error)
                QMessageBox.warning(self, "警告：串口断开", f"旋转器串口 {rotator_selected} 已断开。")
    
        self.Receiver_COM_combo.blockSignals(False)
        self.Rotator_COM_combo.blockSignals(False)

    # 更新地图位置
    def update_map_position(self):
        js_code = f"updatePosition({self.balloon_lat}, {self.balloon_lng});"
        self.map_view.page().runJavaScript(js_code)

    # 窗口关闭事件处理
    def closeEvent(self, event):
        warn = QMessageBox.question(self, "提示", "是否确定要退出程序？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if warn == QMessageBox.StandardButton.Yes:
            event.accept()
        else:
            event.ignore()

# 串口连接
class SerialReader(QThread):
    data_received = pyqtSignal(bytes)
    disconnected = pyqtSignal()  # 串口断开信号

    def __init__(self, port_name, baudrate=9600):
        super().__init__()
        self.port_name = port_name
        self.baudrate = baudrate
        self._running = True
        self.serial = None

    def run(self):
        try:
            self.serial = serial.Serial(self.port_name, self.baudrate, timeout=1)
        except serial.SerialException as e:
            print(f"[错误] 串口打开失败：{e}")
            self.disconnected.emit()
            return

        while self._running:
            try:
                if self.serial.in_waiting:
                    data = self.serial.read(self.serial.in_waiting)
                    self.data_received.emit(data)
            except serial.SerialException as e:
                print(f"[错误] 串口异常断开：{e}")
                self._running = False
                if self.serial and self.serial.is_open:
                    self.serial.close()
                self.serial = None
                self.disconnected.emit()
                break
            except Exception as e:
                print(f"[错误] 串口读取异常：{e}")
                continue

    def stop(self):
        self._running = False
        if self.serial and self.serial.is_open:
            self.serial.close()
        self.quit()
        self.wait()

# 主事件
if __name__ == '__main__':
    app = QApplication(sys.argv)
    GUI = GUI()
    GUI.show()
    sys.exit(app.exec())
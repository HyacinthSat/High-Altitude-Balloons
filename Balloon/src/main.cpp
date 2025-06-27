/*
 * Firmware for an ESP32-based High-Altitude Balloon (HAB) Tracker.
 *
 * This program is firmware designed for an ESP32-based high-altitude balloon (HAB) payload.
 * It utilizes the FreeRTOS operating system to perform multiple tasks concurrently,
 * including capturing images with a camera and encoding them into SSDV packets,
 * as well as collecting telemetry data such as GPS position, altitude, speed, internal temperature, and battery voltage.
 * All data (telemetry and SSDV) is transmitted via a serial port for radio downlink.
 * This firmware provides a complete flight control and data acquisition solution for HAB missions.
 *
 * Author: BG7ZDQ
 * Date: 2025/06/27
 * Version: 1.0.1
 * LICENSE: GNU General Public License v3.0
 */

// 系统开发状态
#define DEBUG_MODE true                

/* --- 综合头文件 --- */

// 核心配置文件和类型定义
#include "config.h"
#include "status_codes.h"

/* --- 系统配置与状态变量 --- */

// 定义并初始化系统动态配置变量
SystemConfig_t g_systemConfig = {
  .cameraImageSize     = FRAMESIZE_VGA,    // 默认摄像机图像尺寸: VGA
  .cameraImageQuality  = 5,                // 默认摄像机图像质量: 5
  .ssdvPacketType      = SSDV_TYPE_NOFEC,  // 默认 SSDV 数据类型: NOFEC
  .ssdvEncodingQuality = 2,                // 默认 SSDV 编码质量: 2
  .ssdvCycleTimeSec    = 60                // 默认 SSDV 发送周期: 60
};

// 定义并初始化系统实时状态变量
SystemStatus_t g_systemStatus = {
  .isRelayEnabled            = true,       // 中继功能默认开启
  .isSsdvEnabled             = true,       // 图传功能默认开启
  .isBuzzerEnabled           = true,       // 蜂鸣功能默认开启
  .isSsdvTransmitting        = false,      // 图传状态默认为否
};

// 定义初始化状态
bool Initialization_Status = true;

// 声明互斥锁
SemaphoreHandle_t g_configMutex = xSemaphoreCreateMutex();  // 配置参数结构体互斥锁
SemaphoreHandle_t g_stateMutex  = xSemaphoreCreateMutex();  // 状态参数结构体互斥锁
SemaphoreHandle_t cameraMutex   = xSemaphoreCreateMutex();  // 摄像头硬件资源互斥锁

// 声明各类队列
QueueHandle_t txQueue;     // 数据发送队列
QueueHandle_t cmdQueue;    // 命令接收队列
QueueHandle_t relayQueue;  // 中继信息队列

// FreeRTOS 任务句柄
TaskHandle_t DatalinkTaskHandle  = NULL;
TaskHandle_t CommandTaskHandle   = NULL;
TaskHandle_t TelemetryTaskHandle = NULL;
TaskHandle_t SSDVTaskHandle      = NULL;
TaskHandle_t RelayTaskHandle     = NULL;

/* --- 遥测模块相关变量 --- */
char TelemetryMessage[256];      // 初始化遥测数据缓冲区
uint16_t Telemetry_Counter = 0;  // 初始化遥测帧计数器

/* --- GPS 模块相关对象 --- */
HardwareSerial GPS_Serial(2);    // GPS 硬件串口分配 (RX on GPIO15, TX on default -1)
char GPS_Timestamp[21];          // GPS 时间戳缓冲区
TinyGPSPlus gps;                 // GPS 解析库对象

/* --- ADC 及传感器相关变量 --- */
esp_adc_cal_characteristics_t adc_chars;    // ADC 校准参数
extern "C" uint8_t temprature_sens_read();  // ROM 内部的温度传感器函数

/* --- SSDV 模块相关变量 --- */
ssdv_t ssdv;              // SSDV 编码器结构体
uint8_t ssdvImageId = 0;  // SSDV 编码器图像计数

/* --- 函数部分 --- */

// 线程安全地获取当前系统动态配置变量的完整副本
void GET_System_Config(SystemConfig_t* config_copy) {
  if (xSemaphoreTake(g_configMutex, portMAX_DELAY) == pdTRUE) {
    memcpy(config_copy, &g_systemConfig, sizeof(SystemConfig_t));
    xSemaphoreGive(g_configMutex);
  }
}

// 使用提供的新配置，线程安全地更新整个系统配置
void Update_System_Config(const SystemConfig_t* new_config) {
  if (xSemaphoreTake(g_configMutex, portMAX_DELAY) == pdTRUE) {
    memcpy(&g_systemConfig, new_config, sizeof(SystemConfig_t));
    xSemaphoreGive(g_configMutex);
  }
}

// 线程安全地获取当前系统实时状态变量的完整副本
void GET_System_Status(SystemStatus_t* status_copy) {
  if (xSemaphoreTake(g_stateMutex, portMAX_DELAY) == pdTRUE) {
    memcpy(status_copy, &g_systemStatus, sizeof(SystemStatus_t));
    xSemaphoreGive(g_stateMutex);
  }
}

// 使用提供的新状态，线程安全地更新系统实时状态变量
void Update_System_Status(SystemStatusParam_t param, bool value) {
  // 在锁的保护下根据传入的枚举来精确地修改一个成员
  if (xSemaphoreTake(g_stateMutex, portMAX_DELAY) == pdTRUE) {
    switch (param) {
      case RELAY_ENABLED_STATUS:
        g_systemStatus.isRelayEnabled = value;
        break;
      case SSDV_ENABLED_STATUS:
        g_systemStatus.isSsdvEnabled = value;
        break;
      case BUZZER_ENABLED_STATUS:
        g_systemStatus.isBuzzerEnabled = value;
        break;
      case SSDV_TRANSMITTING_STATUS:
        g_systemStatus.isSsdvTransmitting = value;
        break;
      default:
        break;
    }
    xSemaphoreGive(g_stateMutex);
  }
}

// 数据发送请求接口
/* --- 函数部分 --- */

// 数据发送请求接口
bool Transmit_Data(const uint8_t *data, size_t length, bool is_binary, bool send_to_front = false) {

  // 检查发送缓冲区是否可容纳数据
  if (length > MAX_TX_BUFF_SIZE) return false;

  RadioPacket_t packet;
  packet.length = length;
  packet.is_binary = is_binary;
  memcpy(packet.data, data, length);

  // 将数据包发送到队列，如果队列满了，等待500ms，最多重试三次
  for (int i = 0; i < 3; i++) {

    // 尝试将数据包放入队列
    // 根据 send_to_front 参数的值，决定调用哪个 FreeRTOS API
    if (send_to_front) {
      // 如果为 true，则进行插队
      if (xQueueSendToFront(txQueue, &packet, pdMS_TO_TICKS(500)) == pdTRUE) {
        return true;
      }
    } else {
      // 如果为 false，则仍然排队
      if (xQueueSend(txQueue, &packet, pdMS_TO_TICKS(500)) == pdTRUE) {
        return true;
      }
    }

    // 短暂挂起任务，给数据链路任务留出时间来处理和清空队列
    vTaskDelay(pdMS_TO_TICKS(50));
  }

  // 如果重试后最终失败
  return false;
}

// 文本信息发送请求接口
bool Transmit_Text(const char *format, ...) {

  char buffer[MAX_TX_BUFF_SIZE];
  size_t offset = 0;

  // 写入固定的帧头
  offset = snprintf(buffer, MAX_TX_BUFF_SIZE, "** ");

  // 写入内容
  va_list args;
  va_start(args, format);
  vsnprintf(buffer + offset, MAX_TX_BUFF_SIZE - offset, format, args);
  va_end(args);

  // 追加帧尾
  offset = strlen(buffer);
  snprintf(buffer + offset, MAX_TX_BUFF_SIZE - offset, " **");

  // 获取最终帧的长度
  size_t total_length = strlen(buffer);

  // 调用底层发送函数
  for (int i = 0; i < 3; i++) {
    if (Transmit_Data((uint8_t *)buffer, total_length, false, true)) {
      return true;
    }
    vTaskDelay(pdMS_TO_TICKS(100));
  }

  return false;
}

// 状态码发送请求接口
void Transmit_Status(StatusCode_t code, const char* info) {
  if (info == nullptr || info[0] == '\0') {
    Transmit_Text("Code: 0x%04X", code);
  } else {
    Transmit_Text("Code: 0x%04X, Info: %s", code, info);
  }
}

// 重载1 发送不带任何附加信息的状态码
void Transmit_Status(StatusCode_t code) {
  Transmit_Status(code, nullptr);
}

// 重载2 发送带数字 Payload 的状态码
void Transmit_Status(StatusCode_t code, int payload) {
  char buffer[20];
  snprintf(buffer, sizeof(buffer), "%d", payload);
  Transmit_Status(code, buffer);
}

// 重载3 发送带布尔值 Payload 的状态码
void Transmit_Status(StatusCode_t code, bool payload) {
  Transmit_Status(code, payload ? "1" : "0");
}

// 告警提醒
void Signal_Error() {
  SystemStatus_t local_status;
  GET_System_Status(&local_status);
  if (local_status.isBuzzerEnabled) {
    for (int i = 0; i < 3; i++) {
      digitalWrite(BUZZER, HIGH);
      vTaskDelay(pdMS_TO_TICKS(50));
      digitalWrite(BUZZER, LOW);
      vTaskDelay(pdMS_TO_TICKS(50));
    }
  }
  Initialization_Status = false;
}

// 就绪提醒
void Signal_Ready() {
  digitalWrite(BUZZER, HIGH);
  vTaskDelay(pdMS_TO_TICKS(100));
  digitalWrite(BUZZER, LOW);
}

// 初始化就绪检查
void Initialization_Check() {

  // 检查初始化变量
  if (Initialization_Status) {
    Signal_Ready();
  } else {
    Transmit_Status(SYS_INIT_FAIL);
    digitalWrite(BUZZER, HIGH);
    vTaskDelay(pdMS_TO_TICKS(2000));
    digitalWrite(BUZZER, LOW);
    esp_restart();
  }
  
  // 开发者模式指示
  if (DEBUG_MODE){
    Transmit_Status(SYS_DEV_MODE_ENABLED);
  }
}

// 配置摄像头信息
bool Setup_Camera() {

  // 通知地面站摄像头开始初始化
  Transmit_Status(CAM_INIT_START);

  // 获取当前配置
  SystemConfig_t local_config;
  GET_System_Config(&local_config);

  camera_config_t config;
  config.ledc_channel  = LEDC_CHANNEL_0;
  config.ledc_timer    = LEDC_TIMER_0;
  config.pin_d0        = CAM_PIN_Y2_GPIO_NUM;
  config.pin_d1        = CAM_PIN_Y3_GPIO_NUM;
  config.pin_d2        = CAM_PIN_Y4_GPIO_NUM;
  config.pin_d3        = CAM_PIN_Y5_GPIO_NUM;
  config.pin_d4        = CAM_PIN_Y6_GPIO_NUM;
  config.pin_d5        = CAM_PIN_Y7_GPIO_NUM;
  config.pin_d6        = CAM_PIN_Y8_GPIO_NUM;
  config.pin_d7        = CAM_PIN_Y9_GPIO_NUM;
  config.pin_xclk      = CAM_PIN_XCLK_GPIO_NUM;
  config.pin_pclk      = CAM_PIN_PCLK_GPIO_NUM;
  config.pin_vsync     = CAM_PIN_VSYNC_GPIO_NUM;
  config.pin_href      = CAM_PIN_HREF_GPIO_NUM;
  config.pin_sccb_sda  = CAM_PIN_SIOD_GPIO_NUM;
  config.pin_sccb_scl  = CAM_PIN_SIOC_GPIO_NUM;
  config.pin_pwdn      = CAM_PIN_PWDN_GPIO_NUM;
  config.pin_reset     = CAM_PIN_RESET_GPIO_NUM;
  config.xclk_freq_hz  = 20000000;
  config.pixel_format  = PIXFORMAT_JPEG;
  config.frame_size    = local_config.cameraImageSize;
  config.jpeg_quality  = local_config.cameraImageQuality;
  config.fb_count      = 2;
  config.grab_mode     = CAMERA_GRAB_LATEST;

  // 应用配置并检查返回状态
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    // 发送失败状态码，并附带错误信息
    Transmit_Status(CAM_INIT_FAIL, err);
    return false;
  }
  
  // 通知地面站初始化成功
  Transmit_Status(CAM_INIT_OK);

  return true;
}

// 拍摄多次进行摄像头校准 (自动曝光/白平衡稳定)
bool Camera_Calibrate() {

  // 通知地面站
  Transmit_Status(CAM_CALIBRATE_START);

  // 拍摄多次进行校准
  for (int i = 0; i < CAM_CALIBRATE_TIMES; i++) {
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) {
      Transmit_Status(CAM_CALIBRATE_FAIL);
      Signal_Error(); 
      return false;
    }
    vTaskDelay(pdMS_TO_TICKS(500));
    esp_camera_fb_return(fb);
  }

  // 通知地面站校准成功
  Transmit_Status(CAM_CALIBRATE_OK);
  return true;
}

// 安全地重新配置摄像头
bool Reconfigure_Camera() {

  // 先卸载当前摄像头驱动
  esp_camera_deinit();

  // 使用全局变量重新初始化
  if (!Setup_Camera()) return false;

  // 重新校准
  if (!Camera_Calibrate()) return false;

  // 一切正常则返回 true
  return true;
}

// GPS 初始化
void Initialize_GPS(unsigned long timeout_ms = 60000) {

  // 发送 GPS 开始初始化状态码
  Transmit_Status(GPS_INIT_START);
  unsigned long start = millis();

  // 调试模式下直接返回成功
  if (DEBUG_MODE) {
    Transmit_Status(GPS_INIT_OK);
    return;
  }

  // 在超时时间内不断尝试数据是否有效
  while (millis() - start < timeout_ms) {
    while (GPS_Serial.available()) {
      gps.encode(GPS_Serial.read());
    }

    if (gps.location.isValid()) {
      Transmit_Status(GPS_INIT_OK);

      // 构建一个初始遥测帧并发送
      Transmit_Text("%s", TelemetryMessage);

      return;
    }
    vTaskDelay(pdMS_TO_TICKS(2000));
  }

  Transmit_Status(GPS_INIT_FAIL, "Timeout");
  Initialization_Status = false;
}

// 初始化电压测量 ADC
void Initialize_Voltage_ADC() {
  // 配置 ADC 的通道衰减
  adc2_config_channel_atten(VOLTAGE_ADC_CHANNEL, VOLTAGE_ADC_ATTEN);
  // 获取 ADC 的校准特性
  esp_adc_cal_characterize(ADC_UNIT_2, VOLTAGE_ADC_ATTEN, VOLTAGE_ADC_WIDTH, VOLTAGE_ADC_VREF_MV, &adc_chars);
}

// 配置并初始化看门狗
void Initialize_Watchdog() {
  // 反初始化，确保后续状态干净
  esp_task_wdt_deinit();
  // 传入超时秒数和 panic 标志位
  esp_task_wdt_init(120, true);
}

// 定义数据链路层任务 (P5 - 最高优先级)
void V_Datalink_Task(void *pvParameters) {

  // 初始化帧缓冲区
  RadioPacket_t txPacket;
  static char frame_buffer[MAX_RX_BUFF_SIZE];
  static int frame_len = 0;

  // 将当前任务加入 WDT 监控 (注册看门狗)
  esp_task_wdt_add(NULL);

  for (;;) {

    // 标志位，记录本轮循环是否处理任何收发任务
    bool task_did_work = false;

    // 喂狗
    esp_task_wdt_reset();

    // 优先处理发送任务
    if (xQueueReceive(txQueue, &txPacket, pdMS_TO_TICKS(10)) == pdTRUE) {

      // 更新标志位
      task_did_work = true;

      // 从队列中获取数据包并写入串口
      Serial.write(txPacket.data, txPacket.length);
    }

    // 然后看看串口是否有数据，处理接收和分发
    if (Serial.available()) {

      // 更新标志位
      task_did_work = true;

      // 读取串口数据
      while (Serial.available()) {
        char c = Serial.read();

        // 检查帧尾 (换行符)
        if (c != '\n') {
          if (frame_len < MAX_RX_BUFF_SIZE - 1) {
            frame_buffer[frame_len++] = c;
          } else {
            // 缓冲区已满但未收到换行符，丢弃此帧，防止解析错误
            frame_len = 0;
          }
        }

        // 如果收到换行符，说明一帧数据接收完毕
        else {
          // 添加字符串结束符
          frame_buffer[frame_len] = '\0';

          // 判断帧类型并分发到对应的队列
          if (frame_len > 2) {

            // 指令帧 (@@)
            if (strncmp(frame_buffer, "@@", 2) == 0) {
              xQueueSend(cmdQueue, &frame_buffer[2], 50);
            }

            // 中继帧 (##)
            else if (strncmp(frame_buffer, "##", 2) == 0) {
              // 获取当前系统状态的副本
              SystemStatus_t local_status;
              GET_System_Status(&local_status);
              
              // 如果中继功能已启用且没有正在进行 SSDV 传输，则将数据包转发到中继队列
              if (local_status.isRelayEnabled && !local_status.isSsdvTransmitting) {
                xQueueSend(relayQueue, &frame_buffer[2], 50);
              }
            }
          }

          // 强制性让出 CPU 时间片，以进行指令解析
          vTaskDelay(pdMS_TO_TICKS(10));

          // 重置帧缓冲区，准备接收下一帧
          frame_len = 0;
        }
      }
    }

    // 如果既没有发送任务，也没有接收到数据，则短暂挂起，让出CPU
    if (!task_did_work) {
      vTaskDelay(pdMS_TO_TICKS(10));
    }
  }
}

// 创建数据链路任务
void Create_Datalink_Task() {

  // 初始化数据链路层各队列
  txQueue = xQueueCreate(120, sizeof(RadioPacket_t));
  cmdQueue = xQueueCreate(10, MAX_RX_BUFF_SIZE);
  relayQueue = xQueueCreate(10, MAX_RX_BUFF_SIZE);

  xTaskCreatePinnedToCore(
    V_Datalink_Task,           // 任务函数
    "DatalinkTask",            // 任务名称
    RTOS_STACK_SIZE,           // 堆栈大小
    NULL,                      // 传递参数
    configMAX_PRIORITIES - 1,  // 优先级P5
    &DatalinkTaskHandle,       // 任务句柄
    1                          // 运行核心
  );
}

// 处理 GET 指令的子函数
static void Handle_GET_Command(const char *target) {
  // 查询中继状态
  if (strcmp(target, "RELAY") == 0) {
    SystemStatus_t local_status;
    GET_System_Status(&local_status);
    Transmit_Status(CMD_ACK_GET_RELAY_STATUS, local_status.isRelayEnabled);
    return;
  }

  // 查询 SSDV 状态
  else if (strcmp(target, "SSDV") == 0) {
    SystemStatus_t local_status;
    GET_System_Status(&local_status);
    SystemConfig_t local_config;
    GET_System_Config(&local_config);
    Transmit_Status(CMD_ACK_GET_SSDV_STATUS, local_status.isSsdvEnabled);
    Transmit_Status(CMD_ACK_GET_SSDV_CYCLE, local_config.ssdvCycleTimeSec);
    Transmit_Status(CMD_ACK_GET_SSDV_TYPE, local_config.ssdvPacketType);
    Transmit_Status(CMD_ACK_GET_SSDV_QUALITY, local_config.ssdvEncodingQuality);
    return;
  }

  // 查询摄像头参数
  else if (strcmp(target, "CAM") == 0) {
    SystemConfig_t local_config;
    GET_System_Config(&local_config);
    Transmit_Status(CMD_ACK_GET_CAM_SIZE, local_config.cameraImageSize);
    Transmit_Status(CMD_ACK_GET_CAM_QUALITY, local_config.cameraImageQuality);
    return;
  }

  else {
    Transmit_Status(CMD_NACK_INVALID_GET);
    return;
  }
}

// 处理 CTL 指令的子函数
static void Handle_CTL_Command(const char *target, const char *value) {

  // 系统控制命令
  if (strcmp(target, "SYS") == 0 && strcmp(value, "REBOOT") == 0) {
    Transmit_Status(SYS_RESTARTING);
    vTaskDelay(pdMS_TO_TICKS(1000));
    esp_restart();
    return;
  }

  // 中继状态控制命令
  else if (strcmp(target, "RELAY") == 0) {
    if (strcmp(value, "ON") == 0) {
      Update_System_Status(RELAY_ENABLED_STATUS, true);
      Transmit_Status(CMD_ACK_RELAY_ON);
    } else if (strcmp(value, "OFF") == 0) {
      Update_System_Status(RELAY_ENABLED_STATUS, false);
      Transmit_Status(CMD_ACK_RELAY_OFF);
    }
    return;
  }

  // SSDV 状态控制命令
  else if (strcmp(target, "SSDV") == 0) {
    if (strcmp(value, "ON") == 0) {
      Update_System_Status(SSDV_ENABLED_STATUS, true);
      Transmit_Status(CMD_ACK_SSDV_ON);
    } else if (strcmp(value, "OFF") == 0) {
      Update_System_Status(SSDV_ENABLED_STATUS, false);
      Transmit_Status(CMD_ACK_SSDV_OFF);
    }
    return;
  }

    // 如果所有命令都未匹配
  else {
    Transmit_Status(CMD_NACK_INVALID_CTL);
  }
}

// 处理 SET 指令的子函数
static void Handle_SET_Command(const char *target, const char *value) {

  // 获取状态体副本
  SystemStatus_t local_status;
  GET_System_Status(&local_status);

  // 前置检查：SSDV 正在传输时，不允许任何设置更改
  if (local_status.isSsdvTransmitting) {
    Transmit_Status(CMD_NACK_SSDV_BUSY);
    return;
  }

  // 处理所有摄像头相关设置命令 (CAM_SIZE、CAM_QUALITY) 
  if (strcmp(target, "CAM_SIZE") == 0 || strcmp(target, "CAM_QUALITY") == 0) {

    // 声明配置变更状态，获取当前配置的副本
    bool config_changed = false;
    SystemConfig_t temp_config;
    GET_System_Config(&temp_config);
    
    // 定义摄像头模式的静态常量数组
    static const struct {
      const char *name;
      int size;
    } cam_modes[] = {
      { "FHD" , FRAMESIZE_FHD  },
      { "SXGA", FRAMESIZE_SXGA },
      { "XGA" , FRAMESIZE_XGA  },
      { "VGA" , FRAMESIZE_VGA  },
      { "QVGA", FRAMESIZE_QVGA }
    };

    // 设置图像尺寸
    if (strcmp(target, "CAM_SIZE") == 0) {
      // 遍历 cam_modes 数组，找到与 value 相等的元素
      for (int i = 0; i < sizeof(cam_modes) / sizeof(cam_modes[0]); i++) {
        // 如果找到相等的元素，则将temp_config.cameraImageSize设置为该元素的size，并设置config_changed为true
        if (strcmp(value, cam_modes[i].name) == 0) {
          temp_config.cameraImageSize = (framesize_t)cam_modes[i].size;
          config_changed = true;
          // 发送 CMD_ACK_CAM_SIZE 响应，并附带 temp_config.cameraImageSize
          Transmit_Status(CMD_ACK_CAM_SIZE, temp_config.cameraImageSize);
          break;
        }
      }
      // 如果没有找到相等的元素，则发送 CMD_NACK_INVALID_TYPE 响应
      if (!config_changed) {
        Transmit_Status(CMD_NACK_INVALID_TYPE);
      }
    }

    // 设置图像质量
    else if (strcmp(target, "CAM_QUALITY") == 0) {
      int requested_quality = atoi(value);

      // 合法性检查
      if (requested_quality < 5 || requested_quality > 20) {
        Transmit_Status(CMD_NACK_SET_CAM_QUAL);
      } else if (temp_config.cameraImageSize > FRAMESIZE_SVGA && requested_quality < 10) {
        Transmit_Status(CMD_NACK_SET_CAM_QUAL_LOW);
      }
      
      // 通过后尝试进行设置
      else {
        temp_config.cameraImageQuality = requested_quality;
        config_changed = true;
        Transmit_Status(CMD_ACK_CAM_QUALITY, requested_quality);
      }
    }

    // 如果摄像头任一配置有变动，则统一执行重配
    if (config_changed) {

      // 获取摄像头硬件资源互斥锁进行保护
      xSemaphoreTake(cameraMutex, portMAX_DELAY);

      // 更新结构体内容并尝试进行设置
      Update_System_Config(&temp_config);
      if (Reconfigure_Camera()) {
        Transmit_Status(CAM_RECONFIG_OK);
      }

      // 如果设置失败，尝试恢复默认设置
      else {
        Transmit_Status(CAM_RECONFIG_FAIL);
        GET_System_Config(&temp_config);
        temp_config.cameraImageSize = FRAMESIZE_VGA;
        temp_config.cameraImageQuality = 5;
        Update_System_Config(&temp_config);
        if (Reconfigure_Camera()) {
          Transmit_Status(CAM_RESTORE_DEFAULT_OK);
        }
        
        // 恢复失败为重大失误，直接重启
        else {
          Transmit_Status(CAM_RESTORE_DEFAULT_FAIL);
          Transmit_Status(SYS_RESTARTING);
          esp_restart();
        }
      }

      // 释放锁
      xSemaphoreGive(cameraMutex);
    }

    // 处理完相机指令后直接返回
    return;
  }

  // 处理所有 SSDV 相关设置命令 (SSDV_TYPE, SSDV_QUALITY, SSDV_CYCLE)
  else if (strcmp(target, "SSDV_TYPE") == 0 || strcmp(target, "SSDV_QUALITY") == 0 || strcmp(target, "SSDV_CYCLE") == 0) {
    
    // 声明配置变更状态，获取当前配置的副本
    bool config_changed = false;
    SystemConfig_t temp_config;
    GET_System_Config(&temp_config);

    // 设置 SSDV 类型
    if (strcmp(target, "SSDV_TYPE") == 0) {

      // 常规模式 (带有 FEC) 
      if (strcmp(value, "NORMAL") == 0) {
        temp_config.ssdvPacketType = SSDV_TYPE_NORMAL;
        config_changed = true;
        Transmit_Status(CMD_ACK_SSDV_TYPE, SSDV_TYPE_NORMAL);
      }
      
      // 轻量化模式 (无 FCE) 
      else if (strcmp(value, "NOFEC") == 0) {
        temp_config.ssdvPacketType = SSDV_TYPE_NOFEC;
        config_changed = true;
        Transmit_Status(CMD_ACK_SSDV_TYPE, SSDV_TYPE_NOFEC);
      }
    }

    // 设置 SSDV 质量
    else if (strcmp(target, "SSDV_QUALITY") == 0) {
      int quality = atoi(value);

      // 合法性校验
      if (quality >= 0 && quality <= 6) {
        temp_config.ssdvEncodingQuality = quality;
        config_changed = true;
        Transmit_Status(CMD_ACK_SSDV_QUALITY, quality);
      } else {
        Transmit_Status(CMD_NACK_SET_SSDV_QUAL);
      }
    }

    // 设置 SSDV 周期
    else if (strcmp(target, "SSDV_CYCLE") == 0) {
      int cycletime = atoi(value);

      // 合法性校验
      if (cycletime >= 10 && cycletime <= 100) {
        temp_config.ssdvCycleTimeSec = cycletime;
        config_changed = true;
        Transmit_Status(CMD_ACK_SSDV_CYCLE, cycletime);
      } else {
        Transmit_Status(CMD_NACK_SET_SSDV_CYCLE);
      }
    }

    // 如果 SSDV 配置发生变动，则统一更新到全局配置
    if (config_changed) {
      Update_System_Config(&temp_config);
    }

    // 处理完SSDV指令后直接返回
    return;
  }
  
  // 如果所有命令都未匹配
  else {
    Transmit_Status(CMD_NACK_INVALID_SET);
  }
}

// 执行命令
void Process_Command(const char *cmd) {

  // 初始化命令缓冲区
  char buffer[MAX_RX_BUFF_SIZE];
  strncpy(buffer, cmd, sizeof(buffer));
  buffer[MAX_RX_BUFF_SIZE - 1] = '\0';
  
  // 解析命令字段
  char *saveptr;
  char *type = strtok_r(buffer, ",", &saveptr);
  char *target = strtok_r(NULL, ",", &saveptr);
  char *value = strtok_r(NULL, ",", &saveptr);

  if (!type || !target) {
    Transmit_Status(CMD_NACK_FORMAT_ERROR);
    return;
  }

  // 查询类命令
  if (strcmp(type, "GET") == 0) {
    Handle_GET_Command(target);
    return;
  }

  // 其余函数需要 Value 字段
  if (!value) {
    Transmit_Status(CMD_NACK_NO_VALUE);
    return;
  }
  
  // 控制类命令
  else if (strcmp(type, "CTL") == 0) {
    Handle_CTL_Command(target, value);
    return;
  }
  
  // 设置类命令
  else if (strcmp(type, "SET") == 0) {
    Handle_SET_Command(target, value);
    return;
  }
  
  // 未定义的命令
  else {
    Transmit_Status(CMD_NACK_INVALID_TYPE);
    return;
  }
}

// 指令解析任务 (P4 - 较高优先级)
// 指令格式：@@<Type>,<SubType>,<Value>\n
void V_Command_Task(void *pvParameters) {

  // 初始化指令缓冲区
  char cmd_buffer[MAX_RX_BUFF_SIZE];

  // 将当前任务加入 WDT 监控 (注册看门狗) 
  esp_task_wdt_add(NULL);

  for (;;) {

    // 喂狗
    esp_task_wdt_reset();

    // 从指令队列中等待消息，如果1000ms内没有消息，会自动超时返回
    if (xQueueReceive(cmdQueue, cmd_buffer, pdMS_TO_TICKS(1000))) {
      Process_Command(cmd_buffer);
    }
  }
}

// 创建指令解析任务
void Create_Command_Task() {
  xTaskCreatePinnedToCore(
    V_Command_Task,            // 任务函数
    "CommandTask",             // 任务名称
    RTOS_STACK_SIZE,           // 堆栈大小
    NULL,                      // 传递参数
    configMAX_PRIORITIES - 2,  // 优先级P4
    &CommandTaskHandle,        // 任务句柄
    1                          // 运行核心
  );
}

// 采集当前电池电压
float Get_Battery_Voltage() {

  // 定义业务逻辑变量
  int valid_samples = 0; int single_raw_adc = 0;
  esp_err_t res; uint32_t total_raw_adc = 0;
  
  // 通过过采样稳定ADC读数
  for (int i = 0; i < 5; i++) {
    res = adc2_get_raw(VOLTAGE_ADC_CHANNEL, VOLTAGE_ADC_WIDTH, &single_raw_adc);
    // 采样成功才进行累加
    if (res == ESP_OK) {
      total_raw_adc += single_raw_adc;
      valid_samples++;
    }
    vTaskDelay(pdMS_TO_TICKS(5));
  }

  // 如果全部失败，发送ADC采样失败状态码，并附带 esp_err_t 作为负载
  if (valid_samples == 0) {
    Transmit_Status(ADC_SAMPLE_FAIL, res);
    return -1145.14f;
  }

  // 计算原始ADC读数的平均值
  uint32_t average_raw_adc = total_raw_adc / valid_samples;

  // 将原始值转换为校准后的电压，然后根据分压电路参数计算实际电池电压
  uint32_t voltage_mv = esp_adc_cal_raw_to_voltage(average_raw_adc, &adc_chars);
  float BAT_Voltage = ((float)voltage_mv / 1000.0f) * (VOLTAGE_TEST_R1 + VOLTAGE_TEST_R2) / VOLTAGE_TEST_R2;

  // 应用校准系数并返回结果
  return BAT_Voltage * 0.9518f; 
}

// 读取温度传感器值 
// 温度传感器与 ADC2 存在冲突
// 此处保护性的封装函数，在读取温度前手动修复硬件状态
float Get_Chip_Temperature() {

  // 操作寄存器，强制开启温度传感器
  SET_PERI_REG_MASK(SENS_SAR_MEAS_WAIT2_REG, SENS_FORCE_XPD_SAR_M);
  SET_PERI_REG_BITS(SENS_SAR_TSENS_CTRL_REG, SENS_TSENS_CLK_DIV, 10, SENS_TSENS_CLK_DIV_S);
  CLEAR_PERI_REG_MASK(SENS_SAR_TSENS_CTRL_REG, SENS_TSENS_POWER_UP);
  CLEAR_PERI_REG_MASK(SENS_SAR_TSENS_CTRL_REG, SENS_TSENS_DUMP_OUT);
  SET_PERI_REG_MASK(SENS_SAR_TSENS_CTRL_REG, SENS_TSENS_POWER_UP_FORCE);
  SET_PERI_REG_MASK(SENS_SAR_TSENS_CTRL_REG, SENS_TSENS_POWER_UP);

  // 等待一小段时间让传感器稳定。
  vTaskDelay(pdMS_TO_TICKS(50));

  float total_temp = 0.0f;
  // 通过过采样稳定读数
  for (int i = 0; i < 5; i++) {
      total_temp += temperatureRead();
      vTaskDelay(pdMS_TO_TICKS(20));
  }

  // 返回计算出的平均值
  return total_temp / 5;
}

// 构建类 UKHAS 格式的遥测数据帧
// $$CALLSIGN,Telemetry_Counter,Time,Latitude,Longitude,Altitude,Speed,Sats,Heading,Temprature,Voltage,GPS_Validity
void Build_Telemetry_Frame(char GPS_Validity) {

  // 读取芯片温度
  float Chip_Temp = Get_Chip_Temperature();
  // 读取电池电压
  float BAT_Voltage = Get_Battery_Voltage();

  // 调试模式：构建一个不依赖 GPS 的调试遥测帧
  if (DEBUG_MODE) {
    snprintf(TelemetryMessage, sizeof(TelemetryMessage),
      "$$%s,%d,DEBUG_MODE,0.000000,0.000000,0.00,0.00,0,0.00,%.2f,%.2f,%c",
      CALLSIGN, Telemetry_Counter, Chip_Temp, BAT_Voltage, GPS_Validity
    );

    Telemetry_Counter += 1;
    return;
  }

  // 拼装 ISO 格式的 UTC 时间戳，如 2006-10-12T05:20:00Z 
  snprintf(GPS_Timestamp, sizeof(GPS_Timestamp),
    "%04d-%02d-%02dT%02d:%02d:%02dZ",
    gps.date.year(),   // 年
    gps.date.month(),  // 月
    gps.date.day(),    // 日
    gps.time.hour(),   // 时
    gps.time.minute(), // 分
    gps.time.second()  // 秒
  );

  // 拼装类 UKHAS 格式的遥测字符串
  snprintf(TelemetryMessage, sizeof(TelemetryMessage),
    "$$%s,%d,%s,%.6f,%.6f,%.2f,%.2f,%d,%.2f,%.2f,%.2f,%c",
    CALLSIGN,                // 呼号
    Telemetry_Counter,       // 帧数
    GPS_Timestamp,           // 时间
    gps.location.lat(),      // 纬度
    gps.location.lng(),      // 经度
    gps.altitude.meters(),   // 高度
    gps.speed.kmph(),        // 速度
    gps.satellites.value(),  // 卫星数
    gps.course.deg(),        // 航向角
    Chip_Temp,               // 摄氏度
    BAT_Voltage,             // 电压值
    GPS_Validity             // 有效性
  );

  Telemetry_Counter += 1;
}

// 遥测发送任务 (P3 - 中等优先级)
void V_Telemetry_Task(void *pvParameters) {

  // 将当前任务加入 WDT 监控 (注册看门狗) 
  esp_task_wdt_add(NULL);

  for (;;) {
    // 先喂狗
    esp_task_wdt_reset();

    // 尝试获取 GPS 更新
    int retries = 0;
    char GPS_Validity = 'V';
    while (retries < 3) {

      // 尝试从串口读取 GPS 数据
      while (GPS_Serial.available()) {
        gps.encode(GPS_Serial.read());
      }

      // 位置有更新则停止重试
      if (gps.location.isUpdated()) {
        GPS_Validity = 'A';
        break;
      }

      // 如果没有更新，等待1秒后重试
      retries++;
      vTaskDelay(pdMS_TO_TICKS(1000));
    }

    // 喂狗
    esp_task_wdt_reset();

    // 重试结束后，无论 GPS 是否更新，都构建并发送遥测帧
    Build_Telemetry_Frame(GPS_Validity);
    Transmit_Text("%s", TelemetryMessage);

    // 每 20 秒发送一次遥测数据
    vTaskDelay(pdMS_TO_TICKS(20000 - 3000));
  }
}

// 创建遥测发送任务
void Create_Telemetry_Task() {
  xTaskCreatePinnedToCore(
    V_Telemetry_Task,          // 任务函数
    "TelemetryTask",           // 任务名称
    RTOS_STACK_SIZE,           // 堆栈大小
    NULL,                      // 传递参数
    configMAX_PRIORITIES - 3,  // 优先级P3
    &TelemetryTaskHandle,      // 任务句柄
    1                          // 运行核心
  );
}

// 读取图像数据
int Read_Image_Buffer(uint8_t *buffer, int numBytes, camera_fb_t *fb, int fbIndex) {

  int bufSize = 0;
  // 检查是否到达图像缓冲区的末尾
  if ((fbIndex + numBytes) < fb->len) {

    bufSize = numBytes;
  } else {

    bufSize = fb->len - fbIndex;
  }
  memcpy(buffer, &fb->buf[fbIndex], bufSize);
  return bufSize;
}

// 调制 SSDV 数据包
void Process_SSDV_Packet(camera_fb_t *fb, const SystemConfig_t* local_config) {

  // 定义函数业务所用逻辑变量
  uint8_t ssdv_out_buffer[SSDV_OUT_BUFF_SIZE];
  uint8_t ssdv_feed_buffer[SSDV_FEED_BUFF_SIZE];
  int index = 0, c = 0, packet_count = 0;

  // 初始化 SSDV 配置结构，默认为无 FEC 模式，质量等级 2，每帧长 256 字节
  ssdv_enc_init(&ssdv, local_config->ssdvPacketType, (char *)CALLSIGN, ssdvImageId++, local_config->ssdvEncodingQuality, SSDV_SIZE_NOFEC);

  // 设置 SSDV 的输出数据包缓冲区
  ssdv_enc_set_buffer(&ssdv, ssdv_out_buffer);

  // 大循环结构
  while (true) {

    // 喂狗
    esp_task_wdt_reset();

    // 当状态为 SSDV_FEED_ME 时投喂数据
    while ((c = ssdv_enc_get_packet(&ssdv)) == SSDV_FEED_ME) {
      int bytes_read_from_image = Read_Image_Buffer(ssdv_feed_buffer, sizeof(ssdv_feed_buffer), fb, index);
      if (bytes_read_from_image > 0) {
        index += bytes_read_from_image;
        ssdv_enc_feed(&ssdv, ssdv_feed_buffer, bytes_read_from_image);
      }
    }

    // 图像编码完成
    if (c == SSDV_EOI) {
      break;
    }

    // 出错处理
    else if (c != SSDV_OK) {
      Transmit_Status(SSDV_ENCODE_ERROR, c);
      break;
    }

    // 确保发送成功
    int retry_count = 0;
    while (!Transmit_Data(ssdv_out_buffer, SSDV_SIZE_NOFEC, true)) {
      retry_count++;
      vTaskDelay(pdMS_TO_TICKS(100));
      if (retry_count >= 3) {
        Transmit_Status(SSDV_TX_BUFFER_FULL);
        break;
      }
    }

    // 短暂延时，让出CPU给其他任务
    vTaskDelay(pdMS_TO_TICKS(20));

    packet_count++;
  }
}

// 图像回传层任务 (P2 - 较低优先级)
void V_SSDV_Task(void *pvParameters) {

  // 初始化图像帧缓冲区
  camera_fb_t *fb = NULL;

  // 将当前任务加入 WDT 监控 (注册看门狗) 
  esp_task_wdt_add(NULL);

  for (;;) {

    // 喂狗
    esp_task_wdt_reset();

    // 获取当前系统状态的本地副本
    SystemStatus_t local_status;
    GET_System_Status(&local_status);

    // 检查任务启用状态
    if (!local_status.isSsdvEnabled) {
      vTaskDelay(pdMS_TO_TICKS(5000));
      continue;
    }

    // 更新状态，发送 "START" 信号，开始处理流程
    Update_System_Status(SSDV_TRANSMITTING_STATUS, true);
    Transmit_Status(SSDV_ENCODE_START, ssdvImageId);

    // 在摄像头硬件资源互斥锁的保护下进行拍摄
    xSemaphoreTake(cameraMutex, portMAX_DELAY);

    // 正式进行拍摄，并进行错误处理
    fb = esp_camera_fb_get();
    if (!fb || !fb->buf || fb->len == 0) {
      Transmit_Status(CAM_CAPTURE_FAIL);
      if (fb) esp_camera_fb_return(fb);
      xSemaphoreGive(cameraMutex);
      Signal_Error();
      continue;
    }

    // 对拍摄的图像进行 SSDV 编码
    SystemConfig_t local_config;
    GET_System_Config(&local_config);
    Process_SSDV_Packet(fb, &local_config);

    // 释放摄像头帧缓冲区
    esp_camera_fb_return(fb);
    fb = NULL;

    // 释放摄像头硬件资源互斥锁
    xSemaphoreGive(cameraMutex);

    // 然后等待发送队列被完全清空
    while (uxQueueMessagesWaiting(txQueue) > 0) {
        vTaskDelay(pdMS_TO_TICKS(200)); 
        esp_task_wdt_reset();
    }

    // 增加一个额外的延时，以确保物理串口的硬件发送缓冲区有足够的时间将最后一个数据包完全发出。
    // 对于 9600 波特率，发送一个 256 字节的数据包大约需要 256 * 10 / 9600 ≈ 267ms。
    // 因此，一个 300ms 到 500ms 的延时是比较安全的。
    vTaskDelay(pdMS_TO_TICKS(500)); 

    // 图像编码并发送完成，发送结束标识，并附带图像编号
    Transmit_Status(SSDV_ENCODE_END, ssdvImageId - 1);

    // 修改 SSDV 发送状态至 False，允许 SET/CTL 命令的执行。
    Update_System_Status(SSDV_TRANSMITTING_STATUS, false);

    // 降频节电
    setCpuFrequencyMhz(80);

    // 待数据全部发送完毕后，开始计算并执行发送周期。
    GET_System_Config(&local_config);
    int cycle_time_sec = local_config.ssdvCycleTimeSec;
    vTaskDelay(pdMS_TO_TICKS(cycle_time_sec * 1000));

    // 恢复高速运行频率，为下一次拍摄做准备
    setCpuFrequencyMhz(240);
  }
}

// 创建 SSDV 发送任务
void Create_SSDV_Task() {
  xTaskCreatePinnedToCore(
    V_SSDV_Task,               // 任务函数
    "SSDVTask",                // 任务名称
    RTOS_STACK_SIZE,           // 堆栈大小
    NULL,                      // 传递参数
    configMAX_PRIORITIES - 4,  // 优先级P2
    &SSDVTaskHandle,           // 任务句柄
    0                          // 运行核心
  );
}

// 中继任务 (P1 - 最低优先级)
// 地面站格式 : ##ToCall,FmCall,Grid,INFO\n
// 转发器格式 ：##RELAY,ToCall,FmCall,Grid,INFO
void V_Relay_Task(void *pvParameters) {

  // 中继帧缓冲区
  char relay_buffer[256];
  int relay_len = 0;

  // 防滥用机制，每两分钟重置一次计数
  int relay_count_since_reset = 0;
  unsigned long last_reset_time = 0;
  static bool relay_limited_warned = false;
  const unsigned long reset_interval_ms = 120000;

  // 将当前任务加入 WDT 监控 (注册看门狗) 
  esp_task_wdt_add(NULL);

  for (;;) {

    // 先喂狗
    esp_task_wdt_reset();

    // 检查任务启用状态，如果任务关闭，挂起2秒再检查
    SystemStatus_t local_status;
    GET_System_Status(&local_status);
    if (!local_status.isRelayEnabled) {
      vTaskDelay(pdMS_TO_TICKS(2000));
      continue;
    }

    // 防滥用机制的计时与重置
    if (millis() - last_reset_time > reset_interval_ms) {
      relay_count_since_reset = 0;
      last_reset_time = millis();
      relay_limited_warned = false;
    }

    // 从中继队列等待消息
    if (xQueueReceive(relayQueue, relay_buffer, pdMS_TO_TICKS(1000))) {
      // 收到完整的中继数据，直接构造转发帧
      if (relay_count_since_reset < 80) {
        Transmit_Text("##RELAY,%s", relay_buffer);
        relay_count_since_reset++;
      } else {
        if (!relay_limited_warned) {
          Transmit_Status(RELAY_RATE_LIMITED);
          relay_limited_warned = true;
        }
      }
    }
  }
}

// 创建中继任务
void Create_Relay_Task() {
  xTaskCreatePinnedToCore(
    V_Relay_Task,              // 任务函数
    "RelayTask",               // 任务名称
    RTOS_STACK_SIZE,           // 堆栈大小
    NULL,                      // 传递参数
    configMAX_PRIORITIES - 5,  // 优先级P1
    &RelayTaskHandle,          // 任务句柄
    1                          // 运行核心
  );
}

/* --- 程序入口 --- */
void setup() {

  /* 阶段 1: 基础硬件和服务初始化 */
  vTaskDelay(pdMS_TO_TICKS(10000));            // 等待十秒，保证上电稳定
  pinMode(BUZZER, OUTPUT);                     // 配置告警 IO
  digitalWrite(BUZZER, LOW);                   // 初始化为低电平
  Serial.begin(9600);                          // 设置主串口波特率
  GPS_Serial.begin(9600, SERIAL_8N1, 15, -1);  // 设置 GPS 串口
  WiFi.mode(WIFI_OFF);                         // 关闭 Wi-Fi
  btStop();                                    // 关闭 蓝牙
  Initialize_Watchdog();                       // 启动看门狗
  Create_Datalink_Task();                      // 创建数据链路层任务
  Transmit_Status(SYS_BOOTING);                // 自检指示1

  /* 阶段 2: 核心模块初始化 */
  Setup_Camera();                              // 摄像头初始化设置
  Camera_Calibrate();                          // 摄像头曝光/白平衡校准
  Initialize_Voltage_ADC();                    // 初始化电压测量 ADC
  Initialize_GPS();                            // 初始化 GPS 模块 

  /* 阶段 3: 初始化检查 */
  Initialization_Check();                      // 初始化就绪检查
  Transmit_Status(SYS_INIT_OK);                // 自检指示2
  vTaskDelay(pdMS_TO_TICKS(2000));             // 等待两秒，保证工作稳定

  /* 阶段 4: 创建所有其他应用任务 */
  Create_Command_Task();                       // 创建命令解析层任务
  Create_SSDV_Task();                          // 创建图像传输层任务
  Create_Telemetry_Task();                     // 创建基础遥测层任务
  Create_Relay_Task();                         // 创建数字中继层任务
}

// 主循环函数
void loop() {

  // 初始化结束后通过线程安全函数关闭蜂鸣器
  Update_System_Status(BUZZER_ENABLED_STATUS, false);

  // 删除主循环任务以释放资源
  vTaskDelete(NULL);
}
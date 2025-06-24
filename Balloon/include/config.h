/*
 * Configuration and Global Declarations for the ESP32 HAB Tracker
 *
 * This header file centralizes all hardware pin assignments, firmware parameters,
 * global type definitions, and external variable declarations for the project.
 * It ensures a single, consistent source for configuration, which improves
 * modularity and simplifies maintenance across the firmware. All global objects
 * are declared here as 'extern' and defined in the main .ino file to adhere
 * to best practices and prevent linker errors.
 *
 * Author: BG7ZDQ
 * Date: 2025/06/21
 * Version: 1.2.0
 * LICENSE: GNU General Public License v3.0
 */

#ifndef CONFIG_H
#define CONFIG_H

/* --- 引入功能头文件 --- */

// Arduino 核心库
#include <Arduino.h>

// C/C++ 标准库 和 FreeRTOS
#include <stdarg.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include <freertos/task.h>

// ESP-IDF 底层驱动和库
#include <WiFi.h>
#include <driver/adc.h>

#include <esp_camera.h>
#include <esp_adc_cal.h>
#include <esp_task_wdt.h>

#include <rom/rtc.h>
#include <rom/ets_sys.h>

#include <soc/sens_reg.h>
#include <soc/sens_reg.h>
#include <soc/rtc_cntl_reg.h>

// 第三方库
#include <TinyGPS++.h>
#include <ssdv.h>

/* --- 分配硬件引脚 --- */

// OV2640 摄像头模块引脚
#define CAM_PIN_Y9_GPIO_NUM      35
#define CAM_PIN_Y8_GPIO_NUM      34
#define CAM_PIN_Y7_GPIO_NUM      39
#define CAM_PIN_Y6_GPIO_NUM      36
#define CAM_PIN_Y5_GPIO_NUM      21
#define CAM_PIN_Y4_GPIO_NUM      19
#define CAM_PIN_Y3_GPIO_NUM      18
#define CAM_PIN_Y2_GPIO_NUM      5
#define CAM_PIN_XCLK_GPIO_NUM    0
#define CAM_PIN_PCLK_GPIO_NUM    22
#define CAM_PIN_VSYNC_GPIO_NUM   25
#define CAM_PIN_HREF_GPIO_NUM    23
#define CAM_PIN_SIOD_GPIO_NUM    26  // SCCB 接口
#define CAM_PIN_SIOC_GPIO_NUM    27  // SCCB 接口
#define CAM_PIN_PWDN_GPIO_NUM    32  // 电源控制
#define CAM_PIN_RESET_GPIO_NUM   -1  // 复位引脚 (未连接)

// 蜂鸣器引脚
#define BUZZER                   13

// 电压 ADC 引脚
#define VOLTAGE_ADC_GPIO_PIN     12  // 连接至分压电路的 ADC GPIO
#define VOLTAGE_ADC_CHANNEL      ADC2_CHANNEL_5


/* --- 固件参数与宏定义 --- */
#define CALLSIGN             "BG7ZDQ"            // 气球呼号
#define DEBUG_MODE           true                // 系统开发状态

// RTOS 相关参数
#define RTOS_STACK_SIZE      4096                // 默认 RTOS 任务堆栈大小

// 缓冲区与数据包大小
#define MAX_TX_BUFF_SIZE     512                 // 发送队列缓冲区大小
#define MAX_RX_BUFF_SIZE     512                 // 接收队列缓冲区大小
#define SSDV_FEED_BUFF_SIZE  128                 // 喂给 SSDV 编码器的缓冲区大小
#define SSDV_OUT_BUFF_SIZE   256                 // 存放 SSDV 数据包的缓冲区大小
#define SSDV_SIZE_NOFEC      256                 // 单个 SSDV 数据包的大小

// 功能参数
#define CAM_CALIBRATE_TIMES  5                   // 摄像头校准拍摄次数

// 电压测量相关参数
#define VOLTAGE_TEST_R1      10000               // 分压电阻 R1 的阻值
#define VOLTAGE_TEST_R2      1000                // 分压电阻 R2 的阻值
#define VOLTAGE_ADC_WIDTH    ADC_WIDTH_BIT_12    // 电压测量 ADC 的分辨率
#define VOLTAGE_ADC_ATTEN    ADC_ATTEN_DB_0      // 电压测量 ADC 的输入衰减
#define VOLTAGE_ADC_VREF_MV  1100                // 电压测量 ADC 的参考电压 (mV)


/* --- 全局数据结构类型定义 --- */

// 声明系统动态配置参数结构体
typedef struct {
  framesize_t cameraImageSize;      // 摄像头图像尺寸
  int         cameraImageQuality;   // 摄像头图像质量
  uint8_t     ssdvPacketType;       // SSDV 数据类型
  int         ssdvEncodingQuality;  // SSDV 编码质量
  int         ssdvCycleTimeSec;     // SSDV 发送周期
} SystemConfig_t;

// 声明系统实时运行状态结构体
typedef struct {
  bool isRelayEnabled;              // 中继功能启用状态
  bool isSsdvEnabled;               // 图传功能启用状态
  bool isBuzzerEnabled;             // 蜂鸣功能启用状态
  bool isSsdvTransmitting;          // 图像传输进行状态
} SystemStatus_t;

// 声明用于安全更新系统状态的枚举
typedef enum {
  RELAY_ENABLED_STATUS,
  SSDV_ENABLED_STATUS,
  BUZZER_ENABLED_STATUS,
  SSDV_TRANSMITTING_STATUS,
} SystemStatusParam_t;

// 声明无线电发送队列的数据包结构体
typedef struct {
  uint8_t data[MAX_TX_BUFF_SIZE];
  size_t length;
  bool is_binary;
} RadioPacket_t;


/* --- 全局变量外部声明 --- */

// 系统配置与状态变量
extern SystemConfig_t g_systemConfig;
extern SystemStatus_t g_systemStatus;
extern bool Initialization_Status;

// 声明互斥锁
extern SemaphoreHandle_t g_configMutex;  // 配置参数结构体互斥锁
extern SemaphoreHandle_t g_stateMutex;   // 状态参数结构体互斥锁
extern SemaphoreHandle_t cameraMutex;    // 摄像头硬件资源互斥锁

// 声明各类队列
extern QueueHandle_t txQueue;            // 数据发送队列
extern QueueHandle_t cmdQueue;           // 命令接收队列
extern QueueHandle_t relayQueue;         // 中继信息队列

// FreeRTOS 任务句柄
extern TaskHandle_t DatalinkTaskHandle;
extern TaskHandle_t CommandTaskHandle;
extern TaskHandle_t TelemetryTaskHandle;
extern TaskHandle_t SSDVTaskHandle;
extern TaskHandle_t RelayTaskHandle;

// 遥测模块相关变量
extern char TelemetryMessage[256];
extern uint16_t Telemetry_Counter;

// GPS 模块相关对象
extern HardwareSerial GPS_Serial;
extern char GPS_Timestamp[21];
extern TinyGPSPlus gps;

// ADC 及传感器相关变量
extern esp_adc_cal_characteristics_t adc_chars;

// SSDV 模块相关变量
extern ssdv_t ssdv;
extern uint8_t ssdvImageId;

#endif // CONFIG_H
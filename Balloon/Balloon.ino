// 宏定义
#define SSDV_CALLSIGN "BG7ZDQ"          // 呼号
#define SSDV_IMG_BUFF_SIZE 128          // 喂给SSDV编码器的缓冲区大小
#define SSDV_OUT_BUFF_SIZE 256          // 用于存放编码后SSDV数据包的缓冲区
#define SSDV_SIZE_NOFEC 256             // 标准SSDV包大小 (无FEC)
#define CAM_CALIBRATE 5                 // 摄像头校准次数
#define DEBUG_MODE false                // 开发状态

// 功能头文件
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "esp_task_wdt.h"
#include "esp_camera.h"
#include "TinyGPS++.h"
#include "Arduino.h"
#include "Balloon.h"
#include "stdarg.h"
#include "WiFi.h"
#include "ssdv.h"

// 启用温度传感器
extern "C" uint8_t temprature_sens_read();

// FreeRTOS 相关全局变量
SemaphoreHandle_t xSerialMutex;
TaskHandle_t ssdvTaskHandle = NULL;
TaskHandle_t gpsTaskHandle = NULL;
TaskHandle_t relayTaskHandle = NULL;

// 初始化状态
bool Initialization_Status = true;

// GPS 相关全局变量
HardwareSerial GPS_Serial(2);
char gpsMessage[256];
char gps_time[21];
TinyGPSPlus gps;

// SSDV 相关全局变量
ssdv_t ssdv;                                 // SSDV编码器状态结构体
uint8_t imageID = 0;                         // 图像计数器
bool SSDV_State = false;                     // SSDV 状态
uint8_t ssdv_feed_buff[SSDV_IMG_BUFF_SIZE];  // 从摄像头读取数据到此缓冲区，再喂给SSDV
uint8_t ssdv_out_buff[SSDV_OUT_BUFF_SIZE];   // SSDV编码器生成的包会存放在这里

// 传输数据（端口短缺，使用主串口连接射频设备）
void Transmit_Text(const char* format, ...) {

  // 尝试获取互斥锁，等待最多500ms
  if (xSerialMutex != NULL && xSemaphoreTake(xSerialMutex, pdMS_TO_TICKS(500)) == pdTRUE) {
    char buffer[256];
    va_list args;
    va_start(args, format);
    vsnprintf(buffer, sizeof(buffer), format, args);
    va_end(args);

    // 必要的延时，避免射频模块丢字
    vTaskDelay(40);
    Serial.print(buffer);
    Serial.flush();

    // 释放互斥锁
    xSemaphoreGive(xSerialMutex);
  } else {
    // 获取锁失败即进行错误提醒
    Serial.print("** 错误：文本数据互斥锁冲突 **");
    Happen_Error();
  }
}

// 传输二进制数据
void Transmit_Data(const uint8_t* data, size_t length) {

  // 尝试获取互斥锁，等待最多500ms
  if (xSerialMutex != NULL && xSemaphoreTake(xSerialMutex, pdMS_TO_TICKS(500)) == pdTRUE) {

    // 必要的延时，避免射频模块丢字
    vTaskDelay(40);
    Serial.write(data, length);
    Serial.flush();

    // 释放互斥锁
    xSemaphoreGive(xSerialMutex);
  } else {
    // 获取锁失败即进行错误提醒
    Serial.print("** 错误：二进制数据互斥锁冲突 **");
    Happen_Error();
  }

}

// 调试函数
bool DEV_Pass(const char* function) {
  if (strcmp(function, "GPS_Initialize") == 0 && DEBUG_MODE) {
    Transmit_Text("** OK - GPS init Completed! **");
    return true;
  } else if (strcmp(function, "GPS_Transmit") == 0 && DEBUG_MODE) {
    return true;
  }
  return false;
}

// 告警提醒函数
void Happen_Error() {
  for(int i = 0; i < 3; i++) {
    digitalWrite(BUZZ, HIGH);
    delay(50);
    digitalWrite(BUZZ, LOW);
    delay(50);
  }
  Initialization_Status = false;
}

// 就绪提醒
void ready_reminder() {
  digitalWrite(BUZZ, HIGH);
  delay(100);
  digitalWrite(BUZZ, LOW);
}

// 初始化就绪检查
void Initialize_Check() {
  if (DEBUG_MODE) Transmit_Text("** 注意：处于开发者模式 **");
  delay(2000);
  if (Initialization_Status) {
    ready_reminder();
  } else {
    Transmit_Text("** Fail - Initialization Fail! **");
    digitalWrite(BUZZ, HIGH);
    delay(2000);
    digitalWrite(BUZZ, LOW);
    esp_restart();
  }
}

// 摄像头初始化
void Setup_Camera() {
  delay(2000);

  // 配置摄像头信息
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0       = Y2_GPIO_NUM;
  config.pin_d1       = Y3_GPIO_NUM;
  config.pin_d2       = Y4_GPIO_NUM;
  config.pin_d3       = Y5_GPIO_NUM;
  config.pin_d4       = Y6_GPIO_NUM;
  config.pin_d5       = Y7_GPIO_NUM;
  config.pin_d6       = Y8_GPIO_NUM;
  config.pin_d7       = Y9_GPIO_NUM;
  config.pin_xclk     = XCLK_GPIO_NUM;
  config.pin_pclk     = PCLK_GPIO_NUM;
  config.pin_vsync    = VSYNC_GPIO_NUM;
  config.pin_href     = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn     = PWDN_GPIO_NUM;
  config.pin_reset    = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  
  config.frame_size   = FRAMESIZE_VGA;
  config.jpeg_quality = 5;
  config.fb_count     = 1;
  config.grab_mode    = CAMERA_GRAB_LATEST;

  if (esp_camera_init(&config) != ESP_OK) {
    Transmit_Text("** Fail - Camera init Failed! **");
    Happen_Error();
  }
}

// 拍摄多次进行摄像头校准(自动曝光/白平衡稳定)
void Camera_Calibrate() {
  delay(2000);
  Transmit_Text("** Wait - Calibrating camera... **");
  for(int i = 0; i < CAM_CALIBRATE; i++) {
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) {
        Transmit_Text("** Fail - Calibrate Failed! **");
        Happen_Error();
        return;
    }
    delay(200);
    esp_camera_fb_return(fb);
  }
  Transmit_Text("** OK - Camera Calibrate Success! **");
}

// GPS 初始化
void Initialize_GPS_Module(unsigned long timeout_ms = 200000) {
  delay(2000);
  Transmit_Text("** Wait - GPS Initializing... **");
  unsigned long start = millis();

  if (DEV_Pass("GPS_Initialize")) return;

  while (millis() - start < timeout_ms) {
    while (GPS_Serial.available()) {
      gps.encode(GPS_Serial.read());
    }

    if (gps.location.isValid()) {
      Transmit_Text("** OK - GPS init Completed! **");

      // 构建一个初始遥测帧并发送
      Build_Telemetry_Frame();
      Transmit_Text("** %s **", gpsMessage);

      return;
    }
    delay(2000);
  }

  Transmit_Text("** Fail - GPS init Failed! **");
  Initialization_Status = false;
}

// 配置看门狗
void Watch_Doge() {

  // 反初始化，确保后续状态干净
  esp_task_wdt_deinit();
  
  esp_task_wdt_config_t twdt_config = {
    // 看门狗超时时间
    .timeout_ms = 30000,
    // 配置空闲核心的看门狗行为
    .idle_core_mask = (1 << 1),
    // 超时时触发恐慌并重启
    .trigger_panic = true
  };

  // 初始化看门狗
  esp_task_wdt_init(&twdt_config);
}

// 构建类 UKHAS 格式的遥测数据帧
// $$CALLSIGN,Frame_Counter,Time,Latitude,Longitude,Altitude,Speed,Sats,Heading,Temprature,Voltage(有待实现)
uint16_t Frame_Counter = 0;
void Build_Telemetry_Frame() {

  // 获取当前片上温度
  float ChipTemp = (temprature_sens_read() - 32) / 1.8;

  // 先拼装标准格式的时间
  snprintf(gps_time, sizeof(gps_time),
    "%04d-%02d-%02dT%02d:%02d:%02dZ",
    gps.date.year(),
    gps.date.month(),
    gps.date.day(),
    gps.time.hour(),
    gps.time.minute(),
    gps.time.second()
  );

  // 再拼装遥测字符串
  snprintf(gpsMessage, sizeof(gpsMessage),
    "$$%s,%d,%s,%.6f,%.6f,%.2f,%.2f,%d,%.2f,%.2f",
    SSDV_CALLSIGN,              // 呼号
    Frame_Counter,              // 帧数
    gps_time,                   // 时间
    gps.location.lat(),         // 纬度
    gps.location.lng(),         // 经度
    gps.altitude.meters(),      // 高度
    gps.speed.kmph(),           // 速度
    gps.satellites.value(),     // 卫星数
    gps.course.deg(),           // 航向角
    ChipTemp                    // 摄氏度
  );

  Frame_Counter += 1;
}

// 启动 GPS 遥测发送任务
void Create_GPS_Task() {
  xTaskCreatePinnedToCore(
    V_Transmit_GPS_Task,      // 任务函数
    "GPS_Telemetry",          // 任务名称
    4096,                     // 堆栈大小
    NULL,                     // 传递参数
    configMAX_PRIORITIES - 2, // 中优先级
    &gpsTaskHandle,           // 任务句柄
    1                         // 运行核心
  );
}

// GPS 遥测发送任务
void V_Transmit_GPS_Task(void *pvParameters) {

  // 如果处于开发状态就删除任务
  if (DEV_Pass("GPS_Transmit")) {
    vTaskDelete(NULL);
    return;
  }

  // 设定每 20 秒执行一次  
  TickType_t xLastWakeTime = xTaskGetTickCount();
  const TickType_t xFrequency = pdMS_TO_TICKS(20000);

  // 将当前任务加入 WDT 监控（注册看门狗）
  esp_task_wdt_add(NULL); 

  for (;;) {
    // 喂狗
    esp_task_wdt_reset();

    // 喂数据
    while (GPS_Serial.available()) {
      gps.encode(GPS_Serial.read());
    }

    // 如果有更新就发送
    if (gps.location.isUpdated()) {

      // 构建遥测帧并发送
      Build_Telemetry_Frame();
      Transmit_Text("** %s **", gpsMessage);

      // 每 20 秒发送一次
      vTaskDelayUntil(&xLastWakeTime, xFrequency);

    } else {
      // 过 1 秒重新检查再发送
      vTaskDelay(pdMS_TO_TICKS(1000));
    }
  }
}

// 启动中继任务
void Create_Relay_Task() {
    xTaskCreatePinnedToCore(
    V_Relay_Task,             // 任务函数
    "RelayTask",              // 任务名称
    4096,                     // 堆栈大小
    NULL,                     // 传递参数
    configMAX_PRIORITIES - 3, // 低优先级
    &relayTaskHandle,         // 任务句柄
    1                         // 运行核心
  );
}

// 中继任务
// 地面站 TX : ##ToCall,FmCall,Grid,INFO\n
// 气球站 TX ：** ##RELAY,ToCall,FmCall,Grid,INFO **
int Relay_Count = 0;  // 发送频率限制，避免破坏性攻击
void V_Relay_Task(void *pvParameters) {

  // 将当前任务加入 WDT 监控（注册看门狗）
  esp_task_wdt_add(NULL);

  // 避免编译器警告
  (void) pvParameters;

  // 初始化中继接收缓存
  static char currentRelayBuffer[256] = {0};
  static int bufferContentLength = 0;

  for (;;) {
    // 读取所有接收到的数据
    while (Serial.available()) {
      char c = (char)Serial.read();

      // 当帧超长或程序处于SSDV发送状态时忽略并丢弃所有接收到的帧
      if ((bufferContentLength >= 255 || SSDV_State)) {
        if (c == '\n') {
          bufferContentLength = 0;
          currentRelayBuffer[0] = '\0';
        }
        continue;
      }

      // 允许所有可打印字符(ASCII)以及多字节字符进入缓存
      if (c >= 32 || c == '\n' || c == '\r') {
        currentRelayBuffer[bufferContentLength++] = c;
        currentRelayBuffer[bufferContentLength] = '\0';
      }
    }

    char* newlinePos;
    // 处理所有完整帧（以 \n 结尾）
    while ((newlinePos = strchr(currentRelayBuffer, '\n')) != NULL) {

      // 从缓存提取完整的一帧
      char line[256];
      size_t lineLength = newlinePos - currentRelayBuffer;
      if (lineLength >= 256) lineLength = 255;
      snprintf(line, sizeof(line), "%.*s", (int)lineLength, currentRelayBuffer);

      // 移除处理过的部分
      size_t remainingLength = strlen(newlinePos + 1);
      memmove(currentRelayBuffer, newlinePos + 1, remainingLength + 1);
      bufferContentLength = remainingLength;

      // 去除行首行尾空格
      char* start = line;
      while (*start == ' ') start++;
      char* end = start + strlen(start) - 1;
      while (end > start && (*end == ' ' || *end == '\r' || *end == '\n')) {
        *end = '\0';
        end--;
      }

      // 构造新的数据帧并发送，要求原帧以 ## 开头，并且计数器不得超过80，以避免破坏性攻击
      if (strlen(start) <= 256 && strncmp(start, "##", 2) == 0 && Relay_Count <= 80) {
        const char* content = start + 2;
        vTaskDelay(pdMS_TO_TICKS(25));
        Transmit_Text("** ##RELAY,%s **", content);
        Relay_Count += 1;
      }
    }

    // 如果 currentRelayBuffer 太长了，说明后面没有换行也超限了，强制清空
    if (bufferContentLength > 255) {
      bufferContentLength = 0;
      currentRelayBuffer[0] = '\0';
    }
        
    // 每 200 毫秒运行一次
    vTaskDelay(pdMS_TO_TICKS(200));
    
    // 喂狗
    esp_task_wdt_reset();
  }
}

// 启动 SSDV 发送任务
void Create_SSDV_Task() {
    xTaskCreatePinnedToCore(
    V_SSDV_Task,              // 任务函数
    "SSDVTask",               // 任务名称
    4096,                     // 堆栈大小
    NULL,                     // 传递参数
    configMAX_PRIORITIES - 1, // 高优先级
    &ssdvTaskHandle,          // 任务句柄
    1                         // 运行核心
  );
}

// SSDV任务
void V_SSDV_Task(void *pvParameters) {

  // 将当前任务加入 WDT 监控（注册看门狗）
  esp_task_wdt_add(NULL);
  
  for (;;) {
    
    camera_fb_t *fb = NULL;

    // 拍摄图片并执行检查，丢弃旧帧
    for (int i = 0; i < 2; i++) {
      fb = esp_camera_fb_get();
      if (!fb) break;
      esp_camera_fb_return(fb);
    }

    // 正式进行拍摄
    fb = esp_camera_fb_get();
    if (!fb || !fb->buf || fb->len == 0) {
      Transmit_Text("** Fail - Camera capture Failed! **");
      if (fb) esp_camera_fb_return(fb);
      Happen_Error();
    }

    // 对拍摄的图像进行SSDV编码
    Process_SSDV_Packet(fb);

    // 释放摄像头帧缓冲区
    esp_camera_fb_return(fb);
    fb = NULL;

    // 降频节电
    setCpuFrequencyMhz(80);

    // 每 60 秒发送一帧 SSDV
    for (int i = 0; i < 12; i++) {
      esp_task_wdt_reset(); // 喂狗
      vTaskDelay(pdMS_TO_TICKS(5000));
    }

    // 恢复高速运行频率
    setCpuFrequencyMhz(240);
  }
}
// 读取图像数据
int Read_IMG_Buffer(uint8_t *buffer, int numBytes, camera_fb_t *fb, int fbIndex) {

  int bufSize = 0;
  // 检查是否到达图像缓冲区的末尾
  if((fbIndex + numBytes ) < fb->len){
  
    bufSize = numBytes;
  }
  else{

    bufSize = fb->len - fbIndex;
  }
  memcpy(buffer,&fb->buf[fbIndex],bufSize);
  return bufSize;
}

// 调制 SSDV 数据包
void Process_SSDV_Packet(camera_fb_t *fb) {

  // 定义函数逻辑所用变量
  int index = 0, c = 0, PacketCount = 0;
  // 更新编码状态
  SSDV_State = true;

  // 图像编号
  Transmit_Text("** SSDV Encoding: image %u **", imageID);

  // 初始化 SSDV 配置结构，无 FEC 模式，质量等级 2，每帧长 256 字节
  ssdv_enc_init(&ssdv, SSDV_TYPE_NOFEC, SSDV_CALLSIGN, imageID++, 2, 256);

  // 设置 SSDV 的输出数据包缓冲区
  ssdv_enc_set_buffer(&ssdv, ssdv_out_buff);

  // 大循环结构
  while (true) {

    // 当状态为 SSDV_FEED_ME 时投喂数据
    while ((c = ssdv_enc_get_packet(&ssdv)) == SSDV_FEED_ME) {
      int bytes_read_from_image = Read_IMG_Buffer(ssdv_feed_buff, SSDV_IMG_BUFF_SIZE, fb, index);
      if (bytes_read_from_image > 0) {
        index += bytes_read_from_image;
        ssdv_enc_feed(&ssdv, ssdv_feed_buff, bytes_read_from_image); 
      }
    }

    // 图像编码完成
    if (c == SSDV_EOI) {
      Transmit_Text("** OK - SSDV End. **");
      break;
    }
    // 出错处理
    else if (c != SSDV_OK) {
      Transmit_Text("** Fail - SSDV Error **");
      break;
    }

    // 喂狗
    esp_task_wdt_reset();

    // 发送数据包
    Transmit_Data(ssdv_out_buff, 256);

    PacketCount++;
  }
  // 清零中继计数
  Relay_Count = 0;
  SSDV_State = false;
}

// 上电初始化
void setup() {

  /* --- 阶段 1: 基础硬件和服务初始化 --- */
  delay(5000);                                 // 等待五秒，保证上电稳定
  pinMode(BUZZ, OUTPUT);                       // 配置告警 IO
  digitalWrite(BUZZ, LOW);                     // 初始化为低电平
  Serial.begin(9600);                          // 设置主串口波特率
  xSerialMutex = xSemaphoreCreateMutex();      // 创建主串口互斥锁
  GPS_Serial.begin(9600, SERIAL_8N1, 15, -1);  // 设置 GPS 串口
  WiFi.mode(WIFI_OFF);                         // 关闭 Wi-Fi
  btStop();                                    // 关闭 蓝牙
  Transmit_Text("** Wait - Booting... **");    // 自检指示1

  /* --- 阶段 2: 核心模块初始化 --- */
  Setup_Camera();                              // 摄像头初始化
  Camera_Calibrate();                          // 摄像头校准
  Initialize_GPS_Module();                     // GPS 校准

  /* --- 阶段 3: 初始化检查 --- */
  Initialize_Check();                          // 初始化就绪检查
  delay(2000);                                 // 等待两秒，保证工作稳定

  /* --- 阶段 4: 初始化系统级服务 --- */
  Watch_Doge();                                // 启动看门狗

  /* --- 阶段 5: 创建所有应用任务 --- */
  Transmit_Text("** OK - Init Done! **");      // 自检指示2
  Create_SSDV_Task();                          // 创建 SSDV 传输任务
  Create_GPS_Task();                           // 创建 GPS 传输任务
  Create_Relay_Task();                         // 创建中继任务
}

// 主循环函数
void loop() {
  vTaskDelete(NULL);
}
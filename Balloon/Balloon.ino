// 宏定义
#define SSDV_CALLSIGN "BG7ZDQ"          // 呼号
#define SSDV_IMG_BUFF_SIZE 128          // 喂给SSDV编码器的缓冲区大小
#define SSDV_OUT_BUFF_SIZE 256          // 用于存放编码后SSDV数据包的缓冲区
#define SSDV_SIZE_NOFEC 256             // 标准SSDV包大小 (无FEC)
#define CAM_CALIBRATE 10                // 摄像头校准次数
#define DEV_STATE false                  // 开发状态

// 头文件
#include "Arduino.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "esp_camera.h"
#include "TinyGPS++.h"
#include "Balloon.h"
#include "ssdv.h"

// GPS 相关全局变量
HardwareSerial GPS_Serial(2);
char gpsMessage[256];
char gps_time[21];
char tempStr[40];
TinyGPSPlus gps;

// SSDV 相关全局变量
ssdv_t ssdv;                                 // SSDV编码器状态结构体
uint8_t imageID = 0;                         // 图像计数器
bool SSDV_State = false;                       // SSDV 状态
uint8_t ssdv_feed_buff[SSDV_IMG_BUFF_SIZE];  // 从摄像头读取数据到此缓冲区，再喂给SSDV
uint8_t ssdv_out_buff[SSDV_OUT_BUFF_SIZE];   // SSDV编码器生成的包会存放在这里

// FreeRTOS 相关全局变量
TaskHandle_t xRelayTaskHandle = NULL;
QueueHandle_t xRelayQueue = NULL;

// 初始化状态
bool Initialization_Status = true;

// 调试函数
bool DEV_Pass(const char* function) {
  if (strcmp(function, "GPS_Initialize") == 0 && DEV_STATE) {
    Serial.println("** OK - GPS init Completed! **");
    delay(25);
    return true;
  } else if (strcmp(function, "GPS_Transmit") == 0 && DEV_STATE) {
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
  delay(2000);
  if(Initialization_Status) {
    ready_reminder();
  } else {
    Serial.printf("** Fail - Initialization Fail! **");
    digitalWrite(BUZZ, HIGH);
    delay(2000);
    digitalWrite(BUZZ, LOW);
    esp_restart();
  }
}

// 摄像头初始化
void Setup_Camera() {
  delay(2000);
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
    Serial.printf("** Fail - Camera init Failed! **");
    Happen_Error();
  }
}

// 拍摄多次进行摄像头校准(自动曝光/白平衡稳定)
void Camera_Calibrate() {
  delay(2000);
  Serial.printf("** Wait - Calibrating camera... **");
  for(int i = 0; i < CAM_CALIBRATE; i++) {
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) {
        Serial.printf("** Fail - Calibrate Failed! **");
        Happen_Error();
        return;
    }
    delay(200);
    esp_camera_fb_return(fb);
  }
  Serial.printf("** OK - Camera Calibrate Success! **");
}

// GPS 初始化
void Initialize_GPS_Module(unsigned long timeout_ms = 200000) {
  delay(2000);
  Serial.println("** Wait - GPS Initializing! **");
  unsigned long start = millis();

  if (DEV_Pass("GPS_Initialize")) return;

  while (millis() - start < timeout_ms) {
    while (GPS_Serial.available()) {
      gps.encode(GPS_Serial.read());
    }

    if (gps.location.isValid()) {
      Serial.println("** OK - GPS init Completed! **");
      // 构建遥测帧
      Build_Telemetry_Frame();

      delay(25);
      Serial.printf("** %s **\n", gpsMessage);
      delay(25);
      return;
    }
    delay(2000);
  }

  Serial.println("** Fail - GPS init Failed! **");
  Initialization_Status = false;
}

// 构建类 UKHAS 格式的遥测数据帧
// $$CALLSIGN,Frame_Counter,HH:MM:SS,latitude,longitude,altitude,other,fields
uint16_t Frame_Counter = 0;
void Build_Telemetry_Frame() {
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
    "$$%s,%d,%s,%.6f,%.6f,%.2f,%.2f,%d,%.2f",
    SSDV_CALLSIGN,              // 呼号
    Frame_Counter,              // 帧数
    gps_time,                   // 时间
    gps.location.lat(),         // 纬度
    gps.location.lng(),         // 经度
    gps.altitude.meters(),      // 高度
    gps.speed.kmph(),           // 速度
    gps.satellites.value(),     // 卫星数
    gps.course.deg()            // 航向角
  );

  Frame_Counter += 1;

  delay(25);
  Serial.printf(gpsMessage);
  delay(25);
}

// 启动 GPS 发送任务
void Create_GPS_Task() {
  xTaskCreate(
    V_Transmit_GPS_Task,   // 任务函数
    "GPS_TX",              // 任务名
    4096,                  // 堆栈大小（字大但稳妥）
    NULL,                  // 参数
    1,                     // 优先级
    NULL                   // 任务句柄
  );
}

// GPS 发送任务
void V_Transmit_GPS_Task(void* pvParameters) {

  // 如果处于开发状态就删除任务
  if (DEV_Pass("GPS_Transmit")) {
    vTaskDelete(NULL);
    return;
  }

  for (;;) {
    // 喂数据
    while (GPS_Serial.available()) {
      gps.encode(GPS_Serial.read());
    }

    // 如果有更新就发送
    if (gps.location.isUpdated()) {

      // 构建遥测帧
      Build_Telemetry_Frame();

      delay(25);
      Serial.printf("** %s **\n", gpsMessage);
      delay(25);

      // 每 20 秒发送一次
      vTaskDelay(pdMS_TO_TICKS(20000));
    } else {
      // 过 100 毫秒重新检查再发送
      vTaskDelay(pdMS_TO_TICKS(100));
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
    configMAX_PRIORITIES - 1, // 高优先级
    &xRelayTaskHandle,        // 任务句柄
    0                         // 运行核心
  );
}

// 中继任务
// 地面站 TX : ##ToCall,FmCall,INFO\n
// 气球站 TX ：** ##RELAY,ToCall,FmCall,INFO **
int Relay_Count = 0;  // 发送频率限制，避免破坏性攻击
void V_Relay_Task(void *pvParameters) {
  // 避免编译器警告
  (void) pvParameters;

  // 初始化中继接收缓存
  String currentRelayBuffer = "";

  for (;;) {
    // 读取所有接收到的数据
    while (Serial.available()) {
      char c = (char)Serial.read();
      // 当帧超长或程序处于SSDV发送状态时忽略并丢弃所有接收到的帧
      if (currentRelayBuffer.length() >= 256 || SSDV_State) {
        if (c == '\n') { 
          currentRelayBuffer = "";
        }
        continue;
      }
      currentRelayBuffer += c;
    }

    int newlineIndex;
    // 处理所有完整帧（以 \n 结尾）
    while ((newlineIndex = currentRelayBuffer.indexOf('\n')) != -1) {
      String line = currentRelayBuffer.substring(0, newlineIndex);
      currentRelayBuffer = currentRelayBuffer.substring(newlineIndex + 1);

      line.trim();

      // 构造新的数据帧并发送，要求原帧以 ## 开头，并且计数器不得超过40，以避免破坏性攻击
      if (line.length() <= 256 && line.startsWith("##") && Relay_Count <= 40) {
        String content = line.substring(2);
        delay(25);
        Serial.printf("** ##RELAY,%s **", content.c_str());
        delay(25);
        Relay_Count += 1;
      }
    }

    // 如果 currentRelayBuffer 太长了，说明后面没有换行也超限了，强制清空
    if (currentRelayBuffer.length() > 256) {
      currentRelayBuffer = "";
    }
        
    // 降低任务优先级，让其他任务也有机会运行
    vTaskDelay(pdMS_TO_TICKS(100)); // 暂停100毫秒，避免饿死其他任务
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
  Serial.printf("** SSDV Encoding: image %u **\n", imageID);

  // 初始化 SSDV 配置结构，无 FEC 模式，质量等级 2，每帧长 256 字节
  ssdv_enc_init(&ssdv, SSDV_TYPE_NOFEC, SSDV_CALLSIGN, imageID++, 2, 256);

  // 设置 SSDV 的输出数据包缓冲区
  ssdv_enc_set_buffer(&ssdv, ssdv_out_buff);

  // 大循环结构
  while (true) {

    // 当状态为 SSDV_FEED_ME 时投喂数据
    while ((c = ssdv_enc_get_packet(&ssdv)) == SSDV_FEED_ME) {
      index += Read_IMG_Buffer(ssdv_feed_buff, SSDV_IMG_BUFF_SIZE, fb, index);
      ssdv_enc_feed(&ssdv, ssdv_feed_buff, SSDV_IMG_BUFF_SIZE);
    }

    // 图像编码完成
    if (c == SSDV_EOI) {
      Serial.println("** OK - SSDV End. **");
      break;
    }
    // 出错处理
    else if (c != SSDV_OK) {
      Serial.printf("** Fail - SSDV Error: Code %d **\n", c);
      break;
    }

    // 发送数据包
    delay(25);
    Serial.write(ssdv_out_buff, 256);
    delay(25);

    PacketCount++;
  }
  // 清零中继计数
  Relay_Count = 0;
  SSDV_State = false;
}

// 上电初始化
void setup() {
  delay(5000);                                 // 等待五秒，保证上电稳定
  pinMode(BUZZ, OUTPUT);                       // 配置告警IO
  digitalWrite(BUZZ, LOW);                     // 初始化为低电平
  Serial.begin(9600);                          // 设置主串口波特率
  GPS_Serial.begin(9600, SERIAL_8N1, 15, -1);  // 设置 GPS 串口
  Serial.printf("** Wait - Booting... **");    // 自检指示1
  Setup_Camera();                              // 摄像头初始化
  Camera_Calibrate();                          // 摄像头校准
  Initialize_GPS_Module();                     // GPS 校准
  Create_GPS_Task();                           // 创建 GPS 传输任务
  Create_Relay_Task();                         // 创建中继任务
  Initialize_Check();                          // 初始化就绪检查
  Serial.printf("** OK - Init Done! **");      // 自检指示2
  delay(1000);                                 // 等待两秒，保证工作稳定
}

// 主入口函数
void loop() {

  // 拍摄图片并执行检查
  camera_fb_t *fb = NULL;

  // 丢弃旧帧
  for (int i = 0; i < 3; i++) {
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) break;
    esp_camera_fb_return(fb);
  }

  // 拍摄
  fb = esp_camera_fb_get();
  if (!fb || !fb->buf || fb->len == 0) {
    Serial.printf("** Fail - Camera capture Failed! **");
    if (fb) esp_camera_fb_return(fb);
    Happen_Error();
    return;
  }

  // 对拍摄的图像进行SSDV编码
  Process_SSDV_Packet(fb);

  // 释放摄像头帧缓冲区
  esp_camera_fb_return(fb);

  // 发送 GPS 信息
  vTaskDelay(pdMS_TO_TICKS(60000));
}
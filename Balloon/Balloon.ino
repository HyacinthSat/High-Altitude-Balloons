#include "HardwareSerial.h"
#include "esp_camera.h"
#include "Balloon.h"
#include "NMEAGPS.h"
#include "GPSfix.h"
#include "ssdv.h"

// 预定义
#define SSDV_CALLSIGN "BG7ZDQ"          // 呼号
#define SSDV_IMG_BUFF_SIZE 128          // 喂给SSDV编码器的缓冲区大小
#define SSDV_OUT_BUFF_SIZE 256          // 用于存放编码后SSDV数据包的缓冲区
#define SSDV_SIZE_NOFEC 256             // 标准SSDV包大小 (无FEC)
#define CAM_CALIBRATE 10                // 摄像头校准次数

// GPS
HardwareSerial GPS_Serial(2);
char gpsMessage[256];
char tempStr[40];
NMEAGPS gps;
gps_fix fix;

// 初始化状态
bool initialization_status = true;

// SSDV 相关全局变量
ssdv_t ssdv;                                 // SSDV编码器状态结构体
uint8_t imageID = 0;                         // 图像计数器
uint8_t ssdv_feed_buff[SSDV_IMG_BUFF_SIZE];  // 从摄像头读取数据到此缓冲区，再喂给SSDV
uint8_t ssdv_out_buff[SSDV_OUT_BUFF_SIZE];   // SSDV编码器生成的包会存放在这里

// 告警提醒
void happen_error() {
  for(int i = 0; i < 20; i++) {
    digitalWrite(ALERTS, LOW);
    delay(200);
    digitalWrite(ALERTS, HIGH);
    delay(200);
  }
  initialization_status = false;
}

// 就绪提醒
void ready_reminder() {
  for(int i = 0; i < 2; i++) {
    digitalWrite(ALERTS, LOW);
    delay(100);
    digitalWrite(ALERTS, HIGH);
    delay(50);
  }
}

// 初始化就绪检查
void initialize_check() {
  delay(2000);
  if(initialization_status) {
    ready_reminder();
  } else {
    Serial.printf("** Fail - Initialization Fail! **");
    happen_error();
    digitalWrite(ALERTS, LOW);
    esp_restart();
  }
}

// 摄像头初始化
void setup_camera() {
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
  config.jpeg_quality = 8;
  config.fb_count     = 1;
  config.grab_mode    = CAMERA_GRAB_LATEST;

  if (esp_camera_init(&config) != ESP_OK) {
    Serial.printf("** Fail - Camera init Failed! **");
    happen_error();
  }
}

// 拍摄多次进行摄像头校准(自动曝光/白平衡稳定)
void camera_calibrate() {
  delay(2000);
  Serial.printf("** Wait - Calibrating camera... **");
  for(int i = 0; i < CAM_CALIBRATE; i++) {
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) {
        Serial.printf("** Fail - Calibrate Failed! **");
        happen_error();
        return;
    }
    delay(200);
    esp_camera_fb_return(fb);
  }
  Serial.printf("** OK - Camera Calibrate Success! **");
}

// 构建类 PITS 格式的数据帧
void buildPITSMessage(const gps_fix &fix) {
  snprintf(gpsMessage, sizeof(gpsMessage),
    "$$%.6f,%.6f,%.1f,%.1f,%d,%.2f",
    fix.latitude(),    // 纬度
    fix.longitude(),   // 经度
    fix.altitude(),    // 高度（米）
    fix.speed_kph(),   // 速度（km/h）
    fix.satellites,    // 可见卫星数
    fix.heading()      // 航向角
  );
  Serial.println(gpsMessage);
}

// GPS 初始化
void gps_init(unsigned long timeout_ms = 180000) {
  delay(2000);
  Serial.println("** Wait - GPS Initializing! **");
  unsigned long start = millis();

  //Serial.println("** OK - GPS init Completed! **");
  //return;
  
  while (millis() - start < timeout_ms) {
    if (gps.available(GPS_Serial)) {
      fix = gps.read();

      if (fix.valid.location) {
        Serial.println("** OK - GPS init Completed! **");
        return;
      }
    }
    delay(100); // 可选：减少 CPU 占用
  }

  Serial.println("** Fail - GPS init Failed! **");
  initialization_status = false;
}

// 发送有效 GPS 数据
void tx_gps_info(unsigned long timeout_ms = 15000) {
  unsigned long start = millis();

  //return;

  while (millis() - start < timeout_ms) {
    if (gps.available(GPS_Serial)) {
      fix = gps.read();

      if (fix.valid.location && fix.valid.altitude && fix.valid.satellites) {
        buildPITSMessage(fix); // 注意传入 fix
        Serial.printf("** %s **\n", gpsMessage);
        delay(2000);
        return;
      }
    }
  }

  Serial.println("** Fail - GPS failure! **");
}


// 读取图像数据
int read_camera_buffer_for_ssdv(uint8_t *buffer, int numBytes, camera_fb_t *fb, int fbIndex) {

  int bufSize = 0;
  // have we reached past end of imagebuffer
  if((fbIndex + numBytes ) < fb->len){
  
    bufSize = numBytes;
  }
  else{

    bufSize = fb->len - fbIndex;
  }
  memcpy(buffer,&fb->buf[fbIndex],bufSize);
  return bufSize;
}

// 处理并编码 SSDV
void process_ssdv(camera_fb_t *fb){

  // 定义函数逻辑所用变量
  int index = 0, c = 0, ssdvPacketCount = 0;

  // 图像编号
  Serial.printf("** SSDV Encoding: image %u **", imageID);

  // 初始化 SSDV 配置结构，无 FEC 模式，质量等级 4，每帧长 256 字节
  ssdv_enc_init(&ssdv, SSDV_TYPE_NOFEC, SSDV_CALLSIGN, imageID++, 2, 256);
  // 设置 SSDV 的输出数据包缓冲区
  ssdv_enc_set_buffer(&ssdv, ssdv_out_buff);

  // 大循环结构
  while(true){
    
    // 当状态为 SSDV_FEED_ME 时投喂数据
    while((c = ssdv_enc_get_packet(&ssdv)) == SSDV_FEED_ME)
    {
        // 从图像缓冲区读取数据包中的字节数
        index += read_camera_buffer_for_ssdv(ssdv_feed_buff, SSDV_IMG_BUFF_SIZE, fb, index);
        // 投喂
        ssdv_enc_feed(&ssdv, ssdv_feed_buff, SSDV_IMG_BUFF_SIZE);
    }
    
    // 当状态为 SSDV_EOI 时，图像编码完成。
    if(c == SSDV_EOI)
    {
        Serial.printf("** OK - SSDV End. **");
        break;
    }
    // 当状态不为 SSDV OK 时证明发生错误
    else if(c != SSDV_OK)
    {
        Serial.printf("** Fail - SSDV Error: Code %d **", c);
        break;
    }

    // 发送数据
    delay(100);
    Serial.write(ssdv_out_buff, 256);
    delay(100);
  }
}

// 上电初始化
void setup() {
  delay(5000);
  pinMode(ALERTS, OUTPUT);                     // 配置告警IO
  digitalWrite(ALERTS, HIGH);                  // 初始化为高电平
  Serial.begin(9600);                          // 设置主串口波特率
  GPS_Serial.begin(9600, SERIAL_8N1, 15, -1);  // 设置 GPS 串口
  Serial.printf("** Wait - Booting... **");    // 自检指示1
  setup_camera();                              // 摄像头初始化
  camera_calibrate();                          // 摄像头校准
  gps_init();                                  // GPS 校准
  initialize_check();                          // 初始化就绪检查
  Serial.printf("** OK - Init Done! **");      // 自检指示2
}

// 主入口函数
void loop() {

  // delay(30000);
  tx_gps_info();

  // 拍摄图片并执行检查
  camera_fb_t *fb = NULL;
  fb = esp_camera_fb_get();
  if (!fb || !fb->buf || fb->len == 0) {
    Serial.printf("** Fail - Camera capture Failed! **");
    if (fb) esp_camera_fb_return(fb);
    happen_error();
    return;
  }

  // 对拍摄的图像进行SSDV编码
  process_ssdv(fb);

  // 释放摄像头帧缓冲区
  esp_camera_fb_return(fb);

  tx_gps_info();
}
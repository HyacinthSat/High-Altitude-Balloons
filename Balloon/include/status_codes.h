/*
 * Communication Protocol for ESP32 High-Altitude Balloon (HAB) Tracker
 *
 * This file defines the complete communication protocol for the ESP32 HAB Tracker payload.
 * It standardizes all status notifications, command responses, and error conditions
 * into a unified status code system, replacing the previous fragile, string-based parsing
 * method. This ensures reliable, robust, and easily parsable data exchange between
 * the firmware and the ground station.
 *
 * Author: BG7ZDQ
 * Date: 2025/06/21
 * Version: 1.1.0
 * LICENSE: GNU General Public License v3.0
 */

#ifndef STATUS_CODES_H
#define STATUS_CODES_H

// 主状态码定义
typedef enum {
    // --- 系统级状态码 (0x10xx) ---
    SYS_BOOTING              = 0x1000, // 系统正在启动
    SYS_INIT_OK              = 0x1001, // 系统初始化完成
    SYS_INIT_FAIL            = 0x1002, // 系统初始化失败
    SYS_RESTARTING           = 0x1003, // 系统将受控重启
    SYS_DEV_MODE_ENABLED     = 0x1004, // 处于开发者模式
    RELAY_RATE_LIMITED       = 0x1005, // 中继功能已限流

    // --- 摄像头模块状态码 (0x20xx) ---
    CAM_INIT_START           = 0x2000, // 相机初始化开始
    CAM_INIT_OK              = 0x2001, // 相机初始化成功
    CAM_INIT_FAIL            = 0x2002, // 相机初始化失败
    CAM_CALIBRATE_START      = 0x2003, // 相机开始校准
    CAM_CALIBRATE_OK         = 0x2004, // 相机校准成功
    CAM_CALIBRATE_FAIL       = 0x2005, // 相机校准失败
    CAM_CAPTURE_FAIL         = 0x2006, // 图像拍摄失败
    CAM_RECONFIG_OK          = 0x2007, // 相机配置成功
    CAM_RECONFIG_FAIL        = 0x2008, // 相机配置失败
    CAM_RESTORE_DEFAULT_OK   = 0x2009, // 相机参数重置
    CAM_RESTORE_DEFAULT_FAIL = 0x200A, // 相机重置失败
    
    // --- GPS 模块状态码 (0x30xx) ---
    GPS_INIT_START           = 0x3000, // GPS 初始化开始
    GPS_INIT_OK              = 0x3001, // GPS 初始化成功
    GPS_INIT_FAIL            = 0x3002, // GPS 初始化超时

    // --- SSDV 模块状态码 (0x40xx) ---
    SSDV_ENCODE_START        = 0x4000, // 图像编码开始
    SSDV_ENCODE_END          = 0x4001, // 图像发送完毕
    SSDV_ENCODE_ERROR        = 0x4002, // 图像编码错误
    SSDV_TX_BUFFER_FULL      = 0x4003, // 图像缓冲区满

    // --- 指令应答状态码 (ACK/NACK) (0x50xx, 0x51xx) ---
    // 通用否定应答 (NACK)
    CMD_NACK_FORMAT_ERROR    = 0x5001, // 指令格式错误
    CMD_NACK_NO_VALUE        = 0x5002, // 指令缺少参数
    CMD_NACK_INVALID_TYPE    = 0x5003, // 指令类型无效
    CMD_NACK_INVALID_GET     = 0x5004, // 查询目标无效
    CMD_NACK_INVALID_CTL     = 0x5005, // 控制目标无效
    CMD_NACK_INVALID_SET     = 0x5006, // 设置目标无效
    CMD_NACK_SSDV_BUSY       = 0x5007, // 图传任务正忙
    CMD_NACK_SET_CAM_QUAL    = 0x5008, // 图像质量无效
    CMD_NACK_SET_CAM_QUAL_LOW= 0x5009, // 图像质量过高
    CMD_NACK_SET_SSDV_QUAL   = 0x500A, // 编码质量无效
    CMD_NACK_SET_SSDV_CYCLE  = 0x500B, // 图传周期无效
    
    // 控制 (CTL) 命令应答 (ACK)
    CMD_ACK_RELAY_ON         = 0x500C, // 中继功能已开启
    CMD_ACK_RELAY_OFF        = 0x500D, // 中继功能已关闭
    CMD_ACK_SSDV_ON          = 0x500E, // 图传功能已开启
    CMD_ACK_SSDV_OFF         = 0x500F, // 图传功能已关闭

    // 设置 (SET) 命令应答 (ACK)
    CMD_ACK_SSDV_TYPE        = 0x5010, // 图传模式已设置
    CMD_ACK_SSDV_QUALITY     = 0x5011, // 图传质量已设置
    CMD_ACK_SSDV_CYCLE       = 0x5012, // 图传周期已设置
    CMD_ACK_CAM_SIZE         = 0x5013, // 图像尺寸已设置
    CMD_ACK_CAM_QUALITY      = 0x5014, // 图像质量已设置

    // 查询 (GET) 命令应答 (ACK)
    CMD_ACK_GET_RELAY_STATUS    = 0x5100, // 中继状态
    CMD_ACK_GET_SSDV_STATUS     = 0x5101, // 图传状态
    CMD_ACK_GET_SSDV_TYPE       = 0x5102, // 图传模式
    CMD_ACK_GET_SSDV_QUALITY    = 0x5103, // 图传质量
    CMD_ACK_GET_SSDV_CYCLE      = 0x5104, // 图传周期
    CMD_ACK_GET_CAM_SIZE        = 0x5105, // 图像尺寸
    CMD_ACK_GET_CAM_QUALITY     = 0x5106, // 图像质量

    // --- 传感器模块状态码 (0x60xx) ---
    ADC_SAMPLE_FAIL          = 0x6000, // ADC电压采样连续失败。Payload: esp_err_t

} StatusCode_t;

#endif // STATUS_CODES_H
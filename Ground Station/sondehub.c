/*

SondeHub Telemetry Uploader for HAB Ground Station.

This program is a command-line utility designed for High-Altitude Balloon (HAB) ground stations.
It leverages the WinHTTP (Windows HTTP Services) API to construct and send real-time telemetry data,formatted as JSON, to the SondeHub amateur telemetry platform.
It serves as a crucial component for relaying balloon flight data (including GPS position, altitude, heading, and satellite count)
from the ground station to the SondeHub centralized database for tracking and visualization.

Compilation command: "gcc -Wall -Wextra -O2 sondehub.c -o sondehub.exe -lwinhttp"

Author: BG7ZDQ
Date: 2025/06/22
Version: 0.0.2
LICENSE: GNU General Public License v3.0

*/

#include <windows.h>
#include <winhttp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int send_https_json(const wchar_t *host, const wchar_t *path, const char *json_data);

int main(int argc, char *argv[]) {
    if (argc < 17) {
        printf("用法: ./sondehub <上传者呼号> <接收时间> <气球呼号> <球上时间> <气球经度> <气球纬度> <气球高度> <气球航向> <气球速度> <卫星数量> <球上温度> <球上电压> <地面站经度> <地面站纬度> <地面站高度> <开发状态>\n");
        printf("注意: <开发状态> 可选值: 'dev' / 其他字符\n");
        return 1;
    }

    const char *uploader_callsign = argv[1];
    const char *time_received     = argv[2];
    const char *payload_callsign  = argv[3];
    const char *datetime          = argv[4];
    const char *lon               = argv[5];
    const char *lat               = argv[6];
    const char *alt               = argv[7];
    const char *heading           = argv[8];
    const char *vel_hv            = argv[9];
    const char *sats              = argv[10];
    const char *temp              = argv[11];
    const char *batt              = argv[12];
    const char *uplon             = argv[13];
    const char *uplat             = argv[14];
    const char *upalt             = argv[15];
    const char *dev_status        = argv[16];

    // 根据开发状态，准备 dev 字段
    char dev_field_str[64] = "";
    if (strcmp(dev_status, "dev") == 0) {
        snprintf(dev_field_str, sizeof(dev_field_str), "\"dev\":\"%s\",", uploader_callsign);
        printf("[INFO] Development mode enabled.\n");
    }

    // 构造 Telemetry JSON 数据
    char telemetry_json[2048];
    int telemetry_json_len = snprintf(telemetry_json, sizeof(telemetry_json),
        "[{%s"
        "\"software_name\":\"BG7ZDQ_HAB_GS\","
        "\"software_version\":\"0.1.0\","
        "\"uploader_callsign\":\"%s\","
        "\"time_received\":\"%s\","
        "\"payload_callsign\":\"%s\","
        "\"datetime\":\"%s\","
        "\"lat\":%s,"
        "\"lon\":%s,"
        "\"alt\":%s,"
        "\"frequency\":435.4,"
        "\"temp\":%s,"
        "\"vel_h\":%s,"
        "\"vel_v\":%s,"
        "\"heading\":%s,"
        "\"batt\":%s,"
        "\"sats\":%s,"
        "\"uploader_position\":[%s,%s,%s]"
        "}]",
        dev_field_str, uploader_callsign, time_received, payload_callsign, datetime, lat, lon, alt, temp, vel_hv, vel_hv, heading, batt, sats, uplat, uplon, upalt
    );
    // 检查 Telemetry JSON 合法性
    if (telemetry_json_len < 0 || telemetry_json_len >= (int)sizeof(telemetry_json)) {
        fprintf(stderr, "[DEBUG] Telemetry data error.\n");
        return 1;
    }
    // 发送 Telemetry JSON 数据到 SondeHub
    printf("[DEBUG] Telemetry JSON: %s\n", telemetry_json);
    send_https_json(L"api.v2.sondehub.org", L"/amateur/telemetry", telemetry_json);


    // 构造 Listener JSON 数据
    char listener_json[2048];
    int listener_json_len = snprintf(listener_json, sizeof(listener_json),
    "{"
    "\"software_name\":\"BG7ZDQ_HAB_GS\","
    "\"software_version\":\"0.1.0\","
    "\"uploader_callsign\":\"%s\","
    "\"uploader_position\":[%s,%s,%s],"
    "\"uploader_radio\":\"BG7ZDQ_CDTU_Ver_1.0.1\","
    "\"mobile\":false"
    "}",
    uploader_callsign, uplat, uplon, upalt
    );

    // 检查 Listener JSON 合法性
    if (listener_json_len < 0 || listener_json_len >= (int)sizeof(listener_json)) {
        fprintf(stderr, "[DEBUG] Listener JSON data error.\n");
        return 1;
    }

    // 发送 Listener JSON 数据到 SondeHub
    printf("[DEBUG] Listener JSON: %s\n", listener_json);
    send_https_json(L"api.v2.sondehub.org", L"/amateur/listeners", listener_json);
}


int send_https_json(const wchar_t *host, const wchar_t *path, const char *json_data) {
    int status_code = -1;
    DWORD dwSize = 0, dwDownloaded = 0;
    HINTERNET hSession = NULL, hConnect = NULL, hRequest = NULL;
    BOOL bResults = FALSE;

    // 创建 session
    hSession = WinHttpOpen(L"BG7ZDQ_HAB_GS", WINHTTP_ACCESS_TYPE_DEFAULT_PROXY, WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
    if (!hSession) goto cleanup;

    // 连接主机
    hConnect = WinHttpConnect(hSession, host, INTERNET_DEFAULT_HTTPS_PORT, 0);
    if (!hConnect) goto cleanup;

    // 创建请求
    hRequest = WinHttpOpenRequest(hConnect, L"PUT", path, NULL, WINHTTP_NO_REFERER, WINHTTP_DEFAULT_ACCEPT_TYPES, WINHTTP_FLAG_SECURE);
    if (!hRequest) goto cleanup;

    // 设置请求头
    WinHttpAddRequestHeaders(hRequest, L"Content-Type: application/json", (ULONG)-1L, WINHTTP_ADDREQ_FLAG_REPLACE | WINHTTP_ADDREQ_FLAG_ADD);
    WinHttpAddRequestHeaders(hRequest, L"Accept: text/plain", (ULONG)-1L, WINHTTP_ADDREQ_FLAG_REPLACE | WINHTTP_ADDREQ_FLAG_ADD);

    // 发送请求，写入 JSON 数据
    int json_len = strlen(json_data);
    bResults = WinHttpSendRequest(hRequest, WINHTTP_NO_ADDITIONAL_HEADERS, 0, (LPVOID)json_data, json_len, json_len, 0);
    if (!bResults) goto cleanup;

    // 接收响应
    bResults = WinHttpReceiveResponse(hRequest, NULL);
    if (!bResults) goto cleanup;

    // 获取 HTTP 状态码
    DWORD dwStatusCode = 0;
    DWORD dwSizeOut = sizeof(dwStatusCode);
    WinHttpQueryHeaders(hRequest, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER, NULL, &dwStatusCode, &dwSizeOut, NULL);
    status_code = (int)dwStatusCode;

    // 读取响应
    WinHttpQueryDataAvailable(hRequest, &dwSize);
    if (dwSize > 0) {
        char *buffer = malloc(dwSize + 1);
        if (buffer) {
            ZeroMemory(buffer, dwSize + 1);
            if (WinHttpReadData(hRequest, buffer, dwSize, &dwDownloaded)) {
                printf("[DEBUG] Server response: %s\n", buffer);
            }
            free(buffer);
        }
    }

cleanup:
    if (hRequest) WinHttpCloseHandle(hRequest);
    if (hConnect) WinHttpCloseHandle(hConnect);
    if (hSession) WinHttpCloseHandle(hSession);

    return status_code;
}
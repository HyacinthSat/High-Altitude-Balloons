/*

SondeHub Telemetry Uploader for HAB Ground Station.

This program is a command-line utility designed for High-Altitude Balloon (HAB) ground stations.
It leverages the WinHTTP (Windows HTTP Services) API to construct and send real-time telemetry data,formatted as JSON, to the SondeHub amateur telemetry platform.
It serves as a crucial component for relaying balloon flight data (including GPS position, altitude, heading, and satellite count)
from the ground station to the SondeHub centralized database for tracking and visualization.

Author: BG7ZDQ
Date: 2025/05/25
Version: 0.0.1
LICENSE: GNU General Public License v3.0

*/

#include <windows.h>
#include <winhttp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#pragma comment(lib, "winhttp.lib")

int main(int argc, char *argv[]) {
    if (argc < 12) {
        printf("用法: %s <上传者呼号> <接收时间> <球上时间> <经度> <纬度> <高度> <航向角> <GPS卫星数> <地面站经度> <地面站纬度> <地面站高度>\n", argv[0]);
        return 1;
    }

    const char *uploader_callsign = argv[1];
    const char *time_received     = argv[2];
    const char *datetime          = argv[3];
    const char *lon               = argv[4];
    const char *lat               = argv[5];
    const char *alt               = argv[6];
    const char *heading           = argv[7];
    const char *sats              = argv[8];
    const char *uplon             = argv[9];
    const char *uplat             = argv[10];
    const char *upalt             = argv[11];

    // 构造 JSON 数据
    char json_data[2048];
    int json_len = snprintf(json_data, sizeof(json_data),
        "[{"
        "\"software_name\":\"BG7ZDQ_HAB_GS\","
        "\"software_version\":\"0.0.1\","
        "\"uploader_callsign\":\"%s\","
        "\"time_received\":\"%s\","
        "\"payload_callsign\":\"BG7ZDQ-11\","
        "\"datetime\":\"%s\","
        "\"lat\":%s,"
        "\"lon\":%s,"
        "\"alt\":%s,"
        "\"frequency\":435.4,"
        "\"heading\":%s,"
        "\"sats\":%s,"
        "\"uploader_position\":[%s,%s,%s]"
        "}]",
        uploader_callsign,
        time_received,
        datetime,
        lat, lon, alt,
        heading,
        sats,
        uplat, uplon, upalt
    );

    if (json_len < 0 || json_len >= sizeof(json_data)) {
        fprintf(stderr, "JSON 数据构造失败或超出缓冲区大小。\n");
        return 1;
    }

    printf("[DEBUG] JSON 内容如下：%s\n", json_data);

    // WinHTTP 相关变量
    HINTERNET hSession = NULL;
    HINTERNET hConnect = NULL;
    HINTERNET hRequest = NULL;
    DWORD dwSize = 0;
    DWORD dwDownloaded = 0;
    LPSTR pszOutBuffer;
    BOOL bResults = FALSE;

    // 初始化 WinHTTP 会话
    hSession = WinHttpOpen(L"BG7ZDQ_HAB_GS", WINHTTP_ACCESS_TYPE_DEFAULT_PROXY, WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);

    if (!hSession) {
        fprintf(stderr, "WinHttpOpen 失败 (%d)\n", GetLastError());
        return 1;
    }

    // 连接到服务器
    hConnect = WinHttpConnect(hSession, L"api.v2.sondehub.org", INTERNET_DEFAULT_HTTPS_PORT, 0);

    if (!hConnect) {
        fprintf(stderr, "WinHttpConnect 失败 (%d)\n", GetLastError());
        WinHttpCloseHandle(hSession);
        return 1;
    }

    // 打开 HTTP 请求
     // WINHTTP_FLAG_SECURE 用于 HTTPS
    hRequest = WinHttpOpenRequest(hConnect, L"PUT", L"/amateur/telemetry", NULL, WINHTTP_NO_REFERER, WINHTTP_DEFAULT_ACCEPT_TYPES, WINHTTP_FLAG_SECURE);

    if (!hRequest) {
        fprintf(stderr, "WinHttpOpenRequest 失败 (%d)\n", GetLastError());
        WinHttpCloseHandle(hConnect);
        WinHttpCloseHandle(hSession);
        return 1;
    }

    // 设置请求头
    bResults = WinHttpAddRequestHeaders(hRequest, L"Content-Type: application/json", (ULONG)-1L, WINHTTP_ADDREQ_FLAG_REPLACE | WINHTTP_ADDREQ_FLAG_ADD);
    if (!bResults) {
        fprintf(stderr, "WinHttpAddRequestHeaders (Content-Type) 失败 (%d)\n", GetLastError());
        WinHttpCloseHandle(hRequest);
        WinHttpCloseHandle(hConnect);
        WinHttpCloseHandle(hSession);
        return 1;
    }

    // Accept
    bResults = WinHttpAddRequestHeaders(hRequest, L"Accept: text/plain", (ULONG)-1L, WINHTTP_ADDREQ_FLAG_REPLACE | WINHTTP_ADDREQ_FLAG_ADD);
     if (!bResults) {
        fprintf(stderr, "WinHttpAddRequestHeaders (Accept) 失败 (%d)\n", GetLastError());
        // 不影响主流程，但可以打印警告
    }


    // 发送请求头和数据
    bResults = WinHttpSendRequest(hRequest, WINHTTP_NO_ADDITIONAL_HEADERS, 0, WINHTTP_NO_REQUEST_DATA, 0, json_len, 0);

    if (!bResults) {
        fprintf(stderr, "WinHttpSendRequest 失败 (%d)\n", GetLastError());
        WinHttpCloseHandle(hRequest);
        WinHttpCloseHandle(hConnect);
        WinHttpCloseHandle(hSession);
        return 1;
    }

    // 发送 JSON 数据体
    bResults = WinHttpWriteData(hRequest, json_data, json_len, &dwSize); // dwSize 是实际写入的字节数
    if (!bResults) {
        fprintf(stderr, "WinHttpWriteData 失败 (%d)\n", GetLastError());
        WinHttpCloseHandle(hRequest);
        WinHttpCloseHandle(hConnect);
        WinHttpCloseHandle(hSession);
        return 1;
    }

    // 接收响应
    bResults = WinHttpReceiveResponse(hRequest, NULL);

    if (!bResults) {
        fprintf(stderr, "WinHttpReceiveResponse 失败 (%d)\n", GetLastError());
        WinHttpCloseHandle(hRequest);
        WinHttpCloseHandle(hConnect);
        WinHttpCloseHandle(hSession);
        return 1;
    } else {
        // 读取响应头和状态码
        DWORD dwStatusCode = 0;
        DWORD dwHeaderSize = sizeof(dwStatusCode);
        WinHttpQueryHeaders(hRequest, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER, NULL, &dwStatusCode, &dwSize, NULL);

        printf("HTTP 状态码: %d\n", dwStatusCode);

        if (dwStatusCode >= 200 && dwStatusCode < 300) {
            printf("上传成功！\n");
        } else {
            fprintf(stderr, "上传失败，HTTP 状态码: %d\n", dwStatusCode);
        }

        // 读取响应体
        // 先查询响应体大小
        dwSize = 0;
        WinHttpQueryDataAvailable(hRequest, &dwSize);

        if (dwSize > 0) {
            pszOutBuffer = (LPSTR)malloc(dwSize + 1);
            if (pszOutBuffer == NULL) {
                fprintf(stderr, "内存分配失败\n");
            } else {
                ZeroMemory(pszOutBuffer, dwSize + 1);
                bResults = WinHttpReadData(hRequest, (LPVOID)pszOutBuffer,
                                           dwSize, &dwDownloaded);

                if (bResults) {
                    printf("[DEBUG] 服务器响应: %s\n", pszOutBuffer);
                } else {
                    fprintf(stderr, "WinHttpReadData 失败 (%d)\n", GetLastError());
                }
                free(pszOutBuffer);
            }
        } else {
            printf("[DEBUG] 服务器没有返回响应体。\n");
        }
    }

    // 关闭句柄
    if (hRequest) WinHttpCloseHandle(hRequest);
    if (hConnect) WinHttpCloseHandle(hConnect);
    if (hSession) WinHttpCloseHandle(hSession);

    return 0;
}
# High-Altitude-Balloons  

~~高空气球，穷人的太空计划~~  
本仓库托管了风信子卫星项目下的一个气球计划的代码与电路设计。  
该项目的主要目标为高空图像采集与回传，围绕此目标开发了一系列软硬件。  
在该项目硬件可行的基础上，额外的增加了业余无线电数字中继等能力。  

数据面板：[hab.satellites.ac.cn](https://hab.satellites.ac.cn/)  

## 展示  

- 地面站程序  
  ![image](https://github.com/user-attachments/assets/690048eb-9224-47ac-8bea-609d323d8b61)  

- 气球电路  
  ![探空气球_PCB（四层板）_仿真图_(顶层)](https://github.com/user-attachments/assets/c3ea96c7-403c-4b36-9f1f-12b1fdd12834)
  ![探空气球_PCB（四层板）_仿真图_(底层)](https://github.com/user-attachments/assets/6acdd4b7-e43d-4971-bfe2-80f71afad268)

- CDUT（可配置数传单元）  
  ![CDUT可配置数传单元装配图](https://github.com/user-attachments/assets/1a91a0ee-ca8a-46ff-9ebf-571ef91527bc)  

## 目录  

1.  **[Ground Station | 地面站](https://github.com/HyacinthSat/High-Altitude-Balloons/tree/main/Ground%20Station)**  
    * `GUI.py`: 基于 PyQt6 的地面站图形化主程序。 它负责连接接收机串口，实时解析遥测、图像(SSDV)和中继通信数据，具备调用外部程序解码图像、上传遥测至 SondeHub、控制天线旋转器以及通过气球进行业余无线电数字通联（QSO）等功能。  
    * `sondehub.c`: 使用 WinHTTP API 向 SondeHub 社区上传遥测数据的命令行工具源代码，用于生成`sondehub.exe`。  
    * `ssdv.exe`: 用于解码气球回传的 SSDV 协议图像的预编译程序，编译自[fsphil ssdv](https://github.com/fsphil/ssdv/)。  
    * `/web/`: 地面站 GUI 内嵌的地图和仪表板网页文件。
        * `map.html` & `map.js`: 内嵌于GUI的百度地图页面，用于显示气球和地面站的实时位置与轨迹。
        * `coordtransform.js`: 用于在 WGS-84、GCJ-02 和百度地图（BD-09）坐标系之间进行转换的库。
        * `index.html`: 项目主数据面板，通过`iframe`整合了 SondeHub 实时追踪、飞行预测和 Grafana 遥测仪表盘。

2.  **[CDUT | 可配置数传单元](https://github.com/HyacinthSat/High-Altitude-Balloons/tree/main/CDUT)**
    * `main.py`: 运行在 MicroPython 开发板上的核心程序，用于将板子转换为一个智能可配置的数传单元（CDUT）。 它能智能解析 AT 指令，通过硬件控制 HC-12 数传模块的参数。

3.  **[Balloon | 气球端](https://github.com/HyacinthSat/High-Altitude-Balloons/tree/main/Balloon)**
    * `/Balloon.ino`: 气球板载控制器的代码。这是载荷的核心逻辑程序，负责初始化板载硬件、采集并传输图像、处理 GPS 与遥测数据的采集、打包和业余无线电数字中继功能。
    * `/Balloon.h`: 气球载荷主控的头文件，定义了外设的硬件引脚。
    * `/ssdv.c` & `/ssdv.h` & `/rs8.c` & `/rs8.h`: 用于将图像编码为 SSDV 数据包的依赖项，来自[fsphil ssdv](https://github.com/fsphil/ssdv/)

## 注意事项  

地面站程序使用了百度地图api，您可以直接使用 [https://hab.satellites.ac.cn/map](https://hab.satellites.ac.cn/map) ，或者将 `Ground Station/web` 目录下的内容托管到自己的服务器。  

## 许可证  

本仓库在 MIT 许可证下发布。  
这意味着：  

* 任何人均可自由使用、复制、修改本仓库中的内容，包括个人和商业用途。  
* 允许以原始或修改后的形式分发本仓库的内容，但须附带原许可证声明，确保后续用户了解其授权条款。  
* 本仓库内容按“现状（as-is）”提供，不附带任何明示或暗示的担保，使用者需自行承担风险。  
* 仓库贡献者无需对使用本内容造成的任何损失或问题负责。  
* 其余未说明但未尽的事项。 更多信息请参见：[LICENSE](https://github.com/HyacinthSat/High-Altitude-Balloons/LICENSE)  

**注意**：该许可证条款仅应用于本项目组所著之内容（除特有说明外），在其之外的诸如网站主题、代码、图片等内容均遵循源许可证或版权要求。  

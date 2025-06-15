# High-Altitude-Balloons  

~~高空气球，穷人的太空计划~~  
本仓库托管了风信子卫星项目下的一个高空气球项目  

该项目的主要目标为高空图像采集与回传，并围绕此目标开发了一系列的软件与硬件解决方案  
借助实现主要目的基本硬件，额外实现了业余无线电数字中继等功能  

主要作者：[BG7ZDQ](https://github.com/X-MQSI)  
![气球标识](https://github.com/user-attachments/assets/7b3a9489-7394-43fc-9d44-142d86b2f106)  

飞行数据仪表板: [hab.satellites.ac.cn](https://hab.satellites.ac.cn/)  

## ✨ 项目功能  

- **实时遥测与追踪**：通过地面站实时接收、解析并展示气球的 GPS 位置、高度、速度、航向等关键遥测数据  
- **图像拍摄与回传**：支持将机载摄像头拍摄的图像通过 SSDV 协议进行编码和下传，并在地面站实时解码显示  
- **业余无线电通信**：集成数字中继功能，允许业余无线电爱好者通过气球作为数字中继进行远距离的通信实验  
- **Web 数据仪表板**：提供一个集成的 Web 仪表板，整合了 SondeHub 实时追踪、飞行轨迹预测和 Grafana 遥测数据可视化图表  

## 📸 系统展示  

- **🎈 气球载荷**  
![Balloon_PCB_仿真](https://github.com/user-attachments/assets/ba6ab02a-0ec4-4297-9382-652cf812d755)  

- **⚙️ 可配置数传单元**  
![CDUT_装配](https://github.com/user-attachments/assets/670276f7-631c-4c8d-99bc-0450763e11d5)

- **📡 地面站程序**  
![Ground_Station](https://github.com/user-attachments/assets/c483e5b9-bf6e-4d8e-be6a-f7b921d360d1)

## 🛠️ 系统架构  
整个项目由三个主要部分组成：  

1. **🎈 [Balloon | 气球载荷](./Balloon)**  
气球飞行的核心控制器，负责所有机载任务。

- `/Balloon.h`: 定义了外设（如摄像头、传感器）的硬件引脚  
- `/Balloon.ino`: 主控程序。负责初始化板载硬件、采集传感器数据、构建遥测帧、捕获图像并使用 SSDV 协议编码，同时处理数字中继功能  
- `/ssdv.c` & `/ssdv.h`: SSDV 图像编码库。实现了将 JPEG 图像转换为一系列可无线传输的数据包的逻辑，来自 [fsphil ssdv](https://github.com/fsphil/ssdv/)  
- `/rs8.c` & `/rs8.h`: Reed-Solomon 前向错误校验库，为 SSDV 数据包提供容错能力，来自 [fsphil ssdv](https://github.com/fsphil/ssdv/)  
- `/Balloon_PCB_Ver1.0.1.epro`: 气球的电路设计，使用立创 EDA 绘制  

2. **⚙️ [CDUT | 可配置数传单元](./CDUT)**  
基于 RP2040-Zero 的智能数传模块控制器。  

- `/main.py`: 运行在 RP2040-Zero 上的核心程序。它将普通的 HC-12 数传模块升级为一个智能可配置的数传单元，实现了：  
  - 简易功能配置：免去了对硬件进行直接操作，智能识别解析配置指令，动态调整模块的参数  
  - 自适应波特率：存储了模块的配置参数，解决了串口通信的波特率管理问题    
  - 自动模式切换：通过硬件引脚控制模块在数据模式和命令模式间无缝切换  
  - 透明数据桥接：在默认模式下作为完全透明的数据传输桥  

- `CDUT_PCB_Ver_0.0.1.epro`: CDUT 的电路设计，使用立创 EDA 绘制  

3. **📡 [Ground Station | 地面站](./Ground%20Station)**  
功能强大的图形化地面站软件，是数据接收、状态监控和任务执行的控制中心。  

- `/GUI.py`: 基于 PyQt6 的地面站图形化主程序。 它负责：  
  - 连接、管理和控制测控用收发信机 CDUT  
  - 连接、管理和控制追踪气球的旋转器  
  - 气球的控制与状态监测  
  - 解析遥测、SSDV 图像数据和中继通信数据  
  - 上传数据至 SondeHub 进行多站点协作  
  - 基于遥测数据绘制实时轨迹  
  - 提供数字中继的客户端  

- `/sondehub.*`: 命令行工具，用于将遥测数据上传至 SondeHub  

- `/ssdv.exe`: 用于解码气球回传的 SSDV 协议图像的预编译程序，编译自 [fsphil ssdv](https://github.com/fsphil/ssdv/)。  

- `/web/`: 地面站 GUI 内嵌的地图和仪表板网页文件  
        * `map.html` & `map.js`: 内嵌于GUI的百度地图页面，用于显示气球和地面站的实时位置与轨迹  
        * `coordtransform.js`: 用于在不同地理坐标系之间转换的库，确保地图定位准确  
        * `index.html`: 项目主数据面板，简单整合了 SondeHub 实时追踪、飞行预测和 Grafana 遥测仪表盘  

## 🚀 使用说明  

1. **Ground Station | 地面站**  
- 运行环境:  
  - Python 3.11.0 及 相关依赖库：  
  (`pip install PyQt6 PyQt6-WebEngine pyserial numpy`)  

## 🔔 注意事项  

地面站程序使用了百度地图api，您可以直接使用 [https://hab.satellites.ac.cn/map](https://hab.satellites.ac.cn/map) ，或者将 `Ground Station/web` 目录下的内容托管到自己的服务器。  

## ‍⚖️ 开源许可  

本仓库在 MIT 许可证下发布。  
这意味着：  

- 任何人均可自由使用、复制、修改本仓库中的内容，包括个人和商业用途。  
- 允许以原始或修改后的形式分发本仓库的内容，但须附带原许可证声明，确保后续用户了解其授权条款。  
- 本仓库内容按“现状（as-is）”提供，不附带任何明示或暗示的担保，使用者需自行承担风险。  
- 仓库贡献者无需对使用本内容造成的任何损失或问题负责。  
- 其余未说明但未尽的事项。 更多信息请参见：[LICENSE](./LICENSE)  

**注意**：该许可证条款仅应用于本项目组所著之内容（除特有说明外），在其之外的代码、图片等任何内容均遵循源许可证或版权要求。  

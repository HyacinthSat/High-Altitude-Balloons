# 导入 PlatformIO 的环境构建工具
Import("env")

# 定义在上传固件前要执行的函数
def before_upload(source, target, env):
    print("--- 自动构建并上传 SPIFFS 文件系统镜像 ---")
    
    # 执行 "buildfs" 命令来构建文件系统镜像
    env.Execute("pio run -t buildfs")
    
    # 执行 "uploadfs" 命令来上传文件系统镜像
    env.Execute("pio run -t uploadfs")
    
    print("--- 文件系统处理完成 ---")


# 注册这个函数，使其在 "upload" 动作之前被调用
env.AddPreAction("upload", before_upload)
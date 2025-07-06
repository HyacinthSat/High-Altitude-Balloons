import re
from datetime import datetime
from xml.etree.ElementTree import Element, SubElement, ElementTree

input_file = "log.txt"
output_kml = "output.kml"

# 用正则解析遥测内容
pattern = re.compile(
    r"\$\$(?P<callsign>[^,]+),"
    r"(?P<counter>\d+),"
    r"(?P<time>[\d\-T:Z]+),"
    r"(?P<lat>[-\d.]+),"
    r"(?P<lon>[-\d.]+),"
    r"(?P<alt>[-\d.]+),"
    r"(?P<speed>[-\d.]+),"
    r"(?P<sats>\d+),"
    r"(?P<heading>[-\d.]+),"
    r"(?P<temp>[-\d.]+),"
    r"(?P<voltage>[-\d.]+),"
    r"(?P<validity>[AV])"
)

data_points = []

seen_positions = set()

with open(input_file, "r", encoding="utf-8") as f:
    for line in f:
        match = pattern.search(line)
        if match and match.group("validity") == "A":
            timestamp_str = match.group("time")
            try:
                timestamp = datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                continue

            lat = float(match.group("lat"))
            lon = float(match.group("lon"))
            alt = float(match.group("alt"))

            pos_key = (round(lat, 6), round(lon, 6), round(alt, 1))
            if pos_key in seen_positions:
                continue  # 跳过重复
            seen_positions.add(pos_key)

            data_points.append((timestamp, lat, lon, alt))

# 按时间排序
data_points.sort()

# 起点、终点、最高点
if not data_points:
    raise ValueError("未找到有效数据点")

start_point = data_points[0]
end_point = data_points[-1]
max_point = max(data_points, key=lambda x: x[3])  # 以高度为标准

# 创建 KML 结构
kml = Element("kml", xmlns="http://www.opengis.net/kml/2.2")
doc = SubElement(kml, "Document")
SubElement(doc, "name").text = "Balloon Flight Track"

# 添加轨迹
placemark = SubElement(doc, "Placemark")
SubElement(placemark, "name").text = "Flight Path"
line = SubElement(placemark, "LineString")
SubElement(line, "tessellate").text = "1"
coords = SubElement(line, "coordinates")
coords.text = "\n".join(f"{lon},{lat},{alt}" for _, lat, lon, alt in data_points)

# 打标函数
def add_point_marker(doc, name, lat, lon, alt):
    pm = SubElement(doc, "Placemark")
    SubElement(pm, "name").text = name
    point = SubElement(pm, "Point")
    SubElement(point, "coordinates").text = f"{lon},{lat},{alt}"

add_point_marker(doc, "🔹 起点", start_point[1], start_point[2], start_point[3])
add_point_marker(doc, "🔺 最高点", max_point[1], max_point[2], max_point[3])
add_point_marker(doc, "🔻 终点", end_point[1], end_point[2], end_point[3])

# 保存 KML 文件
ElementTree(kml).write(output_kml, encoding="utf-8", xml_declaration=True)

print(f"已保存 KML 文件：{output_kml}")
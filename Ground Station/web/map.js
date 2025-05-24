let map = new BMap.Map("map"); // 初始化地图实例
let pointList = []; // 存储所有转换后的百度坐标点
let currentPolyline = null; // 当前轨迹线的引用
let currentMarker = null; // 当前最新点标记的引用

// 地图图标，调整锚点使其底部中心对准坐标
let icon = new BMap.Icon("favicon.ico", new BMap.Size(64, 64), {
    anchor: new BMap.Size(32, 56)
});

// 设置地图中心点和缩放级别，启用滚轮缩放
map.centerAndZoom(new BMap.Point(109.8, 19.17), 15);
map.enableScrollWheelZoom();

/**
 * 更新地图上的位置和轨迹
 * @param {number} lat 纬度 (WGS84)
 * @param {number} lng 经度 (WGS84)
 */

function updatePosition(lat, lng) {
  if (typeof lat !== "number" || typeof lng !== "number" || isNaN(lat) || isNaN(lng)) {
    console.error("坐标非法:", lat, lng);
    return;
  }

  // 手动坐标转换：WGS-84 → GCJ-02 → BD-09
  const gcj = coordtransform.wgs84togcj02(lng, lat); // 注意参数顺序是 (lng, lat)
  const bd09 = coordtransform.gcj02tobd09(gcj[0], gcj[1]);

  const bd09Point = new BMap.Point(bd09[0], bd09[1]);
  pointList.push(bd09Point);

  // 移除旧的轨迹线和标记
  if (currentPolyline) map.removeOverlay(currentPolyline);
  if (currentMarker) map.removeOverlay(currentMarker);

  // 轨迹线
  if (pointList.length > 1) {
    const polyline = new BMap.Polyline(pointList, {
      strokeColor: "blue",
      strokeWeight: 4,
      strokeOpacity: 0.8
    });
    map.addOverlay(polyline);
    currentPolyline = polyline;
  }

  // 标记点
  const marker = new BMap.Marker(bd09Point, { icon: icon });
  map.addOverlay(marker);
  currentMarker = marker;

  // 平移视野
  map.panTo(bd09Point);
}

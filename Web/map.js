let map = new BMap.Map("map"); // 初始化地图实例
let pointList = [];            // 存储所有转换后的百度坐标点
let currentPolyline = null;    // 当前轨迹线的引用
let currentMarker = null;      // 当前最新点标记的引用
let groundMarker = null;       // 地面站标记引用

// 地面站图标
let GroundIcon = new BMap.Icon("ground.ico", new BMap.Size(32, 32), {
  anchor: new BMap.Size(16, 32)
});

// 地图图标
let BalloonIcon = new BMap.Icon("favicon.ico", new BMap.Size(64, 64), {
  anchor: new BMap.Size(32, 56)
});


// 设置地图中心点和缩放级别
map.centerAndZoom(new BMap.Point(110.33, 20.06), 14);
map.enableScrollWheelZoom();

/**
 * 更新地图上的气球位置、轨迹线及地面站位置
 * @param {number=} GroundLat 地面站纬度 (WGS84)
 * @param {number} BalloonLat 气球纬度 (WGS84)
 * @param {number} BalloonLng 气球经度 (WGS84)
 * @param {number=} GroundLng 地面站经度 (WGS84)
 */

// 更新地图上的气球位置、轨迹线及地面站位置
function updatePosition(BalloonLat, BalloonLng, GroundLat, GroundLng) {
  // 地面站标记
  if (typeof GroundLat !== "number" || typeof GroundLng !== "number" || isNaN(GroundLat) || isNaN(GroundLng)) {
    console.error("地面站坐标非法:", GroundLat, GroundLng);
    return;
  }

  // 坐标系转换：WGS-84 → GCJ-02 → BD-09
  const gcjGround = coordtransform.wgs84togcj02(GroundLng, GroundLat);
  const bd09Ground = coordtransform.gcj02tobd09(gcjGround[0], gcjGround[1]);
  const groundPoint = new BMap.Point(bd09Ground[0], bd09Ground[1]);

  // 移除旧的地面站标记
  if (groundMarker) map.removeOverlay(groundMarker);

  groundMarker = new BMap.Marker(groundPoint, { icon: GroundIcon });
  map.addOverlay(groundMarker);

  // 气球标记
  if (typeof BalloonLat !== "number" || typeof BalloonLng !== "number" || isNaN(BalloonLat) || isNaN(BalloonLng)) {
    console.error("气球坐标非法:", BalloonLat, BalloonLng);
    return;
  }

  // 坐标系转换：WGS-84 → GCJ-02 → BD-09
  const gcj = coordtransform.wgs84togcj02(BalloonLng, BalloonLat);
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

  const marker = new BMap.Marker(bd09Point, { icon: BalloonIcon });
  map.addOverlay(marker);
  currentMarker = marker;
  
  // 调整视野以适应新的地面站标记
  //map.setViewport([bd09Point]);
  map.setViewport([bd09Point, groundPoint]);
}
"""GIS、遥感岗位及相关专业关键词词典。"""

# 用于招聘平台检索和岗位相关性判断。
JOB_KEYWORDS = [
    "GIS", "地理信息", "遥感", "测绘", "摄影测量", "地图学",
    "国土空间规划", "自然资源调查", "卫星应用", "空间分析",
    "WebGIS", "三维GIS",
]

# 用于从职位描述中提取技能标签，长词优先可减少别名误匹配。
SKILL_KEYWORDS = [
    "ArcGIS", "QGIS", "ENVI", "SNAP", "IDL", "GDAL", "Rasterio",
    "Fiona", "Shapely", "GeoPandas", "PostGIS", "PostgreSQL",
    "Google Earth Engine", "GEE", "Cesium", "Leaflet", "OpenLayers",
    "Three.js", "WebGL", "InSAR", "LiDAR", "点云", "深度学习",
    "PyTorch", "TensorFlow", "机器学习", "随机森林", "Python", "C++",
    "Java", "JavaScript", "R", "MATLAB", "Linux", "Shell",
]

# 技能按技术体系分类，便于前端分组展示。
SKILL_CATEGORIES: dict[str, list[str]] = {
    "开发工程": [
        "Python", "Java", "C++", "JavaScript", "R", "SQL", "Linux", "Shell",
        "Cesium", "Leaflet", "OpenLayers", "Three.js", "WebGL",
    ],
    "GIS专业工具": [
        "ArcGIS", "QGIS", "ENVI", "SNAP", "IDL", "GDAL", "Rasterio",
        "Fiona", "Shapely", "GeoPandas", "PostGIS", "PostgreSQL",
        "Google Earth Engine", "GEE",
    ],
    "算法与AI": [
        "深度学习", "PyTorch", "TensorFlow", "机器学习", "随机森林", "MATLAB",
    ],
    "遥感与测绘": [
        "InSAR", "LiDAR", "点云",
    ],
}

# 用于事业单位专业限制识别与归类。
MAJOR_KEYWORDS = [
    "地图学与地理信息系统", "摄影测量与遥感", "测绘工程", "地理信息科学",
    "遥感科学与技术", "空间信息与数字技术", "地理空间信息工程",
    "土地资源管理", "生态学", "环境科学", "地质学", "大气科学", "海洋科学",
]


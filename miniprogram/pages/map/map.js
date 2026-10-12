const app = getApp()

// 主要城市经纬度
const cityCoords = {
  '北京': [116.40, 39.90],
  '上海': [121.47, 31.23],
  '广州': [113.26, 23.13],
  '深圳': [114.05, 22.55],
  '杭州': [120.15, 30.28],
  '南京': [118.78, 32.04],
  '武汉': [114.31, 30.52],
  '成都': [104.07, 30.57],
  '西安': [108.94, 34.34],
  '重庆': [106.55, 29.56],
  '天津': [117.20, 39.13],
  '苏州': [120.58, 31.30],
  '长沙': [112.98, 28.19],
  '郑州': [113.62, 34.75],
  '青岛': [120.38, 36.07],
  '济南': [117.00, 36.65],
  '沈阳': [123.43, 41.80],
  '大连': [121.62, 38.91],
  '厦门': [118.10, 24.46],
  '福州': [119.30, 26.08],
  '合肥': [117.27, 31.86],
  '昆明': [102.83, 24.88],
  '南昌': [115.86, 28.68],
  '哈尔滨': [126.53, 45.80],
  '长春': [125.32, 43.89],
  '石家庄': [114.48, 38.03],
  '太原': [112.55, 37.87],
  '贵阳': [106.63, 26.65],
  '南宁': [108.37, 22.82],
  '兰州': [103.83, 36.06],
  '乌鲁木齐': [87.62, 43.82],
}

Page({
  data: {
    topCities: [],
    markers: [],
  },

  onLoad() {
    this.loadData()
  },

  async loadData() {
    try {
      const data = await app.loadJson('/data/cities.json')
      const cities = data.cities.sort((a, b) => b.job_count - a.job_count)
      const topCities = cities.slice(0, 10)

      // 生成地图marker
      const markers = []
      cities.forEach((city, idx) => {
        const coords = cityCoords[city.city]
        if (coords) {
          markers.push({
            id: idx,
            longitude: coords[0],
            latitude: coords[1],
            title: `${city.city}: ${city.job_count}个岗位`,
            width: 30,
            height: 30,
          })
        }
      })

      this.setData({
        topCities,
        markers,
      })
    } catch (e) {
      wx.showToast({ title: '加载失败', icon: 'error' })
    }
  }
})

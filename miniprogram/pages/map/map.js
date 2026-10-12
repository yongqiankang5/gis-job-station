const app = getApp()

Page({
  data: {
    cities: [],
    loading: true,
  },

  onLoad() {
    this.loadData()
  },

  async loadData() {
    try {
      const data = await app.loadJson('/data/cities.json')
      this.setData({
        cities: data.cities,
        loading: false,
      })
    } catch (e) {
      wx.showToast({ title: '加载失败', icon: 'error' })
      this.setData({ loading: false })
    }
  }
})

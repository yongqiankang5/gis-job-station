const app = getApp()

Page({
  data: {
    data: null,
  },

  onLoad() {
    this.loadData()
  },

  async loadData() {
    try {
      const data = await app.loadJson('/data/official.json')
      this.setData({ data })
    } catch (e) {
      wx.showToast({ title: '加载失败', icon: 'error' })
    }
  }
})

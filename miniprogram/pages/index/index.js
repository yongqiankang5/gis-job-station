const app = getApp()

Page({
  data: {
    overview: null,
    loading: true,
  },

  onLoad() {
    this.loadData()
  },

  async loadData() {
    try {
      const overview = await app.loadJson('/data/overview.json')
      this.setData({
        overview,
        loading: false,
      })
    } catch (e) {
      wx.showToast({ title: '加载失败', icon: 'error' })
      this.setData({ loading: false })
    }
  },

  goToJobs() {
    wx.switchTab({ url: '/pages/jobs/jobs' })
  },

  goToMap() {
    wx.switchTab({ url: '/pages/map/map' })
  },

  goToFavorites() {
    wx.navigateTo({ url: '/pages/favorites/favorites' })
  },

  goToOfficial() {
    wx.navigateTo({ url: '/pages/official/official' })
  },

  goToStats() {
    wx.switchTab({ url: '/pages/stats/stats' })
  }
})

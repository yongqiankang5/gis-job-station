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
  },

  copyUrl(e) {
    const url = e.currentTarget.dataset.url
    if (url) {
      wx.setClipboardData({
        data: url,
        success() {
          wx.showModal({
            title: '公告链接已复制',
            content: '打开浏览器粘贴即可查看原公告',
            showCancel: false,
            confirmText: '知道了'
          })
        }
      })
    }
  }
})

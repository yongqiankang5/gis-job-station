const app = getApp()

Page({
  data: {
    job: null,
    loading: true,
  },

  onLoad(options) {
    const jobId = parseInt(options.id)
    this.findJobById(jobId)
  },

  // 从所有分片里找对应id的岗位
  async findJobById(jobId) {
    try {
      // 最多找5个分片，找到就停
      for (let i = 0; i < 5; i++) {
        const data = await app.loadJson(`/data/jobs_${i}.json`)
        const found = data.find(j => j.id === jobId)
        if (found) {
          this.setData({ job: found, loading: false })
          return
        }
      }
      wx.showToast({ title: '岗位未找到', icon: 'error' })
      this.setData({ loading: false })
    } catch (e) {
      wx.showToast({ title: '加载失败', icon: 'error' })
      this.setData({ loading: false })
    }
  },

  // 打开原始链接
  openOriginal() {
    if (this.data.job.url) {
      wx.setClipboardData({
        data: this.data.job.url,
        success() {
          wx.showToast({ title: '链接已复制', icon: 'success' })
        }
      })
    }
  }
})

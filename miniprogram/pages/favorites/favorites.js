const app = getApp()

Page({
  data: {
    jobs: [],
  },

  onShow() {
    this.loadFavs()
  },

  async loadFavs() {
    const favIds = wx.getStorageSync('fav_jobs') || []
    if (favIds.length === 0) {
      this.setData({ jobs: [] })
      return
    }

    let allJobs = []
    for (let i = 0; i < 5; i++) {
      const chunk = await app.loadJson(`/data/jobs_${i}.json`)
      allJobs = allJobs.concat(chunk)
    }

    const favJobs = allJobs.filter(j => favIds.includes(j.id))
    this.setData({ jobs: favJobs })
  },

  goToDetail(e) {
    const job = e.currentTarget.dataset.job
    wx.navigateTo({
      url: `/pages/job-detail/job-detail?id=${job.id}`,
    })
  }
})

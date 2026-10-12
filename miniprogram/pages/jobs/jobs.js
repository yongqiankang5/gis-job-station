const app = getApp()

Page({
  data: {
    jobs: [],
    loading: false,
    hasMore: true,
    currentChunk: 0,
    chunkSize: 500,
    totalChunks: 5,
    cityFilter: '',
  },

  onLoad() {
    this.loadFirstChunk()
  },

  // 加载第一页
  async loadFirstChunk() {
    this.setData({ jobs: [], currentChunk: 0, hasMore: true })
    await this.loadNextChunk()
  },

  // 加载下一个分片
  async loadNextChunk() {
    if (this.data.loading || !this.data.hasMore) return

    this.setData({ loading: true })
    try {
      const chunk = this.data.currentChunk
      const data = await app.loadJson(`/data/jobs_${chunk}.json`)

      let newJobs = data
      if (this.data.cityFilter) {
        newJobs = data.filter(j => j.city === this.data.cityFilter)
      }

      this.setData({
        jobs: [...this.data.jobs, ...newJobs],
        currentChunk: chunk + 1,
        loading: false,
        hasMore: chunk + 1 < this.data.totalChunks,
      })
    } catch (e) {
      wx.showToast({ title: '加载失败', icon: 'error' })
      this.setData({ loading: false })
    }
  },

  // 下拉刷新
  onPullDownRefresh() {
    this.loadFirstChunk().then(() => {
      wx.stopPullDownRefresh()
    })
  },

  // 上拉加载更多
  onReachBottom() {
    this.loadNextChunk()
  },

  // 点击岗位跳转详情
  goToDetail(e) {
    const job = e.currentTarget.dataset.job
    wx.navigateTo({
      url: `/pages/job-detail/job-detail?id=${job.id}`,
    })
  },

  // 城市筛选（简化版，后面再加完整筛选）
  onCityFilter(e) {
    this.setData({ cityFilter: e.detail.value })
    this.loadFirstChunk()
  }
})

const app = getApp()

Page({
  data: {
    jobs: [],
    allJobs: [],
    loading: false,
    hasMore: true,
    displayCount: 20,
    keyword: '',
    cities: ['全部城市'],
    selectedCity: '',
    selectedCityIndex: 0,
    salaryOptions: ['全部薪资', '10K以下', '10-20K', '20-30K', '30K以上'],
    selectedSalary: '',
  },

  onLoad() {
    this.loadAllJobs()
  },

  // 一次性加载全部岗位（2000多条，本地过滤很快）
  async loadAllJobs() {
    this.setData({ loading: true })
    try {
      let allJobs = []
      for (let i = 0; i < 5; i++) {
        const chunk = await app.loadJson(`/data/jobs_${i}.json`)
        allJobs = allJobs.concat(chunk)
      }
      // 提取城市列表
      const citySet = new Set(allJobs.map(j => j.city))
      const cities = ['全部城市', ...Array.from(citySet).sort()]
      this.setData({
        allJobs,
        cities,
        loading: false,
      })
      this.applyFilter()
    } catch (e) {
      wx.showToast({ title: '加载失败', icon: 'error' })
      this.setData({ loading: false })
    }
  },

  // 应用筛选条件
  applyFilter() {
    let result = this.data.allJobs
    const { keyword, selectedCity, selectedSalary } = this.data

    if (keyword) {
      const kw = keyword.toLowerCase()
      result = result.filter(j => 
        j.title.toLowerCase().includes(kw) || 
        j.company.toLowerCase().includes(kw)
      )
    }

    if (selectedCity && selectedCity !== '全部城市') {
      result = result.filter(j => j.city === selectedCity)
    }

    if (selectedSalary && selectedSalary !== '全部薪资') {
      result = result.filter(j => {
        const salary = j.salary_min || 0
        if (selectedSalary === '10K以下') return salary < 10
        if (selectedSalary === '10-20K') return salary >= 10 && salary < 20
        if (selectedSalary === '20-30K') return salary >= 20 && salary < 30
        if (selectedSalary === '30K以上') return salary >= 30
        return true
      })
    }

    this.setData({
      jobs: result.slice(0, this.data.displayCount),
      hasMore: result.length > this.data.displayCount,
    })
  },

  onSearchInput(e) {
    this.setData({ keyword: e.detail.value })
  },

  doSearch() {
    this.setData({ displayCount: 20 })
    this.applyFilter()
  },

  onCityChange(e) {
    const idx = e.detail.value
    this.setData({
      selectedCityIndex: idx,
      selectedCity: this.data.cities[idx],
      displayCount: 20,
    })
    this.applyFilter()
  },

  onSalaryChange(e) {
    this.setData({
      selectedSalary: this.data.salaryOptions[e.detail.value],
      displayCount: 20,
    })
    this.applyFilter()
  },

  // 下拉刷新
  onPullDownRefresh() {
    this.loadAllJobs().then(() => {
      wx.stopPullDownRefresh()
    })
  },

  // 上拉加载更多
  onReachBottom() {
    if (!this.data.hasMore) return
    const newCount = this.data.displayCount + 20
    this.setData({ displayCount: newCount })
    this.applyFilter()
  },

  // 点击岗位跳转详情
  goToDetail(e) {
    const job = e.currentTarget.dataset.job
    wx.navigateTo({
      url: `/pages/job-detail/job-detail?id=${job.id}`,
    })
  },
})

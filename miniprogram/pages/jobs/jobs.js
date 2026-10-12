const app = getApp()

Page({
  data: {
    jobs: [],
    allJobs: [],
    loading: false,
    displayCount: 20,
    keyword: '',
    cities: [],
    filteredCities: [],
    selectedCity: '',
    citySearch: '',
    showCityPopup: false,
    salaryOptions: ['全部薪资', '10K以下', '10-20K', '20-30K', '30K以上'],
    selectedSalary: '',
  },

  onLoad() {
    this.loadAllJobs()
  },

  // 一次性加载全部岗位
  async loadAllJobs() {
    this.setData({ loading: true })
    try {
      let allJobs = []
      for (let i = 0; i < 5; i++) {
        const chunk = await app.loadJson(`/data/jobs_${i}.json`)
        allJobs = allJobs.concat(chunk)
      }
      // 提取城市列表，只保留真实城市，过滤掉省份等非城市
      const citySet = new Set(allJobs.map(j => j.city).filter(c => c && c.length <= 4))
      const cities = Array.from(citySet).sort()
      this.setData({
        allJobs,
        cities,
        filteredCities: cities,
        loading: false,
      })
      this.applyFilter()
    } catch (e) {
      wx.showToast({ title: '加载失败', icon: 'error' })
      this.setData({ loading: false })
    }
  },

  // 打开城市弹窗
  openCityPopup() {
    this.setData({ showCityPopup: true, citySearch: '' })
  },

  closeCityPopup() {
    this.setData({ showCityPopup: false })
  },

  // 城市搜索
  onCitySearch(e) {
    const kw = e.detail.value
    const filtered = this.data.cities.filter(c => c.includes(kw))
    this.setData({
      citySearch: kw,
      filteredCities: filtered,
    })
  },

  // 选择城市
  selectCity(e) {
    const city = e.currentTarget.dataset.city
    this.setData({
      selectedCity: city,
      showCityPopup: false,
      displayCount: 20,
    })
    this.applyFilter()
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

    if (selectedCity) {
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
    })
  },

  onSearchInput(e) {
    this.setData({ keyword: e.detail.value })
  },

  doSearch() {
    this.setData({ displayCount: 20 })
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

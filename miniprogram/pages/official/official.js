const app = getApp()

Page({
  data: {
    data: null,
    allRecords: [],
    filteredRecords: [],
    provinces: ['全部省份'],
    selectedProvince: '',
    years: ['全部年份'],
    selectedYear: '',
  },

  onLoad() {
    this.loadData()
  },

  async loadData() {
    try {
      const data = await app.loadJson('/data/official.json')
      const records = data.records || []
      // 提取省份和年份选项
      const provinceSet = new Set(records.map(r => r.province).filter(Boolean))
      const yearSet = new Set(records.map(r => r.year).filter(Boolean))
      this.setData({
        data,
        allRecords: records,
        filteredRecords: records,
        provinces: ['全部省份', ...Array.from(provinceSet).sort()],
        years: ['全部年份', ...Array.from(yearSet).sort().reverse()],
      })
    } catch (e) {
      wx.showToast({ title: '加载失败', icon: 'error' })
    }
  },

  onProvinceChange(e) {
    const idx = e.detail.value
    this.setData({
      selectedProvince: this.data.provinces[idx] === '全部省份' ? '' : this.data.provinces[idx],
    })
    this.applyFilter()
  },

  onYearChange(e) {
    const idx = e.detail.value
    this.setData({
      selectedYear: this.data.years[idx] === '全部年份' ? '' : this.data.years[idx],
    })
    this.applyFilter()
  },

  applyFilter() {
    let result = this.data.allRecords
    const { selectedProvince, selectedYear } = this.data
    if (selectedProvince) {
      result = result.filter(r => r.province === selectedProvince)
    }
    if (selectedYear) {
      result = result.filter(r => r.year == selectedYear)
    }
    this.setData({ filteredRecords: result })
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

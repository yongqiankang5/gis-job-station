const app = getApp()

Page({
  data: {
    overview: null,
    salary: null,
    cities: null,
    skills: null,
    loading: true,
  },

  onLoad() {
    this.loadData()
  },

  async loadData() {
    try {
      const [overview, salary, cities, skills] = await Promise.all([
        app.loadJson('/data/overview.json'),
        app.loadJson('/data/salary.json'),
        app.loadJson('/data/cities.json'),
        app.loadJson('/data/skills.json'),
      ])
      this.setData({
        overview,
        salary,
        cities: cities.cities.slice(0, 10),
        skills: skills.top_skills.slice(0, 10),
        loading: false,
      })
    } catch (e) {
      wx.showToast({ title: '加载失败', icon: 'error' })
      this.setData({ loading: false })
    }
  }
})

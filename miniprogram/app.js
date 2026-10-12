App({
  onLaunch() {
    // 先加载本地包内置数据（兜底）
    this.loadLocalManifest()
    // 再尝试从线上拉最新数据
    this.checkRemoteUpdate()
  },

  globalData: {
    manifest: null,
    overview: null,
    // 线上数据地址：GitHub Pages地址
    remoteBase: 'https://yongqiankang5.github.io/gis-job-station/miniprogram/data/',
    useRemote: false,
  },

  // 加载本地包内置数据
  loadLocalManifest() {
    const that = this
    wx.request({
      url: '/data/manifest.json',
      success(res) {
        that.globalData.manifest = res.data
      }
    })
  },

  // 检查线上是否有更新数据
  checkRemoteUpdate() {
    const that = this
    wx.request({
      url: that.globalData.remoteBase + 'manifest.json',
      success(res) {
        const local = that.globalData.manifest
        const remote = res.data
        // 如果线上更新时间比本地新，就切换为线上数据源
        if (remote && local && remote.data_updated_at > local.data_updated_at) {
          that.globalData.useRemote = true
          that.globalData.manifest = remote
          wx.showToast({ title: '已加载最新数据', icon: 'success' })
        }
      },
      fail() {
        // 线上拉取失败就用本地数据，不影响使用
        console.log('线上数据不可用，使用本地包数据')
      }
    })
  },

  // 加载JSON数据：优先线上，失败回退本地
  loadJson(path) {
    const that = this
    // 去掉路径开头的斜杠
    const cleanPath = path.replace(/^\//, '')
    return new Promise((resolve, reject) => {
      // 如果开启了线上数据，先请求线上
      if (that.globalData.useRemote) {
        wx.request({
          url: that.globalData.remoteBase + cleanPath,
          success(res) {
            resolve(res.data)
          },
          fail() {
            // 线上失败，回退本地
            wx.request({
              url: path,
              success: res2 => resolve(res2.data),
              fail: reject
            })
          }
        })
      } else {
        // 没开线上，直接读本地
        wx.request({
          url: path,
          success(res) {
            resolve(res.data)
          },
          fail: reject
        })
      }
    })
  }
})

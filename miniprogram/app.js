App({
  onLaunch() {
    // 用文件系统API读取本地包内置数据
    const fs = wx.getFileSystemManager()
    try {
      const manifestStr = fs.readFileSync('/data/manifest.json', 'utf-8')
      this.globalData.manifest = JSON.parse(manifestStr)
      const overviewStr = fs.readFileSync('/data/overview.json', 'utf-8')
      this.globalData.overview = JSON.parse(overviewStr)
    } catch (e) {
      console.error('读取本地数据失败', e)
    }
    // 尝试从线上拉最新数据
    this.checkRemoteUpdate()
  },

  globalData: {
    manifest: null,
    overview: null,
    // 线上数据地址：GitHub Pages地址
    remoteBase: 'https://yongqiankang5.github.io/gis-job-station/miniprogram/data/',
    useRemote: false,
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
        console.log('线上数据不可用，使用本地包数据')
      }
    })
  },

  // 加载JSON数据：优先线上，失败回退本地
  loadJson(path) {
    const that = this
    // 去掉路径开头的斜杠
    const cleanPath = path.replace(/^\//, '')
    const fs = wx.getFileSystemManager()

    // 线上模式
    if (that.globalData.useRemote) {
      return new Promise((resolve, reject) => {
        wx.request({
          url: that.globalData.remoteBase + cleanPath.replace('data/', ''),
          success(res) {
            resolve(res.data)
          },
          fail() {
            // 线上失败，回退本地
            try {
              const str = fs.readFileSync('/' + cleanPath, 'utf-8')
              resolve(JSON.parse(str))
            } catch (e) {
              reject(e)
            }
          }
        })
      })
    }

    // 本地模式：用文件系统读
    return new Promise((resolve, reject) => {
      try {
        const str = fs.readFileSync('/' + cleanPath, 'utf-8')
        resolve(JSON.parse(str))
      } catch (e) {
        reject(e)
      }
    })
  }
})

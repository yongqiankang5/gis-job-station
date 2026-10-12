# GIS 遥感就业情报站部署与运维说明

## 1. 本地开发环境

### 1.1 环境要求

- Python 3.10 以上，推荐 Python 3.11。
- Chromium 或 Chrome。BOSS 抓取需要真实浏览器，首次使用建议在可见浏览器中登录。
- Windows PowerShell、macOS Terminal 或 Linux Shell。

### 1.2 创建环境并安装依赖

```bash
cd gis-job-tracker
python -m venv .venv
```

Windows：

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Linux/macOS：

```bash
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

编辑 `.env`。本地开发建议先关闭调度器，防止启动服务时立即产生后台任务：

```dotenv
DATABASE_URL=sqlite:///./data/gis_jobs.db
SECRET_KEY=请替换为随机长字符串
CORS_ORIGINS=["http://localhost:8000","http://127.0.0.1:8000"]
ENABLE_SCHEDULER=false
REDIS_URL=
CHROMIUM_PATH=
```

如果程序找不到浏览器，Windows 可填写：

```dotenv
CHROMIUM_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe
```

启动服务：

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

浏览器访问 `http://127.0.0.1:8000`，健康检查访问 `http://127.0.0.1:8000/api/health`。

## 2. Docker 一键部署

### 2.1 准备配置

安装 Docker Engine 和 Docker Compose 插件，然后执行：

```bash
cd gis-job-tracker
cp .env.example .env
```

Docker 推荐配置：

```dotenv
DATABASE_URL=sqlite:///./data/gis_jobs.db
SECRET_KEY=请替换为至少32位随机字符串
CORS_ORIGINS=["http://服务器IP:8000"]
ENABLE_SCHEDULER=true
REDIS_URL=redis://redis:6379/0
CHROMIUM_PATH=/usr/bin/chromium
```

### 2.2 构建并启动

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f app
```

访问 `http://服务器IP:8000`。停止服务使用：

```bash
docker compose down
```

`data` 目录挂载到宿主机，删除或重建容器不会删除 SQLite 数据。`static` 以只读方式挂载，便于更新前端资源。

Redis 只用于接口缓存，不可用时应用仍可运行。如不需要 Redis，将 `.env` 中 `REDIS_URL` 留空；也可仅启动应用服务：

```bash
docker compose up -d app
```

## 3. 云服务器部署

推荐阿里云或腾讯云轻量应用服务器，最低 2 核 4 GB 内存、40 GB 系统盘。Chromium 抓取会短时占用较多内存，1 GB 服务器不建议运行定时 BOSS 抓取。

### 3.1 安装 Docker（Ubuntu 22.04/24.04）

```bash
sudo apt update
sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"
```

重新登录后，把项目上传到 `/opt/gis-job-tracker`，执行：

```bash
cd /opt/gis-job-tracker
cp .env.example .env
nano .env
docker compose up -d --build
```

在云防火墙只开放必要端口。测试阶段可开放 TCP 8000；正式环境建议只开放 80/443，并用 Nginx 反向代理到 `127.0.0.1:8000`，同时为 `/api/admin/` 配置 IP 白名单或身份认证。

Nginx 代理示例：

```nginx
server {
    listen 80;
    server_name jobs.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;
    }
}
```

生产环境只运行一个 Uvicorn worker 最直观。若启动多个 worker，项目的领导锁会确保只有一个进程运行 APScheduler，抓取文件锁会阻止重复抓取。

## 4. 首次初始化

1. 启动一次 Web 服务，应用会自动创建数据库表。
2. 查看健康状态：

```bash
curl http://127.0.0.1:8000/api/health
```

3. 首次 BOSS 登录建议在本机可见浏览器完成，再执行小范围验证：

```bash
python scripts/run_boss_scraper.py --cities 北京 --max-pages 1
```

4. 执行一键全量更新。服务器无桌面环境时添加 `--headless`：

```bash
python scripts/update_all.py --max-pages 5
python scripts/update_all.py --headless --max-pages 5
```

Docker 内运行：

```bash
docker compose exec app python scripts/update_all.py --headless --max-pages 5
```

5. 如果 BOSS 暂时受登录或限流影响，可先初始化公开事业单位数据：

```bash
python scripts/update_all.py --skip-boss
```

6. 验证数据和调度器：

```bash
curl http://127.0.0.1:8000/api/stats/overview
curl http://127.0.0.1:8000/api/admin/scheduler-status
```

## 5. 定时计划与日常维护

当 `ENABLE_SCHEDULER=true` 时，时间均为 Asia/Shanghai：

- 周一、周四 02:00：BOSS 最近 7 天岗位增量更新。
- 周日 03:00：事业单位数据更新。
- 每天 04:00：标记 180 天未更新岗位无效，并删除 30 天前抓取日志。
- 每天 04:30：SQLite gzip 备份，保留 30 天。
- 每月 1 日 05:00：写入 `data/snapshots/snapshot_YYYYMM.json`。

常用命令：

```bash
# 查看容器和应用日志
docker compose ps
docker compose logs --tail=200 app
docker compose logs -f app

# 查看调度状态
curl http://127.0.0.1:8000/api/admin/scheduler-status

# 手动后台触发抓取
curl -X POST "http://127.0.0.1:8000/api/admin/run-scraper?source=boss"
curl -X POST "http://127.0.0.1:8000/api/admin/run-scraper?source=official"
curl -X POST "http://127.0.0.1:8000/api/admin/run-scraper?source=all"

# 手动清洗
curl -X POST http://127.0.0.1:8000/api/admin/clean

# 指定城市更新或跳过某来源
python scripts/update_all.py --cities 北京,武汉,成都 --max-pages 3
python scripts/update_all.py --skip-boss
python scripts/update_all.py --skip-official --headless
```

更新日志位于 `data/logs/update_YYYYMMDD_HHMMSS.log`。

## 6. 数据备份与恢复

手动备份：

```bash
python scripts/backup.py
docker compose exec app python scripts/backup.py
```

输出文件为 `data/backups/db_YYYYMMDD_HHMMSS.db.gz`，脚本自动删除 30 天前的同类备份。调度器启用时每天自动执行，无需额外 cron。

如果不启用应用调度器，可在 Linux 添加 cron：

```bash
crontab -e
30 4 * * * cd /opt/gis-job-tracker && /usr/bin/docker compose exec -T app python scripts/backup.py >> data/logs/backup_cron.log 2>&1
```

恢复前先停止应用，保留当前数据库，再解压指定备份：

```bash
docker compose stop app
cp data/gis_jobs.db data/gis_jobs.db.before_restore
gzip -dc data/backups/db_20260831_043000.db.gz > data/gis_jobs.db
docker compose start app
curl http://127.0.0.1:8000/api/health
```

不要在应用写入数据库时直接复制 SQLite 主文件；本项目备份脚本使用 SQLite 在线备份 API，可获得一致性快照。

## 7. 常见问题排查

### 7.1 8000 端口被占用

Linux：

```bash
sudo ss -lntp | grep :8000
```

Windows PowerShell：

```powershell
Get-NetTCPConnection -LocalPort 8000
```

可停止占用程序，或将 `docker-compose.yml` 端口改为 `8080:8000`。

### 7.2 Chromium 启动失败

```bash
docker compose exec app which chromium
docker compose exec app chromium --version
docker compose exec app env | grep CHROMIUM_PATH
```

确认 `CHROMIUM_PATH=/usr/bin/chromium`，并保留 Compose 中的 `shm_size: 1gb`。宿主机目录需要允许容器 UID 1000 写入：

```bash
sudo chown -R 1000:1000 data
```

### 7.3 BOSS 验证、登录墙或限流

- 不要提高并发或缩短间隔。
- 先在可见浏览器中登录，使用一个城市、一页验证。
- 无头模式无法人工处理验证码时，停止该任务并改在本机运行。
- 可临时使用 `--skip-boss`，通过手工导入工具补充数据。
- 项目不会破解验证码、签名或其他反爬措施。

### 7.4 调度器没有运行

检查 `.env`：

```dotenv
ENABLE_SCHEDULER=true
```

重启并查询：

```bash
docker compose restart app
curl http://127.0.0.1:8000/api/admin/scheduler-status
```

返回的 `running=true`、`is_leader=true` 表示当前进程负责调度。多进程环境中其他 worker 返回 `is_leader=false` 属正常现象。

### 7.5 Redis 连接失败

Redis 是可选项。无需缓存时将 `REDIS_URL` 留空；需要时检查：

```bash
docker compose ps redis
docker compose exec redis redis-cli ping
```

### 7.6 SQLite 锁或磁盘空间不足

```bash
df -h
du -sh data/*
docker compose logs --tail=300 app | grep -i locked
```

不要让多个独立部署实例同时写同一个 SQLite 文件。高并发或多实例部署应把 `DATABASE_URL` 切换为 PostgreSQL。

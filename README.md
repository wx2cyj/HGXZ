# 🍊 HGXZ - 黄果下载

自动下载黄果短剧视频到指定目录，带 WebUI 管理界面。

支持增量同步、失败重试、已有视频扫描识别，SQLite 记录下载状态。生成 Emby / Jellyfin 兼容的目录结构与 NFO 元数据。

## 功能特点

- **自动发现与下载** — 遍历分类页面，自动发现新专辑并下载全部剧集
- **HLS 逐段下载** — 不依赖长连接，避免 CDN 断流；支持 AES-128 加密流解密
- **增量同步** — 已下载的跳过，失败的有冷却期后自动重试
- **Emby 兼容** — 自动创建 `tvshow.nfo`、`episodedetails.nfo`、`poster.jpg`
- **多域名故障切换** — 主站不可用时自动切换备用域名，恢复后自动回切
- **WebUI 管理** — 仪表盘统计、专辑浏览、实时日志（WebSocket）、手动同步/重试
- **Docker / Unraid** — 提供 Dockerfile 和 Unraid 社区模板

## 快速开始

### Docker 部署（推荐）

1. **构建镜像：**

```bash
git clone https://github.com/wx2cyj/HGXZ.git
cd HGXZ
docker build -t hgxz:local .
```

2. **准备配置文件：**

```bash
mkdir -p /path/to/appdata/hgxz/config
cp config.example.json /path/to/appdata/hgxz/config/config.json
# 按需修改 config.json
```

3. **启动容器：**

```bash
docker run -d --name hgxz \
  --restart unless-stopped \
  -p 8080:8080 \
  -v /path/to/appdata/hgxz/config:/config \
  -v /path/to/appdata/hgxz/data:/data \
  -v /path/to/appdata/hgxz/logs:/logs \
  -v /path/to/media:/media \
  -e TZ=Asia/Shanghai \
  hgxz:local --daemon --schedule 03:30
```

4. **打开 WebUI：** 浏览器访问 `http://你的IP:8080`

### Unraid 部署

1. 在 Unraid 终端中构建镜像：

```bash
cd /path/to/HGXZ && docker build -t hgxz:local .
```

2. 将 `unraid/hgxz.xml` 复制到 `/boot/config/plugins/dockerMan/templates-user/`
3. 在 Docker 页面点「添加容器」→ 选择模板 → 按需修改路径 → 启动

## 配置说明

`config.json` 结构如下：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `site.base_url` | 主站地址 | — |
| `site.backup_urls` | 备用域名列表 | `[]` |
| `site.request_interval` | 请求间隔（秒） | `2` |
| `site.timeout` | 请求超时（秒） | `30` |
| `site.categories` | 要下载的分类列表 | — |
| `download.root` | 视频下载根目录 | `/media` |
| `download.retries` | 每集下载重试次数 | `3` |
| `download.minimum_duration` | 视频最短有效时长（秒） | `10` |
| `download.recheck_days` | 已完成专辑的重检间隔（天） | `7` |
| `download.failure_cooldown_hours` | 失败集冷却时间（小时） | `24` |
| `download.episode_timeout` | 单集下载总超时（秒） | `1800` |
| `state.database` | SQLite 数据库路径 | `/data/state.sqlite3` |
| `log.directory` | 日志文件目录（可选） | — |

## 命令行参数

```
python -m HGXZ.cli [OPTIONS]

选项：
  --config PATH           配置文件路径（默认 /config/config.json）
  --daemon                常驻运行：启动后同步一次，之后每天定时同步，同时开启 WebUI
  --schedule HH:MM        --daemon 模式下的每日同步时间（默认 03:30）
  --port PORT             WebUI 端口（默认 8080）
  --metadata-only         只生成 NFO 元数据，不下载视频
  --only-id ID            只同步指定的专辑 ID
  --max-albums N          最多同步 N 个专辑
  --max-episodes N        每个专辑最多下载 N 集
  --scan-existing         扫描媒体目录，将已有视频注册到状态库
  --rebuild-covers        重新下载所有缺失的封面
  --json                  输出 JSON 格式结果
```

## 目录结构

下载后的媒体目录结构（Emby / Jellyfin 兼容）：

```
/media/
├── AI成人短剧/
│   ├── 剧名A [huangguo-12345]/
│   │   ├── tvshow.nfo
│   │   ├── poster.jpg
│   │   └── Season 01/
│   │       ├── 剧名A.S01E01.mp4
│   │       ├── 剧名A.S01E01.nfo
│   │       ├── 剧名A.S01E02.mp4
│   │       └── 剧名A.S01E02.nfo
│   └── ...
└── AI成人漫剧/
    └── ...
```

## 代理配置

如果视频 CDN 需要代理访问，通过环境变量配置：

```bash
-e HTTP_PROXY=http://192.168.2.6:10086
-e HTTPS_PROXY=http://192.168.2.6:10086
-e NO_PROXY=127.0.0.1,localhost,huangguoai.com,rxzfszht.cc
```

站点域名直连（`NO_PROXY`），视频 CDN 走代理。

## 依赖

- Python 3.13+
- ffmpeg、ffprobe（视频合并与验证）
- openssl（AES 解密）

Python 包：
- fastapi >= 0.115
- uvicorn[standard] >= 0.30

## 许可证

私有项目，仅供个人使用。

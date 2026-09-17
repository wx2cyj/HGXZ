# 🍊 HGXZ - 黄果下载

自动下载黄果短剧视频到指定目录，带 WebUI 管理界面。

支持增量同步、失败重试、已有视频扫描识别，SQLite 记录下载状态。生成 Emby / Jellyfin 兼容的目录结构与 NFO 元数据。

---

## 功能特点

- **自动发现与下载** — 遍历分类页面，自动发现新专辑并下载全部剧集
- **HLS 逐段下载** — 独立短连接分段下载+自动重试，避免 CDN 长连接断流；支持 AES-128 流解密
- **增量同步** — 已下载完成的自动跳过，失败集进入冷却期后定时重试
- **Emby 兼容** — 自动创建 `tvshow.nfo`、`episodedetails.nfo` 和 `poster.jpg`，智能跳过无变化重写
- **多域名故障切换** — 主站异常时自动无缝切换备用域名，恢复后自动切回
- **WebUI 管理** — 仪表盘统计、专辑列表、实时日志（WebSocket 流式推送）、手动一键同步/重试/扫描
- **Unraid 专属支持** — 提供现成的 Unraid Docker 图形化安装模板

---

## 目录与路径规划

| 用途 | 容器内路径 | Unraid 宿主机路径 | 说明 |
|------|------------|-------------------|------|
| **配置文件** | `/config` | `/mnt/user/appdata/HGXZ/config` | 存放 `config.json` |
| **状态库** | `/data` | `/mnt/user/appdata/HGXZ/data` | 存放 SQLite 状态数据库 `state.sqlite3` |
| **运行日志** | `/logs` | `/mnt/user/appdata/HGXZ/logs` | 存放每日轮转日志 `hgxz.log` |
| **视频媒体库** | `/media` | `/mnt/user/QTZL/黄果` | 下载好的短剧视频与 NFO 元数据 |

---

## 一、Docker 镜像信息

- **镜像地址**：`wangxun2cyj1314/hgxz:latest`
- **平台架构**：`linux/amd64`
- **拉取说明**：因为是 Docker Hub 私有镜像，拉取前需在宿主机/终端先完成一次登录认证：
  ```bash
  docker login
  docker pull wangxun2cyj1314/hgxz:latest
  ```

---

## 二、Unraid 图形化配置部署指南

### 第一步：在 Unraid 登录 Docker Hub（获取私有镜像拉取权限）

由于镜像存放在 Docker Hub 的**私有库**中，Unraid 首次拉取前必须先完成认证：

1. 打开 Unraid 管理网页，点击右上角终端图标 **【`>_`】** 进入命令行。
2. 执行登录命令并按提示输入用户名与密码（或 Token）：
   ```bash
   docker login
   ```
3. 看到 `Login Succeeded` 提示即表示认证成功。此登录状态在 Unraid 中持久保存。

---

### 第二步：准备配置文件目录

在 Unraid 终端中执行以下命令，快速创建目录并将模板配置文件就位：

```bash
mkdir -p /mnt/user/appdata/HGXZ/config /mnt/user/appdata/HGXZ/data /mnt/user/appdata/HGXZ/logs /mnt/user/QTZL/黄果
```

将项目中的 `config.example.json` 复制到 `/mnt/user/appdata/HGXZ/config/config.json`：

```bash
curl -sSL https://raw.githubusercontent.com/wx2cyj/HGXZ/main/config.example.json -o /mnt/user/appdata/HGXZ/config/config.json
```

> 也可以通过 SMB 共享或 Unraid 文件管理器直接在 `/mnt/user/appdata/HGXZ/config/` 下创建并编辑 `config.json`。

---

### 第三步：添加 Unraid 容器模板

1. 在 Unraid 终端中，将本项目的模板文件下载到 Unraid 用户模板目录：
   ```bash
   curl -sSL https://raw.githubusercontent.com/wx2cyj/HGXZ/main/unraid/hgxz.xml -o /boot/config/plugins/dockerMan/templates-user/my-hgxz.xml
   ```

---

### 第四步：Unraid 网页端图形化安装

1. 点击 Unraid 顶部导航栏的 **【Docker】** 标签页。
2. 页面滚动到最底部，点击 **【添加容器】（Add Container）** 按钮。
3. 在 **【模板】（Template）** 下拉菜单中，选择 **`HGXZ`**（系统会自动填充所有配置项）。
4. 确认各项参数设置无误：

| 设置项 | 字段名 | 填写内容 | 说明 |
|--------|--------|----------|------|
| **名称** | Name | `HGXZ` | 容器名称 |
| **存储库** | Repository | `wangxun2cyj1314/hgxz:latest` | 你的私有镜像地址 |
| **WebUI 端口** | Port: 8099 | `8099` | Web 界面访问端口，可按需修改 |
| **配置文件目录** | Path: /config | `/mnt/user/appdata/HGXZ/config` | 存放 config.json |
| **状态库目录** | Path: /data | `/mnt/user/appdata/HGXZ/data` | SQLite 数据库文件 |
| **日志目录** | Path: /logs | `/mnt/user/appdata/HGXZ/logs` | 运行日志 |
| **媒体目录** | Path: /media | `/mnt/user/QTZL/黄果` | 视频下载保存目录 |
| **时区** | Variable: TZ | `Asia/Shanghai` | 确保定时时间准确 |
| **每日同步时间** | Variable: SCHEDULE | `03:30` | 每天自动同步时间（HH:MM 格式，默认凌晨 03:30） |
| **文件权限掩码** | Variable: UMASK | `000` | 赋予生成文件完全读写权限，避免 Unraid SMB 权限问题 |
| **运行参数** | Post Arguments | `--daemon` | 常驻后台运行 |

> 🌐 **关于网络代理配置（必读）：**
> 国内网络环境下 `huangguoai.com` 受限，**必须通过代理访问**，点击界面下方的 **【显示更多设置...】（Show more settings...）**：
> - `HTTP_PROXY` / `HTTPS_PROXY`：填入你的局域网 HTTP 代理地址（例如 `http://192.168.2.6:10086`，注意填真实局域网 IP，不可填 `127.0.0.1`）。
> - `NO_PROXY`：保持默认的 `127.0.0.1,localhost`。**切勿**将 `huangguoai.com` 加入直连白名单，否则会导致主站超时报错。

5. 确认无误后，点击最下方的 **【应用】（Apply）** 按钮。Unraid 将自动拉取私有镜像并启动容器。

---

### 第五步：访问与验证

1. 启动完成后，在 **【Docker】** 页面找到 `HGXZ` 容器，点击图标选择 **【查看日志】（Logs）**，确认看到 WebUI 启动日志。
2. 点击容器图标选择 **【WebUI】**，或直接在浏览器访问：
   ```
   http://[你的Unraid主机IP]:8099
   ```
3. 进入界面后即可查看仪表盘、专辑列表与实时同步日志。

---

## 三、Docker CLI 命令行运行（备用）

如果不使用 Unraid 模板，也可以直接在终端运行以下命令：

```bash
docker run -d --name HGXZ \
  --restart unless-stopped \
  -p 8099:8099 \
  -v /mnt/user/appdata/HGXZ/config:/config \
  -v /mnt/user/appdata/HGXZ/data:/data \
  -v /mnt/user/appdata/HGXZ/logs:/logs \
  -v /mnt/user/QTZL/黄果:/media \
  -e TZ=Asia/Shanghai \
  -e SCHEDULE=03:30 \
  -e UMASK=000 \
  -e HTTP_PROXY=http://192.168.2.6:10086 \
  -e HTTPS_PROXY=http://192.168.2.6:10086 \
  -e NO_PROXY=127.0.0.1,localhost \
  wangxun2cyj1314/hgxz:latest
```

---

## 四、配置文件详细说明

配置文件路径：`/mnt/user/appdata/HGXZ/config/config.json`

```json
{
  "site": {
    "base_url": "https://huangguoai.com",
    "backup_urls": [
      "https://l5f9m.rxzfszht.cc",
      "https://blolhh.rxzfszht.cc"
    ],
    "request_interval": 2,
    "timeout": 30,
    "categories": [
      {
        "name": "AI成人短剧",
        "path": "/ai-duanju/",
        "library": "AI成人短剧"
      },
      {
        "name": "AI成人漫剧",
        "path": "/ai-manju/",
        "library": "AI成人漫剧"
      }
    ]
  },
  "download": {
    "root": "/media",
    "retries": 3,
    "minimum_duration": 10,
    "recheck_days": 7,
    "failure_cooldown_hours": 24,
    "episode_timeout": 1800
  },
  "state": {
    "database": "/data/state.sqlite3"
  },
  "log": {
    "directory": "/logs"
  }
}
```

| 参数项 | 说明 | 默认推荐值 |
|--------|------|------------|
| `site.base_url` | 主站根域名 | `https://huangguoai.com` |
| `site.backup_urls` | 备用域名列表，主站故障时自动切换 | 见模板 |
| `site.request_interval` | 请求间隔延迟（秒），防止被站点风控 | `2` |
| `site.categories` | 抓取的短剧分类与对应生成的 Emby 媒体库目录名 | — |
| `download.root` | 视频下载根目录（对应容器内 `/media`） | `/media` |
| `download.retries` | 单集重试次数 | `3` |
| `download.minimum_duration` | 视频最短有效时长（秒），过滤无效视频 | `10` |
| `download.recheck_days` | 已完结专辑再次核查的间隔天数 | `7` |
| `download.failure_cooldown_hours` | 失败集的冷却等待时间（小时），避免重复无效请求 | `24` |
| `download.episode_timeout` | 单集下载总超时时间（秒） | `1800` |
| `state.database` | SQLite 数据库文件路径 | `/data/state.sqlite3` |
| `log.directory` | 日志存放路径（对应容器内 `/logs`） | `/logs` |

---

## 五、Emby / Jellyfin 刮削结构

下载完成后的媒体库结构直接兼容 Emby 和 Jellyfin，无需额外刮削插件：

```
/mnt/user/QTZL/黄果/
├── AI成人短剧/
│   ├── 剧名A [huangguo-12345]/
│   │   ├── tvshow.nfo           # 剧集元数据（标题/分类/标签/完结状态）
│   │   ├── poster.jpg           # 剧集封面（自动解密）
│   │   └── Season 01/
│   │       ├── 剧名A.S01E01.mp4 # 视频文件
│   │       ├── 剧名A.S01E01.nfo # 单集元数据
│   │       ├── 剧名A.S01E02.mp4
│   │       └── 剧名A.S01E02.nfo
│   └── ...
└── AI成人漫剧/
    └── ...
```

在 Emby 中将 `/mnt/user/QTZL/黄果` 添加为**节目（电视节目）**类型的媒体库即可直接识别展示。

---

## 许可证

私有项目，仅供个人学习与自用。

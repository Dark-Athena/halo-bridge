# Halo-Bridge

将 [Halo 2.x](https://halo.run) 博客文章同步到 CSDN、博客园、墨天轮等平台的 CLI 工具。

## 特性

- 从 Halo 博客拉取已发布文章（支持 slug 或完整 URL）
- 自动将图片转存到 CSDN CDN，作为图床使用
- 同步到多个平台：CSDN、博客园（文章）、墨天轮
- 自动修复相对图片链接、追加版权声明
- 支持 `--dry-run` 预览模式

## 安装

```bash
pip install -e .
```

## 配置

生成示例配置文件：

```bash
halo-bridge config init
```

配置文件默认位于 `~/.halo-bridge/config.yaml`：

```yaml
halo:
  base_url: "https://your-blog.com"
  token: "pat-xxxxxxxxxxxx"           # Halo 个人访问令牌

csdn:
  cookie: "UserToken=xxx; ..."        # 通过 login 命令自动获取

cnblogs:
  cookie: ".CNBlogsCookie=xxx; ..."   # 通过 login 命令自动获取

modb:
  authorization: "Bearer xxxxxx"      # 通过 login 命令自动获取
  cookie: "token=xxx; ..."            # 通过 login 命令自动获取

defaults:
  targets: ["csdn", "cnblogs", "modb"]
  copyright: |
    ---
    > - **本文作者：** [YourName](https://your-blog.com)
    > - **本文链接：** [{permalink}]({permalink})
    > - **版权声明：** 本博客所有文章除特别声明外，均采用[CC BY-NC-SA 3.0](https://creativecommons.org/licenses/by-nc-sa/3.0/) 许可协议。转载请注明出处
```

### 获取凭据

#### 方式一：浏览器登录（推荐）

需要先安装 playwright：

```bash
pip install halo-bridge[login]
```

然后使用 `login` 命令打开浏览器，手动登录后自动保存 Cookie：

```bash
halo-bridge login csdn
halo-bridge login cnblogs
halo-bridge login modb
```

浏览器会保持登录状态，下次登录时自动恢复会话。

#### 方式二：手动复制

| 平台 | 凭据 | 获取方式 |
|------|------|----------|
| Halo | Personal Access Token | Halo 后台 → 个人中心 → 个人令牌 |
| CSDN | Cookie | 登录 CSDN → F12 → Application → Cookies → 复制完整字符串 |
| 博客园 | Cookie | 登录博客园 → F12 → Application → Cookies → 复制完整字符串 |
| 墨天轮 | Authorization + Cookie | 登录墨天轮 → F12 → Network → 保存草稿 → 从请求头复制 |

## 使用

### 同步文章

```bash
# 同步到所有默认目标
halo-bridge sync "your-article-slug" --to csdn,cnblogs,modb

# 使用完整 URL
halo-bridge sync "https://your-blog.com/archives/my-post" --to csdn,cnblogs

# 仅同步到 CSDN
halo-bridge sync "your-article-slug" --to csdn

# 预览模式（不实际发布）
halo-bridge sync "your-article-slug" --to csdn,cnblogs --dry-run

# 跳过 CSDN 图片代理（直接用源站图片链接）
halo-bridge sync "your-article-slug" --to cnblogs --no-csdn-proxy

# 指定配置文件路径（默认 ~/.halo-bridge/config.yaml）
halo-bridge sync "your-article-slug" --to csdn -c /path/to/config.yaml
```

### 浏览器登录

```bash
halo-bridge login csdn      # 登录 CSDN 并保存 Cookie
halo-bridge login cnblogs   # 登录博客园并保存 Cookie
halo-bridge login modb      # 登录墨天轮并保存 Cookie
```

### 其他命令

```bash
# 查看配置
halo-bridge config show

# 列出可用目标平台
halo-bridge config list-targets
```

## 工作流程

```
Halo 拉取文章
      ↓
内容转换（修复图片链接 + 版权声明）
      ↓
CSDN 图片转存（外部图片 → CSDN CDN）
      ↓
发布到各平台（图片统一引用 CSDN CDN）
```

核心思路：利用 CSDN 的图片转存 API 将外部图片转存到 CSDN CDN，后续发布到其他平台时图片引用 CSDN 链接，减少源站流量压力。

## 项目结构

```
src/halo_bridge/
├── cli.py              # Click CLI 定义
├── config.py           # YAML 配置加载
├── models.py           # 数据模型（Article, SyncResult, 各平台 Config）
├── exceptions.py       # 异常定义
├── source/
│   └── halo.py         # Halo 2.x API 客户端
├── targets/
│   ├── csdn.py         # CSDN 适配器（含 API 网关签名 + 图片转存）
│   ├── cnblogs.py      # 博客园适配器（REST API）
│   └── modb.py         # 墨天轮适配器
└── transforms/
    ├── image_urls.py   # 相对路径 → 绝对 URL
    ├── meta_referrer.py # <meta referrer> 标签
    └── copyright.py    # 版权声明追加
```

## 依赖

- Python 3.11+
- httpx
- click
- pyyaml
- Markdown

## 开发

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

## 注意事项

- Cookie/Token 会过期，过期后重新运行 `halo-bridge login <平台>` 即可
- CSDN API 网关签名算法从 CSDN 前端 JS 逆向获得，如果 CSDN 更新可能需要重新提取
- 博客园使用 REST API（`postType: 2`）发布到"文章"分类，XSRF-TOKEN 会在每次请求前自动刷新
- 墨天轮 API 未公开文档，通过抓包逆向实现

# SHARE Instrument Booking System — 开发、调试与部署指南

## 项目概览

**仓库**: `alexyudragonsword-collab/Equip_booking`，`main` 分支  
**部署平台**: Railway（容器化，挂载持久卷）  
**技术栈**: Python 3 · Flask · SQLAlchemy · SQLite · Gunicorn · Docker  
**前端**: Jinja2 模板 + 原生 HTML/CSS/JS（无框架）

---

## 目录结构

```
Equip_booking/
├── app.py                  # Flask 工厂函数，Blueprint 注册，DB 迁移
├── config.py               # 配置类（读取环境变量）
├── extensions.py           # db、login_manager 单例
├── models.py               # User、Instrument、Booking ORM 模型
├── mailer.py               # 邮件发送（SendGrid → Resend → SMTP 优先级）
├── gunicorn.conf.py        # Gunicorn 配置
├── Dockerfile
├── docker-entrypoint.sh    # 启动时 chown /data，然后 gosu app 降权
├── requirements.txt
├── routes/
│   ├── auth.py             # /auth/register  /auth/login  /auth/logout
│   ├── bookings.py         # /  /book  /cancel/<id>  /my-bookings
│   └── admin.py            # /admin/*
├── static/
│   ├── css/main.css        # 全局样式
│   ├── css/timeline.css    # 预定网格样式
│   ├── css/admin.css       # Admin 页面样式
│   ├── js/timeline.js      # 可视化网格渲染 + 拖选 + 仪器过滤
│   └── js/booking_form.js  # 表单模式预定
└── templates/
    ├── base.html           # 导航栏（SHARE logo）、flash 消息
    ├── auth/               # login.html  register.html
    ├── bookings/           # index.html  my_bookings.html
    └── admin/              # bookings.html  users.html  instruments.html
                            # settings.html  base_admin.html
```

---

## 本地开发

### 环境准备

```bash
cd Equip_booking
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### 初始化数据库

```bash
# 方式一：自动（推荐）
ADMIN_EMAIL=admin@example.com ADMIN_PASSWORD=secret123 \
  AUTO_INIT_DB=true flask run

# 方式二：手动
flask init-db
flask create-admin
```

数据库文件位于 `instance/booking.db`（SQLite）。

### 启动开发服务器

```bash
flask run          # http://127.0.0.1:5000
# 或
python app.py
```

### 关键环境变量（本地 `.env` 或 shell export）

| 变量 | 说明 |
|------|------|
| `SECRET_KEY` | Flask session 密钥（生产必填）|
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | 初始管理员账户 |
| `AUTO_INIT_DB=true` | 启动时自动建表、种植数据 |
| `SENDGRID_API_KEY` | 邮件发送（首选）|
| `NOTIFY_ADMIN_EMAIL` | 预定通知收件地址 |
| `DATABASE_URL` | PostgreSQL URI（留空则用 SQLite）|

---

## 常见开发任务

### 添加新路由

1. 在对应 Blueprint 文件（`routes/bookings.py` 等）中添加函数
2. 用 `@login_required` 和 `@admin_required`（如需）装饰
3. 如需新模板，在 `templates/` 对应目录创建，继承 `base.html` 或 `admin/base_admin.html`

### 修改数据库 Schema

1. 在 `models.py` 添加字段
2. 在 `app.py` 的 `_migrate_sqlite()` 中添加 `ALTER TABLE` 迁移语句（对 SQLite 安全，可重复执行）
3. 如需回填数据，在 `_auto_init_db()` 中添加更新逻辑

```python
# 示例：添加新列
new_columns = [
    ...
    ('users', 'new_field', 'VARCHAR(100)'),
]
```

### 修改前端网格

- **样式** → `static/css/timeline.css`
- **渲染逻辑**（格子着色、tooltip）→ `static/js/timeline.js` 的 `renderGrid()`
- **预定数据结构** → `routes/bookings.py` 的 `build_bookings_data()`，同步修改 JS 中对字段的读取

### 修改业务规则

所有预定校验集中在 `routes/bookings.py` 的 `book()` 视图函数中：
- 禁止周末、过去日期
- 时长 1–4 小时（09:00–17:00）
- 每周最多 3 次（普通用户）
- 普通用户只能预定 7 天内的时段

### 发送邮件

```python
from mailer import notify_booking_confirmed, notify_booking_cancelled
notify_booking_confirmed(current_app._get_current_object(), booking_info)
```

`mailer.py` 优先使用 `SENDGRID_API_KEY`，其次 `RESEND_API_KEY`，最后 SMTP。  
可在 Admin → Settings 页面发送测试邮件验证配置。

---

## 调试要点

### 常见问题

| 现象 | 原因 | 解决 |
|------|------|------|
| 预定网格只有第一个仪器能拖选 | popover 用了 `window.scrollY + rect`，而 popover 是 `position:fixed` | 去掉 `window.scrollY` |
| 预定后 tooltip 缺少 email/phone | `/book` 响应 JSON 未包含该字段 | 在 `book()` 返回的 `booking` 对象中加入字段 |
| 仪器过滤器切换周后被重置 | 过滤状态未持久化 | 使用 `localStorage.setItem('instrFilter', id)` 保存，在 `renderGrid()` 后恢复 |
| Railway 部署后数据库文件无法创建 | 挂载卷以 root 所有，app 用户无写权限 | `docker-entrypoint.sh` 以 root 运行 `chown -R app:app /data`，再 `gosu app` 降权 |
| 邮件发送失败（Railway）| Railway 屏蔽 SMTP 25/465/587 端口 | 改用 SendGrid Web API（HTTPS 443）|
| SendGrid 403 sender not verified | 发件地址未在 SendGrid 验证 | 在 SendGrid Dashboard → Single Sender Verification 验证发件地址 |

### 查看 Railway 日志

Railway Dashboard → 对应 Service → **Logs** 标签页，实时查看 Gunicorn 输出。

### 本地调试数据库

```bash
sqlite3 instance/booking.db
.tables
SELECT * FROM users;
SELECT * FROM bookings ORDER BY date DESC LIMIT 10;
```

---

## 部署到 Railway

### 首次部署

1. 在 Railway 创建新 Project → **Deploy from GitHub repo** → 选择 `alexyudragonsword-collab/Equip_booking`，分支选 `main`
2. 添加 **Volume**，挂载路径 `/data`
3. 在 Service → **Variables** 添加以下环境变量：

```
SECRET_KEY=<随机长字符串>
ADMIN_EMAIL=<管理员邮箱>
ADMIN_PASSWORD=<管理员密码>
AUTO_INIT_DB=true
DATABASE_URL=sqlite:////data/booking.db
SENDGRID_API_KEY=<SendGrid API Key>
NOTIFY_ADMIN_EMAIL=<通知接收邮箱>
```

4. Railway 自动检测 `Dockerfile` 并构建镜像，完成后访问生成的域名

### 后续更新

```bash
# 在 main 分支上完成修改后
git add <files>
git commit -m "描述改动"
git push -u origin main
```

Railway 检测到 `main` 分支有新 commit，自动触发重新构建和部署。

### 数据库迁移

`_migrate_sqlite()` 在每次启动时自动执行 `ALTER TABLE`（幂等），无需手动操作。  
新字段的回填逻辑写在 `_auto_init_db()` 中，同样幂等。

### 回滚

```bash
git revert HEAD        # 创建回滚 commit，push 后 Railway 自动重新部署
# 或在 Railway Dashboard → Deployments 中点击之前版本的 Redeploy
```

---

## 分支策略

- `main` — 生产分支，Railway 监听此分支自动部署
- 功能开发在新分支上进行，完成后 merge 到 `main`：

```bash
git checkout -b feature/my-feature
# ... 开发 ...
git checkout main
git merge feature/my-feature
git push origin main
```

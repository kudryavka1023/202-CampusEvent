# CampusEvent 校园活动报名与管理系统

实验二 baseline-v1：先设计（`uml/`、`requirements/`），后由 AI 辅助实现（`app/`、`tests/`）。

- 需求基线：`requirements/SRS.md`（v1.0）
- 需求验收表：`docs/需求验收表.md`（C1～C10、E1～E10、可扩展性验证，47/47 通过）
- 设计基线：`uml/设计说明书.md`、`uml/04-设计原则与模式.md`
- UML：`uml/01-usecase.drawio`、`uml/03-analysis-class.drawio`、`uml/06-design-class*.drawio`、三张顺序图、`uml/09-state.drawio`、`uml/10-activity-报名流程.drawio`
- 图件汇总（mermaid 重绘）：`docs/图件汇总.md`

## 1. 环境配置

```powershell
# Python 3.11+（本项目在 Python 3.14.3 验证通过）
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

依赖只有 Flask 与 pytest（`requirements.txt`）；数据库用 Python 内置 sqlite3，无需安装。

## 2. 运行

```powershell
.\.venv\Scripts\python.exe run.py
# 打开 http://127.0.0.1:5000/demo/login
```

演示身份（固定演示账号，不做注册/登录，假设 A-1）：

| 身份 | 账号 |
|---|---|
| 学生 | stu_demo1（张三）、stu_demo2（李四） |
| 管理员 | 演示入口点“以管理员身份进入” |

数据文件 `data/campus.db`（首次启动自动建表）；通知失败日志 `logs/notification-failure.log`。

## 3. 测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

覆盖（47 个用例）：

| 文件 | 覆盖 |
|---|---|
| tests/test_acceptance.py | C1～C10 核心验收 |
| tests/test_edge.py | E1～E10 边界/并发/异常 |
| tests/test_domain.py | 实体状态机、容量/时间规则、策略契约、事件键、读模型 |
| tests/test_notification.py | 通知幂等、失败隔离、消息内容 |
| tests/test_extensibility.py | CR-1 新增报名方式、CR-2 新增通知渠道（源码零修改断言） |
| tests/test_performance.py | NFR-01 冒烟（200 活动列表、500 报名统计 <2s） |
| tests/test_web.py | Web 路由、角色校验、表单流程冒烟 |

## 4. 代码结构与设计映射

```text
app/
  domain/           领域层：实体、枚举、值对象、策略（Strategy+Factory）、事件（Observer）
  application/      应用服务层：ActivityService / RegistrationService / StatisticsService / NotificationQueryService
  infrastructure/   基础设施层：SQLite 仓储实现、事务管理器（BEGIN IMMEDIATE）、连接提供者
  ui/               界面层：5 个控制器 + 路由 + Jinja2 模板（不直接访问 Repository）
  composition.py    组合根：启动时装配接口与实现（依赖倒置）
run.py              本地启动入口
tests/              自动化测试（含可扩展性验证）
```

设计要点（与 `uml/04-设计原则与模式.md` 对应）：

- **公共规则集中**：活动状态/重复/名额在 `RegistrationService`+`Activity`；策略只决定初始状态。
- **通知解耦**：报名事务提交后发布 `RegistrationEvent`；观察者失败只写日志不回滚；`eventKey = registrationId:eventType` 幂等（唯一约束兜底）。
- **并发**：写事务 `BEGIN IMMEDIATE` + 部分唯一索引；批准时复查名额（E2/E3 已验证）。
- **读模型**：活动列表/我的报名/审批列表/统计用一条 JOIN 查询，避免 N+1。

## 5. 可扩展性验证（代码编写过程中持续验证）

| 变更 | 做法 | 结论 |
|---|---|---|
| 新增报名方式（CR-1 抽签） | 只扩展枚举 + DB CHECK + 工厂注册 | `RegistrationService.submit` 源码零修改（测试断言） |
| 新增通知渠道（CR-2 邮件） | 只新增观察者并订阅 | 服务与发布者源码零修改（测试断言） |
| 策略契约 | 策略不查库、不修改上下文 | 契约测试通过 |

指标：新增类数 ≤1～2；核心业务类修改 0；回归失败 0（详见 `docs/需求验收表.md` §4）。

## 6. 部署（云服务器）

**线上地址**：<http://193.112.133.193:8080/>（演示入口：<http://193.112.133.193:8080/demo/login>）

服务器：Ubuntu（VM-0-7-ubuntu）｜ 部署目录：`/opt/202-CampusEvent` ｜ WSGI：gunicorn（2 worker）｜ 端口：8080

```bash
# 1. 建虚拟环境并装依赖
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt gunicorn

# 2. 建运行目录（data/ 与 logs/ 被 .gitignore 忽略，须手动创建，否则启动报 No such file or directory）
mkdir -p data logs

# 3. 后台启动（端口 8080，先用 ss -tlnp 确认空闲）
nohup gunicorn -w 2 -b 0.0.0.0:8080 "run:app" > logs/gunicorn.log 2>&1 &
echo $! > logs/gunicorn.pid
```

SQLite 单文件；生产用 waitress/gunicorn 多线程即可（写事务串行化）。上线前：改 `SECRET_KEY`、关闭 debug、保留 `data/` 与 `logs/` 目录权限；云厂商安全组需放行 8080 端口。

## 7. Git 流程

- 仓库：`https://github.com/kudryavka1023/202-CampusEvent.git`
- 分支：`main`。
- 标签：`baseline-v1`（初始验收版本，本阶段交付）。
- 提交约定：一个提交一件事；提交信息写“为什么”。

创建 baseline-v1 标签：

```bash
git add -A
git commit -m "docs: 补充云部署说明与图件汇总"
git tag -a baseline-v1 -m "实验二初始验收版本：47/47 测试通过，已部署上线"
git push origin main --tags
```

## 8. AI 使用记录

见 `AI_DEV_LOG.md`（提示策略、生成物、人工核对与验证结果）。

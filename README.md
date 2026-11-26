# CampusEvent 校园活动报名与管理系统

实验二 baseline-v1 + change-v2：先设计（`uml/`、`requirements/`），后由 AI 辅助实现（`app/`、`tests/`）。change-v2 按教师变更单 CR-01（年级限定报名）与 CR-02（模拟邮件通知）增量修改。

- 需求基线：`requirements/SRS.md`（v1.1）
- 需求验收表：`docs/需求验收表.md`（C1～C10、E1～E10、CR1/CR2，59/59 通过）
- 设计基线：`uml/设计说明书.md`（v1.2）、`uml/04-设计原则与模式.md`
- 变更影响分析：`docs/CR-01-CR-02-影响分析.md`
- 两版对比：`docs/baseline-v1-vs-change-v2.md`
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
| 学生 大一 | stu_demo1（张三，年级 1） |
| 学生 大二 | stu_demo2（李四，年级 2） |
| 学生 大三 | stu_demo3（王五，年级 3） |
| 学生 大四 | stu_demo4（赵六，年级 4） |
| 管理员 | 演示入口点“以管理员身份进入” |

数据文件 `data/campus.db`（首次启动自动建表；已有 baseline 数据库会自动补 `students.grade/email`、`activities.allowed_grades`、`email_log`）；通知/邮件失败日志 `logs/notification-failure.log`。

## 3. 测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

覆盖（59 个用例）：

| 文件 | 覆盖 |
|---|---|
| tests/test_acceptance.py | C1～C10 核心验收 |
| tests/test_edge.py | E1～E10 边界/并发/异常 |
| tests/test_domain.py | 实体状态机、容量/时间规则、策略契约、事件键、读模型 |
| tests/test_notification.py | 通知幂等、失败隔离、消息内容 |
| tests/test_extensibility.py | CR-1 新增报名方式、CR-2 新增通知渠道（源码零修改断言） |
| tests/test_performance.py | NFR-01 冒烟（200 活动列表、500 报名统计 <2s） |
| tests/test_web.py | Web 路由、角色校验、表单流程冒烟 |
| tests/test_change_v2.py | CR1-01～05、CR2-01～05、年级表单/邮件页 Web 冒烟（12 个） |

## 4. 代码结构与设计映射

```text
app/
  domain/           领域层：实体、枚举、值对象、策略（Strategy+Factory）、资格规则（EligibilityRule）、事件（Observer）
  application/      应用服务层：ActivityService / RegistrationService / StatisticsService / NotificationQueryService / EmailLogQueryService
  infrastructure/   基础设施层：SQLite 仓储实现、MockEmailSender、事务管理器（BEGIN IMMEDIATE）、连接提供者
  ui/               界面层：6 个控制器 + 路由 + Jinja2 模板（不直接访问 Repository）
  composition.py    组合根：启动时装配接口与实现（依赖倒置）
run.py              本地启动入口
tests/              自动化测试（含可扩展性与 CR 验收）
```

设计要点（与 `uml/04-设计原则与模式.md` 对应）：

- **公共规则集中**：活动状态/重复/年级/名额在 `RegistrationService` + `Activity` + `EligibilityRule`；策略只决定初始状态。
- **年级限定（CR-01）**：`CompositeEligibilityRule` 组合 `GradeEligibilityRule`；未配置允许年级时直接通过，baseline 行为不变。
- **通知解耦（CR-02）**：报名事务提交后发布 `RegistrationEvent`；站内消息与模拟邮件是两个观察者；失败只写日志不回滚；`eventKey = registrationId:eventType` 幂等（两张表唯一约束兜底）。
- **邮件范围**：直接报名通过、审核通过、审核拒绝；审核型提交与取消不发邮件。
- **并发**：写事务 `BEGIN IMMEDIATE` + 部分唯一索引；批准时复查名额（E2/E3 已验证）。
- **读模型**：活动列表/我的报名/审批列表/统计用一条 JOIN 查询，避免 N+1。

## 5. 可扩展性与变更实测

| 变更 | 做法 | 结论 |
|---|---|---|
| baseline 模拟 CR-1 抽签 | 只扩展枚举 + DB CHECK + 工厂注册 | `RegistrationService.submit` 源码零修改（测试断言） |
| baseline 模拟 CR-2 邮件 | 只新增观察者并订阅 | 服务与发布者源码零修改（测试断言） |
| 实际 CR-01 年级限定 | 新增 `EligibilityRule` 组合 + 活动字段 | 策略未改；修改 2 个核心类（`Activity`、`RegistrationService`） |
| 实际 CR-02 模拟邮件 | 新增观察者 + 发送器 + `email_log` 仓储/查询/页面 | `RegistrationService` 无邮件代码；修改 0 个核心业务类 |

**change-v2 实测指标：** 新增 14 个类型（13 类 + 1 枚举）；修改核心业务类 4 个（`Student`、`Activity`、`ActivityService`、`RegistrationService`）；回归失败 0（59 passed）；AI 交互 2 轮；约 1 小时。详见 `docs/需求验收表.md` §9 与 `uml/设计说明书.md` 13.5。

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
- 标签：`baseline-v1`（初始验收版本）；`change-v2`（CR-01/CR-02 变更验收版本，待用户复核后创建）。
- 提交约定：一个提交一件事；提交信息写“为什么”。

baseline-v1 已提交并打标签；change-v2 在 `main` 上增量提交，创建标签命令：

```bash
git add -A
git commit -m "feat: 实现 CR-01 年级限定与 CR-02 模拟邮件通知"
git tag -a change-v2 -m "实验二变更版本：59/59 测试通过，CR-01/CR-02 验收完成"
git push origin main --tags
```

> 按用户要求，`change-v2` 标签在用户复核后再创建/推送；代码与文档已提交到 `main`，标签创建是最后一步。

## 8. AI 使用记录

见 `AI_DEV_LOG.md`（提示策略、生成物、人工核对与验证结果；含 change-v2 的交互轮次、修改时长与回归指标）。

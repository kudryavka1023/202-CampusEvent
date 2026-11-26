# AI_DEV_LOG — CampusEvent baseline-v1 + change-v2

> 按实验二要求保留 AI 交互与人工核对记录；详细过程见各阶段文档。

## 1. 背景与分工

- 输入：实验二 P2-F01～F08 + 附录 B；`requirements/SRS.md`（v1.0）；`uml/` 全部图件与设计说明书。
- AI 职责：按既有需求/设计生成实现骨架、测试、文档更新；**不发明需求**。
- 人工职责：核对设计契约（方法签名、错误码、事务边界、幂等），运行并确认测试，审核 Git 提交。

## 2. 生成与验证过程

| 步骤 | 内容 | 验证方式 | 结果 |
|---|---|---|---|
| 1 | 按设计类图实现领域层（实体/枚举/值对象/策略/事件） | 单元测试 test_domain.py | 通过 |
| 2 | 实现基础设施层（DDL/仓储/事务管理器） | 验收/边界测试 | 通过 |
| 3 | 实现应用服务层（公共规则、事务、事件发布） | C1～C10、E1～E10 | 通过 |
| 4 | 实现界面层（控制器/路由/模板/CSRF/演示会话） | Web 冒烟测试 | 通过 |
| 5 | 可扩展性验证（CR-1/CR-2 模拟 + 源码零修改断言） | test_extensibility.py | 通过 |
| 6 | 性能冒烟（200 活动列表、500 报名统计） | test_performance.py | <2s |
| 7 | 回填验收表、回归测试表、SRS/设计说明书状态 | 人工核对 | 完成 |

## 3. 关键设计决策落点（代码证据）

| 决策 | 代码位置 |
|---|---|
| 策略只决定初始状态 | `app/domain/policies.py`；公共规则在 `app/application/services.py::RegistrationService.submit` |
| 通知解耦与幂等 | `app/domain/events.py`（发布者 try/catch、`MessageNotificationObserver`、eventKey） |
| 事务边界 | `app/infrastructure/transactions.py`（`BEGIN IMMEDIATE`） |
| 部分唯一索引兜底 | `app/infrastructure/db.py` `ux_registration_active` |
| 依赖倒置/组合根 | `app/composition.py` |
| 读模型避免 N+1 | `app/infrastructure/repositories.py`（`search_summaries`/`find_by_student`/`statistics`） |

## 4. 已知取舍（如实记录）

- 单机 SQLite 写吞吐有限（10 并发口径）；多实例需换 PostgreSQL（CR-4 预案）。
- 进程内同步通知；提交与发布间崩溃由启动补偿脚本兜底（初始版本未实现脚本，风险已记录）。
- `StudentRepository.all()` 为演示入口增加的方法，不属于设计类图的最小接口。

## 5. 复核清单（人工）

- [x] 错误码与设计说明书 9.1 一致
- [x] 方法签名与设计类图一致（snake_case 为 Python 化，语义不变）
- [x] C1～C10、E1～E10 全部通过（47/47）
- [x] 无密钥/敏感信息入库；`data/`、`logs/`、`.venv/` 已 gitignore
- [x] 未提前实现变更单（CR）内容；仅以测试模拟扩展点

---

## 6. change-v2（CR-01/CR-02）记录

### 6.1 输入与边界

- 输入：教师变更单 `实验二教师专用材料.docx`；已评审的 baseline-v1；`docs/CR-01-CR-02-影响分析.md`。
- AI 职责：按变更单实现年级限定与模拟邮件，更新 UML/文档，跑全量回归；**不扩大需求范围**（不接真实 SMTP、不做学生管理界面）。
- 人工职责：确认变更范围与设计取舍，复核标签创建时机。

### 6.2 交互与时长（实测）

| 项 | 值 | 口径 |
|---|---|---|
| AI 交互轮次 | 2 | 用户指令：需求下发、继续执行；工具调用不计 |
| 开始时间 | 2026-11-26 16:10 | 变更实现起点 |
| 结束时间 | 2026-11-26（回归/文档完成） | 以最终 `pytest` 通过为准 |
| 修改总时长 | 约 1 小时 | 含代码、UML 生成、文档、回归 |
| 回归失败 | 0 | 59 passed（47 baseline + 12 新增） |
| 新增类型 | 14（13 类 + 1 枚举） | `git diff` / 新增文件 |
| 修改核心业务类 | 4 | `Student`、`Activity`、`ActivityService`、`RegistrationService` |

### 6.3 生成与验证过程

| 步骤 | 内容 | 验证方式 | 结果 |
|---|---|---|---|
| 1 | 读取教师变更单，写影响分析（范围/备选/风险/测试） | 人工核对 | 完成 |
| 2 | CR-01：资格规则、实体字段、服务钩子、表单/列表/详情 | CR1-01～04 + Web 冒烟 | 通过 |
| 3 | CR-02：观察者、发送器、邮件记录仓储/查询/页面 | CR2-01～04 + Web 冒烟 | 通过 |
| 4 | 数据库增量迁移（grade/email/allowed_grades/email_log） | 重启/旧库迁移测试 | 通过 |
| 5 | 更新用例图、分析类图、设计类图、三张顺序图、活动图、状态图 | `validate_all.py`、`check_class_edges.py` | 通过 |
| 6 | 全量回归（含 baseline C1～C10、E1～E10） | `pytest -q` | 59 passed |
| 7 | 回填 SRS/用例规格/设计说明书/模式报告/验收表/README | 人工核对 | 完成 |

### 6.4 关键决策落点（代码证据）

| 决策 | 代码位置 |
|---|---|
| 年级是资格规则，不是新策略 | `app/domain/rules.py`；`RegistrationService.check_eligibility` |
| 规则顺序：存在→未开始→重复→年级→名额→策略 | `app/application/services.py::RegistrationService.submit` |
| 邮件是第二个观察者 | `app/domain/events.py::EmailNotificationObserver` |
| 邮件失败先记 FAILED 再抛出 | `app/infrastructure/email.py::MockEmailSender.send` |
| 幂等键唯一 | `messages.event_key`、`email_log.event_key` |
| 增量迁移旧库 | `app/infrastructure/db.py::_migrate` |

### 6.5 复核清单（人工）

- [x] CR1-01～05、CR2-01～05 全部通过
- [x] baseline C1～C10、E1～E10 无回退
- [x] 邮件失败不回滚报名；重复事件不重复通知
- [x] `RegistrationService` 无邮件代码；策略接口未改
- [x] 旧数据库可增量迁移；演示学生覆盖 1—4 年级
- [x] 未创建/推送 `change-v2` 标签（等待用户复核）
- [ ] 用户复核后创建 `change-v2` 标签并推送

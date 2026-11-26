# baseline-v1 与 change-v2 对比报告

| 项目 | baseline-v1 | change-v2 |
|---|---|---|
| 日期 | 2026-11-22 | 2026-11-26 |
| 需求范围 | P2-F01～P2-F08 | P2-F01～P2-F08 + CR-01 年级限定 + CR-02 模拟邮件 |
| 测试结果 | 47 passed / 0 failed | **59 passed / 0 failed**（47 baseline + 12 新增） |
| 需求文档 | `requirements/SRS.md` v1.0 | v1.1（FR-09/FR-10、BR-23～BR-27、DR-06、UC9、CR1/CR2） |
| 设计文档 | `uml/设计说明书.md` v1.0/v1.1 | v1.2（新增第 13 部分变更设计） |
| 验收证据 | `docs/需求验收表.md` baseline 段 | 同文件 change-v2 段 |
| Git 标签 | `baseline-v1` | `change-v2`（本地已创建，待推送） |

## 1. 变更内容

| 变更 | 实现方式 | 关键类/文件 |
|---|---|---|
| CR-01 年级限定 | 可组合资格规则；活动保存允许年级；报名先查年级再查名额 | `EligibilityRule`、`CompositeEligibilityRule`、`GradeEligibilityRule`、`EligibilityViolation`、`Activity.allowedGrades`、`Student.grade` |
| CR-02 模拟邮件 | 第二个观察者订阅现有报名事件；邮件记录独立仓储；失败只留痕 | `EmailNotificationObserver`、`EmailSender`、`MockEmailSender`、`EmailLog`、`EmailLogRepository`、`SqliteEmailLogRepository`、`EmailLogQueryService` |

## 2. 要求的五项指标

| 指标 | 实测值 | 口径 |
|---|---|---|
| 新增类数 | **14 个类型（13 个类 + 1 个枚举）** | 新增文件中定义的类/接口/值对象/仓储实现，加既有文件中新增的类型；不含新增方法、错误码、模板、测试函数 |
| 修改核心业务类数 | **4 个** | 既有实体 + 应用服务：`Student`、`Activity`、`ActivityService`、`RegistrationService` |
| 回归失败数 | **0** | `pytest -q`：59 passed；C1～C10、E1～E10 全量重跑 |
| AI 交互轮次 | **2 轮** | 本变更会话的用户指令轮次（需求下发、继续执行）；工具调用不计 |
| 修改总时长 | **约 52 分钟** | 2026-11-26 16:10 起至代码、UML、文档、回归完成 |

### 2.1 新增类型明细（14）

1. `EligibilityRule`（接口）
2. `CompositeEligibilityRule`
3. `GradeEligibilityRule`
4. `EligibilityViolation`（值对象）
5. `EmailSender`（接口）
6. `EmailLogRepository`（接口）
7. `EmailNotificationObserver`
8. `MockEmailSender`
9. `EmailLog`（值对象/读模型）
10. `EmailMessage`（值对象）
11. `EmailStatus`（枚举）
12. `EmailLogQueryService`
13. `SqliteEmailLogRepository`
14. `EmailLogController`

### 2.2 修改的支撑类（不计入核心业务类）

`RegistrationContext`（加入 `student`）、`SqliteActivityRepository`（读写允许年级）、`SqliteStudentRepository`（读写年级/邮箱）、`ActivityController`（表单/提示）。

> 口径说明：核心业务类只统计“既有实体 + 应用服务”。基础设施仓储、控制器、值对象单列为支撑类，避免把“改动文件数”混同为“修改核心业务类数”。

## 3. 验收结果

| 编号 | 结果 | 证据 |
|---|---|---|
| CR1-01 | 通过 | 年级 2 报名成功，`APPROVED` |
| CR1-02 | 通过 | 年级 3 报名成功，`APPROVED` |
| CR1-03 | 通过 | 年级 1 拒绝，`GRADE_NOT_ALLOWED`，含允许年级/当前年级 |
| CR1-04 | 通过 | 年级 4 拒绝，原因明确 |
| CR1-05 | 通过 | baseline C1～C10 全量回归 |
| CR2-01 | 通过 | 直接通过：站内消息 + 邮件记录各 1 条 |
| CR2-02 | 通过 | 审核通过/拒绝：两渠道均有，拒绝邮件含理由 |
| CR2-03 | 通过 | 邮件失败：报名仍 `APPROVED`，`email_log=FAILED`，失败日志存在 |
| CR2-04 | 通过 | 重复动作：消息/邮件均不重复 |
| CR2-05 | 通过 | baseline C1～C10 全量回归 |
| Web 冒烟 | 通过 | 年级表单/拒绝提示、管理员邮件记录页 |

## 4. 结论

- CR-01 的年级限制没有新增 `PolicyType`，策略接口未改；年级与报名方式保持正交。
- CR-02 的邮件没有进入 `RegistrationService`，只新增观察者与记录设施；邮件失败不回滚报名。
- baseline 行为无回退；全部 59 个测试通过。
- 代价：新增类型 14 个，多于初始预估（邮件预估 ≤1 类），主要因为邮件记录需要独立的仓储、查询、控制器与页面才能满足“可查看收件人/主题/内容/状态/时间”的验收要求；核心业务类修改 4 个，主要来自年级字段与表单校验，邮件本身未改核心服务。

> 标签 `change-v2` 已在本地创建，未推送；推送命令：`git push origin main --tags`。

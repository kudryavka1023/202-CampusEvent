# AI_DEV_LOG — CampusEvent baseline-v1

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

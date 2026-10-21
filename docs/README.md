# 文档索引 / Documentation Index

> 本页由 `scripts/build_doc_index.py` 自动生成，请勿手工编辑。

共 36 篇设计文档，按主题分组。

## 目标与计划 / Goals and Plan

- [项目目标文档](GOALS.md)
- [项目执行计划](PLAN.md)

## 架构与结构图 / Architecture

- [Android Device Matrix and Parallel Evidence](architecture/android-device-matrix.md)
- [Android Screen Framework](architecture/android-screen-framework.md)
- [Android System Interactions](architecture/android-system-interactions.md)
- [Mobile Driver Call Chain](architecture/mobile-driver-call-chain.md)
- [项目结构与技术栈总览](architecture/project-overview.md)

## 架构决策 / ADR

- [ADR-0001: 本地 SUT 使用 Docker Compose / Local SUT with Docker Compose](adr/0001-local-sut-with-docker-compose.md)
- [ADR-0002: HTTP 客户端超时与重试边界 / HTTP Client Timeout and Retry Boundaries](adr/0002-http-client-timeout-and-retry.md)
- [ADR-0003: 本地 OAuth2/OIDC 认证与刷新轮换边界](adr/0003-local-oauth2-jwt-and-refresh-rotation.md)
- [ADR-0004: OpenAPI 契约来源与兼容性判定](adr/0004-openapi-contract-source-and-compatibility.md)
- [ADR-0005: 错误分类、幂等与状态机契约](adr/0005-api-error-taxonomy-idempotency-and-state-machine.md)
- [ADR-0006: 测试命名空间与并行数据隔离 / Test Namespaces and Parallel Data Isolation](adr/0006-test-namespace-and-parallel-data-isolation.md)
- [ADR-0007: 事务、隔离级别与锁测试策略](adr/0007-transaction-isolation-and-lock-testing.md)
- [ADR-0008: 缓存旁路、TTL 与最终一致性策略](adr/0008-cache-aside-ttl-and-eventual-consistency.md)
- [ADR-0009: RBAC 能力矩阵、BOLA 与输入加固](adr/0009-rbac-bola-and-input-hardening.md)
- [ADR-0010: 并行连接预算、故障注入与缺陷草稿](adr/0010-parallel-budgets-fault-injection-and-defect-drafts.md)

## 测试策略 / Test Strategy

- [Defect Lifecycle, Fingerprint, and Allure Linking](test-strategy/defect-lifecycle-and-allure.md)

## 排障手册 / Runbooks

- [Android Device Matrix Triage](runbooks/android-device-matrix-triage.md)
- [Android Locator and Wait Triage](runbooks/android-locator-and-wait-triage.md)
- [Android Permissions and Recovery Triage](runbooks/android-permissions-and-recovery-triage.md)
- [Android Session Debugging](runbooks/android-session-debugging.md)
- [负向、幂等与状态机失败排查 / API Negative, Idempotency, and State Failure Triage](runbooks/api-negative-and-state-failures.md)
- [认证失败排查 / Authentication Failure Triage](runbooks/authentication-failures.md)
- [Authorization and Input Security Triage](runbooks/authorization-and-input-security-triage.md)
- [API 契约失败排查 / API Contract Failure Triage](runbooks/contract-test-failures.md)
- [数据库锁等待与死锁排查 / Database Lock-Wait and Deadlock Triage](runbooks/database-lock-and-deadlock-triage.md)
- [Failed Quality Gate Triage Runbook](runbooks/failed-quality-gate.md)
- [Fault Injection and Defect Draft Triage](runbooks/fault-injection-and-defect-drafts.md)
- [iOS WDA Build and Signing Triage](runbooks/ios-wda-signing-triage.md)
- [iOS XCUITest Simulator and Device Environment Runbook](runbooks/ios-xcuitest-simulator.md)
- [Local SUT Docker Compose Runbook](runbooks/local-sut-compose.md)
- [并行数据隔离失败排查 / Parallel Data-Isolation Failure Triage](runbooks/parallel-data-isolation-failures.md)
- [Redis Cache and Consistency Triage](runbooks/redis-cache-and-consistency-triage.md)
- [Week 1 Environment Recovery](runbooks/week1-environment-recovery.md)
- [Yuque Project Hub Runbook](runbooks/yuque-project-hub.md)

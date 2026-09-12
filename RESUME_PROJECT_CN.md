# 中文简历项目表述

## 项目名称

**Reliable Agent Runtime｜有状态、可恢复、可审计的 Agent Runtime MVP**

## 技术栈

Python、Pydantic、SQLite、MCP protocol boundary、pytest；显式条件状态工作流，
官方 MCP SDK adapter 已通过真实 stdio fixture 集成测试。

## 项目经历（推荐版）

- 面向高敏感对话场景实现有状态 Agent Runtime，设计 `extract → retrieve → generate → safety → confirmation → persist` 工作流，统一管理结构化状态、条件路由和用户确认中断。
- 在 MCP 工具边界实现超时、指数退避重试、fallback、结构化错误和幂等保存；使用 SQLite 持久化带版本号的 checkpoint 与 append-only 审计事件，支持中断恢复和运行回放。
- 使用 Pydantic 约束模型输出，加入高风险安全出口与未确认结果不落库规则；构建 24 个确定性场景及工具错误、超时、永久非法输出、重复确认、旧 checkpoint、并发 checkpoint 与真实 MCP stdio fixture 等故障注入测试，当前共 36 个测试通过。

## 面试时的准确定位

这是基于开源 Agent 工程思想实现的独立 MVP。当前核心协调器是显式状态机，官方 MCP SDK adapter 已完成真实 stdio fixture 集成测试；没有把 LangGraph 或 MCP 协议本身包装成自研。

## 不要提前写入简历的内容

- 生产级可用性、吞吐量或成本下降比例；
- 长期记忆、Phoenix 完整部署、多 Agent 辩论；
- 未经实测的成功率、恢复率或用户效果；
- “独立开发 LangGraph/MCP”。

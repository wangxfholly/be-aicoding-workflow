# Goal Contract：目标形式化与可机检预检

loop 的第一件事不是写代码，是把"目标"变成**可机检**的 acceptance criteria。不可机检的目标会让 goal-verifier 只能回退问人，loop 也就退化成普通的 harness。

## 1. 每条 acceptance criterion 必须是一个三元组

**每条 acceptance criterion 必须**同时具备以下三项，缺一不可：

| 要素 | 含义 | 反例 |
| --- | --- | --- |
| 命令 | `commands.*` 中的一个 key（`build` / `unit_test` / `integration_test`） | 「跑一下看看」 |
| 通过条件 | 可观测、布尔化的判据 | 「性能良好」「代码优雅」 |
| 证据载体 | 承载该判据的 artifact 或退出码 | 「感觉对了」 |

示例：

```json
{
  "id": "AC-1",
  "assertion": "全量单元测试通过",
  "command": "unit_test",
  "pass_condition": "exit status == 0",
  "evidence": "verify.unit_test 的 artifact 与退出码"
}
```

不可判定的诉求不得塞进 criteria。它们必须二选一：

- 放入 **non-goals**：明确本次不做的范围；
- 放入 **open questions**：需要人类先回答才能形式化的问题。

这与 `ai-workflow-harness-grill` 处理 PRD 的方式一致：acceptance criteria、non-goals、open questions 是同一个三件套，缺了后两者，criteria 会不断膨胀成愿望清单。

## 2. 存放位置：按 profile 分层

| 方案 | 载体 | 主 Agent 可写 | full profile | grill profile | child 能否看到 |
| --- | --- | --- | --- | --- | --- |
| A | `spec.spec` 产出的 `technical-spec.md` | 否（须由 spec-writer child 写） | 是 | 否（无 spec node） | 是（进 dispatch packet） |
| B | `plan.prd`（workflow-owned） | 是 | **否**（`stage-owned` 只认 workflow_owned node） | **是** | 是 |

**grill profile 下**用方案 B：`plan.prd` 是 run graph 中唯一的 workflow-owned node，主 Agent 是它的作者，`workflow stage-owned` 会提供不可变副本、摘要与路径授权。这是主 Agent 唯一能机械登记自己文档的口子。

**full profile 下**用方案 A：criteria 必须是 `spec.spec` 的交付物。

## 3. full profile 的信息流断点（重要）

child 的唯一初始上下文是 Helper 生成的 `prompt_file`，其中只含 Helper 组装的 packet。**loop 没有任何合法手段把自己写的文档塞进 coder 的上下文。**

因此 full profile 下存在**信息流断点**：

- criteria 若想被 coder 看见，必须是 `spec.spec` child 的交付物。
- loop 只能**要求**它、**检查**它，不能自己补写。
- 若 spec-writer 没有写出可机检的 criteria，loop 只能 `workflow block`，不得自己造一份继续跑。

这会让 full profile 的首次成功率显著低于 grill profile，需要在选用时如实告知。

## 4. 可机检性预检（round 1 之前必做）

在第一次 `workflow begin` 之前，从 `workflow status` 的 `run_graph` 或 `config show` 核对：

1. 每条 criterion 依赖的 node **确实在图上**。
2. 注意 `disabled_nodes` 与"config 缺对应命令"都会把 node 从图上剔除——`verify.integration_test` 在未配置 `integration_test` 命令时根本不生成。
3. 依赖被剔除的 criterion 无法机检，必须降级并在 block reason 中点名。

这一步把"目标必须可机检"从口号变成一次机械检查：**node 不在图上 ⇒ 该 criterion 不可机检**。

## 5. criteria 冻结

round 1 开始前，对 criteria 集合算一次摘要并写入 ledger，作为本轮之后的比对基线。

中途变更 criteria 属于**人类决定**，不是 loop 的自主行为：

- grill profile：走 `plan.prd` 的 rerun，重新走一次 Review Gate；
- full profile：走 `spec.spec` 的 rerun。

loop 不得在轮次之间悄悄放宽或收紧 criteria——那会让"达标"变成一个移动靶，也会让停滞检测失去基准。

冻结摘要进 ledger 的 `criteria-digest.txt`，之后每轮开头重算一次并比对：不一致即说明 criteria 被改动过，必须回到人类，不得继续自动迭代。

## 6. 与 child 契约的关系

criteria 是**验收契约**，不是实现指令。它约束的是"做完要能证明什么"，不规定怎么实现：

- 不得把 criteria 写成实现步骤（那属于 `plan.solution`）。
- 不得把 criteria 写成测试代码（那属于 `plan.test_strategy` 与 `implement.code`）。
- child 不得为了满足 criterion 而改写该 criterion；发现 criterion 写错只能上报，不能自改。

这条边界的作用是保住"写的人不判自己的人"：criteria 的作者、实现者、判定者必须是三个不同角色。方案同样分开：design-researcher 出 brief，planner 或 grill 主 Agent 写 plan artifact，design-critic 在编码前审拆解。三者都不是 goal-verifier。

## 7. 反例清单

以下措辞一律视为不可机检，必须改写或移出 criteria：

| 不可机检写法 | 改写方向 |
| --- | --- |
| 性能良好 | 某命令在给定输入下退出码为 0 且耗时低于阈值 |
| 代码优雅 | 通过既有的 lint / 静态检查命令 |
| 覆盖全面 | `unit_test` 退出码为 0 且覆盖率不低于给定值 |
| 兼容旧版本 | 指定的兼容性测试命令退出码为 0 |
| 用户体验更好 | 移入 non-goals 或 open questions |

改写的判据只有一条：**"能否由某个命令的退出码或某份 artifact 的内容判定真伪"**。答不上来就不算可机检。

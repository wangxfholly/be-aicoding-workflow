from pathlib import Path

import json
import re


SKILL_DIR = Path("skills/ai-goal-loop")

REFERENCE_FILES = (
    "references/design-research.md",
    "references/loop-control.md",
    "references/goal-contract.md",
    "references/goal-verifier.md",
    "references/evidence-ledger.md",
    "references/non-convergence.md",
)


def _read(relative: str = "SKILL.md") -> str:
    return (SKILL_DIR / relative).read_text(encoding="utf-8")


def test_goal_loop_frontmatter_and_display_metadata_are_canonical() -> None:
    skill = _read()
    metadata = _read("agents/openai.yaml")
    assert skill.startswith(
        "---\nname: ai-goal-loop\n"
        "description: Use when 用户显式要求 multi-agent 自我迭代直至达标、"
        "goal-driven loop，或要求把测试证据回灌给 coder 的多轮收敛。\n---\n"
    )
    assert 'display_name: "AI Goal Loop"' in metadata
    assert "多 agent 自我迭代" in metadata
    display_line = next(line for line in metadata.splitlines() if "display_name:" in line)
    assert display_line.isascii()


def test_goal_loop_defines_budget_math_and_two_topologies() -> None:
    skill = _read()
    for phrase in (
        "ai-workflow-harness 之上的自动驱动层",
        "run_graph 是唯一调度真值",
        "max_attempts",
        "attempts[phase]",
        "单调递增",
        "Shape 1",
        "Shape 2",
        "review-accept",
        "human_review",
        "attempt_limit",
        "goal-verifier",
        "design-researcher",
        "design-critic",
        "不得在方案未被接受时开始编码",
        "workflow init --goal-loop",
        "verify_repair: auto",
        "其他 skill 不传 `--goal-loop`",
        "acceptance criteria",
        "不可机检",
        "不得编辑 `.ai-workflow.yaml`",
        "不得新建 run 来重置 attempt 预算",
        "方案先审、测试失败自修、终点人工",
    ):
        assert phrase in skill
    assert len(skill.splitlines()) >= 90


def test_goal_loop_pins_skill_dir_to_the_harness() -> None:
    skill = _read()
    for phrase in (
        "skills/ai-workflow-harness",
        "--skill-dir",
        "common-phase-contract.md",
        "invalid_skill_dir",
        "本 skill 不能作为 `--skill-dir`",
    ):
        assert phrase in skill


def test_goal_loop_references_cover_control_criteria_verifier_ledger_block() -> None:
    control = _read("references/loop-control.md")
    contract = _read("references/goal-contract.md")
    verifier = _read("references/goal-verifier.md")
    ledger = _read("references/evidence-ledger.md")
    block = _read("references/non-convergence.md")

    for phrase in (
        "attempts[phase]",
        "current_attempts",
        "apply_reruns",
        "只重置 earliest phase 之后",
        "同一 phase 内的兄弟 node 不受影响",
        "Shape 1",
        "Shape 2",
        "workflow init --goal-loop",
        "verify_repair: auto",
        "无 rerun 的达标终审不自动接受",
        "review_mode 在 `init` 时冻结",
        "UNABLE_REASON",
        "unable_to_complete",
        "actionable reason",
        "不得用 `workflow abort`",
    ):
        assert phrase in control

    for phrase in (
        "每条 acceptance criterion 必须",
        "可机检",
        "non-goals",
        "open questions",
        "disabled_nodes",
        "plan.prd",
        "spec.spec",
        "信息流断点",
        "criteria 冻结",
    ):
        assert phrase in contract

    for phrase in (
        "不是 run_graph node",
        "loop-owned child",
        "blind",
        "不读实现者的推理",
        "verdict",
        "met",
        "unmet",
        "unverifiable",
        "不得修改 workflow state",
        "不得调用 workflow helper",
        "不得把 verdict 当作 phase 通过",
    ):
        assert phrase in verifier

    for phrase in (
        "artifact.sha256",
        "implementation_baseline",
        "head_revision",
        "dirty_paths",
        "归一化",
        "剔除",
        "sorted(finding.title)",
        "假阴性",
        "假阳性",
        "连续两轮",
        "AND",
    ):
        assert phrase in ledger

    for phrase in (
        "预算耗尽",
        "指纹停滞",
        "acceptance criteria 不可机检",
        "环境或权限失败",
        "workflow block",
        "仍失败的 acceptance criteria",
        "不得 self-block + self-resume",
        "resume --rerun",
    ):
        assert phrase in block

    assert len(control.splitlines()) >= 90
    assert len(contract.splitlines()) >= 80
    assert len(verifier.splitlines()) >= 80
    assert len(ledger.splitlines()) >= 80
    assert len(block.splitlines()) >= 70


def test_goal_loop_exact_command_order_is_documented() -> None:
    skill = _read()
    blocks = re.findall(r"```text\n(.*?)```", skill, re.DOTALL)
    assert blocks, "SKILL.md must contain a text control-order block"
    control = blocks[0]
    lines = [line.strip() for line in control.splitlines() if line.strip()]
    expected_order = (
        "workflow status",
        "design-researcher",
        "workflow begin --phase plan",
        "design-critic",
        "workflow review-accept",
        "workflow begin --phase implement",
        "workflow stage",
        "workflow finalize",
        "workflow review",
        "workflow transition",
        "workflow begin --phase verify",
        "goal-verifier",
        "workflow review --rerun",
        "workflow transition",
    )
    position = -1
    for phrase in expected_order:
        next_position = next(
            (
                index
                for index, line in enumerate(lines)
                if phrase in line and index > position
            ),
            -1,
        )
        assert next_position > position, phrase
        position = next_position


def test_goal_loop_verdict_example_has_exact_keys() -> None:
    verifier = _read("references/goal-verifier.md")
    blocks = re.findall(r"```json\n(.*?)```", verifier, re.DOTALL)
    assert blocks, "goal-verifier.md must contain a json verdict example"
    verdict = json.loads(blocks[0])
    assert set(verdict) == {"verdict", "criteria", "blockers", "recommended_node"}
    assert verdict["verdict"] in {"met", "unmet", "unverifiable"}
    assert isinstance(verdict["criteria"], list) and verdict["criteria"]
    assert set(verdict["criteria"][0]) == {"id", "status", "evidence", "command", "observed"}


def test_design_review_blocks_coding_until_plan_is_accepted() -> None:
    skill = _read()
    design = _read("references/design-research.md")
    for phrase in (
        "implement 之前",
        "不得 `workflow begin --phase implement`",
        "design-brief.md",
        "不产出 `met` / `unmet`",
        "plan.prd",
        "plan.solution",
        "no-paper-found",
        "ai-agent-book/skills",
        "不得编造引用",
        "不进停滞指纹",
    ):
        assert phrase in skill or phrase in design
    assert "verify 审的是已经写出来的代码" in design
    assert "不得在人尚未 `review-accept` 时 `begin implement`" in design


def test_goal_loop_skill_links_every_reference_directly() -> None:
    skill = _read()
    for relative in REFERENCE_FILES:
        assert f"]({relative})" in skill, relative

"""验证 CI 事件分工、手动平台筛选及取消策略，避免漏构建或误取消发布。"""

import json
import shutil
import subprocess

import pytest

from test_publish_workflows import load_workflow


WHEEL_JOBS = {"build_linux_x86_64", "build_linux_aarch64", "build_macos", "check_macos_older_sdk",
              "build_windows", "build_windows_arm64"}
FULL_JOBS = WHEEL_JOBS | {"preflight", "validate_wheels"}


def workflow_plan(event, ref="refs/heads/main", platform="", run_id=1):
    """用 Node 求值当前工作流的字符串/布尔表达式子集，按真实条件生成任务与并发计划。"""
    node = shutil.which("node")
    if node is None:
        pytest.skip("工作流条件验证需要 Node.js")
    payload = {
        "workflow": load_workflow("build-wheels.yml"),
        "github": {"workflow": "Build wheels", "event_name": event, "ref": ref, "run_id": run_id,
                   "ref_type": "tag" if ref.startswith("refs/tags/") else "branch"},
        "inputs": {"platform": platform},
    }
    runner = r"""
        const {workflow, github, inputs} = JSON.parse(require('fs').readFileSync(0, 'utf8'));
        const needs = {preflight: {outputs: {}}};
        // 当前条件仅使用字符串比较、布尔运算与属性访问，与 JavaScript 的本组输入语义一致。
        const evaluate = expression => new Function('github', 'inputs', 'needs',
            'return (' + expression.replace(/^\$\{\{\s*|\s*\}\}$/g, '') + ')')(github, inputs, needs);
        needs.preflight.outputs.build_wheels = String(evaluate(workflow.jobs.preflight.outputs.build_wheels));
        const jobs = Object.entries(workflow.jobs).filter(([name, job]) => !job.if || evaluate(job.if))
            .map(([name]) => name);
        const group = workflow.concurrency.group.replace(/\$\{\{(.*?)\}\}/g,
            (_, expression) => evaluate(expression));
        process.stdout.write(JSON.stringify({jobs, group, cancel: evaluate(workflow.concurrency['cancel-in-progress'])}));
    """
    result = subprocess.run([node, "-e", runner], input=json.dumps(payload), capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


@pytest.mark.parametrize("event,ref,platform,expected", [
    ("push", "refs/heads/main", "", {"preflight"}),
    ("push", "refs/tags/v0.2.1", "", FULL_JOBS),
    ("pull_request", "refs/pull/7/merge", "", FULL_JOBS),
    ("workflow_dispatch", "refs/heads/candidate", "all", FULL_JOBS),
    ("workflow_dispatch", "refs/heads/candidate", "linux", {"preflight", "build_linux_x86_64", "build_linux_aarch64"}),
    ("workflow_dispatch", "refs/heads/candidate", "windows", {"preflight", "build_windows", "build_windows_arm64"}),
    ("workflow_dispatch", "refs/heads/candidate", "windows-arm64", {"preflight", "build_windows_arm64"}),
    ("workflow_dispatch", "refs/heads/candidate", "macos", {"preflight", "build_macos", "check_macos_older_sdk"}),
    ("workflow_dispatch", "refs/heads/candidate", "windows-runtime", {"preflight", "diagnose_windows_runtime"}),
])
def test_event_selects_expected_jobs(event, ref, platform, expected):
    """main 不重建发布包，PR/tag 保留完整矩阵，手动入口继续精确筛选平台。"""
    assert set(workflow_plan(event, ref, platform)["jobs"]) == expected


def test_builds_require_successful_preflight():
    """所有编译任务必须依赖快速检查，汇总仍等待全部平台及旧 SDK 检查通过。"""
    workflow = load_workflow("build-wheels.yml")
    triggers = workflow.get("on", workflow.get(True))
    assert triggers["pull_request"] == {"branches": ["main"]}
    assert triggers["push"] == {"branches": ["main"], "tags": ["v*"]}
    for name in WHEEL_JOBS | {"diagnose_windows_runtime", "validate_wheels"}:
        assert "preflight" in workflow["jobs"][name]["needs"]
        # 不覆盖 GitHub 默认的 success() 门禁，快速检查失败时不能继续编译。
        assert "always()" not in workflow["jobs"][name]["if"]
    assert set(workflow["jobs"]["validate_wheels"]["needs"]) == WHEEL_JOBS | {"preflight"}


@pytest.mark.parametrize("event,ref,cancel", [
    ("push", "refs/heads/main", True),
    ("pull_request", "refs/pull/7/merge", True),
    ("push", "refs/tags/v0.2.1", False),
    ("workflow_dispatch", "refs/heads/main", False),
    ("workflow_dispatch", "refs/tags/v0.2.1", False),
])
def test_concurrency_preserves_release_and_manual_runs(event, ref, cancel):
    """同一 PR/main 的新提交替换旧检查，标签及手动任务各有独立分组且不取消。"""
    first = workflow_plan(event, ref, "all", run_id=1)
    second = workflow_plan(event, ref, "all", run_id=2)
    assert first["cancel"] is cancel
    assert (first["group"] == second["group"]) is cancel
    assert first["group"] != workflow_plan("pull_request", "refs/pull/8/merge")["group"]

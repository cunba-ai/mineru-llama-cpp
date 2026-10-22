"""直接执行生产 CMake 架构约束，覆盖交叉编译和多架构目标。"""

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("apple,processor,architectures,accepted", [
    (True, "arm64", None, True),
    (True, "arm64", "", True),
    (True, "x86_64", "arm64", True),
    (True, "x86_64", None, False),
    (True, "x86_64", "", False),
    (True, "arm64", "x86_64", False),
    (True, "arm64", "arm64;x86_64", False),
    (True, "arm64", "x86_64;arm64", False),
    (True, "arm64", "universal2", False),
    (False, "x86_64", None, True),
    (False, "aarch64", None, True),
])
def test_macos_target_policy(tmp_path, apple, processor, architectures, accepted):
    """显式 arm64 目标优先于宿主信息，同时拒绝任何 Intel 目标或切片。"""
    cmake = shutil.which("cmake")
    if cmake is None:
        pytest.skip("CMake is required for source-build policy checks")
    policy = Path(__file__).resolve().parents[1] / "cmake/macos_target.cmake"
    script = tmp_path / "check.cmake"
    script.write_text(f'set(APPLE {"TRUE" if apple else "FALSE"})\ninclude("{policy.as_posix()}")\n', encoding="utf-8")
    command = [cmake, f"-DCMAKE_SYSTEM_PROCESSOR={processor}"]
    if architectures is not None:
        command.append(f"-DCMAKE_OSX_ARCHITECTURES={architectures}")
    result = subprocess.run([*command, "-P", str(script)], capture_output=True, text=True)
    if accepted:
        assert result.returncode == 0, result.stdout + result.stderr
    else:
        assert result.returncode != 0
        assert "supports only macOS arm64 targets" in result.stderr

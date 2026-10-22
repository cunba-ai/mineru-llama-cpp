"""Linux hybrid CPU regression tests using the patched production helper."""

import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux-only CPU topology patch")


@pytest.fixture(scope="session")
def cpu_topology_probe(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = Path(__file__).resolve().parents[1]
    executable = tmp_path_factory.mktemp("cpu_topology") / "probe"
    subprocess.run(
        [
            *shlex.split(os.environ.get("CXX", "c++")),
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(root / "third_party/llama.cpp/common"),
            str(root / "tests/native/cpu_topology_test.cpp"),
            "-o",
            str(executable),
        ],
        check=True,
    )
    return executable


@pytest.mark.parametrize(
    "scenario",
    [
        "no-smt",
        "adjacent-smt",
        "non-adjacent-smt",
        "restricted-siblings",
        "sparse-ids",
        "pin-failure",
        "read-failure",
        "empty-topology",
        "only-efficiency",
        "restore-retry",
        "affinity-failure",
        "exception-restores",
        "fallback-physical-limit",
    ],
)
def test_hybrid_core_count_and_affinity(cpu_topology_probe: Path, scenario: str) -> None:
    subprocess.run([str(cpu_topology_probe), scenario], check=True)

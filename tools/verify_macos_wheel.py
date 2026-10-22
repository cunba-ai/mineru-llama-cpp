"""审计 macOS wheel 的架构、最低系统版本和可迁移动态库依赖。"""

from __future__ import annotations

import argparse
from email.parser import Parser
import json
from pathlib import Path
import re
import subprocess
import tempfile
import zipfile

from packaging.tags import parse_tag


def inspect_binary(path: Path, architecture: str) -> dict:
    """要求每个 Mach-O 仅包含目标架构且不依赖构建机器路径。"""
    archs = subprocess.check_output(["lipo", "-archs", str(path)], text=True).strip().split()
    assert archs == [architecture], f"unexpected architectures: {path}: {archs}"
    commands = subprocess.check_output(["otool", "-l", str(path)], text=True)
    minimums = []
    for block in commands.split("Load command"):
        if "LC_BUILD_VERSION" in block:
            minimums += re.findall(r"\bminos (\d+\.\d+(?:\.\d+)?)", block)
        elif "LC_VERSION_MIN_MACOSX" in block:
            minimums += re.findall(r"\bversion (\d+\.\d+(?:\.\d+)?)", block)
    assert minimums, f"no deployment target: {path}"
    for version in minimums:
        parts = tuple(int(p) for p in version.split("."))
        assert parts <= (14, 0, 0), f"requires macOS > 14: {path}: {version}"
    dependencies = subprocess.check_output(["otool", "-L", str(path)], text=True).splitlines()[1:]
    dependencies = [line.strip().split(" (compatibility", 1)[0] for line in dependencies]
    rpaths = re.findall(r"cmd LC_RPATH\s+cmdsize \d+\s+path (.*?) \(offset", commands)
    for dependency in dependencies + rpaths:
        assert dependency.startswith(("@", "/usr/lib/", "/System/Library/")), (
            f"non-relocatable dependency/RPATH: {path}: {dependency}")
    return {"name": path.name, "architectures": archs, "minimum_macos": minimums,
            "dependencies": dependencies, "rpaths": rpaths}


def main() -> None:
    """解包真实 wheel 并审计全部原生产物，输出可存档的 JSON 报告。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    assert args.wheel.name.endswith("-macosx_14_0_arm64.whl"), f"expected macosx_14_0_arm64 wheel: {args.wheel}"
    architecture = "arm64"
    report = []
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        with zipfile.ZipFile(args.wheel) as wheel:
            metadata = wheel.read(next(n for n in wheel.namelist() if n.endswith(".dist-info/WHEEL"))).decode()
            tags = {tag for value in Parser().parsestr(metadata).get_all("Tag", []) for tag in parse_tag(value)}
            assert tags and all(tag.platform == "macosx_14_0_arm64" for tag in tags), metadata
            wheel.extractall(root)
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.read_bytes()[:4] in (b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xca\xfe\xba\xbe"):
                item = inspect_binary(path, architecture)
                item["path"] = str(path.relative_to(root))
                report.append(item)
    assert report, "wheel contains no Mach-O files"
    assert any("ggml-cpu" in item["name"] for item in report), "CPU backend missing"
    assert any("ggml-metal" in item["name"] for item in report), "Metal backend missing"
    print(json.dumps({"wheel": args.wheel.name, "binaries": report}, indent=2))


if __name__ == "__main__":
    main()

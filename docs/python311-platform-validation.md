# Python 3.11 abi3 与五平台支持范围验证

本轮将安装下限与稳定 ABI 基线统一提升到 Python 3.11，停止 macOS Intel、
Rosetta x86_64 和 universal2 的 wheel 与源码构建支持。现有公开 API 和模型调用行为保持不变。
项目版本号暂未变更，本轮候选不是新的正式发布；历史 0.1.5 产物继续保留原标签和支持范围。

## 发布矩阵

每个平台发布一个 `cp311-abi3` wheel，复用同一产物在普通 GIL 版 CPython 3.11–3.14 安装测试。

| 平台 | 平台标签 | 后端 |
|---|---|---|
| Linux x86_64 | `manylinux_2_28_x86_64` | CPU、Vulkan |
| Linux aarch64 | `manylinux_2_28_aarch64` | CPU、Vulkan |
| Windows AMD64 | `win_amd64` | CPU、Vulkan |
| Windows ARM64 | `win_arm64` | CPU、Vulkan |
| macOS arm64 | `macosx_14_0_arm64` | CPU、Metal |

macOS 14、Linux glibc/CPU 指令集要求以及其他后端策略沿用原规则。
macOS 架构约束检查编译目标，显式 arm64 目标优先于宿主处理器信息。
五平台审计拒绝 Intel/universal2 及压缩标签中混入的这些架构；macOS 专项审计同时检查
WHEEL 元数据和所有 Mach-O 切片。

## 本机验证

本地归档位于 `build/python311-validation/`。原生构建及隔离 Python 环境位于该目录
`runtime-root.txt` 指向的系统临时目录，避免外置盘创建虚拟环境时的文件系统错误。

| 检查 | 结果与证据 |
|---|---|
| 发布、平台与 CMake 策略 | 109 passed；包含完整/子集发布、旧 ABI 拒绝和目标架构优先级 |
| macOS arm64 wheel | 已构建 `mineru_llama_cpp-0.1.5-cp311-abi3-macosx_14_0_arm64.whl`；`candidate-build.log` |
| 稳定 ABI | 严格审计通过，基线 3.11，无非稳定或未来 ABI 符号；`abi3-audit.json` |
| Mach-O 与运行库 | 11 个 Mach-O 均为 arm64，部署版本及动态库依赖审计通过；`macos-audit.json` |
| 同一 wheel 跨 Python 安装 | 3.11、3.12、3.13、3.14 各 128 passed、20 skipped，安装路径及 smoke 见 `python-3.*-contracts.log` 和 `cross-python.json` |
| 不支持的源码目标 | 实际 CMake 配置拒绝 x86_64 与 arm64+x86_64，在 llama.cpp 配置前失败；`configure-rejection.json` |
| wheel / sdist 安装下限 | 二者 `Requires-Python` 均为 `>=3.11`，Python 3.10.20 安装解析均明确拒绝；`metadata-validation.json` |
| 源码包完整性 | 包含新增 CMake 架构约束及验证文档，解包后在 Python 3.11 / arm64 下独立配置成功；`sdist-configure.log` |
| 真实模型回归 | Python 3.11 下 240 passed、19 skipped，483.08 秒；`model-suite-3.11.log` |
| 同页输出比较 | 生成文本、布局输出及完整提取结构均一致，19 个提取块；`semantic-comparison.json` |
| 工作流语法 | `actionlint` 通过 |

真实模型使用相同的 MinerU2.5-Pro-2605-1.2B-Q8_0 模型及投影器、demo1 第一页。
基线来自 `aa8fa21`，候选对应本轮实现；两包均以相同已应用补丁的 llama.cpp 源码构建，
并在同一 Python 3.14 环境以独立进程执行页面对比。两包的模型和投影器均卸载 25/25 层到 Metal。
该单轮对比用于确认输出兼容，不作为性能改善结论。

完整回归的 19 个跳过项为 Linux CPU 拓扑、队列原生符号与 ELF 运行库专项检查。
无模型安装回归额外跳过一次真实模型关闭测试，因此各 Python 版本为 20 个跳过项。
本机验证后仅撤回构建自动应用的既有 0004–0006 补丁，原有子模块未提交改动逐字节保留；
记录见 `source-state.json` 与 `submodule-restoration.json`。

## 五平台 CI

验证源码提交：`68ec8339597c9e4115866bec3f77b8f025378957`。
[五平台构建运行](https://github.com/myhloli/mineru-llama-cpp/actions/runs/39809112323)
通过 fork 的验证分支手动触发，不创建版本标签或发布包。

运行最终状态为 success，五个平台、Xcode 16.4 与最终五包汇总均通过。

| 检查 | 结果 |
|---|---|
| Linux x86_64 / aarch64 | 各自在 Python 3.11–3.14 复用同一 wheel，每版本 134 passed、3 skipped |
| Windows AMD64 / ARM64、macOS arm64 | 各自在 Python 3.11–3.14 复用同一 wheel，每版本 117 passed、20 skipped |
| Xcode 16.4 | Python 3.12 下 117 passed、20 skipped，部署下限与 Mach-O 审计通过 |
| 汇总验证 | 发布输入与 CMake 策略 82 passed，恰好五个 cp311-abi3 wheel，严格 ABI 审计通过 |
| 下载后复核 | 五包架构、后端、Python 元数据及严格 ABI 审计均通过；`ci/manifest.json`、`ci/wheel-policy.json`、`ci/abi3-audit.json` |
| CI macOS 真实页面 | 下载本次 CI wheel 隔离安装后复跑同一页面，文本、布局和 19 个提取块均与旧基线一致，模型及投影器各卸载 25/25 层；`ci/semantic-comparison.json` |

CI 状态及逐平台测试摘要归档为 `ci/run.json`、`ci/run.log` 和 `ci/test-summaries.json`。
非 macOS 平台的 GPU 推理仍需相应真机，不由安装 smoke 代替。

## 历史记录

[原六平台验证记录](abi3-backends-validation.md)保留历史 wheel、Python 3.10 和 Intel Mac
测试结果，不将旧结果改写为新支持矩阵的验证证据。

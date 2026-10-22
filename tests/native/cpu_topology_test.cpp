// Exercise the same template instantiated by common/common.cpp, without a model.
#include "cpu-topology.h"

#include <cassert>
#include <iostream>
#include <map>
#include <stdexcept>
#include <vector>

struct core {
    bool efficiency;
    std::string siblings;
};

struct fake_probe {
    std::map<int, core> cpus;
    cpu_set_t original;
    cpu_set_t current;
    std::vector<int> visited;
    int current_cpu = -1;
    int physical = 14;
    int pin_failure = -1;
    int read_failure = -1;
    int throw_on_read = -1;
    int restore_failures = 0;
    int restore_calls = 0;
    int fallback_calls = 0;
    bool affinity_failure = false;

    // 初始化模拟的原始及当前线程亲和性。
    fake_probe() {
        CPU_ZERO(&original);
        CPU_ZERO(&current);
    }
    // 添加模拟核心及其 SMT 兄弟拓扑，并设置允许访问的 CPU。
    void add(int cpu, bool efficiency, const std::string & siblings, bool allowed = true) {
        cpus.emplace(cpu, core{efficiency, siblings});
        if (allowed) {
            CPU_SET(cpu, &original);
            CPU_SET(cpu, &current);
        }
    }
    // 返回原始亲和性，并支持模拟读取失败。
    bool get_affinity(cpu_set_t & mask) {
        mask = original;
        return !affinity_failure;
    }
    // 记录亲和性恢复次数，并支持模拟临时恢复失败。
    bool set_affinity(const cpu_set_t & mask) {
        ++restore_calls;
        if (restore_failures > 0) {
            --restore_failures;
            return false;
        }
        current = mask;
        return true;
    }
    // 模拟绑核并记录访问顺序，支持指定 CPU 绑核失败。
    bool pin_cpu(int cpu) {
        assert(CPU_ISSET(cpu, &original));
        visited.push_back(cpu);
        if (cpu == pin_failure) {
            return false;
        }
        CPU_ZERO(&current);
        CPU_SET(cpu, &current);
        current_cpu = cpu;
        return true;
    }
    // 返回当前模拟核心是否为能效核。
    bool is_efficiency_core() { return cpus.at(current_cpu).efficiency; }
    // 返回 SMT 兄弟拓扑，并注入读取失败或异常。
    bool thread_siblings(int cpu, std::string & out) {
        if (cpu == throw_on_read) {
            throw std::runtime_error("simulated read failure");
        }
        out = cpus.at(cpu).siblings;
        return cpu != read_failure;
    }
    // 返回模拟物理核数，同时记录回退调用。
    int physical_cores() {
        ++fallback_calls;
        return physical;
    }
};

// 按场景验证物理 P 核计数、亲和性恢复及失败回退。
int main(int argc, char ** argv) {
    assert(argc == 2);
    const std::string scenario = argv[1];
    fake_probe probe;
    int expected = 4;
    bool fallback = false;
    if (scenario == "no-smt" || scenario == "adjacent-smt" || scenario == "non-adjacent-smt") {
        const bool smt = scenario != "no-smt";
        for (int i = 0; i < 4; ++i) {
            const int first = scenario == "adjacent-smt" ? 2 * i : i;
            probe.add(first, false, "core-" + std::to_string(i));
            if (smt) {
                const int second = scenario == "adjacent-smt" ? first + 1 : first + 8;
                probe.add(second, false, "core-" + std::to_string(i));
            }
        }
        for (int i = 20; i < 30; ++i) {
            probe.add(i, true, "efficiency-" + std::to_string(i));
        }
    } else if (scenario == "restricted-siblings") {
        probe.add(0, false, "00000101", false);
        probe.add(8, false, "00000101");
        probe.add(1, false, "00000202");
        probe.add(9, false, "00000202");
        probe.add(31, true, "80000000");
        expected = 2;
    } else if (scenario == "sparse-ids") {
        probe.add(5, false, "00000020");
        probe.add(127, false, "80000000,00000000,00000000,00000000");
        probe.add(CPU_SETSIZE - 1, true, "last-cpu");
        expected = 2;
    } else {
        probe.add(2, false, "00000004");
        probe.add(7, false, "00000080");
        probe.add(13, true, "00002000");
        expected = 3;
        fallback = true;
        if (scenario == "pin-failure") {
            probe.pin_failure = 7;
        } else if (scenario == "read-failure") {
            probe.read_failure = 7;
        } else if (scenario == "empty-topology") {
            probe.cpus.at(7).siblings.clear();
        } else if (scenario == "only-efficiency") {
            probe.cpus.at(2).efficiency = probe.cpus.at(7).efficiency = true;
        } else if (scenario == "restore-retry") {
            probe.restore_failures = 1;
        } else if (scenario == "affinity-failure") {
            probe.affinity_failure = true;
            expected = 14;
        } else if (scenario == "exception-restores") {
            probe.throw_on_read = 7;
            bool thrown = false;
            try {
                common_cpu_count_hybrid(probe);
            } catch (const std::runtime_error &) {
                thrown = true;
            }
            assert(thrown);
            assert(CPU_EQUAL(&probe.current, &probe.original));
            assert(probe.restore_calls == 1);
            return 0;
        } else if (scenario == "fallback-physical-limit") {
            probe.read_failure = 7;
            probe.physical = 2;
            expected = 2;
        } else {
            throw std::runtime_error("unknown test scenario");
        }
    }
    assert(common_cpu_count_hybrid(probe) == expected);
    assert(CPU_EQUAL(&probe.current, &probe.original));
    assert(probe.fallback_calls == (fallback ? 1 : 0));
    assert(probe.restore_calls == (probe.affinity_failure ? 0 : scenario == "restore-retry" ? 2 : 1));
    std::cout << scenario << ": " << expected << '\n';
}

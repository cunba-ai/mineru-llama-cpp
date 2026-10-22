#include "server-queue.h"
#include <cassert>
#include <string>
#include <thread>

int main(int argc, char ** argv) {
    assert(argc == 2);
    const std::string scenario = argv[1];
    const int repeats = scenario == "concurrent" ? 100 : 1;
    for (int iteration = 0; iteration < repeats; ++iteration) {
        server_queue queue;
        int updates = 0;
        queue.on_new_task([](server_task &&, bool) { return true; });
        queue.on_update_slots([&] {
            ++updates;
            // Also lets the old implementation finish after losing an early stop.
            queue.terminate();
        });
        if (scenario == "early-stop") {
            queue.terminate();
            queue.terminate();
            queue.start_loop();
            assert(updates == 0);
        } else if (scenario == "running-stop") {
            queue.start_loop();
            assert(updates == 1);
        } else if (scenario == "concurrent") {
            std::thread loop([&] { queue.start_loop(); });
            queue.terminate();
            loop.join();
            assert(updates <= 1);
        } else {
            return 2;
        }
        // A stopped queue instance must not be revived by a delayed loop entry.
        const int finished_updates = updates;
        queue.start_loop();
        assert(updates == finished_updates);
    }
}

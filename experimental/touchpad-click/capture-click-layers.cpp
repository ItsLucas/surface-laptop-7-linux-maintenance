// SPDX-License-Identifier: GPL-2.0-or-later
// Passive, read-only capture of button states. No feature writes, grabs or uinput.
#include <hid/parser.hpp>
#include <ipts/descriptor.hpp>
#include <ipts/parser.hpp>
#include <linux/hidraw.h>
#include <linux/input.h>
#include <sys/ioctl.h>
#include <fcntl.h>
#include <poll.h>
#include <unistd.h>
#include <chrono>
#include <csignal>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <vector>

using namespace iptsd;
static volatile std::sig_atomic_t running = 1;
static void stop(int) { running = 0; }
static double epoch_ms() {
    return std::chrono::duration<double, std::milli>(
        std::chrono::system_clock::now().time_since_epoch()).count();
}
static std::string read_text(const std::filesystem::path &p) {
    std::ifstream f(p); std::string s; std::getline(f, s); return s;
}
int main() {
    std::signal(SIGTERM, stop); std::signal(SIGINT, stop);
    std::cout << std::fixed << std::setprecision(3);
    std::vector<pollfd> fds;
    std::vector<std::string> names;
    std::optional<ipts::Descriptor> descriptor;
    for (const auto &node : std::filesystem::directory_iterator("/sys/class/hidraw")) {
        const std::string dev = "/dev/" + node.path().filename().string();
        int fd = open(dev.c_str(), O_RDONLY | O_NONBLOCK | O_CLOEXEC);
        if (fd < 0) continue;
        hidraw_devinfo info {};
        if (ioctl(fd, HIDIOCGRAWINFO, &info) < 0 ||
            info.vendor != 0x045e || info.product != 0x0c77) { close(fd); continue; }
        hidraw_report_descriptor desc {};
        int size = 0;
        if (ioctl(fd, HIDIOCGRDESCSIZE, &size) < 0 || size <= 0 ||
            size > HID_MAX_DESCRIPTOR_SIZE) return 2;
        desc.size = static_cast<unsigned>(size);
        if (ioctl(fd, HIDIOCGRDESC, &desc) < 0) return 2;
        hid::Descriptor parsed;
        hid::parse(gsl::span<u8>(desc.value, desc.size), parsed);
        descriptor.emplace(std::move(parsed));
        fds.push_back({fd, POLLIN, 0}); names.push_back(node.path().filename());
        break;
    }
    if (!descriptor) return 3;
    for (const auto &node : std::filesystem::directory_iterator("/sys/class/input")) {
        const auto n = node.path().filename().string();
        if (n.rfind("event", 0) != 0) continue;
        const auto name = read_text(node.path() / "device/name");
        if (name != "spi 045E:0C77 Mouse" && name != "spi 045E:0C77 Touchpad" &&
            name != "IPTSD Virtual Touchpad 045E:0C77") continue;
        int fd = open(("/dev/input/" + n).c_str(), O_RDONLY | O_NONBLOCK | O_CLOEXEC);
        if (fd < 0) return 4;
        fds.push_back({fd, POLLIN, 0}); names.push_back(name);
    }
    if (fds.size() < 3) return 5;
    const auto touch_reports = descriptor->find_touch_data_reports();
    const auto button_report = descriptor->find_button_report();
    unsigned report_id = 0;
    double received = 0;
    ipts::Parser parser;
    parser.on_button = [&](const ipts::samples::Button &b) {
        std::cout << "{\"source\":\"ipts\",\"epoch_ms\":" << received
                  << ",\"report_id\":" << report_id << ",\"active\":" << b.active << "}\n";
    };
    std::cout << "{\"ready\":true,\"epoch_ms\":" << epoch_ms()
              << ",\"mode_changed\":false,\"captures\":\"buttons_and_touch_presence_only\"}\n" << std::flush;
    const auto end = std::chrono::steady_clock::now() + std::chrono::seconds(180);
    unsigned errors = 0;
    while (running && std::chrono::steady_clock::now() < end) {
        if (poll(fds.data(), fds.size(), 100) <= 0) continue;
        for (size_t i = 0; i < fds.size(); ++i) {
            if (!(fds[i].revents & POLLIN)) continue;
            if (i == 0) {
                std::vector<u8> buffer(65536);
                const auto size = read(fds[i].fd, buffer.data(), buffer.size());
                if (size <= 0) continue;
                received = epoch_ms(); report_id = buffer[0];
                gsl::span<u8> data(buffer.data(), size);
                try {
                    if (std::any_of(touch_reports.begin(), touch_reports.end(),
                        [&](const auto &r) { return r.report_id == buffer[0]; })) parser.parse(data);
                    else if (button_report && button_report->report_id == buffer[0] && size >= 2)
                        std::cout << "{\"source\":\"standalone\",\"epoch_ms\":" << received
                                  << ",\"report_id\":" << report_id << ",\"active\":" << (buffer[1] & 1) << "}\n";
                } catch (const std::exception &) { ++errors; }
            } else {
                input_event buffer[128];
                const auto size = read(fds[i].fd, buffer, sizeof(buffer));
                if (size <= 0) continue;
                for (size_t j = 0; j < static_cast<size_t>(size) / sizeof(input_event); ++j) {
                    const auto &e = buffer[j];
                    if (e.type == EV_KEY && (e.code == BTN_LEFT || e.code == BTN_TOUCH || e.code == BTN_RIGHT))
                        std::cout << "{\"source\":\"evdev\",\"device\":\"" << names[i]
                                  << "\",\"epoch_ms\":" << (e.time.tv_sec * 1000.0 + e.time.tv_usec / 1000.0)
                                  << ",\"code\":" << e.code << ",\"active\":" << e.value << "}\n";
                }
            }
        }
        std::cout << std::flush;
    }
    std::cout << "{\"finished\":true,\"parse_errors\":" << errors << "}\n";
    for (const auto &fd : fds) close(fd.fd);
}

// SPDX-License-Identifier: GPL-2.0-or-later
// Exercise the actual TouchDevice header with an in-memory uinput sink.
// This executable never opens input devices or injects desktop events.
#include <common/types.hpp>
#include <linux/input.h>
#include <map>
#include <string>
#include <vector>
#include <functional>
#include <iostream>
#define IPTSD_APPS_DAEMON_UINPUT_DEVICE_HPP
namespace iptsd::apps::daemon {
class UinputDevice {
public:
    inline static std::map<int,int> keys;
    inline static std::map<int,int> slots;
    inline static std::vector<int> button_edges;
    inline static int slot = 0;
    UinputDevice() { keys.clear(); slots.clear(); button_edges.clear(); slot = 0; }
    void set_name(std::string) {}
    void set_vendor(u16) {}
    void set_product(u16) {}
    void set_evbit(i32) {}
    void set_keybit(i32) {}
    void set_propbit(i32) {}
    void set_absinfo(u16,i32,i32,i32) {}
    void create() {}
    void emit(u16 type,u16 code,i32 value) const {
        if(type==EV_KEY) {
            if(code==BTN_LEFT && keys[code]!=value) button_edges.push_back(value);
            keys[code]=value;
        }
        if(type==EV_ABS && code==ABS_MT_SLOT) slot=value;
        if(type==EV_ABS && code==ABS_MT_TRACKING_ID) {
            if(value<0) slots.erase(slot); else slots[slot]=value;
        }
    }
};
}
#include <apps/daemon/touch.hpp>
using namespace iptsd;
using apps::daemon::TouchDevice;
using Sink=apps::daemon::UinputDevice;
static int failures=0, checks=0;
static void expect(bool ok,const char *message) {
    ++checks;
    if(!ok) { ++failures; std::cout << "FAIL " << message << '\n'; }
}
static contacts::Contact<f64> finger(usize id,bool stable=true,bool valid=true) {
    contacts::Contact<f64> c;
    c.index=id; c.stable=stable; c.valid=valid;
    c.mean={.5,.5}; c.size={.08,.07}; return c;
}
static void consistent(int count,const char *message) {
    expect(static_cast<int>(Sink::slots.size())==count,message);
    expect(Sink::keys[BTN_TOUCH]==(count>0),message);
    expect(Sink::keys[BTN_TOOL_FINGER]==(count==1),message);
    expect(Sink::keys[BTN_TOOL_DOUBLETAP]==(count==2),message);
}
int main() {
    core::Config cfg; cfg.width=12; cfg.height=8; cfg.touchpad_button_debounce_ms=0;
    core::DeviceInfo info; info.vendor=0x045e; info.product=0x0c77;
    info.type=ipts::Device::Type::Touchpad;
    const ipts::samples::Button down{1,true}, up{0,false};
    {
        TouchDevice d(cfg,info);
        d.update(std::vector{finger(3)});
        consistent(1,"first contact with nonzero ID is present immediately");
        d.update(std::vector{finger(3,false)});
        consistent(1,"unstable existing contact retains touch presence");
        d.update(std::vector{finger(3),finger(7)});
        consistent(2,"two accepted contacts");
        d.update(std::vector{finger(7)});
        consistent(1,"primary handoff does not release remaining finger");
        d.update(std::vector<contacts::Contact<f64>>{});
        consistent(0,"actual lift clears both APIs");
    }
    {
        TouchDevice d(cfg,info);
        d.update(std::vector{finger(0),finger(1,true,false),finger(2,false)});
        consistent(1,"palm and new unstable contact do not inflate finger count");
        d.update(std::vector{finger(0,true,false)});
        consistent(0,"invalidated contact is lifted");
    }
    {
        TouchDevice d(cfg,info);
        d.update(std::vector{finger(0)});d.update(down);
        d.update(std::vector{finger(0,false)});
        expect(Sink::keys[BTN_LEFT]==1,"physical hold survives unstable measurement");
        d.update(std::vector<contacts::Contact<f64>>{});
        expect(Sink::keys[BTN_LEFT]==1,"contact loss does not release physical button");
        d.update(up);
        expect(Sink::button_edges==std::vector<int>{1,0},"one hardware click produces one pair");
    }
    {
        TouchDevice d(cfg,info);
        d.update(std::vector{finger(0)});d.update(down);d.disable();
        expect(Sink::keys[BTN_LEFT]==0,"disable releases held button");
        consistent(0,"disable lifts all contacts");
        d.enable();d.update(std::vector{finger(0)});d.update(down);d.update(up);
        expect(Sink::button_edges==std::vector<int>{1,0,1,0},"disable resets emitted button state");
    }
    {
        auto palm_cfg=cfg;palm_cfg.touchpad_disable_on_palm=true;
        TouchDevice d(palm_cfg,info);
        d.update(std::vector{finger(0)});d.update(down);
        d.update(std::vector{finger(0,true,false)});d.update(down);
        consistent(0,"palm suppression clears contact state");
        expect(Sink::keys[BTN_LEFT]==0,"palm suppression blocks physical button");
        d.update(std::vector{finger(1)});d.update(down);d.update(up);
        expect(Sink::button_edges==std::vector<int>{1,0,1,0},"palm release leaves button state synchronized");
    }
    {
        auto screen=info;screen.type=ipts::Device::Type::Touchscreen;
        TouchDevice d(cfg,screen);d.update(std::vector{finger(4)});
        expect(Sink::keys[BTN_TOUCH]==1 && Sink::slots.size()==1,"screen contact starts immediately");
        d.update(std::vector{finger(4,false)});
        expect(Sink::keys[BTN_TOUCH]==1 && Sink::slots.size()==1,"screen unstable contact remains present");
        d.update(std::vector<contacts::Contact<f64>>{});
        expect(Sink::keys[BTN_TOUCH]==0 && Sink::slots.empty(),"screen lift is complete");
    }
    std::cout << checks << " checks, " << failures << " failures\n";
    return failures ? 1 : 0;
}

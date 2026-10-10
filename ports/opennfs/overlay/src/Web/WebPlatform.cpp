#include "WebPlatform.h"

#include <cmath>
#include <malloc.h>
#include <unistd.h>
#include <emscripten.h>
#include <emscripten/html5.h>

namespace {
    uint32_t gPageMask{0};
    float gPageSteer{0.f};
    bool gDebugUi{false};
    bool gPaused{false};
    bool gRacePending{false};
    int gFastForward{0};
    bool gShadows{true};
    bool gAutopilot{false};
    int gStartVroad{0};
    OpenNFS::Web::RaceRequest gRace;
} // namespace

extern "C" {
// Called from JavaScript: Module._web_set_input(mask, steer)
EMSCRIPTEN_KEEPALIVE void web_set_input(uint32_t const mask, float const steer) {
    gPageMask = mask;
    gPageSteer = steer;
}

// Module.ccall('web_race', null, ['string', 'number', 'number', 'number', 'string'], [car, colour, opponents, laps, track])
EMSCRIPTEN_KEEPALIVE void web_race(char const *car, int const colour, int const opponents, int const laps, char const *track) {
    gRace.car = car != nullptr ? car : "";
    gRace.track = track != nullptr ? track : "";
    gRace.colour = colour;
    gRace.opponents = static_cast<uint32_t>(opponents < 0 ? 0 : (opponents > 7 ? 7 : opponents));
    gRace.laps = static_cast<uint32_t>(laps < 1 ? 1 : (laps > 20 ? 20 : laps));
    gRacePending = true;
}

// Called before main(): options of the first race that are not command line arguments
EMSCRIPTEN_KEEPALIVE void web_preset(int const colour, int const laps) {
    gRace.colour = colour;
    gRace.laps = static_cast<uint32_t>(laps < 1 ? 1 : (laps > 20 ? 20 : laps));
}

EMSCRIPTEN_KEEPALIVE void web_set_flag(int const flag, int const value) {
    switch (flag) {
    case 0:
        gDebugUi = value != 0;
        break;
    case 1:
        gPaused = value != 0;
        break;
    case 2:
        gFastForward = value < 0 ? 0 : (value > 240 ? 240 : value);
        break;
    case 3:
        gShadows = value != 0;
        break;
    case 4:
        gAutopilot = value != 0;
        break;
    case 5:
        gStartVroad = value < 0 ? 0 : value;
        break;
    default:
        break;
    }
}
}

namespace OpenNFS::Web {
    static bool PollGamepad(uint32_t &mask, float &steer) {
        if (emscripten_sample_gamepad_data() != EMSCRIPTEN_RESULT_SUCCESS) {
            return false;
        }
        int const count{emscripten_get_num_gamepads()};
        for (int idx = 0; idx < count; ++idx) {
            EmscriptenGamepadEvent pad;
            if (emscripten_get_gamepad_status(idx, &pad) != EMSCRIPTEN_RESULT_SUCCESS || !pad.connected) {
                continue;
            }
            auto const button{[&pad](int const b) { return b < pad.numButtons && (pad.digitalButton[b] || pad.analogButton[b] > 0.35); }};
            // Standard mapping: 0 A, 1 B, 2 X, 3 Y, 4 LB, 5 RB, 6 LT, 7 RT, 8 back, 9 start, 12-15 d-pad
            if (button(7) || button(0)) mask |= kAccelerate;
            if (button(6) || button(2)) mask |= kBrake;
            if (button(1)) mask |= kHandbrake;
            if (button(3)) mask |= kCamera;
            if (button(8)) mask |= kReset;
            if (button(9)) mask |= kPause;
            if (button(5)) mask |= kShiftUp;
            if (button(4)) mask |= kShiftDown;
            if (button(14)) mask |= kLeft;
            if (button(15)) mask |= kRight;
            if (pad.numAxes > 0 && std::fabs(pad.axis[0]) > 0.12) {
                steer = static_cast<float>(pad.axis[0]);
            }
            return true;
        }
        return false;
    }

    uint32_t InputMask() {
        uint32_t mask{gPageMask};
        float steer{0.f};
        PollGamepad(mask, steer);
        return mask;
    }

    float SteerAxis() {
        uint32_t mask{0};
        float steer{gPageSteer};
        PollGamepad(mask, steer);
        return steer;
    }

    bool &DebugUi() {
        return gDebugUi;
    }

    bool &Paused() {
        return gPaused;
    }

    int FastForwardSteps() {
        return gFastForward;
    }

    bool Shadows() {
        return gShadows;
    }

    bool Autopilot() {
        return gAutopilot;
    }

    int StartVroad() {
        return gStartVroad;
    }

    bool ConsumeRaceRequest(RaceRequest &request) {
        if (!gRacePending) {
            return false;
        }
        gRacePending = false;
        request = gRace;
        return true;
    }

    uint32_t Laps() {
        return gRace.laps;
    }

    int Colour() {
        return gRace.colour;
    }

    void SyncCanvasSize(GLFWwindow *window) {
        double cssWidth{0}, cssHeight{0};
        if (emscripten_get_element_css_size("#canvas", &cssWidth, &cssHeight) != EMSCRIPTEN_RESULT_SUCCESS) {
            return;
        }
        // Cap the pixel ratio: phones report 3x, which is a lot of fragments for this renderer
        double const ratio{std::fmin(emscripten_get_device_pixel_ratio(), 1.5)};
        int const wantWidth{static_cast<int>(std::lround(cssWidth * ratio))};
        int const wantHeight{static_cast<int>(std::lround(cssHeight * ratio))};
        int width{0}, height{0};
        glfwGetWindowSize(window, &width, &height);
        if (wantWidth > 0 && wantHeight > 0 && (wantWidth != width || wantHeight != height)) {
            glfwSetWindowSize(window, wantWidth, wantHeight);
        }
    }

    void NotifyReady() {
        EM_ASM({
            if (Module.onGameReady) {
                Module.onGameReady();
            }
        });
    }

    void ReportFatal(char const *message) {
        EM_ASM({
            if (Module.onGameFatal) {
                Module.onGameFatal(UTF8ToString($0));
            }
        }, message);
    }

    // Development aid: walk the allocator's chunk chain (dlmalloc layout: size word in front of every block) from the
    // first block this function ever saw to the end of the heap and report the first broken link with its neighbourhood.
    static bool HeapWalk(char const *where) {
        static uintptr_t first{0};
        static bool reported{false};
        if (first == 0) {
            first = reinterpret_cast<uintptr_t>(malloc(24)) - 8; // deliberately never freed: the anchor of the walk
        }
        if (reported) {
            return false;
        }
        uintptr_t const end{reinterpret_cast<uintptr_t>(sbrk(0))};
        uintptr_t chunk{first};
        uintptr_t previous{0};
        while (chunk + 64 < end) {
            uint32_t const head{*reinterpret_cast<uint32_t const *>(chunk + 4)};
            uint32_t const size{head & ~7u};
            if (size < 16 || size > end - chunk) {
                reported = true;
                EM_ASM({
                    var hex = function(a, n) { var s = ''; for (var i = 0; i < n; i += 4) { s += (HEAPU32[(a + i) >> 2] >>> 0).toString(16).padStart(8, '0') + ' '; } return s; };
                    console.log('HEAPWALK ' + UTF8ToString($0) + ': broken chunk at 0x' + $1.toString(16) + ' head 0x' + ($2 >>> 0).toString(16) +
                                ', previous chunk 0x' + $3.toString(16) + ' size ' + $4 + ', heap end 0x' + $5.toString(16));
                    console.log('HEAPWALK previous start: ' + hex($3, 96));
                    console.log('HEAPWALK before broken: ' + hex($1 - 96, 96));
                    console.log('HEAPWALK broken onward: ' + hex($1, 96));
                }, where, chunk, head, previous, previous ? (*reinterpret_cast<uint32_t const *>(previous + 4) & ~7u) : 0, end);
                return false;
            }
            previous = chunk;
            chunk += size;
        }
        return true;
    }

    void GlCheckpoint(char const *where) {
        // the heap walk is a development aid: only with ?heapwalk in the page address
        static bool const walk{EM_ASM_INT({ return new URLSearchParams(location.search).has('heapwalk') ? 1 : 0; }) != 0};
        if (walk && !HeapWalk(where)) {
            return;
        }
        EM_ASM({
            var gl = Module.ctx || (typeof GLctx !== 'undefined' ? GLctx : null);
            if (!gl) { return; }
            var lost = gl.isContextLost();
            var err = lost ? 0 : gl.getError();
            if (lost || err) {
                console.log('GLCHECK ' + UTF8ToString($0) + (lost ? ' CONTEXT LOST' : ' error 0x' + err.toString(16)));
            } else if (Module.glCheckVerbose) {
                console.log('GLCHECK ' + UTF8ToString($0) + ' ok, wasm memory ' + (HEAP8.length / 1048576).toFixed(0) + ' MB, heap in use ' +
                            ($1 / 1048576).toFixed(1) + ' MB, heap end ' + ($2 / 1048576).toFixed(1) + ' MB');
            }
        }, where, 0.0, static_cast<double>(reinterpret_cast<uintptr_t>(sbrk(0))));
    }

    void PublishState(char const *json) {
        EM_ASM({
            if (Module.onGameState) {
                Module.onGameState(UTF8ToString($0));
            }
        }, json);
    }
} // namespace OpenNFS::Web

#ifdef WEB_FILL_NEW
// Development aid (cmake -DWEB_FILL=<byte>): every C++ allocation starts filled with a known byte and is filled with 0xDD
// when released, so code that reads memory it never initialised, or memory it already freed, fails the same way every run.
#include <cstring>
#include <new>
void *operator new(std::size_t size) {
    void *const p{malloc(size ? size : 1)};
    if (!p) {
        throw std::bad_alloc();
    }
#ifdef WEB_FILL_RANGE
    // only allocations whose size is in [filllo, fillhi) (page query) are zeroed: a bisection aid
    static int lo{-1};
    static int hi{0};
    if (lo < 0) {
        lo = 0;
        lo = EM_ASM_INT({ return parseInt(new URLSearchParams(location.search).get('filllo') || '0'); });
        hi = EM_ASM_INT({ return parseInt(new URLSearchParams(location.search).get('fillhi') || '0'); });
    }
    if (static_cast<int>(size) >= lo && static_cast<int>(size) < hi) {
        memset(p, 0, size);
    }
#elif defined(WEB_FILL_WORD)
    for (std::size_t i = 0; i + 4 <= size; i += 4) {
        static_cast<uint32_t *>(p)[i / 4] = WEB_FILL_WORD;
    }
#elif !defined(WEB_FILL_SKIP_NEW)
    memset(p, WEB_FILL_NEW, size);
#endif
    return p;
}
void *operator new[](std::size_t size) {
    return operator new(size);
}
void operator delete(void *p) noexcept {
    if (p) {
#ifndef WEB_FILL_KEEP_FREED
        memset(p, 0xDD, malloc_usable_size(p));
#endif
        free(p);
    }
}
void operator delete[](void *p) noexcept {
    operator delete(p);
}
void operator delete(void *p, std::size_t) noexcept {
    operator delete(p);
}
void operator delete[](void *p, std::size_t) noexcept {
    operator delete(p);
}
#endif

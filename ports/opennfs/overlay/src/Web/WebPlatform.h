// Browser glue for the web port: canvas sizing, page notifications and injected input
// (touch buttons, gamepad and automated tests all feed the same state).
#pragma once

#include <GL/glew.h>
#include <GLFW/glfw3.h>
#include <cstdint>
#include <string>

namespace OpenNFS::Web {
    enum InputBit : uint32_t {
        kAccelerate = 1u << 0,
        kBrake = 1u << 1,
        kLeft = 1u << 2,
        kRight = 1u << 3,
        kHandbrake = 1u << 4,
        kReset = 1u << 5,
        kLights = 1u << 6,
        kCamera = 1u << 7,
        kPause = 1u << 8,
        kShiftUp = 1u << 9,
        kShiftDown = 1u << 10,
        kConfirm = 1u << 11,
        kBack = 1u << 12,
    };

    // Buttons held by the page (touch controls / test hooks) OR-ed with the first connected gamepad
    uint32_t InputMask();
    // Analogue steering from a gamepad stick or touch, -1 (left) .. 1 (right); 0 when unused
    float SteerAxis();

    // Developer overlay (the engine's ImGui tools); off unless toggled with F1 or ?debug=1
    bool &DebugUi();
    // The page pauses the simulation while its menu is open
    bool &Paused();
    // Automated tests: extra fixed 1/60 s simulation steps per rendered frame (0 = real time)
    int FastForwardSteps();
    // Shadow maps can be switched off on slow devices (and in software-rendered tests)
    bool Shadows();
    // Automated tests: the player's car is driven by a simple autopilot through the normal controls
    bool Autopilot();
    // Automated tests: move the starting grid to this virtual road position (0 = the start line)
    int StartVroad();

    // Race set-up chosen on the page. The page calls web_race(car, colour, opponents, laps, timeOfDay).
    struct RaceRequest {
        std::string car;
        std::string track;
        int colour{-1};
        uint32_t opponents{0};
        uint32_t laps{3};
    };
    // True once when a new race was requested; fills the request
    bool ConsumeRaceRequest(RaceRequest &request);
    uint32_t Laps();
    int Colour(); // paint index of the player's car, -1 = random

    // Keep the GL framebuffer matched to the canvas' CSS size
    void SyncCanvasSize(GLFWwindow *window);
    // Tell the page the first frames have been presented (hides the loading screen)
    void NotifyReady();
    // Show an error on the page (the game cannot continue)
    void ReportFatal(char const *message);
    // Log the WebGL state at a named point of loading (context lost? pending GL error?)
    void GlCheckpoint(char const *where);
    // Publish race telemetry to the page (used by the HUD overlay, audio and automated tests)
    void PublishState(char const *json);
} // namespace OpenNFS::Web

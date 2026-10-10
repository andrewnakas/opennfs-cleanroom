#pragma once

#include <GL/glew.h>
#include <GLFW/glfw3.h>
#include <memory>

namespace OpenNFS {
    enum WindowStatus : uint8_t {
        UI,
        GAME
    };

    // Attenuate scroll towards 0 over time
    constexpr double kScrollAttenuation = 0.85;

    // Web port input: keyboard (WASD or arrows) merged with the page's injected state (touch, gamepad, tests)
    class InputManager {
      public:
        bool accelerate{};
        bool reverse{};
        bool brakes{};
        bool handbrakes{};
        bool left{};
        bool right{};
        float steerAxis{}; // analogue steering, -1 (left) .. 1 (right); 0 when only digital input is used
        bool lights{};
        bool shiftUp{};
        bool shiftDown{};
        bool reset{};
        bool cameraToggle{};
        bool escape{};
        bool cameraForwards{};
        bool cameraBackwards{};
        bool cameraLeft{};
        bool cameraRight{};
        double cursorX{};
        double cursorY{};
        double uiCursorX{};
        double uiCursorY{};
        bool mouseLeft{};
        bool mouseRight{};
        bool camSpeedUp{};
        double scrollY{};
        double mouseDeltaX{};
        double mouseDeltaY{};

        explicit InputManager(std::shared_ptr<GLFWwindow> const &window);
        void Scan();
        void ResetCursorPosition() const;
        [[nodiscard]] WindowStatus GetWindowStatus() const;

      private:
        std::shared_ptr<GLFWwindow> m_window;
        WindowStatus m_windowStatus{GAME};
        bool m_lightsKeyPrev{};
        bool m_shiftUpKeyPrev{};
        bool m_shiftDownKeyPrev{};
        bool m_resetKeyPrev{};
        bool m_cameraKeyPrev{};
        bool m_debugKeyPrev{};

        static void ScrollCallback(GLFWwindow *window, double xoffset, double yoffset);
    };
} // namespace OpenNFS

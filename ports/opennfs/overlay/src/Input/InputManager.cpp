#include "InputManager.h"

#include <imgui.h>

#include "../Config.h"
#include "../Web/WebPlatform.h"

namespace OpenNFS {
    InputManager::InputManager(std::shared_ptr<GLFWwindow> const &window) : m_window(window) {
        glfwSetWindowUserPointer(m_window.get(), this);
        glfwSetScrollCallback(m_window.get(), ScrollCallback);
    }

    void InputManager::Scan() {
        auto const key{[this](int const code) { return glfwGetKey(m_window.get(), code) == GLFW_PRESS; }};
        auto const risingEdge{[](bool const current, bool &previous) {
            bool const edge{current && !previous};
            previous = current;
            return edge;
        }};
        uint32_t const web{Web::InputMask()};
        // Typing into a debug text box must not drive the car
        bool const keyboard{!ImGui::GetIO().WantCaptureKeyboard};
        auto const held{[&](int const a, int const b, uint32_t const bit) { return (keyboard && (key(a) || key(b))) || (web & bit) != 0; }};

        accelerate = held(GLFW_KEY_W, GLFW_KEY_UP, Web::kAccelerate);
        // One pedal for brake and reverse: PlayerAgent reverses once the car has stopped
        brakes = held(GLFW_KEY_S, GLFW_KEY_DOWN, Web::kBrake);
        reverse = false;
        handbrakes = held(GLFW_KEY_SPACE, GLFW_KEY_SPACE, Web::kHandbrake);
        right = held(GLFW_KEY_D, GLFW_KEY_RIGHT, Web::kRight);
        left = held(GLFW_KEY_A, GLFW_KEY_LEFT, Web::kLeft);
        steerAxis = Web::SteerAxis();

        lights = risingEdge(held(GLFW_KEY_L, GLFW_KEY_L, Web::kLights), m_lightsKeyPrev);
        shiftUp = risingEdge(held(GLFW_KEY_RIGHT_BRACKET, GLFW_KEY_E, Web::kShiftUp), m_shiftUpKeyPrev);
        shiftDown = risingEdge(held(GLFW_KEY_LEFT_BRACKET, GLFW_KEY_Q, Web::kShiftDown), m_shiftDownKeyPrev);
        reset = risingEdge(held(GLFW_KEY_R, GLFW_KEY_BACKSPACE, Web::kReset), m_resetKeyPrev);
        cameraToggle = risingEdge(held(GLFW_KEY_C, GLFW_KEY_C, Web::kCamera), m_cameraKeyPrev);
        if (risingEdge(keyboard && (key(GLFW_KEY_F1) || key(GLFW_KEY_GRAVE_ACCENT)), m_debugKeyPrev)) {
            Web::DebugUi() = !Web::DebugUi();
        }

        escape = key(GLFW_KEY_ESCAPE);
        camSpeedUp = key(GLFW_KEY_LEFT_SHIFT);
        cameraForwards = accelerate;
        cameraBackwards = brakes;
        cameraLeft = left;
        cameraRight = right;

        // Mouse: only meaningful for the developer tools (orbit camera, entity picking)
        double currentX, currentY;
        glfwGetCursorPos(m_window.get(), &currentX, &currentY);
        mouseDeltaX = currentX - cursorX;
        mouseDeltaY = currentY - cursorY;
        cursorX = currentX;
        cursorY = currentY;
        bool const devMouse{Web::DebugUi() && !ImGui::GetIO().WantCaptureMouse};
        mouseLeft = devMouse && (glfwGetMouseButton(m_window.get(), GLFW_MOUSE_BUTTON_LEFT) == GLFW_PRESS);
        mouseRight = devMouse && (glfwGetMouseButton(m_window.get(), GLFW_MOUSE_BUTTON_RIGHT) == GLFW_PRESS);
        scrollY = Web::DebugUi() ? scrollY * kScrollAttenuation : 0.0;

        // Cursor Y needs to be inverted
        uiCursorX = cursorX;
        uiCursorY = (Config::get().windowSizeY) - cursorY;
    }

    void InputManager::ResetCursorPosition() const {
        glfwSetCursorPos(m_window.get(), Config::get().windowSizeX / 2, Config::get().windowSizeY / 2);
    }

    WindowStatus InputManager::GetWindowStatus() const {
        return m_windowStatus;
    }

    void InputManager::ScrollCallback(GLFWwindow *window, double xoffset, double yoffset) {
        auto *inputManager = static_cast<InputManager *>(glfwGetWindowUserPointer(window));
        if (inputManager) {
            inputManager->scrollY = yoffset;
        }
    }
} // namespace OpenNFS

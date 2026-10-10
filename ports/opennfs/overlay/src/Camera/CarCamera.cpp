#include "CarCamera.h"

#include <algorithm>
#include <cmath>

namespace OpenNFS {
    namespace {
        struct View {
            float distance, height, lookUp;
        };
        // near chase, far chase, bonnet
        constexpr View kViews[CarCamera::kNumViews] = {{7.2f, 2.4f, 1.0f}, {11.5f, 3.8f, 1.0f}, {-0.35f, 0.72f, 0.62f}};

        float WrapDegrees(float angle) {
            while (angle > 180.f) {
                angle -= 360.f;
            }
            while (angle < -180.f) {
                angle += 360.f;
            }
            return angle;
        }
    } // namespace

    CarCamera::CarCamera(InputManager const &inputManager) : BaseCamera(CameraMode::FOLLOW_CAR, inputManager) {
        SetView(0);
    }

    void CarCamera::SetView(int const view) {
        m_view = std::clamp(view, 0, kNumViews - 1);
        m_distanceFromCar = kViews[m_view].distance;
        m_height = kViews[m_view].height;
        m_lookAhead = kViews[m_view].lookUp;
    }

    void CarCamera::EnableCarouselMode(float const initialAngularVelocity) {
        m_carouselMode = true;
        m_angularVelocity = m_initialAngularVelocity = initialAngularVelocity;
    }

    void CarCamera::DisableCarouselMode() {
        m_carouselMode = false;
        m_angularVelocity = 0.f;
    }

    void CarCamera::FollowCar(std::shared_ptr<Car> const &targetCar, float const deltaTime) {
        this->_CalculateZoom();
        this->_CalculatePitch();
        this->_CalculateAngleAroundCar(deltaTime);

        float const carYaw{targetCar->GetCarBodyOrientation()};
        bool const rigid{m_view == 2 || m_carouselMode}; // the bonnet view is bolted to the car
        if (!m_followInitialised || rigid) {
            m_followYaw = carYaw;
            m_followInitialised = true;
        } else {
            // Critically damped-ish follow: the car can rotate a little inside the frame before the camera catches up
            float const blend{1.f - std::exp(-std::min(deltaTime, 0.1f) * 7.0f)};
            m_followYaw = WrapDegrees(m_followYaw + WrapDegrees(carYaw - m_followYaw) * blend);
        }

        float const theta{glm::radians(m_followYaw + m_angleAroundCar)};
        glm::vec3 const carPosition{targetCar->carBodyModel.position};
        position.x = carPosition.x - m_distanceFromCar * std::sin(theta);
        position.z = carPosition.z - m_distanceFromCar * std::cos(theta);
        position.y = carPosition.y + m_height;

        // Aim slightly above the car so the road ahead fills the frame
        glm::vec3 const target{carPosition + glm::vec3(std::sin(theta), 0.f, std::cos(theta)) * (m_view == 2 ? 20.f : 4.0f) +
                               glm::vec3(0.f, m_lookAhead, 0.f)};
        viewMatrix = glm::lookAt(position, target, glm::vec3(0.f, 1.f, 0.f));
        m_yaw = 180.f - (m_followYaw + m_angleAroundCar);
    }

    void CarCamera::_CalculateZoom() {
        float const zoomLevel{static_cast<float>(m_inputManager.scrollY) * .1f};
        m_distanceFromCar -= zoomLevel;
        if (m_carouselMode) {
            m_distanceFromCar = std::clamp(m_distanceFromCar, kCarouselMinZoom, kCarouselMaxZoom);
        }
    }

    void CarCamera::_CalculatePitch() {
        if (m_inputManager.mouseRight) {
            m_height += static_cast<float>(m_inputManager.mouseDeltaY) * 0.02f;
        }
    }

    void CarCamera::_CalculateAngleAroundCar(float const deltaTime) {
        if (m_carouselMode) {
            if (m_inputManager.mouseLeft) {
                m_angularVelocity += static_cast<float>(m_inputManager.mouseDeltaX) * 0.5f;
            }
            m_angleAroundCar -= m_angularVelocity * deltaTime;
        } else if (m_inputManager.mouseLeft) {
            m_angleAroundCar -= static_cast<float>(m_inputManager.mouseDeltaX) * 0.3f;
        }
    }
} // namespace OpenNFS

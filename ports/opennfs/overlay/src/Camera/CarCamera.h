#pragma once

#include "../Physics/Car.h"
#include "BaseCamera.h"

namespace OpenNFS {
    // Web port chase camera: three views (near chase, far chase, bonnet) with a damped follow
    class CarCamera : public BaseCamera {
      public:
        static constexpr int kNumViews{3};

        explicit CarCamera(InputManager const &inputManager);
        void FollowCar(std::shared_ptr<Car> const &targetCar, float deltaTime = 0.016f);
        void SetView(int view);
        void EnableCarouselMode(float initialAngularVelocity = 20.f);
        void DisableCarouselMode();

      private:
        void _CalculateZoom();
        void _CalculatePitch();
        void _CalculateAngleAroundCar(float deltaTime);

        int m_view{0};
        float m_distanceFromCar = 7.2f;
        float m_height = 2.4f;
        float m_lookAhead = 2.0f; // the camera aims at a point this far above the car origin
        float m_angleAroundCar = 0.f;
        float m_pitch = 10.f;
        float m_yaw = 0.f;
        float m_followYaw = 0.f; // damped copy of the car heading, degrees
        bool m_followInitialised = false;
        // Carousel variables
        bool m_carouselMode = false;
        float m_angularVelocity = 0.f;
        float m_initialAngularVelocity = 0.f;
        float const kCarouselMinZoom{5.0f};
        float const kCarouselMaxZoom{20.f};
    };
} // namespace OpenNFS

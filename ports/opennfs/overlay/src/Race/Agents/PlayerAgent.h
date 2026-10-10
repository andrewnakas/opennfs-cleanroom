#pragma once

#include "../../Input/InputManager.h"
#include "CarAgent.h"

namespace OpenNFS {
    class PlayerAgent final : public CarAgent {
      public:
        PlayerAgent(InputManager const &inputManager, std::shared_ptr<Car> const &car, std::shared_ptr<Track> const &raceTrack);
        void Simulate() override;

      private:
        InputManager const &m_inputManager;
        uint32_t m_autopilotTicks{0}; // test autopilot: ticks spent stationary
        float m_autopilotLane{0.f};   // test autopilot: lateral offset it is steering for
    };
} // namespace OpenNFS

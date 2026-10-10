#pragma once

#include "CarAgent.h"

#include <string>

namespace OpenNFS {
    struct RacerData {
        std::string name;
        std::string favouriteVehicle;
    };

    enum class RacerState {
        TRACK_FOLLOWING, // Normal racing, following the track
        STUCK_REVERSING, // Detected as stuck, reversing to get unstuck
        RESETTING,
    };

    // Web port AI: pure-pursuit steering along the virtual road with a braking-distance speed plan.
    // (The upstream agent resets itself every time a lap wraps around and is capped at a test speed.)
    class RacerAgent final : public CarAgent {
      public:
        RacerAgent(RacerData const &racerData, std::shared_ptr<Car> const &car, std::shared_ptr<Track> const &raceTrack);
        void Simulate() override;
        [[nodiscard]] RacerState State() const;

        uint32_t m_futureVroadID = 0;
        glm::vec3 targetVroadPosition{};

      private:
        void _Drive();

        RacerState m_state = RacerState::TRACK_FOLLOWING;
        float m_skill{0.9f}; // 0..1, scales cornering and top speed
        float m_lane{0.f};   // preferred lateral position, as a fraction (-1..1) of the usable half width
        float m_laneNow{0.f}; // lateral offset currently aimed for, metres
        float m_segmentLength{6.f};
        uint32_t m_ticksSlow{0};
        uint32_t m_ticksReversing{0};
        uint32_t m_ticksWrongWay{0};
        uint32_t m_ticksAlive{0};
        uint32_t m_reverseAttempts{0};
    };
} // namespace OpenNFS

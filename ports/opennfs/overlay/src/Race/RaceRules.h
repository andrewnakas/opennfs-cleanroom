// Race rules for the web port: starting grid, countdown, lap counting, timing, positions, finish.
// The upstream engine only free-roams; this layer turns that into a race and publishes telemetry
// for the page's HUD and audio.
#pragma once

#include <memory>
#include <string>
#include <vector>

#include "../Scene/Track.h"
#include "Agents/CarAgent.h"

namespace OpenNFS {
    enum class RacePhase : uint8_t {
        Countdown,
        Racing,
        Finished, // the player has completed the race
    };

    struct RacerProgress {
        int crossings{0};      // times the start line was crossed going forwards (lap N is running after N crossings)
        int sector{3};         // last sector reached in order (cars start just behind the line, in the last sector)
        float lapStart{0.f};   // race time when the current lap began
        float bestLap{0.f};
        float lastLap{0.f};
        float finishTime{0.f}; // race time at the finish, 0 while still racing
        int position{1};
        float progress{0.f};   // laps completed + fraction of the current lap
        float stuckTime{0.f};
        float wrongWayTime{0.f};
    };

    class RaceRules {
      public:
        RaceRules(std::shared_ptr<Track> const &track, uint32_t laps);

        // Line the field up behind the start line, player at the back
        void PlaceGrid(std::vector<std::shared_ptr<CarAgent>> const &racers);
        void Update(float deltaTime, std::vector<std::shared_ptr<CarAgent>> const &racers);
        // Send the HUD/audio telemetry for the player (racers[0]) to the page
        void Publish(std::vector<std::shared_ptr<CarAgent>> const &racers, int cameraMode) const;

        [[nodiscard]] bool CarsMayMove() const {
            return m_phase != RacePhase::Countdown;
        }
        [[nodiscard]] RacePhase Phase() const {
            return m_phase;
        }
        [[nodiscard]] bool Finished(size_t const racerIdx) const {
            return racerIdx < m_progress.size() && m_progress[racerIdx].finishTime > 0.f;
        }
        [[nodiscard]] float RaceTime() const {
            return m_raceTime;
        }

        static constexpr float kCountdownSeconds{4.0f};

      private:
        std::shared_ptr<Track> m_track;
        uint32_t m_laps;
        RacePhase m_phase{RacePhase::Countdown};
        float m_countdown{kCountdownSeconds};
        float m_raceTime{0.f};
        int m_finishers{0};
        std::vector<RacerProgress> m_progress;
        std::vector<int> m_finishOrder;
    };
} // namespace OpenNFS

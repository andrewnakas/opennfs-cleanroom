#include "PlayerAgent.h"

#include <algorithm>
#include <cmath>

#include "../../Physics/Car.h"
#include "../../Util/Utils.h"
#include "../../Web/WebPlatform.h"

#define GLM_ENABLE_EXPERIMENTAL
#include <glm/gtx/vector_angle.hpp>

namespace OpenNFS {
    PlayerAgent::PlayerAgent(InputManager const &inputManager, std::shared_ptr<Car> const &car, std::shared_ptr<Track> const &raceTrack)
        : CarAgent(PLAYER, car, raceTrack), m_inputManager(inputManager) {
        name = "You";
        car->physicsModel = Config::get().hsPhysics ? PhysicsModel::NFS4_PC : PhysicsModel::BULLET;
    }

    void PlayerAgent::Simulate() {
        // Update data required for efficient track physics update
        this->_UpdateNearestTrackblock();
        this->_UpdateNearestVroad();

        float const speed{vehicle->GetVehicle()->getCurrentSpeedKmHour()};
        bool accelerate{m_inputManager.accelerate};
        bool brakePedal{m_inputManager.brakes};
        bool left{m_inputManager.left}, right{m_inputManager.right};
        float steerAxis{m_inputManager.steerAxis};

        // Test autopilot: drives the player's car through the same controls a person uses (analogue steering,
        // throttle and brake) so automated runs can cover laps, finish and results
        if (Web::Autopilot() && !m_track->virtualRoad.empty()) {
            auto const &vroad{m_track->virtualRoad};
            auto const flat{[](glm::vec3 const &v) { return glm::normalize(glm::vec3(v.x, 0.f, v.z)); }};
            float const metresPerSecond{std::max(speed / 3.6f, 0.f)};
            uint32_t const aheadIdx{VroadAhead(8.f + metresPerSecond * 0.55f)};
            m_autopilotLane += std::clamp(ClearLane(aheadIdx, 0.f) - m_autopilotLane, -0.25f, 0.25f);
            glm::vec3 const target{LanePoint(aheadIdx, m_autopilotLane)};
            glm::vec3 const carForward{flat(Utils::bulletToGlm(vehicle->GetVehicle()->getForwardVector()))};
            float const angle{glm::orientedAngle(carForward, flat(target - vehicle->carBodyModel.position), glm::vec3(0, 1, 0))};
            steerAxis = std::clamp(-angle * 3.0f, -1.f, 1.f); // positive angle = target to the left
            left = right = false;

            float const grip{vehicle->assetData.physicsData.wheelFriction * 9.81f * 0.42f};
            float const targetSpeed{PlanSpeed(metresPerSecond, grip, 7.f, vehicle->assetData.physicsData.maxSpeed / 3.6f)};
            brakePedal = metresPerSecond > targetSpeed + 2.f;
            accelerate = !brakePedal && metresPerSecond < targetSpeed;
            // a test driver has no reverse gear: put the car back on the road when it is stuck
            m_autopilotTicks = (metresPerSecond < 2.f) ? m_autopilotTicks + 1 : 0;
            if (m_autopilotTicks > 400) {
                ResetOnRoad(m_nearestVroadID, 0.f);
                m_autopilotTicks = 0;
            }
        }

        // The brake pedal becomes reverse once the car is (nearly) stationary
        bool const reverse{brakePedal && !accelerate && speed < 4.f};
        bool const brake{brakePedal && !reverse};

        vehicle->ApplyAccelerationForce(accelerate, reverse);
        vehicle->ApplyBrakingForce(brake);
        vehicle->steerAxis = steerAxis;
        vehicle->ApplySteeringRight(right);
        vehicle->ApplySteeringLeft(left);
        vehicle->ApplyHandbrakes(m_inputManager.handbrakes);
        vehicle->ApplyGearChange(m_inputManager.shiftUp, m_inputManager.shiftDown);

        if (m_inputManager.reset) {
            ResetOnRoad(m_nearestVroadID, 0.f);
        }
        if (m_inputManager.lights) {
            vehicle->ToggleHeadlights();
        }
    }
} // namespace OpenNFS

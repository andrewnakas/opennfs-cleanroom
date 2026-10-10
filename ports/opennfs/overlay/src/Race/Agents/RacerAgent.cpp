#include "RacerAgent.h"

#include <algorithm>
#include <cmath>

#include "../../Physics/Car.h"
#include "../../Util/Utils.h"

#define GLM_ENABLE_EXPERIMENTAL
#include <glm/gtx/vector_angle.hpp>

namespace OpenNFS {
    namespace {
        constexpr uint32_t kSlowTicksBeforeReverse{150};
        constexpr uint32_t kReverseTicks{70};
        constexpr uint32_t kMaxReverseAttempts{2};
        constexpr uint32_t kWrongWayTicksBeforeReset{120};
        constexpr float kBrakeDeceleration{7.0f}; // m/s^2 assumed when planning for a corner

        glm::vec3 Flat(glm::vec3 const &v) {
            glm::vec3 const flat{v.x, 0.f, v.z};
            float const length{glm::length(flat)};
            return length > 1e-5f ? flat / length : glm::vec3(0, 0, 1);
        }
    } // namespace

    RacerAgent::RacerAgent(RacerData const &racerData, std::shared_ptr<Car> const &car, std::shared_ptr<Track> const &raceTrack)
        : CarAgent(AgentType::AI, car, raceTrack) {
        name = racerData.name;
        this->vehicle = std::make_shared<Car>(car->assetData, car->assetPath);
        vehicle->physicsModel = PhysicsModel::BULLET;
        m_skill = Utils::RandomFloat(0.80f, 0.97f);
        m_lane = Utils::RandomFloat(-0.55f, 0.55f); // fraction of the usable half width
        if (m_track->virtualRoad.size() > 1) {
            m_segmentLength = std::max(glm::distance(m_track->virtualRoad[0].position, m_track->virtualRoad[1].position), 0.5f);
        }
    }

    RacerState RacerAgent::State() const {
        return m_state;
    }

    void RacerAgent::Simulate() {
        this->_UpdateNearestTrackblock();
        this->_UpdateNearestVroad();
        ++m_ticksAlive;

        auto const &vroad{m_track->virtualRoad};
        if (vroad.empty()) {
            return;
        }
        float const speedKmh{vehicle->GetVehicle()->getCurrentSpeedKmHour()};
        glm::vec3 const carForward{Flat(Utils::bulletToGlm(vehicle->GetVehicle()->getForwardVector()))};
        glm::vec3 const roadForward{Flat(vroad[m_nearestVroadID % vroad.size()].forward)};
        bool const upsideDown{vehicle->rangefinderInfo.upDistance <= 0.1f && vehicle->rangefinderInfo.downDistance > 1.f};

        switch (m_state) {
        case RacerState::RESETTING:
            ResetOnRoad(m_nearestVroadID, m_lane * std::clamp(RoadHalfWidth(m_nearestVroadID) - 1.6f, 0.f, 3.2f));
            m_ticksSlow = m_ticksReversing = m_ticksWrongWay = m_reverseAttempts = 0;
            m_state = RacerState::TRACK_FOLLOWING;
            break;
        case RacerState::STUCK_REVERSING:
            vehicle->ApplyAbsoluteSteerAngle(0.f);
            vehicle->ApplyAccelerationForce(false, true);
            vehicle->ApplyBrakingForce(false);
            if (++m_ticksReversing >= kReverseTicks) {
                m_ticksReversing = m_ticksSlow = 0;
                m_state = RacerState::TRACK_FOLLOWING;
            }
            break;
        case RacerState::TRACK_FOLLOWING:
            this->_Drive();
            // Give the start (and the countdown) time before deciding the car is stuck
            m_ticksSlow = (std::fabs(speedKmh) < 6.f && m_ticksAlive > 600) ? m_ticksSlow + 1 : 0;
            m_ticksWrongWay = (glm::dot(carForward, roadForward) < -0.2f) ? m_ticksWrongWay + 1 : 0;
            if (upsideDown || m_ticksWrongWay > kWrongWayTicksBeforeReset) {
                m_state = RacerState::RESETTING;
            } else if (m_ticksSlow > kSlowTicksBeforeReverse) {
                m_state = (m_reverseAttempts++ < kMaxReverseAttempts) ? RacerState::STUCK_REVERSING : RacerState::RESETTING;
                m_ticksSlow = 0;
            }
            break;
        }
    }

    void RacerAgent::_Drive() {
        auto const &vroad{m_track->virtualRoad};
        auto const &physics{vehicle->assetData.physicsData};
        float const speed{std::max(vehicle->GetVehicle()->getCurrentSpeedKmHour() / 3.6f, 0.f)}; // m/s
        glm::vec3 const position{vehicle->carBodyModel.position};
        glm::vec3 const carForward{Flat(Utils::bulletToGlm(vehicle->GetVehicle()->getForwardVector()))};
        glm::vec3 const up{0.f, 1.f, 0.f};

        // Steering: aim at a point on the virtual road further ahead the faster we go
        m_futureVroadID = VroadAhead(8.f + speed * 0.55f);
        glm::vec3 const targetForward{Flat(vroad[m_futureVroadID].forward)};
        glm::vec3 const targetRight{glm::normalize(glm::cross(targetForward, up))};
        // the stored wall distances include verges and run-off: stay within a lane's width of the driving line
        float const usable{std::clamp(RoadHalfWidth(m_futureVroadID) - 1.6f, 0.f, 3.2f)};
        // ... unless something stands in the way: then move over (and ease back once it is passed)
        float const wanted{ClearLane(m_futureVroadID, m_lane * usable)};
        m_laneNow += std::clamp(wanted - m_laneNow, -0.25f, 0.25f);
        targetVroadPosition = vroad[m_futureVroadID].position + targetRight * m_laneNow;
        float const angle{glm::orientedAngle(carForward, Flat(targetVroadPosition - position), up)};
        vehicle->ApplyAbsoluteSteerAngle(angle * 0.85f);

        // Speed plan: for every upcoming bend, the speed we may carry now and still brake in time
        float const lateralGrip{physics.wheelFriction * 9.81f * 0.44f * m_skill};
        float targetSpeed{PlanSpeed(speed, lateralGrip, kBrakeDeceleration, physics.maxSpeed / 3.6f * (0.90f + 0.10f * m_skill))};
        // Ease off when badly misaligned so the car can turn in
        if (std::fabs(angle) > 0.5f) {
            targetSpeed = std::min(targetSpeed, 14.f);
        }

        bool const brake{speed > targetSpeed + 2.f};
        vehicle->ApplyAccelerationForce(!brake && speed < targetSpeed, false);
        vehicle->ApplyBrakingForce(brake);
    }
} // namespace OpenNFS

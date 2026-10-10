#include "CarAgent.h"

#include <algorithm>
#include <cfloat>
#include <cmath>

#include "../../Physics/Car.h"

namespace OpenNFS {
    CarAgent::CarAgent(AgentType const agentType, std::shared_ptr<Car> const &car, std::shared_ptr<Track> const &track)
        : vehicle(car), m_track(track), m_agentType(agentType) {
    }

    void CarAgent::ResetToIndexInTrackblock(int trackBlockIndex, int const posIndex, float const offset) const {
        // Can move this by trk[trackBlockIndex].nodePositions
        uint32_t nodeNumber{m_track->trackBlocks[trackBlockIndex].virtualRoadStartIndex};
        uint32_t nPositions{m_track->trackBlocks[trackBlockIndex].nVirtualRoadPositions};
        if (posIndex <= nPositions) {
            nodeNumber += posIndex;
        } else {
            // Advance the trackblock until we can get to posIndex
            int nExtra = posIndex - static_cast<int>(nPositions);
            while (true) {
                nodeNumber = m_track->trackBlocks[++trackBlockIndex].virtualRoadStartIndex;
                nPositions = m_track->trackBlocks[trackBlockIndex].nVirtualRoadPositions;
                if (nExtra < nPositions) {
                    nodeNumber += nExtra;
                    break;
                }
                nExtra -= static_cast<int>(nPositions);
            }
        }
        this->ResetToVroad(nodeNumber, offset);
    }

    // offset: metres from the road centre, positive to the right of travel
    void CarAgent::ResetToVroad(int const vroadIndex, float const offset) const {
        CHECK_F(vroadIndex >= 0 && static_cast<size_t>(vroadIndex) < m_track->virtualRoad.size(),
                "Requested reset to vroad index: %d outside of num vroad chunks", vroadIndex);
        auto const &vroad{m_track->virtualRoad[vroadIndex]};
        glm::vec3 vroadPoint{vroad.position + vroad.respawn};
        // The virtual road floats 0.2 above the surface. Put the wheels on the ground, not the chassis origin
        vroadPoint.y += vehicle->assetData.physicsData.wheelRadius - vehicle->leftFrontWheelModel.initialPosition.y - 0.15f;
        glm::quat const carOrientation{glm::conjugate(glm::toQuat(glm::lookAt(vroadPoint, vroadPoint - vroad.forward, vroad.normal)))};
        // The loader does not mirror the 'right' vector with the rest of the track: derive it from forward
        vroadPoint += offset * glm::normalize(glm::cross(vroad.forward, glm::vec3(0, 1, 0)));
        vehicle->SetPosition(vroadPoint, carOrientation);
    }

    // Half of the drivable width at a virtual road position, from the wall distances stored with the track
    float CarAgent::RoadHalfWidth(uint32_t const vroadIndex) const {
        auto const &vroad{m_track->virtualRoad[vroadIndex % m_track->virtualRoad.size()]};
        float const left{glm::length(vroad.leftWall)}, right{glm::length(vroad.rightWall)};
        float const half{std::min(left, right)};
        return (half > 1.f && half < 40.f) ? half : 6.f;
    }

    uint32_t CarAgent::VroadAhead(float const distance) const {
        auto const &vroad{m_track->virtualRoad};
        auto const count{static_cast<uint32_t>(vroad.size())};
        uint32_t idx{m_nearestVroadID % count};
        float travelled{0.f};
        for (uint32_t step = 0; step < count && travelled < distance; ++step) {
            uint32_t const next{(idx + 1) % count};
            travelled += glm::distance(vroad[idx].position, vroad[next].position);
            idx = next;
        }
        return idx;
    }

    float CarAgent::PlanSpeed(float const currentSpeed, float const lateralGrip, float const brakeDeceleration, float const topSpeed) const {
        auto const &vroad{m_track->virtualRoad};
        auto const count{static_cast<uint32_t>(vroad.size())};
        if (count < 4) {
            return topSpeed;
        }
        float targetSpeed{topSpeed};
        float const planDistance{currentSpeed * currentSpeed / (2.f * brakeDeceleration) + 45.f};
        uint32_t idx{m_nearestVroadID % count};
        float travelled{0.f};
        // Curvature from the positions themselves (the stored direction vectors are coarse 8-bit values and the
        // spacing between positions is not constant)
        for (uint32_t step = 0; step < count && travelled < planDistance; ++step) {
            glm::vec3 const p0{vroad[idx].position}, p1{vroad[(idx + 1) % count].position}, p2{vroad[(idx + 2) % count].position};
            glm::vec3 a{p1 - p0}, b{p2 - p1};
            a.y = b.y = 0.f;
            float const la{glm::length(a)}, lb{glm::length(b)};
            travelled += la;
            idx = (idx + 1) % count;
            if (la < 0.01f || lb < 0.01f) {
                continue;
            }
            float const bend{std::acos(std::clamp(glm::dot(a, b) / (la * lb), -1.f, 1.f))};
            float const curvature{bend / (0.5f * (la + lb))};
            if (curvature < 1e-4f) {
                continue;
            }
            float const cornerSpeed{std::sqrt(lateralGrip / curvature)};
            targetSpeed = std::min(targetSpeed, std::sqrt(cornerSpeed * cornerSpeed + 2.f * brakeDeceleration * travelled));
        }
        return targetSpeed;
    }

    glm::vec3 CarAgent::LanePoint(uint32_t const vroadIndex, float const lateral) const {
        auto const &vroad{m_track->virtualRoad[vroadIndex % m_track->virtualRoad.size()]};
        glm::vec3 const right{glm::normalize(glm::cross(glm::vec3(vroad.forward.x, 0.f, vroad.forward.z), glm::vec3(0, 1, 0)))};
        return vroad.position + right * lateral;
    }

    float CarAgent::ClearLane(uint32_t const vroadIndex, float const preferred) const {
        // Some circuits put scenery on the driving line itself (traffic islands, signs, pillars)
        float const limit{std::max(RoadHalfWidth(vroadIndex) - 1.4f, 0.f)};
        glm::vec3 const from{vehicle->carBodyModel.position};
        glm::vec3 const side{glm::normalize(glm::cross(LanePoint(vroadIndex, 0.f) - from, glm::vec3(0, 1, 0)))};
        // rays run at bumper height (kerbs and planters stop a car as surely as walls do), one along each flank
        glm::vec3 const low{from - glm::vec3(0.f, 0.35f, 0.f)};
        auto const blocked{[&](float const lateral) {
            glm::vec3 const to{LanePoint(vroadIndex, lateral) + glm::vec3(0.f, 0.15f, 0.f)};
            return vehicle->PathBlocked(low + side * 0.95f, to + side * 0.95f) || vehicle->PathBlocked(low - side * 0.95f, to - side * 0.95f);
        }};
        if (!blocked(preferred)) {
            return preferred;
        }
        for (float const step : {2.5f, 4.5f, 6.5f, 9.f}) {
            // try the side nearer to the preferred line first
            for (float const sign : {preferred >= 0.f ? 1.f : -1.f, preferred >= 0.f ? -1.f : 1.f}) {
                float const lateral{preferred + sign * step};
                if (std::fabs(lateral) <= limit && !blocked(lateral)) {
                    return lateral;
                }
            }
        }
        return preferred;
    }

    void CarAgent::ResetOnRoad(uint32_t const vroadIndex, float const preferred) const {
        auto const count{static_cast<uint32_t>(m_track->virtualRoad.size())};
        float const limit{std::max(RoadHalfWidth(vroadIndex) - 1.4f, 0.f)};
        // a spot is usable when the stretch from it to a few positions further on is free of scenery
        auto const clear{[&](float const lateral) {
            glm::vec3 const here{LanePoint(vroadIndex, lateral) + glm::vec3(0.f, 0.25f, 0.f)};
            glm::vec3 const ahead{LanePoint((vroadIndex + 3) % count, lateral) + glm::vec3(0.f, 0.25f, 0.f)};
            glm::vec3 const side{glm::normalize(glm::cross(ahead - here, glm::vec3(0, 1, 0)))};
            return !vehicle->PathBlocked(here + side * 0.95f, ahead + side * 0.95f) && !vehicle->PathBlocked(here - side * 0.95f, ahead - side * 0.95f) &&
                   !vehicle->PathBlocked(here - side * 1.2f, here + side * 1.2f);
        }};
        float lateral{preferred};
        if (!clear(lateral)) {
            for (float const step : {2.5f, -2.5f, 4.5f, -4.5f, 6.5f, -6.5f}) {
                if (std::fabs(preferred + step) <= limit && clear(preferred + step)) {
                    lateral = preferred + step;
                    break;
                }
            }
        }
        ResetToVroad(static_cast<int>(vroadIndex), lateral);
    }

    void CarAgent::_UpdateNearestTrackblock() {
        // Web port: the block follows from the virtual road position (see _UpdateNearestVroad). Picking the block whose
        // centre is nearest, as upstream does, jumps to a neighbouring stretch of road wherever two sections run close together.
        auto const count{static_cast<uint32_t>(m_track->virtualRoad.size())};
        if (count == 0) {
            return;
        }
        uint32_t const vroad{m_nearestVroadID % count};
        for (auto const &trackblock : m_track->trackBlocks) {
            if (vroad >= trackblock.virtualRoadStartIndex && vroad < trackblock.virtualRoadStartIndex + trackblock.nVirtualRoadPositions) {
                m_nearestTrackblockID = trackblock.id;
                return;
            }
        }
    }

    void CarAgent::_UpdateNearestVroad() {
        auto const &vroad{m_track->virtualRoad};
        auto const count{static_cast<int>(vroad.size())};
        if (count == 0) {
            return;
        }
        glm::vec3 const position{vehicle->carBodyModel.position};
        // Follow the road continuously: look a little behind and further ahead of the last known position
        constexpr int kBack{6}, kAhead{18};
        float lowestDistance{FLT_MAX};
        int best{static_cast<int>(m_nearestVroadID) % count};
        for (int step = -kBack; step <= kAhead; ++step) {
            int const idx{((static_cast<int>(m_nearestVroadID) + step) % count + count) % count};
            float const distance{glm::distance(position, vroad[idx].position)};
            if (distance < lowestDistance) {
                lowestDistance = distance;
                best = idx;
            }
        }
        // Lost (first frame, or after being put back on the road elsewhere): search the whole track
        if (lowestDistance > 45.f) {
            for (int idx = 0; idx < count; ++idx) {
                float const distance{glm::distance(position, vroad[idx].position)};
                if (distance < lowestDistance) {
                    lowestDistance = distance;
                    best = idx;
                }
            }
        }
        m_nearestVroadID = static_cast<uint32_t>(best);
    }
} // namespace OpenNFS

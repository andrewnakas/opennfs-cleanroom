#include "RaceRules.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <numeric>

#include "../Physics/Car.h"
#include "../Util/Utils.h"
#include "../Web/WebPlatform.h"

namespace OpenNFS {
    namespace {
        constexpr int kSectors{4};
        constexpr float kGridLateral{2.6f}; // metres either side of the centre line
        constexpr uint32_t kGridRowSpacing{2}; // virtual road positions between grid rows

        // Arcade automatic gearbox, only used to give the page an engine note to play
        struct GearInfo {
            int gear;
            float rpm;
        };
        GearInfo FakeGearbox(float const speedKmh, float const maxSpeedKmh) {
            static constexpr float kTop[6] = {0.17f, 0.31f, 0.47f, 0.64f, 0.82f, 1.05f};
            float const ratio{std::clamp(std::fabs(speedKmh) / std::max(maxSpeedKmh, 1.f), 0.f, 1.05f)};
            int gear{0};
            while (gear < 5 && ratio > kTop[gear]) {
                ++gear;
            }
            float const lower{gear == 0 ? 0.f : kTop[gear - 1] * 0.62f};
            float const t{std::clamp((ratio - lower) / (kTop[gear] - lower), 0.f, 1.f)};
            return {gear + 1, 1100.f + 5900.f * t};
        }
    } // namespace

    RaceRules::RaceRules(std::shared_ptr<Track> const &track, uint32_t const laps) : m_track(track), m_laps(std::max(laps, 1u)) {
    }

    void RaceRules::PlaceGrid(std::vector<std::shared_ptr<CarAgent>> const &racers) {
        auto const nVroad{static_cast<uint32_t>(m_track->virtualRoad.size())};
        m_progress.assign(racers.size(), RacerProgress{});
        m_finishOrder.clear();
        m_finishers = 0;
        for (size_t racerIdx = 0; racerIdx < racers.size(); ++racerIdx) {
            // racers[0] is the player and starts from the back of the grid
            size_t const slot{racerIdx == 0 ? racers.size() - 1 : racerIdx - 1};
            uint32_t const back{2 + static_cast<uint32_t>(slot / 2) * kGridRowSpacing + static_cast<uint32_t>(slot % 2)};
            uint32_t const vroadIdx{(static_cast<uint32_t>(Web::StartVroad()) + nVroad - (back % nVroad)) % nVroad};
            float const lateral{std::clamp(racers[racerIdx]->RoadHalfWidth(vroadIdx) - 1.5f, 0.f, kGridLateral)};
            racers[racerIdx]->ResetToVroad(static_cast<int>(vroadIdx), (slot % 2 == 0) ? -lateral : lateral);
        }
    }

    void RaceRules::Update(float const deltaTime, std::vector<std::shared_ptr<CarAgent>> const &racers) {
        if (m_progress.size() != racers.size()) {
            m_progress.assign(racers.size(), RacerProgress{});
        }
        auto const nVroad{static_cast<int>(m_track->virtualRoad.size())};
        if (nVroad == 0) {
            return;
        }

        if (m_phase == RacePhase::Countdown) {
            m_countdown -= deltaTime;
            for (auto const &racer : racers) {
                // Hold the field on the brakes
                racer->vehicle->ApplyAccelerationForce(false, false);
                racer->vehicle->ApplyBrakingForce(true);
                racer->vehicle->ApplySteeringLeft(false);
                racer->vehicle->ApplySteeringRight(false);
            }
            if (m_countdown <= 0.f) {
                m_phase = RacePhase::Racing;
                m_raceTime = 0.f;
                for (auto const &racer : racers) {
                    racer->vehicle->ApplyBrakingForce(false);
                }
            }
        } else {
            m_raceTime += deltaTime;
            if (m_phase == RacePhase::Finished && !racers.empty()) {
                // The player's race is over: roll to a stop while the rest of the field finishes
                racers[0]->vehicle->ApplyAccelerationForce(false, false);
                racers[0]->vehicle->ApplyBrakingForce(true);
            }
        }

        for (size_t racerIdx = 0; racerIdx < racers.size(); ++racerIdx) {
            auto const &racer{racers[racerIdx]};
            RacerProgress &progress{m_progress[racerIdx]};
            int const vroad{static_cast<int>(racer->NearestVroad()) % nVroad};
            int const sector{std::min(vroad * kSectors / nVroad, kSectors - 1)};

            if (m_phase != RacePhase::Countdown && sector == (progress.sector + 1) % kSectors) {
                progress.sector = sector;
                if (sector == 0) {
                    if (progress.crossings > 0) {
                        progress.lastLap = m_raceTime - progress.lapStart;
                        if (progress.bestLap <= 0.f || progress.lastLap < progress.bestLap) {
                            progress.bestLap = progress.lastLap;
                        }
                    }
                    progress.lapStart = (progress.crossings == 0) ? 0.f : m_raceTime;
                    ++progress.crossings;
                    if (progress.crossings > static_cast<int>(m_laps) && progress.finishTime <= 0.f) {
                        progress.finishTime = m_raceTime;
                        m_finishOrder.push_back(static_cast<int>(racerIdx));
                        ++m_finishers;
                        if (racerIdx == 0) {
                            m_phase = RacePhase::Finished;
                        }
                    }
                }
            }

            // Laps completed + fraction of the lap, robust to a car sitting just behind the line
            float fraction{static_cast<float>(vroad) / static_cast<float>(nVroad)};
            if (progress.sector == 0 && sector == kSectors - 1) {
                fraction -= 1.f; // rolled back over the line
            } else if (progress.sector == kSectors - 1 && sector == 0) {
                fraction += 1.f;
            }
            progress.progress = static_cast<float>(progress.crossings - 1) + fraction;

            // Wrong way: moving against the virtual road direction
            btVector3 const velocity{racer->vehicle->GetVehicleRigidBody()->getLinearVelocity()};
            glm::vec3 const roadForward{m_track->virtualRoad[vroad].forward};
            float const along{glm::dot(Utils::bulletToGlm(velocity), glm::normalize(roadForward))};
            progress.wrongWayTime = (along < -3.f) ? progress.wrongWayTime + deltaTime : 0.f;

            // Recover cars that ended up on their roof, wedged with no wheel on the ground, or outside the world
            btTransform const &transform{racer->vehicle->GetVehicleRigidBody()->getWorldTransform()};
            float const upY{static_cast<float>(transform.getBasis().getColumn(1).getY())};
            float const height{static_cast<float>(transform.getOrigin().getY()) - m_track->virtualRoad[vroad].position.y};
            int grounded{0};
            btRaycastVehicle *raycastVehicle{racer->vehicle->GetVehicle()};
            for (int wheelIdx = 0; wheelIdx < raycastVehicle->getNumWheels(); ++wheelIdx) {
                grounded += raycastVehicle->getWheelInfo(wheelIdx).m_raycastInfo.m_isInContact ? 1 : 0;
            }
            bool const lost{height < -25.f || height > 60.f};
            bool const helpless{upY < 0.25f || (grounded == 0 && velocity.length() < 2.f)};
            progress.stuckTime = (helpless || lost) ? progress.stuckTime + deltaTime : 0.f;
            if (m_phase != RacePhase::Countdown && (lost || progress.stuckTime > 2.0f)) {
                racer->ResetOnRoad(static_cast<uint32_t>(vroad), 0.f);
                progress.stuckTime = 0.f;
            }
        }

        // Positions: finishers in finishing order, then everyone else by distance covered
        std::vector<int> order(racers.size());
        std::iota(order.begin(), order.end(), 0);
        std::ranges::stable_sort(order, [this](int const a, int const b) {
            bool const aDone{m_progress[a].finishTime > 0.f}, bDone{m_progress[b].finishTime > 0.f};
            if (aDone != bDone) {
                return aDone;
            }
            if (aDone) {
                return m_progress[a].finishTime < m_progress[b].finishTime;
            }
            return m_progress[a].progress > m_progress[b].progress;
        });
        for (size_t place = 0; place < order.size(); ++place) {
            m_progress[order[place]].position = static_cast<int>(place) + 1;
        }
    }

    void RaceRules::Publish(std::vector<std::shared_ptr<CarAgent>> const &racers, int const cameraMode) const {
        if (racers.empty() || m_progress.size() != racers.size()) {
            return;
        }
        auto const &player{racers[0]};
        RacerProgress const &progress{m_progress[0]};
        btRaycastVehicle *vehicle{player->vehicle->GetVehicle()};
        float const speed{vehicle->getCurrentSpeedKmHour()};
        float const maxSpeed{player->vehicle->assetData.physicsData.maxSpeed};
        auto const [gear, rpm]{FakeGearbox(speed, maxSpeed)};

        float skid{0.f};
        int grounded{0};
        for (int wheelIdx = 0; wheelIdx < vehicle->getNumWheels(); ++wheelIdx) {
            btWheelInfo const &wheel{vehicle->getWheelInfo(wheelIdx)};
            if (wheel.m_raycastInfo.m_isInContact) {
                ++grounded;
                skid = std::max(skid, 1.f - static_cast<float>(wheel.m_skidInfo));
            }
        }
        bool const throttle{player->vehicle->vehicleState.gEngineForce > 0.f};
        bool const braking{player->vehicle->vehicleState.gBrakingForce > 0.f};
        btVector3 const velocity{player->vehicle->GetVehicleRigidBody()->getLinearVelocity()};

        int const lap{std::clamp(progress.crossings, 1, static_cast<int>(m_laps))};
        float const lapTime{m_phase == RacePhase::Countdown ? 0.f : (progress.finishTime > 0.f ? progress.lastLap : m_raceTime - progress.lapStart)};

        // Where the car is on the road (for the page's off-road hint and for automated tests)
        auto const nVroad{static_cast<uint32_t>(m_track->virtualRoad.size())};
        uint32_t const vroadIdx{nVroad > 0 ? player->NearestVroad() % nVroad : 0};
        float lateral{0.f}, halfWidth{0.f}, headingError{0.f};
        if (nVroad > 0) {
            auto const &vroad{m_track->virtualRoad[vroadIdx]};
            glm::vec3 const roadForward{glm::normalize(glm::vec3(vroad.forward.x, 0.f, vroad.forward.z))};
            glm::vec3 const roadRight{glm::normalize(glm::cross(roadForward, glm::vec3(0, 1, 0)))};
            lateral = glm::dot(player->vehicle->carBodyModel.position - vroad.position, roadRight);
            halfWidth = player->RoadHalfWidth(vroadIdx);
            glm::vec3 const carForward{Utils::bulletToGlm(vehicle->getForwardVector())};
            headingError = glm::degrees(std::atan2(glm::dot(carForward, roadRight), glm::dot(carForward, roadForward)));
        }

        char json[1536];
        int n{std::snprintf(
            json, sizeof(json),
            "{\"phase\":%d,\"count\":%.2f,\"speed\":%.1f,\"max\":%.0f,\"gear\":%d,\"rpm\":%.0f,\"thr\":%d,\"brk\":%d,\"skid\":%.2f,"
            "\"gnd\":%d,\"vy\":%.2f,\"lap\":%d,\"laps\":%u,\"pos\":%d,\"n\":%zu,\"time\":%.2f,\"lapTime\":%.2f,\"best\":%.2f,\"last\":%.2f,"
            "\"wrong\":%d,\"cam\":%d,\"finish\":%.2f,\"vr\":%u,\"nvr\":%u,\"off\":%.1f,\"hw\":%.1f,\"head\":%.0f,\"results\":[",
            static_cast<int>(m_phase), std::max(m_countdown, 0.f), std::fabs(speed), maxSpeed, speed < -1.f ? 0 : gear, rpm, throttle ? 1 : 0,
            braking ? 1 : 0, skid, grounded, static_cast<double>(velocity.getY()), lap, m_laps, progress.position, racers.size(),
            m_raceTime, lapTime, progress.bestLap, progress.lastLap, progress.wrongWayTime > 1.2f ? 1 : 0, cameraMode,
            progress.finishTime, vroadIdx, nVroad, lateral, halfWidth, headingError)};
        n = std::min(n, static_cast<int>(sizeof(json)) - 3);
        // Standings (name, finish time or 0, best lap), in position order
        std::vector<int> order(racers.size());
        std::iota(order.begin(), order.end(), 0);
        std::ranges::sort(order, [this](int const a, int const b) { return m_progress[a].position < m_progress[b].position; });
        for (size_t place = 0; place < order.size() && n < static_cast<int>(sizeof(json)) - 96; ++place) {
            int const idx{order[place]};
            std::string name{racers[idx]->name.substr(0, 16)};
            std::erase_if(name, [](char const c) { return c == '"' || c == '\\' || static_cast<unsigned char>(c) < 32; });
            n += std::snprintf(json + n, sizeof(json) - n, "%s{\"name\":\"%s\",\"me\":%d,\"t\":%.2f,\"best\":%.2f}", place ? "," : "", name.c_str(),
                               idx == 0 ? 1 : 0, m_progress[idx].finishTime, m_progress[idx].bestLap);
            n = std::min(n, static_cast<int>(sizeof(json)) - 3); // snprintf returns the untruncated length
        }
        std::snprintf(json + n, sizeof(json) - n, "]}");
        Web::PublishState(json);
    }
} // namespace OpenNFS

"""Patch list that turns the pristine OpenNFS engine into the web port.

PATCHES: {relative path: [(old, new[, expected count; 0 = any])]}
REMOVED: files of the pristine tree that are not part of the port.
"""

import codecs


def _d(text):
    """Upstream strings that name retail car folders are stored encoded (see tools/name_scan.py)."""
    return codecs.decode(text[::-1], "rot13")


REMOVED = {
    "src/Renderer/vkRenderer.cpp",
    "src/Renderer/vkRenderer.h",
    # decoder for retail audio containers; unused by the engine and of no use without retail files
    "src/Loaders/MusicLoader.cpp",
    "src/Loaders/MusicLoader.h",
}

NOT_GL4 = "#if !defined(__APPLE__) && !defined(__EMSCRIPTEN__)"
GL3_ONLY = "#if defined(__APPLE__) || defined(__EMSCRIPTEN__)"

SHADOW_BOUNDS = """    // Check if outside shadow map
    if (projCoords.z > 1.0 || projCoords.x < 0.0 || projCoords.x > 1.0 || projCoords.y < 0.0 || projCoords.y > 1.0) {
        return 0.0;
    }"""
SHADOW_BOUNDS_OLD = """    // Check if outside shadow map
    if (projCoords.z > 1.0) {
        return 0.0;
    }"""

PATCHES = {
    # ---------------------------------------------------------------- configuration
    "src/Config.h": [
        ('std::string const ONFS_GL_VERSION{"330"};', 'std::string const ONFS_GL_VERSION{"300 es"};'),
        # generic clean-room car id (the engine default names a retail car folder)
        ('std::string const DEFAULT_CAR{"' + _d("iebp") + '"};', 'std::string const DEFAULT_CAR{"cgt1"};'),
    ],
    # ---------------------------------------------------------------- GL context
    "src/Renderer/Renderer.cpp": [
        ("""        glfwWindowHint(GLFW_CONTEXT_VERSION_MAJOR, 3);
        glfwWindowHint(GLFW_CONTEXT_VERSION_MINOR, 3);
        glfwWindowHint(GLFW_OPENGL_PROFILE, GLFW_OPENGL_CORE_PROFILE);
        glfwWindowHint(GLFW_OPENGL_FORWARD_COMPAT, GL_TRUE); // Appease the OSX Gods
""", """        // WebGL2 == OpenGL ES 3.0
        glfwWindowHint(GLFW_CLIENT_API, GLFW_OPENGL_ES_API);
        glfwWindowHint(GLFW_CONTEXT_VERSION_MAJOR, 3);
        glfwWindowHint(GLFW_CONTEXT_VERSION_MINOR, 0);
"""),
        ("""            GLFWmonitor *monitor = glfwGetPrimaryMonitor();
            int monitorWidth, monitorHeight;
            glfwGetMonitorWorkarea(monitor, nullptr, nullptr, &monitorWidth, &monitorHeight);
""", """            // The canvas is resized to its CSS box every frame (Web::SyncCanvasSize)
            int monitorWidth{1280}, monitorHeight{720};
"""),
        ('#ifndef __APPLE__\n        ImGui::Begin("Shadow Map Cascades");', NOT_GL4 + '\n        ImGui::Begin("Shadow Map Cascades");'),
    ],
    "src/Renderer/ShadowMapRenderer.cpp": [
        ("#ifdef __APPLE__\n        glTexImage3D", GL3_ONLY + "\n        glTexImage3D"),
        ("""        float borderColour[] = {1.0f, 1.0f, 1.0f, 1.0f};
        glTexParameterfv(GL_TEXTURE_2D_ARRAY, GL_TEXTURE_BORDER_COLOR, borderColour);
""", """#ifndef __EMSCRIPTEN__
        float borderColour[] = {1.0f, 1.0f, 1.0f, 1.0f};
        glTexParameterfv(GL_TEXTURE_2D_ARRAY, GL_TEXTURE_BORDER_COLOR, borderColour);
#endif
"""),
        ("        glDrawBuffer(GL_NONE);\n", "        {\n            GLenum const none{GL_NONE};\n            glDrawBuffers(1, &none);\n        }\n"),
        ("#ifndef __APPLE__\n        // Gahh", NOT_GL4 + "\n        // Gahh"),
        # shadows can be switched off (slow devices, software-rendered tests): the cleared map reads as "lit"
        ("        glClear(GL_DEPTH_BUFFER_BIT);\n", "        glClear(GL_DEPTH_BUFFER_BIT);\n        if (!Web::Shadows()) {\n            return;\n        }\n"),
        ('#include "ShadowMapRenderer.h"\n', '#include "ShadowMapRenderer.h"\n\n#include "../Web/WebPlatform.h"\n'),
    ],
    "src/Renderer/GLTexture.h": [("#include <GL/glew.h>\n", "#include <GL/glew.h>\n#include <map>\n")],
    "src/Renderer/GLTexture.cpp": [
        # allocate only the layers in use (512 layers of RGBA8 is far too much for a browser tab) and a full mip chain
        ("""        glTexStorage3D(GL_TEXTURE_2D_ARRAY, 3, GL_RGBA8, static_cast<GLsizei>(max_width), static_cast<GLsizei>(max_height),
                       MAX_TEXTURE_ARRAY_SIZE);
""", """        uint32_t layerCount{1};
        for (auto &[id, glTexture] : textures) {
            layerCount = std::max(layerCount, id + 1);
        }
        GLsizei mipLevels{1};
        for (size_t extent = std::max(max_width, max_height); extent > 1; extent >>= 1) {
            ++mipLevels;
        }
        glTexStorage3D(GL_TEXTURE_2D_ARRAY, mipLevels, GL_RGBA8, static_cast<GLsizei>(max_width), static_cast<GLsizei>(max_height),
                       static_cast<GLsizei>(layerCount));
"""),
        ("""        glTexParameteri(GL_TEXTURE_2D_ARRAY, GL_TEXTURE_MIN_FILTER, GL_NEAREST_MIPMAP_LINEAR);
        glTexParameteri(GL_TEXTURE_2D_ARRAY, GL_TEXTURE_MAG_FILTER, GL_NEAREST_MIPMAP_LINEAR);
""", """        glTexParameteri(GL_TEXTURE_2D_ARRAY, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR);
        glTexParameteri(GL_TEXTURE_2D_ARRAY, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
"""),
    ],
    # ---------------------------------------------------------------- shaders (GLSL ES 3.00)
    "shaders/ShaderPreamble.h": [
        ("#pragma once\n", """#pragma once
precision highp float;
precision highp int;
precision highp sampler2D;
precision highp sampler2DArray;
precision highp sampler2DArrayShadow;
"""),
    ],
    # GLSL ES has no implicit int -> float conversion
    "shaders/SkydomeShader.frag": [
        ("round(400*x.x)", "round(400.0*x.x)"), ("round(400*x.y)", "round(400.0*x.y)"), ("round(400*x.z)", "round(400.0*x.z)"),
        ("/(2*3.14159265)", "/(2.0*3.14159265)"),
        ("(sun_norm.y > 0 ? 0.95", "(sun_norm.y > 0.0 ? 0.95"),
        ("clamp(sun_norm.y,0.01,1)", "clamp(sun_norm.y,0.01,1.0)"),
        ("clamp(-sun_norm.y*3,0,1)", "clamp(-sun_norm.y*3.0,0.0,1.0)"),
        ("clamp((2-weather)*transparency,0,1)", "clamp((2.0-weather)*transparency,0.0,1.0)"),
    ],
    "src/Renderer/SkyRenderer.cpp": [
        # the cloud layer scrolls in u and is addressed with negative v: it has to wrap (the upstream border clamp shows no clouds)
        ("clouds1TextureID = ImageLoader::LoadImage(clouds1_texture_path, &width, &height, GL_CLAMP_TO_BORDER, GL_LINEAR_MIPMAP_LINEAR);",
         "clouds1TextureID = ImageLoader::LoadImage(clouds1_texture_path, &width, &height, GL_REPEAT, GL_LINEAR_MIPMAP_LINEAR);"),
        ("clouds2TextureID = ImageLoader::LoadImage(clouds2_texture_path, &width, &height, GL_CLAMP_TO_BORDER, GL_LINEAR_MIPMAP_LINEAR);",
         "clouds2TextureID = ImageLoader::LoadImage(clouds2_texture_path, &width, &height, GL_REPEAT, GL_LINEAR_MIPMAP_LINEAR);"),
    ],
    "src/UI/UIFontAtlas.cpp": [
        # WebGL2 wants a sized internal format for single-channel textures
        ("glTexImage2D(GL_TEXTURE_2D, 0, GL_RED, m_atlasWidth, m_atlasHeight, 0, GL_RED, GL_UNSIGNED_BYTE, nullptr);",
         "glTexImage2D(GL_TEXTURE_2D, 0, GL_R8, m_atlasWidth, m_atlasHeight, 0, GL_RED, GL_UNSIGNED_BYTE, nullptr);"),
        ("                glTexSubImage2D(GL_TEXTURE_2D, 0, ox, oy, g->bitmap.width, g->bitmap.rows, GL_RED, GL_UNSIGNED_BYTE, g->bitmap.buffer);",
         "                if (g->bitmap.width > 0 && g->bitmap.rows > 0 && g->bitmap.buffer != nullptr) {\n"
         "                    glTexSubImage2D(GL_TEXTURE_2D, 0, ox, oy, g->bitmap.width, g->bitmap.rows, GL_RED, GL_UNSIGNED_BYTE, g->bitmap.buffer);\n"
         "                }"),
    ],
    "src/Util/ImageLoader.cpp": [
        # mipmap filters are only valid for minification
        ("    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, sampleParam);\n",
         "    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, sampleParam == GL_NEAREST ? GL_NEAREST : GL_LINEAR);\n"),
    ],
    # ---------------------------------------------------------------- collision shapes only where they are used
    "src/Scene/Entity.cpp": [
        # Upstream builds the mesh of a movable object (cones, signs) in a temporary that is freed at the end of the
        # block while the convex shape keeps pointing at it: every later use reads freed memory. Keep it in the entity.
        ("""                auto const mesh = std::make_unique<btTriangleMesh>();
                for (size_t vertIdx = 0; vertIdx < m_vertices.size() - 2; vertIdx += 3) {""",
         """                btTriangleMesh *const mesh{&m_collisionMesh};
                for (size_t vertIdx = 0; vertIdx + 2 < m_vertices.size(); vertIdx += 3) {"""),
        ("""                m_collisionShape = std::make_unique<btConvexTriangleMeshShape>(mesh.get(), true);""",
         """                m_collisionShape = std::make_unique<btConvexTriangleMeshShape>(mesh, true);"""),
        # Upstream builds a triangle-mesh BVH for every entity, including scenery nothing can touch, and feeds
        # the physics library empty meshes when an entity has no triangles (which corrupts memory there).
        ('#include "Entity.h"\n', '#include "Entity.h"\n\n#include <BulletCollision/CollisionShapes/btEmptyShape.h>\n'),
        ("""                // TODO: Use passable flags (flags&0x80) of VROAD to work out whether collidable
                for (size_t vertIdx = 0; vertIdx < m_vertices.size() - 2; vertIdx += 3) {""",
         """                if (!trackEntity->collidable || m_vertices.size() < 3) {
                    if (m_vertices.size() < 3) {
                        static int emptyEntities{0};
                        if (++emptyEntities <= 3) {
                            LOG(WARNING) << "Track entity without triangles (type " << magic_enum::enum_name(trackEntity->type) << ")";
                        }
                    }
                    m_collisionShape = std::make_unique<btEmptyShape>();
                    break;
                }
                for (size_t vertIdx = 0; vertIdx + 2 < m_vertices.size(); vertIdx += 3) {"""),
    ],
    # ---------------------------------------------------------------- loading checkpoints (WebGL state)
    "src/Renderer/SkyRenderer.cpp#check": [],
    "src/Scene/Track.cpp": [
        ("""        this->_GenerateEntities();
        this->_LoadTextures();
        this->_GenerateSpline();
        this->_GenerateAabbTree();
""", """        Web::GlCheckpoint("track: start");
        this->_GenerateEntities();
        Web::GlCheckpoint("track: entities");
        this->_LoadTextures();
        Web::GlCheckpoint("track: textures");
        this->_GenerateSpline();
        this->_GenerateAabbTree();
        Web::GlCheckpoint("track: done");
"""),
        ('#include "Track.h"\n', '#include "Track.h"\n\n#include "../Web/WebPlatform.h"\n'),
        # The culling tree keeps references into its node array while it allocates more nodes; when the array has to grow
        # (more than 25,000 objects with the fixed upstream capacity) those references dangle and the heap is corrupted.
        # Size the tree for the track before filling it, so it never grows.
        ("""    void Track::_GenerateAabbTree() {
""", """    void Track::_GenerateAabbTree() {
        size_t entityCount{globalEntities.size()};
        for (auto const &trackBlockEntities : perTrackblockEntities) {
            entityCount += trackBlockEntities.size();
        }
        LOG(INFO) << "Track has " << entityCount << " entities in " << perTrackblockEntities.size() << " blocks";
        cullTree = AABBTree(static_cast<unsigned>(entityCount * 2 + 1024));
"""),
    ],
    # ---------------------------------------------------------------- opponents
    "src/Race/RacerManager.cpp": [
        # the upstream build hard-codes one retail car folder for every AI racer: use the cars that are installed
        ("""        std::shared_ptr<Car> racerVehicle{CarLoader::LoadCar(NFSVersion::NFS_3, "@CAR@")};
""".replace("@CAR@", _d("553s")), """        NFSVersion const carTag{get_enum(Config::get().carTag)};
        std::vector<std::string> carIds;
        {
            std::string const carDir{RESOURCE_PATH + std::string(magic_enum::enum_name(carTag)) + NFS_3_CAR_PATH};
            if (carTag == NFSVersion::NFS_3 && std::filesystem::exists(carDir)) {
                for (auto const &entry : std::filesystem::directory_iterator(carDir)) {
                    if (entry.is_directory() && std::filesystem::exists(entry.path() / "car.viv")) {
                        carIds.push_back(entry.path().filename().string());
                    }
                }
                std::ranges::sort(carIds);
            }
            if (carIds.empty()) {
                carIds.push_back(Config::get().car);
            }
        }
"""),
        ("""            auto racer{std::make_shared<RacerAgent>(m_racerData[racerDataIdx], racerVehicle, m_currentTrack)};
""", """            std::shared_ptr<Car> racerVehicle{CarLoader::LoadCar(carTag, carIds[racerIdx % carIds.size()])};
            auto racer{std::make_shared<RacerAgent>(m_racerData[racerDataIdx], racerVehicle, m_currentTrack)};
"""),
        ("#include <fstream>\n", "#include <algorithm>\n#include <filesystem>\n#include <fstream>\n"),
    ],
    # ---------------------------------------------------------------- agents
    "src/Race/Agents/CarAgent.h": [
        ("        uint32_t m_nearestTrackblockID = 0;\n", """        uint32_t m_nearestTrackblockID = 0;
        [[nodiscard]] uint32_t NearestVroad() const {
            return m_nearestVroadID;
        }
        // Half of the drivable width at a virtual road position (metres)
        [[nodiscard]] float RoadHalfWidth(uint32_t vroadIndex) const;
        // Virtual road index roughly 'distance' metres ahead of the car along the road
        [[nodiscard]] uint32_t VroadAhead(float distance) const;
        // Highest speed (m/s) from which the car can still slow down in time for every bend ahead
        [[nodiscard]] float PlanSpeed(float currentSpeed, float lateralGrip, float brakeDeceleration, float topSpeed) const;
        // Lateral offset (metres, + = right) at a virtual road position ahead that the car can reach in a straight
        // line without hitting scenery; 'preferred' is returned when it is clear or when nothing is
        [[nodiscard]] float ClearLane(uint32_t vroadIndex, float preferred) const;
        // World position of a lateral offset at a virtual road position
        [[nodiscard]] glm::vec3 LanePoint(uint32_t vroadIndex, float lateral) const;
        // Put the car back on the road at a virtual road position, beside any scenery that stands on the driving line
        void ResetOnRoad(uint32_t vroadIndex, float preferred) const;
"""),
    ],
    # ---------------------------------------------------------------- parser asserts: no stringified expressions
    # (the conditions name the per-game namespaces, which would put retail title abbreviations into the binary)
    "lib/LibOpenNFS/Common/Utils.h": [
        ('std::cerr << "Assertion `" #condition "` failed in " << __FILE__', 'std::cerr << "Assertion failed in " << __FILE__'),
        ('std::cerr << "Check `" #condition "` failed in " << __FILE__', 'std::cerr << "Check failed in " << __FILE__'),
    ],
    # ---------------------------------------------------------------- loader: normals that match the mirrored track
    "lib/LibOpenNFS/NFS3/NFS3Loader.cpp": [
        # quad normals are computed from raw (unmirrored) vertices while positions are mirrored in x
        ("                                normals.emplace_back(normal);\n"
         "                                vertexIndices.emplace_back(objectPolygons[polyIdx].vertex[quadToTriVertNumber]);",
         "                                normals.emplace_back(normal * TRACK_SCALE_FACTOR);\n"
         "                                vertexIndices.emplace_back(objectPolygons[polyIdx].vertex[quadToTriVertNumber]);"),
        ("                        normals.emplace_back(normal);\n"
         "                        vertexIndices.emplace_back(chunkPolygonData[polyIdx].vertex[quadToTriVertNumber]);",
         "                        normals.emplace_back(normal * TRACK_SCALE_FACTOR);\n"
         "                        vertexIndices.emplace_back(chunkPolygonData[polyIdx].vertex[quadToTriVertNumber]);"),
        # extra objects are mostly two-sided boards (trees, signs): light them like open ground
        ("                            normals.emplace_back(normal);\n"
         "                            vertexIndices.emplace_back(extraObjectData.polyData[k].vertex[quadToTriVertNumber]);",
         "                            normals.emplace_back(glm::vec3(0.f, 1.f, 0.f));\n"
         "                            vertexIndices.emplace_back(extraObjectData.polyData[k].vertex[quadToTriVertNumber]);"),
    ],
    # ---------------------------------------------------------------- car handling
    "src/Physics/Car.h": [
        ("        VehicleState vehicleState{};\n", """        VehicleState vehicleState{};
        float steerAxis{0.f}; // analogue steering request, -1 (left) .. 1 (right); 0 = use the digital flags
"""),
        ("        void _ApplyInputs();\n", "        void _ApplyInputs();\n        [[nodiscard]] float _SteeringLock() const;\n        float m_inputDt{1.f / 60.f};\n"
         "        btDynamicsWorld const *m_world{nullptr};\n"),
        ("        void ApplyAbsoluteSteerAngle(float targetAngle);\n", "        void ApplyAbsoluteSteerAngle(float targetAngle);\n"
         "        // True when static track geometry lies on the straight line between two points (used by the AI to pick a lane)\n"
         "        [[nodiscard]] bool PathBlocked(glm::vec3 const &from, glm::vec3 const &to) const;\n"),
    ],
    "src/Physics/Car.cpp": [
        ("        // Apply user input\n        this->_ApplyInputs();\n", "        // Apply user input\n        m_inputDt = dt;\n        m_world = dynamicsWorld;\n        this->_ApplyInputs();\n"),
        ("""    void Car::ApplyAbsoluteSteerAngle(float const targetAngle) {
""", """    bool Car::PathBlocked(glm::vec3 const &from, glm::vec3 const &to) const {
        if (m_world == nullptr) {
            return false;
        }
        btVector3 const start{Utils::glmToBullet(from)}, end{Utils::glmToBullet(to)};
        btCollisionWorld::ClosestRayResultCallback rayCallback(start, end);
        rayCallback.m_collisionFilterMask = COL_TRACK | COL_DYNAMIC_TRACK;
        m_world->rayTest(start, end, rayCallback);
        return rayCallback.hasHit();
    }

    void Car::ApplyAbsoluteSteerAngle(float const targetAngle) {
"""),
        ("""                // update front wheels steering value
                if (vehicleState.steerRight) {
                    vehicleState.gVehicleSteering -= assetData.physicsData.steeringIncrement;
                    if (vehicleState.gVehicleSteering < -assetData.physicsData.steeringClamp) {
                        vehicleState.gVehicleSteering = -assetData.physicsData.steeringClamp;
                    }
                } else if (vehicleState.steerLeft) {
                    vehicleState.gVehicleSteering += assetData.physicsData.steeringIncrement;
                    if (vehicleState.gVehicleSteering > assetData.physicsData.steeringClamp) {
                        vehicleState.gVehicleSteering = assetData.physicsData.steeringClamp;
                    }
                } else {
                    if (vehicleState.gVehicleSteering > 0) {
                        vehicleState.gVehicleSteering -= assetData.physicsData.steeringIncrement;
                    } else if (vehicleState.gVehicleSteering < 0) {
                        vehicleState.gVehicleSteering += assetData.physicsData.steeringIncrement;
                    }
                }
""", """                // Web port: frame-rate independent, speed sensitive steering with optional analogue input.
                // Full lock at parking speed, progressively less as speed rises.
                float const lock{this->_SteeringLock()};
                float request{vehicleState.steerRight ? 1.f : (vehicleState.steerLeft ? -1.f : 0.f)};
                if (std::fabs(steerAxis) > 0.01f) {
                    request = std::clamp(steerAxis, -1.f, 1.f);
                }
                float const target{-request * lock}; // negative steering value turns right
                float const rate{(request == 0.f ? 2.6f : 1.5f) * lock + 0.08f}; // radians per second
                float const step{rate * std::min(m_inputDt, 0.05f)};
                vehicleState.gVehicleSteering += std::clamp(target - vehicleState.gVehicleSteering, -step, step);
"""),
        # engine force tapers towards top speed instead of cutting out at the limiter
        ("""                if (m_vehicle->getCurrentSpeedKmHour() < assetData.physicsData.maxSpeed) {
                    vehicleState.gEngineForce = assetData.physicsData.maxEngineForce;
                    vehicleState.gBrakingForce = 0.f;
                } else {
                    vehicleState.gEngineForce = 0.f;
                }
""", """                {
                    float const ratio{std::clamp(m_vehicle->getCurrentSpeedKmHour() / assetData.physicsData.maxSpeed, 0.f, 1.2f)};
                    vehicleState.gEngineForce = assetData.physicsData.maxEngineForce * std::clamp(1.18f - ratio * ratio * 1.18f, 0.f, 1.f);
                    vehicleState.gBrakingForce = 0.f;
                }
"""),
        ('#include "Car.h"\n', '#include "Car.h"\n\n#include <algorithm>\n#include <cmath>\n'),
        # steering lock shrinks with speed so that full lock asks for about as much cornering as the tyres can give
        ("""    void Car::ApplySteeringRight(bool const apply) {
""", """    float Car::_SteeringLock() const {
        float const speed{std::fabs(m_vehicle->getCurrentSpeedKmHour()) / 3.6f};
        float const wheelBase{std::max(std::fabs(leftFrontWheelModel.initialPosition.z - leftRearWheelModel.initialPosition.z), 1.5f)};
        float const lateralLimit{assetData.physicsData.wheelFriction * 9.81f * 0.62f};
        return std::clamp(std::atan(lateralLimit * wheelBase / std::max(speed * speed, 1.f)), 0.012f, 0.45f);
    }

    void Car::ApplySteeringRight(bool const apply) {
"""),
        ("""            vehicleState.gVehicleSteering =
                std::max(-assetData.physicsData.steeringClamp, std::min(finalSteering, assetData.physicsData.steeringClamp));
""", """            float const lock{this->_SteeringLock()};
            vehicleState.gVehicleSteering = std::clamp(finalSteering, -lock, lock);
"""),
        # driving aids, run once per physics substep
        ("""        case PhysicsModel::BULLET:
            break;
        case PhysicsModel::NFS4_PC:
            m_nfs4VehiclePhysics->Update(dt);
            break;
""", """        case PhysicsModel::BULLET: {
            // Web port driving aids: aerodynamic downforce, a little lateral damping and a yaw assist that
            // pulls the car towards the turn rate its steering angle asks for, so slides stay catchable
            int grounded{0};
            for (int wheelIdx = 0; wheelIdx < m_vehicle->getNumWheels(); ++wheelIdx) {
                grounded += m_vehicle->getWheelInfo(wheelIdx).m_raycastInfo.m_isInContact ? 1 : 0;
            }
            if (grounded >= 2) {
                auto const &physics{assetData.physicsData};
                btMatrix3x3 const &basis{m_carChassis->getWorldTransform().getBasis()};
                btVector3 const right{basis.getColumn(0)}, up{basis.getColumn(1)}, forward{basis.getColumn(2)};
                btVector3 const velocity{m_carChassis->getLinearVelocity()};
                float const speed{static_cast<float>(velocity.length())};
                m_carChassis->applyCentralForce(-up * (physics.mass * 0.0022f * speed * speed));
                float const assist{vehicleState.handbrake ? 0.25f : 1.f};
                float const lateral{static_cast<float>(velocity.dot(right))};
                m_carChassis->applyCentralImpulse(-right * (lateral * physics.mass * std::min(1.1f * assist * dt, 0.5f)));
                float const wheelBase{std::max(std::fabs(leftFrontWheelModel.initialPosition.z - leftRearWheelModel.initialPosition.z), 1.5f)};
                float const wantedYaw{static_cast<float>(velocity.dot(forward)) * std::tan(vehicleState.gVehicleSteering) / wheelBase};
                btVector3 angular{m_carChassis->getAngularVelocity()};
                float const yaw{static_cast<float>(angular.dot(up))};
                angular += up * ((wantedYaw - yaw) * std::min(3.0f * assist * dt, 0.5f));
                m_carChassis->setAngularVelocity(angular);
            }
        } break;
        case PhysicsModel::NFS4_PC:
            m_nfs4VehiclePhysics->Update(dt);
            break;
"""),
        # arcade tuning: this car generation only carries mass, top speed and braking in its data file
        ("""        // Build the Bullet physics representation of the vehicle
        this->_GenPhysicsShapes();
""", """        // Build the Bullet physics representation of the vehicle
        this->_GenPhysicsShapes();
        {
            auto &physics{assetData.physicsData};
            float const brakeDeceleration{std::clamp(physics.maxBreakingForce / 3.6f, 7.f, 14.f)}; // m/s^2
            physics.maxBreakingForce = physics.mass * brakeDeceleration / 240.f;                  // impulse per wheel and 60 Hz step
            physics.maxEngineForce = physics.mass * (2.8f + physics.maxSpeed / 3.6f / 26.f) / 2.f; // per driven wheel
            physics.wheelFriction = 1.9f;
            // softer, longer suspension than the kart-stiff upstream defaults, so the wheels stay on the road
            physics.suspensionRestLength = 0.22f;
            physics.suspensionStiffness = 45.f;
            physics.suspensionDamping = 5.5f;     // relaxation
            physics.suspensionCompression = 3.5f;
            physics.rollInfluence = 0.08f;
        }
"""),
        ("""            // Apply engine force to rear wheels (RWD only)
            m_vehicle->applyEngineForce(vehicleState.gEngineForce, REAR_LEFT);
            m_vehicle->setBrake(vehicleState.gBrakingForce, REAR_LEFT);
            m_vehicle->applyEngineForce(vehicleState.gEngineForce, REAR_RIGHT);
            m_vehicle->setBrake(vehicleState.gBrakingForce, REAR_RIGHT);
""", """            // Rear wheel drive; brakes on all four wheels (front biased); engine braking when coasting;
            // the handbrake locks the rear axle and lets it slide
            {
                auto const &physics{assetData.physicsData};
                bool const coasting{vehicleState.gEngineForce == 0.f && vehicleState.gBrakingForce == 0.f};
                float const engineBrake{coasting ? physics.mass * 1.0f / 120.f : 0.f};
                float const rearBrake{vehicleState.handbrake ? physics.mass * 16.f / 120.f : vehicleState.gBrakingForce * 0.8f + engineBrake};
                float const engineForce{vehicleState.handbrake ? 0.f : vehicleState.gEngineForce};
                m_vehicle->applyEngineForce(engineForce, REAR_LEFT);
                m_vehicle->applyEngineForce(engineForce, REAR_RIGHT);
                // ease the front brakes while steering so braking into a corner does not use up all the grip
                float const steerUse{std::min(std::fabs(vehicleState.gVehicleSteering) / this->_SteeringLock(), 1.f)};
                float const frontBrake{vehicleState.gBrakingForce * (1.2f - 0.6f * steerUse)};
                m_vehicle->setBrake(frontBrake, FRONT_LEFT);
                m_vehicle->setBrake(frontBrake, FRONT_RIGHT);
                m_vehicle->setBrake(rearBrake, REAR_LEFT);
                m_vehicle->setBrake(rearBrake, REAR_RIGHT);
                float const rearGrip{physics.wheelFriction * (vehicleState.handbrake ? 0.42f : 1.f)};
                m_vehicle->getWheelInfo(REAR_LEFT).m_frictionSlip = rearGrip;
                m_vehicle->getWheelInfo(REAR_RIGHT).m_frictionSlip = rearGrip;
            }
"""),
    ],
    "src/Physics/PhysicsManager.cpp": [
        ("""            wheel.m_rollInfluence = car->assetData.physicsData.rollInfluence;
""", """            wheel.m_rollInfluence = car->assetData.physicsData.rollInfluence;
            // Raise the suspension mount so the wheel still sits where the model has it once the spring has settled
            // (static compression of a Bullet raycast wheel is g / (4 * stiffness))
            float const settled{static_cast<float>(sRestLength) - 9.81f / (4.f * car->assetData.physicsData.suspensionStiffness)};
            wheel.m_chassisConnectionPointCS += btVector3(0, settled, 0);
            wheel.m_maxSuspensionTravelCm = 30.f;
            wheel.m_maxSuspensionForce = car->assetData.physicsData.mass * 40.f;
"""),
    ],
    # ---------------------------------------------------------------- race session
    "src/Race/RaceSession.h": [
        ('#include "RacerManager.h"\n', '#include "RaceRules.h"\n#include "RacerManager.h"\n#include "../Web/WebPlatform.h"\n'),
        ("        UIManager m_uiManager;\n", """        UIManager m_uiManager;
        RaceRules m_rules{m_track, Web::Laps()};
        int m_cameraView{0};
        uint32_t m_publishTick{0};
"""),
    ],
    "src/Race/RaceSession.cpp": [
        ("""        m_userParams.drawNFS4PhysicsVectors = Config::get().hsPhysics;
""", """        m_userParams.drawNFS4PhysicsVectors = Config::get().hsPhysics;
        m_userParams.timeScaleFactor = 0.f; // fixed afternoon sun (the developer overlay can still spin the clock)
        m_rules.PlaceGrid(m_racerManager.racers);
"""),
        ("""    void RaceSession::Update(float const deltaTime) {
""", """    void RaceSession::Update(float const frameDeltaTime) {
        // The page pauses the race while its menu is open: keep rendering, stop the clock
        bool const paused{Web::Paused()};
        float const deltaTime{paused ? 0.f : (Web::FastForwardSteps() > 0 ? 1.f / 60.f : frameDeltaTime)};
"""),
        ("""        if (m_userParams.simulateCars) {
            m_racerManager.Simulate();
        }
""", """        // Automated tests fast-forward: extra fixed simulation steps per rendered frame
        for (int extra = paused ? 0 : Web::FastForwardSteps(); extra > 0; --extra) {
            m_racerManager.Simulate();
            m_rules.Update(1.f / 60.f, m_racerManager.racers);
            m_physicsManager.StepSimulation(1.f / 60.f, m_racerManager.GetRacerResidentTrackblocks());
        }
        if (m_userParams.simulateCars && !paused) {
            m_racerManager.Simulate();
        }
        // Race rules run after the agents so the countdown and the finish can override their inputs
        if (!paused) {
            m_rules.Update(deltaTime, m_racerManager.racers);
        }
        if (m_inputManager.cameraToggle) {
            m_cameraView = (m_cameraView + 1) % CarCamera::kNumViews;
            m_carCamera.SetView(m_cameraView);
        }
"""),
        ("""        // Draw the Game UI
        m_uiManager.Update(m_inputManager);
""", """        // Draw the Game UI
        m_uiManager.Update(m_inputManager);
        if ((m_publishTick++ % 2) == 0) {
            m_rules.Publish(m_racerManager.racers, m_cameraView);
        }
        // A new race chosen on the page reloads the session through the engine's own asset-change path
        if (Web::RaceRequest request; Web::ConsumeRaceRequest(request)) {
            if (!request.car.empty()) {
                m_loadedAssets.car = request.car;
            }
            if (!request.track.empty()) {
                m_loadedAssets.track = request.track;
            }
            m_loadedAssets.colour = request.colour;
            Config::get().nRacers = request.opponents;
            m_assetChanged = true;
        }
"""),
    ],
    # ---------------------------------------------------------------- font shipped with the clean assets (DejaVu Sans)
    "src/Renderer/Text3DRenderer.cpp": [
        ('"../resources/ui/fonts/Roboto-VariableFont_wdth,wght.ttf"', '"../resources/ui/fonts/ui-font.ttf"'),
    ],
    # ---------------------------------------------------------------- sun: afternoon angle instead of straight overhead
    "src/Race/OrbitalManager.cpp": [
        ("std::make_unique<GlobalLight>(glm::vec3(0, 0, 0), glm::vec3(0, SKYDOME_RADIUS, 0))",
         "std::make_unique<GlobalLight>(glm::vec3(0, 0, 0), glm::normalize(glm::vec3(0.45f, 0.72f, 0.52f)) * SKYDOME_RADIUS)"),
        ("std::make_unique<GlobalLight>(glm::vec3(0, 0, 0), glm::vec3(0, -SKYDOME_RADIUS, 0))",
         "std::make_unique<GlobalLight>(glm::vec3(0, 0, 0), glm::normalize(glm::vec3(-0.45f, -0.72f, -0.52f)) * SKYDOME_RADIUS)"),
    ],
    # ---------------------------------------------------------------- camera: real aspect ratio, saner near plane
    "src/Camera/BaseCamera.cpp": [
        ("""    void BaseCamera::UpdateFrustum() {
""", """    void BaseCamera::UpdateFrustum() {
        // The canvas can have any shape (the upstream projection is fixed at 4:3 with a 1 cm near plane)
        float const width{static_cast<float>(Config::get().windowSizeX)}, height{static_cast<float>(Config::get().windowSizeY)};
        float const aspect{(width > 0.f && height > 0.f) ? width / height : 16.f / 9.f};
        // Keep the horizontal field of view on narrow (portrait) screens
        float const fov{aspect >= 1.f ? m_fov : glm::degrees(2.f * std::atan(std::tan(glm::radians(m_fov) / 2.f) / aspect))};
        projectionMatrix = glm::perspective(glm::radians(std::min(fov, 110.f)), aspect, 0.3f, 4000.0f);
"""),
        ('#include "../Config.h"\n', '#include "../Config.h"\n\n#include <algorithm>\n#include <cmath>\n'),
    ],
    # ---------------------------------------------------------------- developer overlay only on request
    "src/Renderer/Renderer.cpp#debug": [],
}

PATCHES["src/Renderer/Renderer.cpp"] += [
    ("""        if (this->_DrawMenuBar(loadedAssets)) {
            newAssetSelected = true;
        }

        if (targetedEntity.has_value()) {
            _DrawMetadata(targetedEntity.value());
        }

        // Render the Debug UI
        this->_DrawDebugUI(userParams, deltaTime, activeCamera);

        if (userParams.showNFS4PhysicsDebug) {
            this->_DrawNFS4PhysicsDebug(racers);
        }
""", """        if (Web::DebugUi()) {
            if (this->_DrawMenuBar(loadedAssets)) {
                newAssetSelected = true;
            }
            if (targetedEntity.has_value()) {
                _DrawMetadata(targetedEntity.value());
            }
            // Render the Debug UI
            this->_DrawDebugUI(userParams, deltaTime, activeCamera);
            if (userParams.showNFS4PhysicsDebug) {
                this->_DrawNFS4PhysicsDebug(racers);
            }
        }
"""),
    ('#include "Renderer.h"\n', '#include "Renderer.h"\n\n#include "../Web/WebPlatform.h"\n'),
]
del PATCHES["src/Renderer/Renderer.cpp#debug"]

PATCHES["src/Renderer/SkyRenderer.cpp"] += [
    ("        clouds1TextureID = ImageLoader::LoadImage(", "        Web::GlCheckpoint(\"sky: start\");\n        clouds1TextureID = ImageLoader::LoadImage("),
    ('#include "SkyRenderer.h"\n', '#include "SkyRenderer.h"\n\n#include "../Web/WebPlatform.h"\n'),
]
del PATCHES["src/Renderer/SkyRenderer.cpp#check"]

# ---------------------------------------------------------------- loader indices read outside their arrays (upstream bugs)
# COL polygons index their vertices with bytes; as plain (signed) char any object with more than 127 vertices
# indexed in front of its vertex array.
PATCHES["lib/LibOpenNFS/NFS3/COL/ColFile.h"] = [("        char v[4]; // vertices", "        uint8_t v[4]; // vertices")]
_INDEX_GUARD = """            if (%(i)s >= %(v)s.size()) {
                // index from the file points outside the array: report once per mesh and use the first element
                if (!badIndices++) {
                    std::printf("BADINDEX %(what)s %%u of %%u\\n", static_cast<unsigned>(%(i)s), static_cast<unsigned>(%(v)s.size()));
                }
                %(dst)s.push_back(%(v)s.empty() ? %(zero)s : %(v)s[0]);
                continue;
            }
"""
PATCHES["lib/LibOpenNFS/Entities/Geometry.cpp"] = [
    ("""            for (auto const &vertex_index : m_vertexIndices) {
""", """            unsigned badIndices{0};
            for (auto const &vertex_index : m_vertexIndices) {
""" + _INDEX_GUARD % {"i": "vertex_index", "v": "vertices", "dst": "m_vertices", "zero": "glm::vec3(0.f)", "what": "vertex"}),
    ("#include <utility>\n", "#include <cstdio>\n#include <utility>\n"),
]
PATCHES["lib/LibOpenNFS/Entities/TrackGeometry.cpp"] = [
    ("""        for (uint32_t const m_vertex_index : vertexIndices) {
""", """        unsigned badIndices{0};
        for (uint32_t const m_vertex_index : vertexIndices) {
""" + _INDEX_GUARD % {"i": "m_vertex_index", "v": "shadingData", "dst": "m_shadingData", "zero": "glm::vec4(1.f)", "what": "shading"}),
    ("""        for (auto const &vertexIndex : vertexIndices) {
""", """        unsigned badIndices{0};
        for (auto const &vertexIndex : vertexIndices) {
""" + _INDEX_GUARD % {"i": "vertexIndex", "v": "shadingData", "dst": "m_shadingData", "zero": "glm::vec4(1.f)", "what": "shading"}),
    ('#include "TrackGeometry.h"\n', '#include "TrackGeometry.h"\n\n#include <cstdio>\n'),
]
# the line buffers were sized with the byte count used as an element count (57 MB each instead of 2.4 MB)
PATCHES["src/Renderer/BulletDebugDrawer.cpp"] = [
    ("INITIAL_LINE_BUF_SIZE * sizeof(BulletLine)", "MAX_NUM_LINES * sizeof(BulletLine)"),
    ("INITIAL_LINE_BUF_SIZE * sizeof(glm::vec3)", "2 * MAX_NUM_LINES * sizeof(glm::vec3)"),
]
PATCHES["lib/LibOpenNFS/NFS3/NFS3Loader.cpp"] += [
    # the car file can declare more colours than the text file names
    ("            Car::Colour originalPrimaryColour(fedataFile.primaryColourNames[colourIdx], ",
     "            Car::Colour originalPrimaryColour(colourIdx < fedataFile.primaryColourNames.size() ? fedataFile.primaryColourNames[colourIdx] : std::string(\"Colour\"), "),
]

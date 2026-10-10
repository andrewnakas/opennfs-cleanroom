// Web (emscripten) entry point. Same start-up sequence as the desktop main.cpp, but the frame loop is
// driven by the browser (requestAnimationFrame) and everything that must outlive main() lives on the heap.
#include <LibOpenNFS.h>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <string>

#include <emscripten.h>
#include <emscripten/html5.h>

#include "Config.h"
#include "GameState/GameStateManager.h"
#include "GameState/MainMenuState.h"
#include "GameState/RaceLoadState.h"
#include "GameState/RaceState.h"
#include "GameState/TrackSelectionState.h"
#include "GameState/VehicleSelectionState.h"
#include "Renderer/Renderer.h"
#include "Util/Logger.h"
#include "Web/WebPlatform.h"

using namespace std::filesystem;
using namespace OpenNFS;

namespace {
    struct WebApp {
        std::shared_ptr<Logger> logger;
        std::shared_ptr<GLFWwindow> window;
        std::vector<NfsAssetList> installedNFS;
        std::unique_ptr<GameContext> context;
        GameStateManager stateManager;
        double lastTime{0.0};
        uint32_t frames{0};
    };

    WebApp *gApp{nullptr};

    void Frame() {
        WebApp &app{*gApp};
        Web::SyncCanvasSize(app.window.get());

        double const currentTime{glfwGetTime()};
        // Clamp long gaps (tab in background, shader compilation hitch) so physics does not explode
        auto const deltaTime{std::min(static_cast<float>(currentTime - app.lastTime), 0.1f)};
        app.lastTime = currentTime;

        Renderer::NewFrame();
        try {
            app.stateManager.Update(deltaTime);
        } catch (std::exception const &e) {
            LOG(WARNING) << "Unhandled exception in frame: " << e.what();
            emscripten_cancel_main_loop();
            Web::ReportFatal(e.what());
            return;
        }
        Renderer::EndFrame();
        glfwPollEvents();

        if (++app.frames == 3) {
            Web::NotifyReady();
        }
    }
} // namespace

static int RunGame(int argc, char **argv);

int main(int const argc, char **argv) {
    try {
        return RunGame(argc, argv);
    } catch (std::exception const &e) {
        std::fprintf(stderr, "FATAL unhandled exception during start-up: %s\n", e.what());
        Web::ReportFatal(e.what());
        return EXIT_FAILURE;
    }
}

static int RunGame(int const argc, char **argv) {
    // The working directory mirrors the desktop layout: ../resources and ../shaders
    create_directories("/game/run");
    current_path("/game/run");

    auto const logger{std::make_shared<Logger>()};
    Config::get().InitFromCommandLine(argc, argv);

    auto makeLogCallback{[=](auto &logLevel) -> std::function<void(char const *, int, char const *, std::string)> {
        return [logLevel](char const *file, int const line, char const *func, std::string const &logMessage) {
            LogCapture(file, line, func, logLevel).stream() << logMessage;
        };
    }};
    LibOpenNFS::RegisterLogCallback(LibOpenNFS::LogLevel::INFO, makeLogCallback(INFO));
    LibOpenNFS::RegisterLogCallback(LibOpenNFS::LogLevel::WARNING, makeLogCallback(WARNING));
    LibOpenNFS::RegisterLogCallback(LibOpenNFS::LogLevel::DEBUG, makeLogCallback(DEBUG));

    create_directories(OpenNFS::CAR_PATH);
    create_directories(OpenNFS::TRACK_PATH);

    gApp = new WebApp();
    WebApp &app{*gApp};
    app.logger = logger;
    app.installedNFS = OpenNFS::Utils::PopulateAssets();

    LOG(INFO) << "Engine version " << ONFS_VERSION << " (web build)";
    app.window = Renderer::InitOpenGL("Open Road");

    app.context = std::make_unique<GameContext>(GameContext{
        .window = app.window,
        .logger = app.logger,
        .installedNFS = app.installedNFS,
        .loadedAssets = {get_enum(Config::get().carTag), Config::get().car, get_enum(Config::get().trackTag), Config::get().track}});
    GameContext &context{*app.context};
    context.loadedAssets.colour = Web::Colour();
    CHECK_F(context.loadedAssets.trackTag != NFSVersion::UNKNOWN, "Unknown track type!");

    app.stateManager.RegisterState(GameState::MainMenu, std::make_unique<MainMenuState>(context));
    app.stateManager.RegisterState(GameState::Race, std::make_unique<RaceState>(context));
    app.stateManager.RegisterState(GameState::RaceLoad, std::make_unique<RaceLoadState>(context));
    app.stateManager.RegisterState(GameState::TrackSelection, std::make_unique<TrackSelectionState>(context));
    app.stateManager.RegisterState(GameState::VehicleSelection, std::make_unique<VehicleSelectionState>(context));
    app.stateManager.TransitionTo(Config::get().ui ? GameState::MainMenu : GameState::Race);

    app.lastTime = glfwGetTime();
    emscripten_set_main_loop(Frame, 0, false);
    return EXIT_SUCCESS;
}

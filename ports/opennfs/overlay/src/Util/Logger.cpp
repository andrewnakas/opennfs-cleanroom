#include "Logger.h"

#include <cstring>

namespace g3 {
    LogSink gLogSink{nullptr};

    void Emit(LEVELS const &level, char const *file, int const line, char const *func, std::string const &message) {
        if (gLogSink != nullptr) {
            gLogSink(level, file, line, func, message);
            return;
        }
        std::printf("%s: %s\n", level.text, message.c_str());
    }
} // namespace g3

namespace OpenNFS {
    static AppLog *gOnScreenLog{nullptr};

    static void LogToConsoleAndScreen(LEVELS const &level, char const *file, int const line, char const *func, std::string const &message) {
        char const *shortFile{std::strrchr(file, '/')};
        shortFile = (shortFile != nullptr) ? shortFile + 1 : file;
        std::string text{std::string(level.text) + " [" + shortFile + "->" + func + ":" + std::to_string(line) + "]: " + message};
        if (text.empty() || text.back() != '\n') {
            text += '\n';
        }
        // stderr is unbuffered, so the browser console sees fatal messages before the abort
        std::fputs(text.c_str(), (level.value >= WARNING.value) ? stderr : stdout);
        if (level.value >= FATAL.value) {
            std::fflush(stdout);
        }
        if (gOnScreenLog != nullptr) {
            gOnScreenLog->AddLine(text.c_str());
        }
    }

    Logger::Logger() {
        gOnScreenLog = &onScreenLog;
        g3::gLogSink = &LogToConsoleAndScreen;
    }
} // namespace OpenNFS

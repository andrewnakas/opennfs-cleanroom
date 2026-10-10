// Single-threaded stand-in for g3log (the real one needs a worker thread, which a
// plain wasm build does not have). Provides the subset of the API the engine uses.
#pragma once

#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <sstream>
#include <string>

struct LEVELS {
    int value;
    char const *text;
};

static const LEVELS DEBUG{100, "DEBUG"};
static const LEVELS INFO{300, "INFO"};
static const LEVELS WARNING{500, "WARNING"};
static const LEVELS FATAL{1000, "FATAL"};

namespace g3 {
    using LogSink = void (*)(LEVELS const &level, char const *file, int line, char const *func, std::string const &message);
    // Defined in Util/Logger.cpp
    extern LogSink gLogSink;
    void Emit(LEVELS const &level, char const *file, int line, char const *func, std::string const &message);
} // namespace g3

class LogCapture {
  public:
    LogCapture(char const *file, int const line, char const *func, LEVELS const &level, char const *expression = "")
        : m_file(file), m_line(line), m_func(func), m_level(level), m_expression(expression) {
    }
    ~LogCapture() {
        std::string message{m_stream.str()};
        if (m_level.value >= FATAL.value && m_expression[0] != '\0') {
            message = std::string("CHECK(") + m_expression + ") failed: " + message;
        }
        g3::Emit(m_level, m_file, m_line, m_func, message);
        if (m_level.value >= FATAL.value) {
            std::abort();
        }
    }
    std::ostringstream &stream() {
        return m_stream;
    }
    void capturef(char const *fmt, ...) __attribute__((format(printf, 2, 3))) {
        char buffer[2048];
        va_list args;
        va_start(args, fmt);
        vsnprintf(buffer, sizeof(buffer), fmt, args);
        va_end(args);
        m_stream << buffer;
    }

  private:
    std::ostringstream m_stream;
    char const *m_file;
    int m_line;
    char const *m_func;
    LEVELS m_level;
    char const *m_expression;
};

#define LOG(level) LogCapture(__FILE__, __LINE__, __func__, level).stream()
#define LOGF(level, ...) LogCapture(__FILE__, __LINE__, __func__, level).capturef(__VA_ARGS__)
#define CHECK_F(condition, ...)                                                      \
    if (!(condition))                                                                \
    LogCapture(__FILE__, __LINE__, __func__, FATAL, #condition).capturef(__VA_ARGS__)

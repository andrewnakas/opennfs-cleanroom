// WebGL2 (GLES3) stand-in for GLEW. Shadows emscripten's desktop-GL emulation header.
#pragma once

#include <GLES3/gl3.h>

#define GLEW_OK 0
static int glewExperimental = 0;
static inline int glewInit(void) {
    (void)glewExperimental;
    return GLEW_OK;
}

// Not available in WebGL2: border clamping. Edge clamping is the closest behaviour.
#define GL_CLAMP_TO_BORDER GL_CLAMP_TO_EDGE

// Shader stages that do not exist in GLES3; the engine only names them in a file-extension switch.
#define GL_GEOMETRY_SHADER 0x8DD9
#define GL_TESS_CONTROL_SHADER 0x8E88
#define GL_TESS_EVALUATION_SHADER 0x8E87
#define GL_COMPUTE_SHADER 0x91B9

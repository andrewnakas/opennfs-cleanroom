// Web port track shader: directional sun + sky ambient + cascaded shadows + local lights + distance haze.
// (The upstream shader runs 20 point lights with specular and 16 spotlights on every fragment and gives
// the sun no colour; this one skips inactive lights and lights the scene from the sun.)

// Interpolated values from the vertex shaders
in vec2 UV;
flat in uint texIndex;
in vec4 nfsDataOut;
flat in uint debugDataOut;

// Diffuse and Specular
in vec3 surfaceNormal;

// CSM inputs
in vec3 fragPosWorldSpace;
in float clipSpaceZ;

// Ouput data
out vec4 color;

uniform bool useClassic;

uniform sampler2DArray textureArray;
uniform sampler2DArrayShadow shadowMapArray;
uniform float ambientFactor;
uniform vec3 cameraPosition;
uniform vec3 lightPosition[MAX_TRACK_CONTRIB_LIGHTS];
uniform vec4 lightColour[MAX_TRACK_CONTRIB_LIGHTS];
uniform vec3 attenuation[MAX_TRACK_CONTRIB_LIGHTS];
uniform vec3 spotlightPosition[MAX_SPOTLIGHTS];
uniform vec3 spotlightColour[MAX_SPOTLIGHTS];
uniform vec3 spotlightDirection[MAX_SPOTLIGHTS];
uniform float spotlightInnerCutOff[MAX_SPOTLIGHTS];
uniform float spotlightOuterCutOff[MAX_SPOTLIGHTS];
uniform float shineDamper;
uniform float reflectivity;

// CSM uniforms
uniform mat4 lightSpaceMatrices[CSM_NUM_CASCADES];
uniform float cascadePlaneDistances[CSM_NUM_CASCADES];

// Shadow amount (0 = lit, 1 = shadowed) from one cascade, 4-tap PCF with hardware comparison
float ShadowCascade(int cascadeIndex, vec3 worldPos) {
    vec4 lightSpacePos = lightSpaceMatrices[cascadeIndex] * vec4(worldPos, 1.0);
    vec3 projCoords = lightSpacePos.xyz / lightSpacePos.w * 0.5 + 0.5;
    if (projCoords.z > 1.0 || projCoords.x < 0.0 || projCoords.x > 1.0 || projCoords.y < 0.0 || projCoords.y > 1.0) {
        return 0.0;
    }
    float currentDepth = projCoords.z - 0.0008 * float(cascadeIndex + 1);
    vec2 texel = 0.75 / vec2(textureSize(shadowMapArray, 0).xy);
    float lit = 0.0;
    lit += texture(shadowMapArray, vec4(projCoords.xy + vec2(-texel.x, -texel.y), float(cascadeIndex), currentDepth));
    lit += texture(shadowMapArray, vec4(projCoords.xy + vec2(texel.x, -texel.y), float(cascadeIndex), currentDepth));
    lit += texture(shadowMapArray, vec4(projCoords.xy + vec2(-texel.x, texel.y), float(cascadeIndex), currentDepth));
    lit += texture(shadowMapArray, vec4(projCoords.xy + vec2(texel.x, texel.y), float(cascadeIndex), currentDepth));
    return 1.0 - lit * 0.25;
}

float Shadow(vec3 worldPos, float viewDepth) {
    int cascadeIndex = CSM_NUM_CASCADES - 1;
    for (int i = 0; i < CSM_NUM_CASCADES; ++i) {
        if (viewDepth < cascadePlaneDistances[i]) {
            cascadeIndex = i;
            break;
        }
    }
    if (viewDepth > cascadePlaneDistances[CSM_NUM_CASCADES - 1]) {
        return 0.0;
    }
    float shadow = ShadowCascade(cascadeIndex, worldPos);
    // fade the last cascade out instead of ending on a hard line
    float fade = clamp((cascadePlaneDistances[CSM_NUM_CASCADES - 1] - viewDepth) / 12.0, 0.0, 1.0);
    return shadow * fade;
}

void main(){
    vec4 texColour = texture(textureArray, vec3(UV, texIndex));
    vec4 surface = texColour * nfsDataOut;
    if (surface.a < 0.1 || texColour.a < 0.5) {
        discard;
    }
    if (useClassic) {
        color = vec4(surface.rgb, 1.0);
        return;
    }

    vec3 normal = normalize(surfaceNormal);
    // light 0 is always the sun, treated as directional
    vec3 sunDirection = normalize(lightPosition[0]);
    float day = clamp(sunDirection.y * 4.0 + 0.25, 0.0, 1.0);
    vec3 sunColour = mix(vec3(1.0, 0.55, 0.30), vec3(1.0, 0.96, 0.88), clamp(sunDirection.y * 2.5, 0.0, 1.0)) * day;
    vec3 skyAmbient = mix(vec3(0.06, 0.07, 0.12), vec3(0.52, 0.57, 0.66), day);

    float shadow = Shadow(fragPosWorldSpace, clipSpaceZ);
    float sunDiffuse = max(dot(normal, sunDirection), 0.0);
    vec3 lighting = skyAmbient * (0.78 + 0.22 * normal.y) + sunColour * sunDiffuse * (1.0 - shadow) * 0.80;

    // local point lights (track lamps, tail lights); inactive slots have no colour
    vec3 viewDirection = normalize(cameraPosition - fragPosWorldSpace);
    vec3 specular = vec3(0.0);
    for (int i = 1; i < MAX_TRACK_CONTRIB_LIGHTS; ++i) {
        if (lightColour[i].r + lightColour[i].g + lightColour[i].b < 0.001) {
            continue;
        }
        vec3 toLight = lightPosition[i] - fragPosWorldSpace;
        float dist = length(toLight);
        float falloff = attenuation[i].x + attenuation[i].y * dist + attenuation[i].z * dist * dist;
        vec3 lightDirection = toLight / max(dist, 0.001);
        lighting += max(dot(normal, lightDirection), 0.0) * lightColour[i].rgb / falloff * mix(1.0, 0.3, day);
        float highlight = pow(max(dot(reflect(-lightDirection, normal), viewDirection), 0.0), max(shineDamper, 1.0));
        specular += highlight * reflectivity * lightColour[i].rgb / falloff * 0.25;
    }

    // headlights
    float nightBoost = clamp(1.0 - day * 0.9, 0.1, 1.0);
    for (int i = 0; i < MAX_SPOTLIGHTS; ++i) {
        if (spotlightColour[i].r + spotlightColour[i].g + spotlightColour[i].b < 0.001) {
            continue;
        }
        vec3 toSpotlight = spotlightPosition[i] - fragPosWorldSpace;
        float dist = length(toSpotlight);
        float theta = dot(toSpotlight / max(dist, 0.001), normalize(-spotlightDirection[i]));
        float epsilon = spotlightInnerCutOff[i] - spotlightOuterCutOff[i];
        float intensity = clamp((theta - spotlightOuterCutOff[i]) / epsilon, 0.0, 1.0);
        lighting += intensity * nightBoost * spotlightColour[i] / (1.0 + 0.09 * dist + 0.032 * dist * dist);
    }

    vec3 rgb = surface.rgb * lighting + specular;

    // distance haze towards the horizon colour
    vec3 haze = mix(vec3(0.05, 0.06, 0.10), vec3(0.72, 0.80, 0.88), day);
    float fog = 1.0 - exp(-pow(clipSpaceZ / 950.0, 1.5));
    color = vec4(mix(rgb, haze, clamp(fog, 0.0, 0.85)), 1.0);
}

// Web port car shader: tinted paint lit by the sun, sky ambient, cascaded shadow, a fresnel-weighted
// environment reflection and a sun highlight. Same inputs and texture-alpha conventions as upstream.

// Interpolated values from the vertex shaders
in vec2 envUV;
in vec2 UV;

// Diffuse and Specular
in vec3 surfaceNormal;
in vec3 toLightVector[MAX_CAR_CONTRIB_LIGHTS];
in vec3 toCameraVector;

// CSM inputs
in vec3 fragPosWorldSpace;
in float clipSpaceZ;

flat in uint texIndex;
flat in uint polyFlag;

// Ouput data
out vec4 color;

// Values that stay constant for the whole mesh.
uniform sampler2DArray textureArray;
uniform sampler2D envMapTextureSampler;
uniform sampler2D carTextureSampler;
uniform sampler2DArrayShadow shadowMapArray;
uniform vec4 lightColour[MAX_CAR_CONTRIB_LIGHTS];
uniform vec3 attenuation[MAX_CAR_CONTRIB_LIGHTS];
uniform vec4 carColour;
uniform vec4 carSecondaryColour;
uniform float shineDamper;
uniform float reflectivity;
uniform float envReflectivity;
uniform bool multiTextured;
uniform bool polyFlagged;

// CSM uniforms
uniform mat4 lightSpaceMatrices[CSM_NUM_CASCADES];
uniform float cascadePlaneDistances[CSM_NUM_CASCADES];

float ShadowCascade(int cascadeIndex, vec3 worldPos) {
    vec4 lightSpacePos = lightSpaceMatrices[cascadeIndex] * vec4(worldPos, 1.0);
    vec3 projCoords = lightSpacePos.xyz / lightSpacePos.w * 0.5 + 0.5;
    if (projCoords.z > 1.0 || projCoords.x < 0.0 || projCoords.x > 1.0 || projCoords.y < 0.0 || projCoords.y > 1.0) {
        return 0.0;
    }
    float currentDepth = projCoords.z - 0.0012 * float(cascadeIndex + 1);
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
    return ShadowCascade(cascadeIndex, worldPos);
}

void main(){
    vec4 texel = multiTextured ? texture(textureArray, vec3(UV, texIndex)) : texture(carTextureSampler, UV);
    // texture alpha selects the role: < 0.35 cut out, 0.35-0.75 primary paint, 0.75-0.8 secondary paint, above: as drawn
    if (texel.a < 0.35) {
        discard;
    }
    bool paint = texel.a < 0.8;
    vec3 base = texel.rgb;
    if (texel.a > 0.75 && texel.a < 0.8) {
        base *= carSecondaryColour.rgb / max(carSecondaryColour.a, 0.001);
    } else if (texel.a <= 0.75) {
        base *= carColour.rgb / max(carColour.a, 0.001);
    }

    vec3 normal = normalize(surfaceNormal);
    vec3 view = normalize(toCameraVector);
    // light 0 is always the sun, treated as directional
    vec3 sunDirection = normalize(toLightVector[0] + fragPosWorldSpace);
    float day = clamp(sunDirection.y * 4.0 + 0.25, 0.0, 1.0);
    vec3 sunColour = mix(vec3(1.0, 0.55, 0.30), vec3(1.0, 0.96, 0.88), clamp(sunDirection.y * 2.5, 0.0, 1.0)) * day;
    vec3 skyAmbient = mix(vec3(0.06, 0.07, 0.12), vec3(0.50, 0.55, 0.64), day);

    float shadow = Shadow(fragPosWorldSpace, clipSpaceZ);
    float sunDiffuse = max(dot(normal, sunDirection), 0.0);
    vec3 lighting = skyAmbient * (0.70 + 0.30 * normal.y) + sunColour * sunDiffuse * (1.0 - shadow) * 0.85;

    // local lights (track lamps, other cars' tail lights)
    for (int i = 1; i < MAX_CAR_CONTRIB_LIGHTS; ++i) {
        if (lightColour[i].r + lightColour[i].g + lightColour[i].b < 0.001) {
            continue;
        }
        float dist = length(toLightVector[i]);
        float falloff = attenuation[i].x + attenuation[i].y * dist + attenuation[i].z * dist * dist;
        lighting += max(dot(normal, toLightVector[i] / max(dist, 0.001)), 0.0) * lightColour[i].rgb / falloff;
    }

    // reflection: stronger at grazing angles, strongest on glass and chrome
    float fresnel = pow(1.0 - max(dot(normal, view), 0.0), 3.0);
    vec3 environment = texture(envMapTextureSampler, envUV).rgb * mix(0.25, 1.0, day);
    float gloss = paint ? 0.10 + 0.55 * fresnel : (0.05 + 0.45 * fresnel) * (texel.r + texel.g + texel.b < 0.6 ? 1.0 : 0.3);
    float highlight = pow(max(dot(reflect(-sunDirection, normal), view), 0.0), 48.0) * (1.0 - shadow);

    vec3 rgb = base * lighting * (1.0 - gloss * 0.5) + environment * gloss * max(envReflectivity, 0.6) + sunColour * highlight * 0.55;
    color = vec4(rgb, 1.0);
}

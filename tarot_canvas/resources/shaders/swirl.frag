uniform vec2 resolution;
uniform vec2 centre;
uniform float scale;
uniform float t;
uniform float twirl;
uniform float spin;
uniform int blooms;
// Per bloom: centre x, centre y, turn in radians, radius
uniform vec4 bloom_at[8];
uniform int rounds;
uniform float warp;
uniform float contrast;
uniform vec3 colour_1;
uniform vec3 colour_2;
uniform vec3 colour_3;

vec2 turn_about(vec2 p, vec2 c, float angle, float size) {
    vec2 d = p - c;
    float a = angle * exp(-dot(d, d) / (size * size));
    float s = sin(a);
    float co = cos(a);
    return c + vec2(co * d.x - s * d.y, s * d.x + co * d.y);
}

float band(float v, float at) {
    return clamp(2.2 - abs(v - at) * 7.0, 0.0, 1.0);
}

void main() {
    vec2 frag = vec2(gl_FragCoord.x, resolution.y - gl_FragCoord.y);
    vec2 p = (frag - centre) / min(resolution.x, resolution.y) * 4.2 / scale;

    float r = length(p);
    float a = atan(p.y, p.x) + twirl * r + spin * t;
    p = r * vec2(cos(a), sin(a));

    for (int i = 0; i < 8; i++) {
        if (i >= blooms) break;
        vec4 b = bloom_at[i];
        p = turn_about(p, b.xy, b.z, b.w);
    }

    float amp = warp;
    float freq = 1.0;
    for (int i = 0; i < 8; i++) {
        if (i >= rounds) break;
        float k = float(i) + 1.0;
        p += amp * vec2(
            sin(p.y * freq + t * 0.613 + k * 1.71),
            cos(p.x * freq * 1.13 - t * 0.427 + k * 2.93)
        );
        p = vec2(0.96 * p.x - 0.28 * p.y, 0.28 * p.x + 0.96 * p.y);
        freq *= 1.83;
        amp *= 0.58;
    }

    float s = 0.5 + 0.5 * sin(p.x * 1.9 + p.y * 0.7 + 0.6 * sin(p.y * 1.3 - t * 0.21));
    float v = 0.5 + contrast * (s - 0.5);

    float w2 = band(v, 0.0);
    float w1 = band(v, 0.5);
    float w3 = band(v, 1.0);
    vec3 colour = (colour_1 * w1 + colour_2 * w2 + colour_3 * w3) / max(w1 + w2 + w3, 1e-4);
    OUT_COLOUR = vec4(colour, 1.0);
}

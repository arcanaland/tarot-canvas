attribute vec2 corner;
void main() {
    gl_Position = vec4(corner, 0.0, 1.0);
}

"""The 3D renderer: OpenGL 3.3 through moderngl, without a screen (EGL).

Why moderngl (benchmarked Nov 2026, see README "Why this renderer"):
* On a Colab GPU it renders on the NVIDIA card (hundreds of frames per second); without a GPU, Mesa's
  llvmpipe renders on the CPU (about 7 fps at 1080x1920 on 4 cores), so a free CPU runtime works too.
* Frames come straight back as numpy arrays and go into FFmpeg (no browser, no screenshots).
  Three.js in headless Chrome did ~2 fps here (frame capture alone took ~0.5 s); Blender would need a
  ~350 MB download every session and its Python module doesn't support Colab's Python version.

Look: flat-shaded low poly, sun + sky light, soft shadows (shadow map + PCF), fog into a dark teal
background, a glowing grid floor, bloom on glowing parts, cutaway (clip plane with a darker inside),
x-ray (see-through shells with bright edges), particles and floating labels drawn on top.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

# ---------------------------------------------------------------------------
# Math helpers (row-major numpy; transposed when sent to OpenGL)
# ---------------------------------------------------------------------------


def perspective(fov_y: float, aspect: float, near: float, far: float) -> np.ndarray:
    t = 1 / math.tan(math.radians(fov_y) / 2)
    return np.array([[t / aspect, 0, 0, 0], [0, t, 0, 0], [0, 0, (far + near) / (near - far), 2 * far * near / (near - far)],
                     [0, 0, -1, 0]], np.float32)


def ortho(half: float, near: float, far: float) -> np.ndarray:
    m = np.eye(4, dtype=np.float32)
    m[0, 0] = m[1, 1] = 1 / half
    m[2, 2] = -2 / (far - near)
    m[2, 3] = -(far + near) / (far - near)
    return m


def look_at(eye, target, up=(0, 1, 0)) -> np.ndarray:
    e, c, u = (np.asarray(x, np.float64) for x in (eye, target, up))
    f = c - e
    f /= max(np.linalg.norm(f), 1e-9)
    if abs(np.dot(f, u)) > 0.999:  # looking straight down: pick another up
        u = np.array([0.0, 0.0, -1.0])
    s = np.cross(f, u)
    s /= max(np.linalg.norm(s), 1e-9)
    uu = np.cross(s, f)
    m = np.eye(4)
    m[0, :3], m[1, :3], m[2, :3] = s, uu, -f
    m[:3, 3] = -m[:3, :3] @ e
    return m.astype(np.float32)


def trs(t=(0, 0, 0), r=(0, 0, 0), s=(1, 1, 1)) -> np.ndarray:
    from .mesh import rot_matrix  # noqa: PLC0415

    m = np.eye(4, dtype=np.float32)
    m[:3, :3] = rot_matrix(*r) * np.asarray(s, np.float32)
    m[:3, 3] = t
    return m


def hex_rgb(c) -> tuple[float, float, float]:
    if isinstance(c, (list, tuple)):
        return tuple(float(x) for x in c[:3])
    c = str(c).lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    try:
        return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return (0.8, 0.8, 0.8)


# ---------------------------------------------------------------------------
# What to draw in one frame
# ---------------------------------------------------------------------------


@dataclass
class Draw:
    key: str  # mesh key (uploaded once)
    model: np.ndarray  # 4x4
    color: tuple
    emissive: float = 0.0
    opacity: float = 1.0
    clip: tuple | None = None  # plane (nx, ny, nz, d): keep where dot(n, p) <= d
    inner: tuple = (0.12, 0.1, 0.1)  # colour of the inside when cut open
    xray: bool = False
    shadow: bool = True
    shine: float = 0.0  # 0 = matte, 1 = shiny metal / glass (specular highlight + sky reflection)
    additive: bool = False  # light beams (headlamps, light shafts): added on top, no depth write
    cap: int = 0  # cut open: 1 = a solid → a flat cut face in the inner colour; 2 = an open surface → a rim at the cut


@dataclass
class Label:
    texture_key: str
    image: object  # RGBA numpy (H, W, 4) uint8, only needed the first time
    x: float  # pixels, where the pointer touches (from left)
    y: float  # pixels (from top)
    scale: float = 1.0
    alpha: float = 1.0
    anchor: str = "bottom"  # bottom = the picture sits above (x, y); center


@dataclass
class Frame:
    eye: tuple
    target: tuple
    fov: float = 40.0
    draws: list = field(default_factory=list)
    particles: np.ndarray | None = None  # (N, 8): x y z size r g b emissive
    labels: list = field(default_factory=list)
    focus: tuple = (0.0, 0.0, 0.0)  # centre of the shadow map
    focus_radius: float = 20.0
    grid_center: tuple = (0.0, 0.0)
    bloom: float = 0.6
    fade: float = 0.0  # 0..1 fade to the background colour (transitions)
    flash: float = 0.0  # 0..1 white flash
    sun: tuple | None = None  # direction TO the sun (default: from the upper left)
    card: object = None  # optional full-frame RGBA overlay (end card)
    lights: list = field(default_factory=list)  # warm point lights [(pos, rgb, radius)], max 4
    style: dict | None = None  # this shot's look (colours, sky, grade): overrides the renderer's style
    dof: float = 0.0  # depth of field (0 = sharp everywhere, 1 = close-up/macro blur outside the subject)
    focus_dist: float = 0.0  # metres from the eye to what is sharp (0 = the target)
    time: float = 0.0  # seconds (film grain, drifting clouds)
    dyn: list = field(default_factory=list)  # [(world triangles (K*3, 3), rgb, emissive)]: cut faces made this frame


STYLE = {
    "background": "#cfd9e1", "horizon": "#f3f6f8", "floor": "#e4e9ed", "grid": "#000000",
    "sky": "#ffffff", "ground_light": "#b9c4cc", "sun": "#fff6ea", "sky_mode": 0, "grade": "bright",
}
# Colour grading per look (Part 6): exposure, saturation, contrast, lift (shadows tint), gain (highlights tint),
# vignette, film grain, SSAO strength, height fog
GRADES = {
    "bright": dict(exposure=1.12, sat=1.1, contrast=1.04, lift=(0.0, 0.0, 0.004), gain=(1.0, 0.995, 0.985),
                   vignette=0.16, grain=0.010, ao=0.55, hfog=0.0),
    "dark": dict(exposure=1.08, sat=1.05, contrast=1.1, lift=(0.0, 0.004, 0.008), gain=(1.03, 1.0, 0.96),
                 vignette=0.45, grain=0.022, ao=0.6, hfog=0.0),
    "documentary": dict(exposure=1.0, sat=0.86, contrast=1.14, lift=(0.006, 0.012, 0.022), gain=(1.06, 1.0, 0.9),
                        vignette=0.55, grain=0.03, ao=0.7, hfog=0.35),
    "underwater": dict(exposure=1.05, sat=1.0, contrast=1.05, lift=(0.0, 0.01, 0.02), gain=(0.86, 1.0, 1.06),
                       vignette=0.35, grain=0.015, ao=0.5, hfog=0.2),
    "space": dict(exposure=1.05, sat=1.05, contrast=1.1, lift=(0.0, 0.0, 0.01), gain=(1.0, 1.0, 1.02),
                  vignette=0.4, grain=0.015, ao=0.5, hfog=0.0),
}

VERT = """#version 330
uniform mat4 u_model; uniform mat4 u_vp; uniform mat4 u_light;
in vec3 in_pos; in vec3 in_nrm;
out vec3 v_world; out vec3 v_n; out vec4 v_light;
void main(){
  vec4 w = u_model * vec4(in_pos, 1.0);
  v_world = w.xyz; v_n = mat3(u_model) * in_nrm; v_light = u_light * w;
  gl_Position = u_vp * w;
}"""

LIT = """
uniform vec3 u_sun_dir; uniform vec3 u_sun_col; uniform vec3 u_sky; uniform vec3 u_ground;
uniform vec3 u_fog; uniform float u_fog_near; uniform float u_fog_far; uniform vec3 u_eye;
uniform vec3 u_bg_top; uniform vec3 u_bg_bottom; uniform vec2 u_res;
uniform int u_nl; uniform vec3 u_lpos[4]; uniform vec3 u_lcol[4]; uniform float u_lrad[4];
uniform sampler2DShadow u_shadow; uniform float u_texel; uniform int u_taps;
uniform int u_sky_mode; uniform vec3 u_cam_r; uniform vec3 u_cam_u; uniform vec3 u_cam_f; uniform vec2 u_tan;
uniform float u_hfog;
const vec2 POISSON[12] = vec2[](vec2(-0.326,-0.406), vec2(-0.840,-0.074), vec2(-0.696,0.457), vec2(-0.203,0.621),
  vec2(0.962,-0.195), vec2(0.473,-0.480), vec2(0.519,0.767), vec2(0.185,-0.893), vec2(0.507,0.064),
  vec2(0.896,0.412), vec2(-0.322,-0.933), vec2(-0.792,-0.598));
float shadow_at(vec4 lp, vec3 n){  // soft shadows: 12 Poisson taps, turned per pixel (no banding)
  vec3 p = lp.xyz / lp.w * 0.5 + 0.5;
  if (p.x < 0.0 || p.x > 1.0 || p.y < 0.0 || p.y > 1.0 || p.z > 1.0) return 1.0;
  float bias = 0.0012 + 0.003 * (1.0 - max(dot(n, u_sun_dir), 0.0));
  float a = fract(sin(dot(gl_FragCoord.xy, vec2(12.9898, 78.233))) * 43758.5453) * 6.2831;
  mat2 R = mat2(cos(a), sin(a), -sin(a), cos(a));
  float s = 0.0;
  int taps = clamp(u_taps, 4, 12);
  for (int k = 0; k < 12; k++) {
    if (k >= taps) break;
    s += texture(u_shadow, vec3(p.xy + R * POISSON[k] * u_texel * 2.2, p.z - bias));
  }
  return s / float(taps);
}
vec3 light(vec3 base, vec3 n, vec3 world, vec4 lp){
  float hemi = 0.5 + 0.5 * n.y;
  vec3 bounce = u_ground * (0.55 + 0.45 * base);  // light bounced off the floor tints the undersides
  vec3 amb = mix(bounce, u_sky, hemi) * 0.5;
  float d = max(dot(n, u_sun_dir), 0.0);
  float wrap = max(dot(n, u_sun_dir) * 0.8 + 0.2, 0.0);  // soft terminator (less harsh than Lambert)
  float sh = shadow_at(lp, n);
  float ao = mix(0.62, 1.0, smoothstep(0.0, 0.7, world.y));  // contact shadow: bases sit ON the floor
  vec3 col = base * (amb * ao + u_sun_col * mix(d, wrap, 0.35) * (0.15 + 0.85 * sh) * 1.05);
  for (int k = 0; k < 4; k++) {  // warm lamps and lit windows
    if (k >= u_nl) break;
    vec3 L = u_lpos[k] - world; float dl = length(L);
    float att = clamp(1.0 - dl / u_lrad[k], 0.0, 1.0);
    col += base * u_lcol[k] * att * att * (0.35 + 0.65 * max(dot(n, L / max(dl, 1e-3)), 0.0)) * 1.2;
  }
  return col;
}
vec3 view_dir(){  // the direction this pixel looks in (for the sky)
  vec2 uv = gl_FragCoord.xy / u_res * 2.0 - 1.0;
  return normalize(u_cam_f + uv.x * u_tan.x * u_cam_r + uv.y * u_tan.y * u_cam_u);
}
vec3 sky_at(vec3 d){  // a real sky: deep blue up high, pale at the horizon, a warm glow around the sun
  float h = clamp(d.y, -0.2, 1.0);
  vec3 c = mix(u_bg_bottom, u_bg_top, pow(smoothstep(-0.05, 0.75, h), 0.8));
  float sg = max(dot(d, u_sun_dir), 0.0);
  return c + u_sun_col * (pow(sg, 24.0) * 0.35 + pow(sg, 4.0) * 0.06);
}
vec3 bg_at(){  // the background colour behind this pixel (same formula as the background pass, no clouds)
  if (u_sky_mode == 1) return sky_at(view_dir());
  vec2 uv = gl_FragCoord.xy / u_res; vec2 c = uv - 0.5;
  return mix(u_bg_bottom, u_bg_top, smoothstep(0.0, 1.0, uv.y)) * (1.0 - 0.35 * dot(c, c));
}
vec3 fogged(vec3 col, vec3 world){  // far things melt into the background: no hard horizon line
  float dist = length(u_eye - world);
  float t = smoothstep(u_fog_near, u_fog_far, dist);
  float hf = u_hfog * exp(-max(world.y, 0.0) * 0.45) * (1.0 - exp(-dist * 0.035));  // low mist, thicker far away
  return mix(col, bg_at(), clamp(max(t, hf), 0.0, 1.0));
}
"""

FRAG = """#version 330
uniform vec3 u_color; uniform float u_emissive; uniform float u_opacity; uniform vec4 u_clip; uniform int u_clip_on;
uniform vec3 u_inner; uniform int u_xray; uniform float u_shine; uniform int u_additive;
uniform int u_cap; uniform float u_rim; uniform mat4 u_vp;
in vec3 v_world; in vec3 v_n; in vec4 v_light; out vec4 f_color;
""" + LIT + """
void main(){
  if (u_clip_on == 1 && dot(v_world, u_clip.xyz) > u_clip.w) discard;
  vec3 n = normalize(v_n);
  vec3 base = u_color;
  vec3 pw = v_world;
#ifdef CAP
  gl_FragDepth = gl_FragCoord.z;
  if (!gl_FrontFacing && u_clip_on == 1 && u_cap == 1) {  // a solid seen through the cut: its flat cut face
    vec3 rd = v_world - u_eye;
    float t = (u_clip.w - dot(u_clip.xyz, u_eye)) / dot(u_clip.xyz, rd);
    pw = u_eye + rd * clamp(t, 0.0, 1.0);
    vec4 cp = u_vp * vec4(pw, 1.0);
    gl_FragDepth = cp.z / cp.w * 0.5 + 0.5;
    n = normalize(u_clip.xyz); base = u_inner;
  } else if (!gl_FrontFacing && u_clip_on == 1 && u_cap == 2) {  // an open wall: its inside, a rim at the cut
    n = -n;
    base = (u_clip.w - dot(v_world, u_clip.xyz)) < u_rim ? u_inner : u_color * 0.62;
  } else
#endif
  if (!gl_FrontFacing) { n = -n; if (u_clip_on == 1) base = u_inner; }
  vec3 V = normalize(u_eye - pw);
  float rim = pow(1.0 - max(dot(n, V), 0.0), 3.0);
  vec3 col = light(base * (1.0 - 0.25 * u_shine), n, pw, v_light) + rim * 0.2 * u_sky + base * u_emissive * 1.6;
#ifdef CAP
  if (!gl_FrontFacing && u_clip_on == 1 && base == u_inner) col += u_inner * 0.28;  // cut faces read bright
#endif
  if (u_shine > 0.0) {  // metal, paint and glass: a sun highlight on each facet + the sky reflected in it
    vec3 H = normalize(u_sun_dir + V);
    float sh = shadow_at(v_light, n);
    float spec = pow(max(dot(n, H), 0.0), mix(10.0, 60.0, u_shine)) * (0.25 + 0.75 * sh);
    vec3 R = reflect(-V, n);
    col += u_sun_col * spec * u_shine * 0.9 + mix(u_ground, u_sky, 0.5 + 0.5 * R.y) * u_shine * 0.22 * (0.4 + 0.6 * rim);
  }
  float a = u_opacity;
  if (u_opacity < 0.6 && u_shine > 0.5) a = min(1.0, u_opacity + 0.45 * rim);  // glass: clearer face-on, bright edges
  if (u_xray == 1) { a = 0.06 + 0.22 * rim; col = mix(col, u_color * 1.2 + 0.1, 0.4); }  // a faint ghost
  if (u_additive == 1) { f_color = vec4(u_color * u_emissive * (0.25 + 0.75 * (1.0 - rim)) * u_opacity, 1.0); return; }
  f_color = vec4(fogged(col, pw), a);
}"""
FRAG_CAP = FRAG.replace("#version 330\n", "#version 330\n#define CAP 1\n", 1)

GRID_FRAG = """#version 330
uniform vec3 u_floor; uniform vec3 u_grid; uniform vec2 u_center; uniform float u_radius;
in vec3 v_world; in vec3 v_n; in vec4 v_light; out vec4 f_color;
""" + LIT + """
float line(float c, float w){ float d = abs(fract(c - 0.5) - 0.5) / fwidth(c); return 1.0 - min(d / w, 1.0); }
void main(){
  vec2 p = v_world.xz;
  float minor = max(line(p.x, 0.9), line(p.y, 0.9));
  float major = max(line(p.x / 5.0, 1.3), line(p.y / 5.0, 1.3));
  float fade = 1.0 - smoothstep(u_radius * 0.35, u_radius, length(p - u_center));
  float sh = shadow_at(v_light, vec3(0.0, 1.0, 0.0));
  float nz = fract(sin(dot(floor(p * 1.7), vec2(127.1, 311.7))) * 43758.5453);
  float nz2 = fract(sin(dot(floor(p * 0.35), vec2(269.5, 183.3))) * 43758.5453);
  vec3 col = u_floor * (0.97 + 0.03 * nz + 0.04 * nz2 - 0.02) * (0.58 + 0.42 * sh);
  col += u_grid * (minor * 0.06 + major * 0.24) * fade;  // faint: the places are the stars
  f_color = vec4(fogged(col, v_world), 1.0);
}"""

SHADOW_VERT = """#version 330
uniform mat4 u_model; uniform mat4 u_light; in vec3 in_pos;
void main(){ gl_Position = u_light * u_model * vec4(in_pos, 1.0); }"""
SHADOW_FRAG = """#version 330
void main(){}"""

PART_VERT = """#version 330
uniform mat4 u_vp; uniform mat4 u_light;
in vec3 in_pos; in vec3 in_nrm; in vec3 in_col; in float in_emi;
out vec3 v_world; out vec3 v_n; out vec4 v_light; out vec3 v_col; out float v_emi;
void main(){ v_world = in_pos; v_n = in_nrm; v_light = u_light * vec4(in_pos, 1.0); v_col = in_col; v_emi = in_emi;
  gl_Position = u_vp * vec4(in_pos, 1.0); }"""
PART_FRAG = """#version 330
in vec3 v_world; in vec3 v_n; in vec4 v_light; in vec3 v_col; in float v_emi; out vec4 f_color;
""" + LIT + """
void main(){ vec3 n = normalize(v_n); if (!gl_FrontFacing) n = -n;
  vec3 col = light(v_col, n, v_world, v_light) + v_col * v_emi * 1.8;
  f_color = vec4(fogged(col, v_world), 1.0); }"""

QUAD_VERT = """#version 330
in vec2 in_pos; out vec2 v_uv;
void main(){ v_uv = in_pos * 0.5 + 0.5; gl_Position = vec4(in_pos, 0.0, 1.0); }"""
BG_FRAG = """#version 330
uniform vec3 u_top; uniform vec3 u_bottom; uniform float u_time; in vec2 v_uv; out vec4 f_color;
uniform vec3 u_bg_top; uniform vec3 u_bg_bottom; uniform vec2 u_res; uniform int u_sky_mode;
uniform vec3 u_cam_r; uniform vec3 u_cam_u; uniform vec3 u_cam_f; uniform vec2 u_tan; uniform vec3 u_sun_dir;
uniform vec3 u_sun_col;
float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p){ vec2 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1, 0)), f.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), f.x), f.y); }
float fbm(vec2 p){ float v = 0.0, a = 0.5; for (int k = 0; k < 4; k++) { v += a * noise(p); p *= 2.03; a *= 0.5; }
  return v; }
void main(){
  if (u_sky_mode == 1) {
    vec2 uv = v_uv * 2.0 - 1.0;
    vec3 d = normalize(u_cam_f + uv.x * u_tan.x * u_cam_r + uv.y * u_tan.y * u_cam_u);
    float h = clamp(d.y, -0.2, 1.0);
    vec3 col = mix(u_bg_bottom, u_bg_top, pow(smoothstep(-0.05, 0.75, h), 0.8));
    float sg = max(dot(d, u_sun_dir), 0.0);
    col += u_sun_col * (pow(sg, 24.0) * 0.35 + pow(sg, 4.0) * 0.06);
    if (d.y > 0.01) {  // soft white clouds on a high plane, drifting slowly
      vec2 q = d.xz / (d.y + 0.08) * 0.9 + vec2(u_time * 0.012, u_time * 0.004);
      float c = smoothstep(0.52, 0.8, fbm(q * 1.3)) * smoothstep(0.01, 0.12, d.y);
      vec3 cloud = mix(vec3(0.82, 0.86, 0.92), vec3(1.0, 0.99, 0.97), smoothstep(0.5, 0.9, fbm(q * 1.3 + 0.3)));
      col = mix(col, cloud * 1.08, c * 0.9);
    }
    f_color = vec4(col, 1.0); return;
  }
  float t = smoothstep(0.0, 1.0, v_uv.y); vec2 c = v_uv - 0.5;
  vec3 col = mix(u_bottom, u_top, t) * (1.0 - 0.35 * dot(c, c)); f_color = vec4(col, 1.0); }"""
BRIGHT_FRAG = """#version 330
uniform sampler2D u_tex; in vec2 v_uv; out vec4 f_color;
void main(){ vec3 c = texture(u_tex, v_uv).rgb; float l = max(max(c.r, c.g), c.b);
  f_color = vec4(c * smoothstep(0.75, 1.4, l), 1.0); }"""
BLUR_FRAG = """#version 330
uniform sampler2D u_tex; uniform vec2 u_dir; in vec2 v_uv; out vec4 f_color;
void main(){ vec3 s = texture(u_tex, v_uv).rgb * 0.227;
  s += (texture(u_tex, v_uv + u_dir * 1.38).rgb + texture(u_tex, v_uv - u_dir * 1.38).rgb) * 0.316;
  s += (texture(u_tex, v_uv + u_dir * 3.23).rgb + texture(u_tex, v_uv - u_dir * 3.23).rgb) * 0.070;
  f_color = vec4(s, 1.0); }"""
SSAO_FRAG = """#version 330
uniform sampler2D u_depth; uniform vec2 u_px; uniform float u_near; uniform float u_far; uniform float u_proj;
uniform float u_radius; in vec2 v_uv; out vec4 f_color;
float lin(float d){ float z = d * 2.0 - 1.0; return 2.0 * u_near * u_far / (u_far + u_near - z * (u_far - u_near)); }
void main(){  // depth-only ambient occlusion: creases and contact shadows (works on low poly flat faces)
  float d = texture(u_depth, v_uv).r;
  if (d >= 0.99999) { f_color = vec4(1.0); return; }
  float z0 = lin(d); float w0 = 1.0 / z0;
  float wx1 = 1.0 / lin(texture(u_depth, v_uv + vec2(u_px.x, 0.0)).r) - w0;
  float wx2 = w0 - 1.0 / lin(texture(u_depth, v_uv - vec2(u_px.x, 0.0)).r);
  float wy1 = 1.0 / lin(texture(u_depth, v_uv + vec2(0.0, u_px.y)).r) - w0;
  float wy2 = w0 - 1.0 / lin(texture(u_depth, v_uv - vec2(0.0, u_px.y)).r);
  float gx = abs(wx1) < abs(wx2) ? wx1 : wx2; float gy = abs(wy1) < abs(wy2) ? wy1 : wy2;
  float rpx = clamp(u_radius * u_proj / z0, 3.0, 48.0);
  float a0 = fract(sin(dot(gl_FragCoord.xy, vec2(12.9898, 78.233))) * 43758.5453) * 6.2831;
  float occ = 0.0;
  for (int k = 0; k < 10; k++) {
    float r = rpx * (float(k) + 0.5) / 10.0; float a = a0 + float(k) * 2.39996;
    vec2 o = vec2(cos(a), sin(a)) * r;
    float ws = 1.0 / lin(texture(u_depth, v_uv + o * u_px).r);
    float we = w0 + gx * o.x + gy * o.y;  // where the surface would be if it were flat here
    float closer = (ws - we) / max(we, 1e-6);
    float dz = 1.0 / we - 1.0 / ws;  // metres in front of the expected surface
    occ += smoothstep(0.015, 0.06, closer) * (1.0 - smoothstep(u_radius * 0.6, u_radius * 1.6, dz));
  }
  f_color = vec4(vec3(1.0 - occ / 10.0), 1.0); }"""
FINAL_FRAG = """#version 330
uniform sampler2D u_scene; uniform sampler2D u_bloom; uniform sampler2D u_ao; uniform sampler2D u_blur;
uniform sampler2D u_depth; uniform float u_bloom_k; uniform vec3 u_fade_col;
uniform float u_fade; uniform float u_flash; uniform float u_exposure; uniform float u_sat; uniform float u_contrast;
uniform vec3 u_lift; uniform vec3 u_gain; uniform float u_vignette; uniform float u_grain; uniform float u_time;
uniform float u_ao_k; uniform float u_dof; uniform float u_focus; uniform float u_near; uniform float u_far;
in vec2 v_uv; out vec4 f_color;
float lin(float d){ float z = d * 2.0 - 1.0; return 2.0 * u_near * u_far / (u_far + u_near - z * (u_far - u_near)); }
vec3 aces(vec3 x){ return clamp((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0.0, 1.0); }
void main(){
  vec3 c = texture(u_scene, v_uv).rgb;
  if (u_dof > 0.0) {  // depth of field: sharp at the subject, soft before and behind it
    float z = lin(texture(u_depth, v_uv).r);
    float coc = clamp(abs(z - u_focus) / max(u_focus * 1.1, 0.05), 0.0, 1.0) * u_dof;
    c = mix(c, texture(u_blur, v_uv).rgb, smoothstep(0.08, 0.9, coc));
  }
  float ao = texture(u_ao, v_uv).r;
  c *= mix(1.0, ao, u_ao_k);
  c += texture(u_bloom, v_uv).rgb * u_bloom_k;
  c = aces(c * u_exposure);                                   // filmic: highlights roll off, never blown out
  float l = dot(c, vec3(0.2126, 0.7152, 0.0722));
  c = mix(vec3(l), c, u_sat);
  c = clamp((c - 0.5) * u_contrast + 0.5, 0.0, 1.0);
  c = c * u_gain + u_lift * (1.0 - c);                        // warm highlights, cool shadows (per look)
  vec2 d = v_uv - 0.5; c *= 1.0 - u_vignette * dot(d, d) * 1.6;
  float g = fract(sin(dot(v_uv * 1000.0 + u_time * 37.0, vec2(12.9898, 78.233))) * 43758.5453) - 0.5;
  c += g * u_grain;
  c = mix(c, u_fade_col, u_fade); c = mix(c, vec3(1.0), u_flash);
  f_color = vec4(clamp(c, 0.0, 1.0), 1.0); }"""
LABEL_VERT = """#version 330
uniform vec4 u_rect; in vec2 in_pos; out vec2 v_uv;
void main(){ v_uv = vec2(in_pos.x * 0.5 + 0.5, 0.5 - in_pos.y * 0.5);
  vec2 p = u_rect.xy + (in_pos * 0.5 + 0.5) * u_rect.zw; gl_Position = vec4(p, 0.0, 1.0); }"""
LABEL_FRAG = """#version 330
uniform sampler2D u_tex; uniform float u_alpha; in vec2 v_uv; out vec4 f_color;
void main(){ vec4 c = texture(u_tex, v_uv); f_color = vec4(c.rgb, c.a * u_alpha); }"""


class RendererError(RuntimeError):
    pass


PAD = {"1f": "1x4", "2f": "2x4", "3f": "3x4", "4f": "4x4"}


def attrs_of(prog, layout: list[tuple[str, str]]) -> tuple[str, list[str]]:
    """The vertex format for a program, keeping ONLY the attributes it really has.

    GPU drivers (NVIDIA on Colab) remove inputs a shader never uses, e.g. the grid floor never reads the normal,
    so asking for "in_nrm" raised KeyError on a T4. Missing attributes become padding bytes in the same buffer."""
    fmt, names = [], []
    for f, name in layout:
        if name in prog:
            fmt.append(f)
            names.append(name)
        else:
            fmt.append(PAD[f])
    return " ".join(fmt), names


def set_uniform(prog, name: str, value) -> None:
    """Set a uniform if the driver kept it (unused uniforms are removed too)."""
    if name in prog:
        prog[name].value = value


def write_uniform(prog, name: str, data: bytes) -> None:
    if name in prog:
        prog[name].write(data)


def create_context():
    """A headless OpenGL context: the NVIDIA GPU if there is one, else Mesa (CPU)."""
    import moderngl  # noqa: PLC0415

    errors = []
    for kw in ({"backend": "egl"}, {}):
        try:
            return moderngl.create_standalone_context(require=330, **kw)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{kw or 'default'}: {exc}")
    raise RendererError("OpenGL is not available (" + "; ".join(errors)[:300] + ")")


class Renderer:
    def __init__(self, size: tuple[int, int], msaa: int = 4, shadow_size: int = 2048, ctx=None, style: dict | None = None,
                 effects: bool = True, shadow_taps: int = 12):
        import moderngl  # noqa: PLC0415

        self.mgl = moderngl
        self.W, self.H = size
        self.ctx = ctx or create_context()
        self.info = self.ctx.info.get("GL_RENDERER", "?")
        self.style = {**STYLE, **(style or {})}
        ctx = self.ctx
        self.prog = ctx.program(vertex_shader=VERT, fragment_shader=FRAG)
        self.cap_prog = ctx.program(vertex_shader=VERT, fragment_shader=FRAG_CAP)  # cut faces (writes depth)
        self.grid_prog = ctx.program(vertex_shader=VERT, fragment_shader=GRID_FRAG)
        self.shadow_prog = ctx.program(vertex_shader=SHADOW_VERT, fragment_shader=SHADOW_FRAG)
        self.part_prog = ctx.program(vertex_shader=PART_VERT, fragment_shader=PART_FRAG)
        self.bg_prog = ctx.program(vertex_shader=QUAD_VERT, fragment_shader=BG_FRAG)
        self.bright_prog = ctx.program(vertex_shader=QUAD_VERT, fragment_shader=BRIGHT_FRAG)
        self.blur_prog = ctx.program(vertex_shader=QUAD_VERT, fragment_shader=BLUR_FRAG)
        self.final_prog = ctx.program(vertex_shader=QUAD_VERT, fragment_shader=FINAL_FRAG)
        self.ssao_prog = ctx.program(vertex_shader=QUAD_VERT, fragment_shader=SSAO_FRAG)
        self.effects = effects  # SSAO + depth of field (off = the fastest look, e.g. tiny test frames)
        self.shadow_taps = int(shadow_taps)  # soft shadow samples: 12 on a GPU, fewer on the CPU (speed)
        self.label_prog = ctx.program(vertex_shader=LABEL_VERT, fragment_shader=LABEL_FRAG)
        quad = ctx.buffer(np.array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1], np.float32).tobytes())
        self.quads = {name: self.vertex_array(p, quad, [("2f", "in_pos")])
                      for name, p in (("bg", self.bg_prog), ("bright", self.bright_prog), ("blur", self.blur_prog),
                                      ("final", self.final_prog), ("label", self.label_prog), ("ssao", self.ssao_prog))}
        self.meshes: dict = {}
        self.textures: dict = {}
        self.shadow_size = shadow_size
        self.shadow_tex = ctx.depth_texture((shadow_size, shadow_size))
        self.shadow_tex.compare_func = "<="
        self.shadow_tex.repeat_x = self.shadow_tex.repeat_y = False
        self.shadow_fbo = ctx.framebuffer(depth_attachment=self.shadow_tex)
        samples = msaa if msaa and msaa > 1 else 0
        self.ms_fbo = ctx.framebuffer(color_attachments=[ctx.renderbuffer((self.W, self.H), 4, samples=samples,
                                                                           dtype="f2")],
                                      depth_attachment=ctx.depth_renderbuffer((self.W, self.H), samples=samples))
        self.scene_tex = ctx.texture((self.W, self.H), 4, dtype="f2")
        self.scene_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self.depth_tex = ctx.depth_texture((self.W, self.H))  # resolved depth: SSAO + depth of field
        self.depth_tex.repeat_x = self.depth_tex.repeat_y = False
        self.scene_fbo = ctx.framebuffer(color_attachments=[self.scene_tex], depth_attachment=self.depth_tex)
        hw, hh = max(8, self.W // 2), max(8, self.H // 2)
        self.ao_a = ctx.texture((hw, hh), 4, dtype="f1")
        self.ao_b = ctx.texture((hw, hh), 4, dtype="f1")
        self.dof_a = ctx.texture((hw, hh), 4, dtype="f2")
        self.dof_b = ctx.texture((hw, hh), 4, dtype="f2")
        for t in (self.ao_a, self.ao_b, self.dof_a, self.dof_b):
            t.filter = (moderngl.LINEAR, moderngl.LINEAR)
            t.repeat_x = t.repeat_y = False
        self.ao_fa, self.ao_fb = ctx.framebuffer([self.ao_a]), ctx.framebuffer([self.ao_b])
        self.dof_fa, self.dof_fb = ctx.framebuffer([self.dof_a]), ctx.framebuffer([self.dof_b])
        self.ao_fa.clear(1, 1, 1, 1)
        bw, bh = max(8, self.W // 4), max(8, self.H // 4)
        self.bloom_a = ctx.texture((bw, bh), 4, dtype="f2")
        self.bloom_b = ctx.texture((bw, bh), 4, dtype="f2")
        for t in (self.bloom_a, self.bloom_b):
            t.filter = (moderngl.LINEAR, moderngl.LINEAR)
            t.repeat_x = t.repeat_y = False
        self.bloom_fa = ctx.framebuffer(color_attachments=[self.bloom_a])
        self.bloom_fb = ctx.framebuffer(color_attachments=[self.bloom_b])
        self.out_fbo = ctx.framebuffer(color_attachments=[ctx.renderbuffer((self.W, self.H), 3)])
        from .mesh import sphere  # noqa: PLC0415

        self.upload("__puff", sphere(1.0, 1))  # smoke puffs
        from .mesh import arrow2d, xf  # noqa: PLC0415

        self.upload("__arrow", xf(arrow2d(1.0, 0.32, 0.42, 0.12), (0, -0.06, 0), (90, 0, 0)))  # flow arrows (+x)
        floor = np.array([[-1, 0, -1], [1, 0, 1], [1, 0, -1], [-1, 0, -1], [-1, 0, 1], [1, 0, 1]], np.float32) * 400
        fn = np.tile([0, 1, 0], (6, 1)).astype(np.float32)
        self._floor = self._vao(self.grid_prog, floor, fn)
        self._part_vbo = None

    # ------------------------------------------------------------------ geometry
    def vertex_array(self, prog, vbo, layout: list[tuple[str, str]]):
        """A vertex array that binds only the attributes `prog` has (see attrs_of)."""
        fmt, names = attrs_of(prog, layout)
        if not names:
            raise RendererError("a shader has none of its inputs (" + ", ".join(n for _, n in layout) + ")")
        return self.ctx.vertex_array(prog, [(vbo, fmt, *names)])

    def _vao(self, prog, pos, nrm):
        data = np.hstack([pos, nrm]).astype(np.float32)
        vbo = self.ctx.buffer(data.tobytes())
        return self.vertex_array(prog, vbo, [("3f", "in_pos"), ("3f", "in_nrm")]), vbo

    def upload(self, key: str, geo) -> None:
        """Send a mesh to the GPU once."""
        if key in self.meshes or geo.tris == 0:
            return
        pos, nrm = geo.pos.astype(np.float32), geo.normals()
        vao, vbo = self._vao(self.prog, pos, nrm)
        cvao = self.vertex_array(self.cap_prog, vbo, [("3f", "in_pos"), ("3f", "in_nrm")])
        svbo = self.ctx.buffer(pos.tobytes())
        svao = self.vertex_array(self.shadow_prog, svbo, [("3f", "in_pos")])
        self.meshes[key] = (vao, svao, (vbo, svbo), cvao)

    def texture(self, key: str, rgba: np.ndarray):
        if key not in self.textures:
            if len(self.textures) > 400:  # keep memory small (count-up numbers make many)
                for k in list(self.textures)[:200]:
                    self.textures.pop(k).release()
            img = np.ascontiguousarray(rgba)
            t = self.ctx.texture((img.shape[1], img.shape[0]), 4, img.tobytes())
            t.filter = (self.mgl.LINEAR, self.mgl.LINEAR)
            self.textures[key] = t
        return self.textures[key]

    # ------------------------------------------------------------------ one frame
    @staticmethod
    def _sun(fr: Frame) -> np.ndarray:
        sun = np.array(fr.sun if fr.sun is not None else (-0.45, 0.8, 0.4), np.float64)
        return sun / np.linalg.norm(sun)

    def _common(self, prog, fr: Frame, vp, light_vp):
        st = getattr(self, "_st", None) or self.style
        sun = self._sun(fr)
        for name, val in (("u_vp", vp.T.tobytes()), ("u_light", light_vp.T.tobytes())):
            if name in prog:
                prog[name].write(val)
        vals = {"u_sun_dir": tuple(sun), "u_sun_col": hex_rgb(st["sun"]), "u_sky": hex_rgb(st["sky"]),
                "u_ground": hex_rgb(st["ground_light"]), "u_fog": hex_rgb(st["horizon"]), "u_eye": tuple(fr.eye),
                "u_texel": 1.0 / self.shadow_size, "u_bg_top": hex_rgb(st["background"]),
                "u_bg_bottom": hex_rgb(st["horizon"]), "u_res": (float(self.W), float(self.H)),
                "u_nl": len(fr.lights[:4]), "u_sky_mode": int(st.get("sky_mode", 0) or 0), "u_taps": self.shadow_taps,
                "u_hfog": float(GRADES.get(st.get("grade"), GRADES["bright"])["hfog"] * st.get("hfog_k", 1.0))}
        vals.update(self._basis(fr))
        dist = float(np.linalg.norm(np.asarray(fr.eye) - np.asarray(fr.target)))
        fog = float(st.get("fog", 1.0))  # < 1 = thicker air (under water, inside the body)
        vals["u_fog_near"] = max(20.0, dist * 1.6) * fog
        vals["u_fog_far"] = max(60.0, dist * 4.5) * fog
        for k, v in vals.items():
            if k in prog:
                prog[k].value = v
        lights = list(fr.lights[:4]) + [((0.0, -99.0, 0.0), (0.0, 0.0, 0.0), 1.0)] * (4 - len(fr.lights[:4]))
        for name, idx in (("u_lpos", 0), ("u_lcol", 1)):
            if name in prog:
                prog[name].value = [tuple(float(x) for x in li[idx]) for li in lights]
        if "u_lrad" in prog:
            prog["u_lrad"].value = [float(li[2]) for li in lights]
        if "u_shadow" in prog:
            prog["u_shadow"].value = 0

    def _basis(self, fr: Frame) -> dict:
        """Camera right/up/forward + tan(fov/2): the sky shader turns pixels into view directions."""
        f = np.asarray(fr.target, np.float64) - np.asarray(fr.eye, np.float64)
        f /= max(np.linalg.norm(f), 1e-9)
        up = np.array([0.0, 1.0, 0.0]) if abs(f[1]) < 0.999 else np.array([0.0, 0.0, -1.0])
        r = np.cross(f, up)
        r /= max(np.linalg.norm(r), 1e-9)
        u = np.cross(r, f)
        ty = math.tan(math.radians(fr.fov) / 2)
        return {"u_cam_r": tuple(r), "u_cam_u": tuple(u), "u_cam_f": tuple(f), "u_tan": (ty * self.W / self.H, ty)}

    def render(self, fr: Frame) -> np.ndarray:
        ctx, mgl = self.ctx, self.mgl
        st = {**self.style, **(fr.style or {})}
        self._st = st
        aspect = self.W / self.H
        dist = float(np.linalg.norm(np.asarray(fr.eye) - np.asarray(fr.target)))
        near = max(0.02, dist * 0.02)
        far = max(300.0, dist * 30)
        vp = perspective(fr.fov, aspect, near, far) @ look_at(fr.eye, fr.target)
        sun = self._sun(fr)
        rad = max(4.0, fr.focus_radius)
        center = np.asarray(fr.focus, np.float64)
        light_vp = ortho(rad, 0.1, rad * 6) @ look_at(center + sun * rad * 3, center)

        # 1) shadows
        self.shadow_fbo.use()
        ctx.viewport = (0, 0, self.shadow_size, self.shadow_size)
        self.shadow_fbo.clear(depth=1.0)
        ctx.enable(mgl.DEPTH_TEST)
        ctx.disable(mgl.CULL_FACE)
        write_uniform(self.shadow_prog, "u_light", light_vp.T.tobytes())
        for d in fr.draws:
            if d.shadow and d.opacity > 0.5 and not d.xray and d.key in self.meshes and d.clip is None:
                write_uniform(self.shadow_prog, "u_model", d.model.T.tobytes())
                self.meshes[d.key][1].render()

        # 2) the scene (HDR, multisampled)
        self.ms_fbo.use()
        ctx.viewport = (0, 0, self.W, self.H)
        self.ms_fbo.clear(0, 0, 0, 1, depth=1.0)
        ctx.disable(mgl.DEPTH_TEST)
        set_uniform(self.bg_prog, "u_top", hex_rgb(st["background"]))
        set_uniform(self.bg_prog, "u_bottom", hex_rgb(st["horizon"]))
        bp = self.bg_prog
        for k, v in {**self._basis(fr), "u_bg_top": hex_rgb(st["background"]), "u_bg_bottom": hex_rgb(st["horizon"]),
                     "u_res": (float(self.W), float(self.H)), "u_sky_mode": int(st.get("sky_mode", 0) or 0),
                     "u_sun_dir": tuple(sun), "u_sun_col": hex_rgb(st["sun"]), "u_time": float(fr.time)}.items():
            set_uniform(bp, k, v)
        self.quads["bg"].render()
        ctx.enable(mgl.DEPTH_TEST)
        self.shadow_tex.use(0)
        gp = self.grid_prog
        self._common(gp, fr, vp, light_vp)
        write_uniform(gp, "u_model", np.eye(4, dtype=np.float32).tobytes())
        set_uniform(gp, "u_floor", hex_rgb(st["floor"]))
        set_uniform(gp, "u_grid", hex_rgb(st["grid"]))
        set_uniform(gp, "u_center", tuple(float(x) for x in fr.grid_center))
        set_uniform(gp, "u_radius", max(25.0, dist * 3.0))
        self._floor[0].render()
        self._common(self.prog, fr, vp, light_vp)
        if any(d.cap for d in fr.draws):
            self._common(self.cap_prog, fr, vp, light_vp)
        beams = [d for d in fr.draws if d.additive]  # headlamp beams, light shafts: light added on top
        draws = [d for d in fr.draws if not d.additive]
        solid = [d for d in draws if d.opacity >= 0.99 and not d.xray]
        thick = [d for d in draws if 0.6 <= d.opacity < 0.99 and not d.xray]  # liquids, water: blended, but solid
        glass = [d for d in draws if d.opacity < 0.6 or d.xray]  # glass, gas, x-ray shells
        eye = np.asarray(fr.eye)
        far_first = lambda d: -float(np.linalg.norm(d.model[:3, 3] - eye))  # noqa: E731
        thick.sort(key=far_first)
        glass.sort(key=far_first)
        for group, blend, write in ((solid, False, True), (thick, True, True), (glass, True, False), (beams, "add", False)):
            if blend:
                ctx.enable(mgl.BLEND)
                ctx.blend_func = (mgl.ONE, mgl.ONE) if blend == "add" else (mgl.SRC_ALPHA, mgl.ONE_MINUS_SRC_ALPHA)
                self.ms_fbo.depth_mask = write  # thin see-through parts don't hide what's behind or inside them
            for d in group:
                if d.key not in self.meshes:
                    continue
                p = self.cap_prog if d.cap else self.prog
                write_uniform(p, "u_model", d.model.T.tobytes())
                set_uniform(p, "u_color", tuple(d.color))
                set_uniform(p, "u_emissive", float(d.emissive))
                set_uniform(p, "u_opacity", float(d.opacity))
                set_uniform(p, "u_xray", 1 if d.xray else 0)
                set_uniform(p, "u_shine", float(d.shine))
                set_uniform(p, "u_additive", 1 if d.additive else 0)
                set_uniform(p, "u_clip_on", 1 if d.clip is not None else 0)
                if d.clip is not None:
                    set_uniform(p, "u_clip", tuple(float(x) for x in d.clip))
                    set_uniform(p, "u_inner", tuple(d.inner))
                if d.cap:
                    set_uniform(p, "u_cap", int(d.cap))
                    set_uniform(p, "u_rim", float(max(0.002, dist * 0.004)))  # a thin rim, not a pink inside
                self.meshes[d.key][3 if d.cap else 0].render()
            if blend:
                ctx.disable(mgl.BLEND)
                self.ms_fbo.depth_mask = True
        if fr.dyn:
            self._dynamic(fr)
        if fr.particles is not None and len(fr.particles):
            self._particles(fr, vp, light_vp)

        # 3) bloom + final colour
        ctx.disable(mgl.DEPTH_TEST)
        ctx.copy_framebuffer(self.scene_fbo, self.ms_fbo)
        bw, bh = self.bloom_a.size
        if fr.bloom > 0:
            self.bloom_fa.use()
            ctx.viewport = (0, 0, bw, bh)
            self.scene_tex.use(0)
            set_uniform(self.bright_prog, "u_tex", 0)
            self.quads["bright"].render()
            for _ in range(2):
                for src, dst, direction in ((self.bloom_a, self.bloom_fb, (1 / bw, 0)), (self.bloom_b, self.bloom_fa, (0, 1 / bh))):
                    dst.use()
                    src.use(0)
                    set_uniform(self.blur_prog, "u_tex", 0)
                    set_uniform(self.blur_prog, "u_dir", direction)
                    self.quads["blur"].render()
        else:
            self.bloom_fa.clear(0, 0, 0, 1)
        grade = {**GRADES.get(st.get("grade"), GRADES["bright"]), **(st.get("grade_k") or {})}
        hw, hh = self.ao_a.size
        if self.effects and grade["ao"] > 0:  # ambient occlusion at half size, blurred once
            self.ao_fa.use()
            ctx.viewport = (0, 0, hw, hh)
            self.depth_tex.use(0)
            sp = self.ssao_prog
            set_uniform(sp, "u_depth", 0)
            set_uniform(sp, "u_px", (1.0 / self.W, 1.0 / self.H))
            set_uniform(sp, "u_near", float(near))
            set_uniform(sp, "u_far", float(far))
            set_uniform(sp, "u_proj", float(self.H / 2 / math.tan(math.radians(fr.fov) / 2)))
            set_uniform(sp, "u_radius", float(min(1.2, max(0.06, dist * 0.06))))
            self.quads["ssao"].render()
            for src, dst, direction in ((self.ao_a, self.ao_fb, (1 / hw, 0)), (self.ao_b, self.ao_fa, (0, 1 / hh))):
                dst.use()
                src.use(0)
                set_uniform(self.blur_prog, "u_tex", 0)
                set_uniform(self.blur_prog, "u_dir", direction)
                self.quads["blur"].render()
        dof = float(fr.dof) if self.effects else 0.0
        if dof > 0:  # a soft copy of the picture for what is out of focus
            self.dof_fa.use()
            ctx.viewport = (0, 0, hw, hh)
            self.scene_tex.use(0)
            set_uniform(self.blur_prog, "u_tex", 0)
            set_uniform(self.blur_prog, "u_dir", (0.0, 0.0))
            self.quads["blur"].render()
            for _ in range(2):
                for src, dst, direction in ((self.dof_a, self.dof_fb, (2.2 / hw, 0)), (self.dof_b, self.dof_fa, (0, 2.2 / hh))):
                    dst.use()
                    src.use(0)
                    set_uniform(self.blur_prog, "u_tex", 0)
                    set_uniform(self.blur_prog, "u_dir", direction)
                    self.quads["blur"].render()
        self.out_fbo.use()
        ctx.viewport = (0, 0, self.W, self.H)
        self.scene_tex.use(0)
        self.bloom_a.use(1)
        self.ao_a.use(2)
        self.dof_a.use(3)
        self.depth_tex.use(4)
        fp = self.final_prog
        for k, v in {"u_scene": 0, "u_bloom": 1, "u_ao": 2, "u_blur": 3, "u_depth": 4, "u_bloom_k": float(fr.bloom),
                     "u_fade_col": hex_rgb(st["background"]), "u_fade": float(min(1.0, max(0.0, fr.fade))),
                     "u_flash": float(min(1.0, max(0.0, fr.flash))), "u_exposure": float(grade["exposure"]),
                     "u_sat": float(grade["sat"]), "u_contrast": float(grade["contrast"]),
                     "u_lift": tuple(grade["lift"]), "u_gain": tuple(grade["gain"]), "u_vignette": float(grade["vignette"]),
                     "u_grain": float(grade["grain"]), "u_time": float(fr.time % 1000.0),
                     "u_ao_k": float(grade["ao"]) if self.effects else 0.0, "u_dof": dof,
                     "u_focus": float(fr.focus_dist or dist), "u_near": float(near), "u_far": float(far)}.items():
            set_uniform(fp, k, v)
        self.quads["final"].render()

        # 4) labels on top
        if fr.labels:
            ctx.enable(mgl.BLEND)
            ctx.blend_func = mgl.SRC_ALPHA, mgl.ONE_MINUS_SRC_ALPHA
            for lb in fr.labels:
                tex = self.texture(lb.texture_key, lb.image)
                w, h = tex.size[0] * lb.scale, tex.size[1] * lb.scale
                x0 = lb.x - w / 2
                y0 = lb.y - (h if lb.anchor == "bottom" else h / 2)
                rect = (x0 / self.W * 2 - 1, 1 - (y0 + h) / self.H * 2, w / self.W * 2, h / self.H * 2)
                tex.use(0)
                set_uniform(self.label_prog, "u_tex", 0)
                set_uniform(self.label_prog, "u_rect", rect)
                set_uniform(self.label_prog, "u_alpha", float(lb.alpha))
                self.quads["label"].render()
            ctx.disable(mgl.BLEND)
        data = self.out_fbo.read(components=3)
        img = np.frombuffer(data, np.uint8).reshape(self.H, self.W, 3)
        return img[::-1]

    def _dynamic(self, fr: Frame):
        """Meshes made for this frame only (the flat cut faces of a hero part)."""
        p = self.prog
        write_uniform(p, "u_model", np.eye(4, dtype=np.float32).tobytes())
        for k, v in (("u_opacity", 1.0), ("u_xray", 0), ("u_shine", 0.0), ("u_additive", 0), ("u_clip_on", 0)):
            set_uniform(p, k, v)
        for tris, rgb, emi in fr.dyn:
            pos = np.asarray(tris, np.float32).reshape(-1, 3)
            if len(pos) < 3:
                continue
            from .mesh import Geo  # noqa: PLC0415

            nrm = Geo(pos).normals()
            data = np.hstack([pos, nrm]).astype(np.float32).tobytes()
            vbo = self.ctx.buffer(data)
            vao = self.vertex_array(p, vbo, [("3f", "in_pos"), ("3f", "in_nrm")])
            set_uniform(p, "u_color", tuple(rgb))
            set_uniform(p, "u_emissive", float(emi))
            vao.render()
            vao.release()
            vbo.release()

    def _particles(self, fr: Frame, vp, light_vp):
        """Small glowing octahedra (gas, bubbles, sparks, electrons, flow dots)."""
        P = np.asarray(fr.particles, np.float32)
        oct_v = np.array([[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]], np.float32)
        faces = np.array([[0, 2, 4], [2, 1, 4], [1, 3, 4], [3, 0, 4], [2, 0, 5], [1, 2, 5], [3, 1, 5], [0, 3, 5]])
        tri = oct_v[faces.ravel()]  # (24, 3)
        n = np.cross(tri[1::3] - tri[0::3], tri[2::3] - tri[0::3])
        n = np.repeat(n / np.linalg.norm(n, axis=1, keepdims=True), 3, 0)
        k = len(P)
        pos = (tri[None] * P[:, 3:4, None] + P[:, None, :3]).reshape(-1, 3)
        nrm = np.tile(n, (k, 1))
        col = np.repeat(P[:, 4:7], 24, 0)
        emi = np.repeat(P[:, 7:8], 24, 0)
        data = np.hstack([pos, nrm, col, emi]).astype(np.float32).tobytes()
        if self._part_vbo is None or self._part_vbo.size < len(data):
            if self._part_vbo is not None:
                self._part_vbo.release()
            self._part_vbo = self.ctx.buffer(reserve=max(len(data), 1 << 20), dynamic=True)
        self._part_vbo.write(data)
        vao = self.vertex_array(self.part_prog, self._part_vbo, [("3f", "in_pos"), ("3f", "in_nrm"), ("3f", "in_col"),
                                                                ("1f", "in_emi")])
        self._common(self.part_prog, fr, vp, light_vp)
        vao.render(vertices=k * 24)
        vao.release()

    def project(self, fr: Frame, pts) -> np.ndarray:
        """World points → pixel coordinates (x from left, y from top, depth). Behind the camera: depth < 0."""
        aspect = self.W / self.H
        dist = float(np.linalg.norm(np.asarray(fr.eye) - np.asarray(fr.target)))
        vp = perspective(fr.fov, aspect, max(0.02, dist * 0.02), max(300.0, dist * 30)) @ look_at(fr.eye, fr.target)
        P = np.hstack([np.asarray(pts, np.float64).reshape(-1, 3), np.ones((len(np.asarray(pts).reshape(-1, 3)), 1))])
        c = P @ vp.T
        w = c[:, 3:4]
        ndc = c[:, :3] / np.where(np.abs(w) < 1e-9, 1e-9, w)
        x = (ndc[:, 0] * 0.5 + 0.5) * self.W
        y = (0.5 - ndc[:, 1] * 0.5) * self.H
        return np.stack([x, y, w[:, 0]], 1)

    def release(self) -> None:
        try:
            self.ctx.release()
        except Exception:  # noqa: BLE001
            pass


def project_points(eye, target, fov, size, pts) -> np.ndarray:
    """Same as Renderer.project, without a GL context (used for checks and labels)."""
    W, H = size
    dist = float(np.linalg.norm(np.asarray(eye) - np.asarray(target)))
    vp = perspective(fov, W / H, max(0.02, dist * 0.02), max(300.0, dist * 30)) @ look_at(eye, target)
    pts = np.asarray(pts, np.float64).reshape(-1, 3)
    c = np.hstack([pts, np.ones((len(pts), 1))]) @ vp.T
    w = c[:, 3:4]
    ndc = c[:, :3] / np.where(np.abs(w) < 1e-9, 1e-9, w)
    return np.stack([(ndc[:, 0] * 0.5 + 0.5) * W, (0.5 - ndc[:, 1] * 0.5) * H, w[:, 0]], 1)

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


STYLE = {
    "background": "#0b2a30", "horizon": "#13414a", "floor": "#0e3238", "grid": "#2ee6d6",
    "sky": "#a8e4ec", "ground_light": "#24474d", "sun": "#fff4e0",
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
uniform sampler2DShadow u_shadow; uniform float u_texel;
float shadow_at(vec4 lp, vec3 n){
  vec3 p = lp.xyz / lp.w * 0.5 + 0.5;
  if (p.x < 0.0 || p.x > 1.0 || p.y < 0.0 || p.y > 1.0 || p.z > 1.0) return 1.0;
  float bias = 0.0015 + 0.003 * (1.0 - max(dot(n, u_sun_dir), 0.0));
  float s = 0.0;
  for (int x = -1; x <= 1; x++) for (int y = -1; y <= 1; y++)
    s += texture(u_shadow, vec3(p.xy + vec2(x, y) * u_texel * 1.5, p.z - bias));
  return s / 9.0;
}
vec3 light(vec3 base, vec3 n, vec3 world, vec4 lp){
  float hemi = 0.5 + 0.5 * n.y;
  vec3 amb = mix(u_ground, u_sky, hemi) * 0.55;
  float d = max(dot(n, u_sun_dir), 0.0);
  float sh = shadow_at(lp, n);
  vec3 col = base * (amb + u_sun_col * d * (0.25 + 0.75 * sh) * 0.85);
  return col;
}
vec3 fogged(vec3 col, vec3 world){
  float t = smoothstep(u_fog_near, u_fog_far, length(u_eye - world));
  return mix(col, u_fog, t);
}
"""

FRAG = """#version 330
uniform vec3 u_color; uniform float u_emissive; uniform float u_opacity; uniform vec4 u_clip; uniform int u_clip_on;
uniform vec3 u_inner; uniform int u_xray;
in vec3 v_world; in vec3 v_n; in vec4 v_light; out vec4 f_color;
""" + LIT + """
void main(){
  if (u_clip_on == 1 && dot(v_world, u_clip.xyz) > u_clip.w) discard;
  vec3 n = normalize(v_n);
  vec3 base = u_color;
  if (!gl_FrontFacing) { n = -n; if (u_clip_on == 1) base = u_inner; }
  vec3 V = normalize(u_eye - v_world);
  float rim = pow(1.0 - max(dot(n, V), 0.0), 3.0);
  vec3 col = light(base, n, v_world, v_light) + rim * 0.12 * u_sky + base * u_emissive * 1.6;
  float a = u_opacity;
  if (u_xray == 1) { a = 0.12 + 0.55 * rim; col = mix(col, u_color * 1.4 + 0.2, 0.5); }
  f_color = vec4(fogged(col, v_world), a);
}"""

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
  vec3 col = u_floor * (0.55 + 0.45 * sh);
  col += u_grid * (minor * 0.11 + major * 0.42) * fade;
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
uniform vec3 u_top; uniform vec3 u_bottom; in vec2 v_uv; out vec4 f_color;
void main(){ float t = smoothstep(0.0, 1.0, v_uv.y); vec2 c = v_uv - 0.5;
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
FINAL_FRAG = """#version 330
uniform sampler2D u_scene; uniform sampler2D u_bloom; uniform float u_bloom_k; uniform vec3 u_fade_col;
uniform float u_fade; uniform float u_flash; in vec2 v_uv; out vec4 f_color;
void main(){ vec3 c = texture(u_scene, v_uv).rgb + texture(u_bloom, v_uv).rgb * u_bloom_k;
  c = c / (1.0 + 0.18 * max(c - 0.8, 0.0));
  vec2 d = v_uv - 0.5; c *= 1.0 - 0.28 * dot(d, d);
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
    def __init__(self, size: tuple[int, int], msaa: int = 4, shadow_size: int = 2048, ctx=None, style: dict | None = None):
        import moderngl  # noqa: PLC0415

        self.mgl = moderngl
        self.W, self.H = size
        self.ctx = ctx or create_context()
        self.info = self.ctx.info.get("GL_RENDERER", "?")
        self.style = {**STYLE, **(style or {})}
        ctx = self.ctx
        self.prog = ctx.program(vertex_shader=VERT, fragment_shader=FRAG)
        self.grid_prog = ctx.program(vertex_shader=VERT, fragment_shader=GRID_FRAG)
        self.shadow_prog = ctx.program(vertex_shader=SHADOW_VERT, fragment_shader=SHADOW_FRAG)
        self.part_prog = ctx.program(vertex_shader=PART_VERT, fragment_shader=PART_FRAG)
        self.bg_prog = ctx.program(vertex_shader=QUAD_VERT, fragment_shader=BG_FRAG)
        self.bright_prog = ctx.program(vertex_shader=QUAD_VERT, fragment_shader=BRIGHT_FRAG)
        self.blur_prog = ctx.program(vertex_shader=QUAD_VERT, fragment_shader=BLUR_FRAG)
        self.final_prog = ctx.program(vertex_shader=QUAD_VERT, fragment_shader=FINAL_FRAG)
        self.label_prog = ctx.program(vertex_shader=LABEL_VERT, fragment_shader=LABEL_FRAG)
        quad = ctx.buffer(np.array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1], np.float32).tobytes())
        self.quads = {name: ctx.vertex_array(p, [(quad, "2f", "in_pos")])
                      for name, p in (("bg", self.bg_prog), ("bright", self.bright_prog), ("blur", self.blur_prog),
                                      ("final", self.final_prog), ("label", self.label_prog))}
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
        self.scene_fbo = ctx.framebuffer(color_attachments=[self.scene_tex])
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
        floor = np.array([[-1, 0, -1], [1, 0, 1], [1, 0, -1], [-1, 0, -1], [-1, 0, 1], [1, 0, 1]], np.float32) * 400
        fn = np.tile([0, 1, 0], (6, 1)).astype(np.float32)
        self._floor = self._vao(self.grid_prog, floor, fn)
        self._part_vbo = None

    # ------------------------------------------------------------------ geometry
    def _vao(self, prog, pos, nrm):
        data = np.hstack([pos, nrm]).astype(np.float32)
        vbo = self.ctx.buffer(data.tobytes())
        return self.ctx.vertex_array(prog, [(vbo, "3f 3f", "in_pos", "in_nrm")]), vbo

    def upload(self, key: str, geo) -> None:
        """Send a mesh to the GPU once."""
        if key in self.meshes or geo.tris == 0:
            return
        pos, nrm = geo.pos.astype(np.float32), geo.normals()
        vao, vbo = self._vao(self.prog, pos, nrm)
        svbo = self.ctx.buffer(pos.tobytes())
        svao = self.ctx.vertex_array(self.shadow_prog, [(svbo, "3f", "in_pos")])
        self.meshes[key] = (vao, svao, (vbo, svbo))

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
        st = self.style
        sun = self._sun(fr)
        for name, val in (("u_vp", vp.T.tobytes()), ("u_light", light_vp.T.tobytes())):
            if name in prog:
                prog[name].write(val)
        vals = {"u_sun_dir": tuple(sun), "u_sun_col": hex_rgb(st["sun"]), "u_sky": hex_rgb(st["sky"]),
                "u_ground": hex_rgb(st["ground_light"]), "u_fog": hex_rgb(st["horizon"]), "u_eye": tuple(fr.eye),
                "u_texel": 1.0 / self.shadow_size}
        dist = float(np.linalg.norm(np.asarray(fr.eye) - np.asarray(fr.target)))
        vals["u_fog_near"] = max(20.0, dist * 1.6)
        vals["u_fog_far"] = max(60.0, dist * 4.5)
        for k, v in vals.items():
            if k in prog:
                prog[k].value = v
        if "u_shadow" in prog:
            prog["u_shadow"].value = 0

    def render(self, fr: Frame) -> np.ndarray:
        ctx, mgl = self.ctx, self.mgl
        st = self.style
        aspect = self.W / self.H
        dist = float(np.linalg.norm(np.asarray(fr.eye) - np.asarray(fr.target)))
        near = max(0.02, dist * 0.02)
        vp = perspective(fr.fov, aspect, near, max(300.0, dist * 30)) @ look_at(fr.eye, fr.target)
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
        self.shadow_prog["u_light"].write(light_vp.T.tobytes())
        for d in fr.draws:
            if d.shadow and d.opacity > 0.5 and not d.xray and d.key in self.meshes and d.clip is None:
                self.shadow_prog["u_model"].write(d.model.T.tobytes())
                self.meshes[d.key][1].render()

        # 2) the scene (HDR, multisampled)
        self.ms_fbo.use()
        ctx.viewport = (0, 0, self.W, self.H)
        self.ms_fbo.clear(0, 0, 0, 1, depth=1.0)
        ctx.disable(mgl.DEPTH_TEST)
        self.bg_prog["u_top"].value = hex_rgb(st["background"])
        self.bg_prog["u_bottom"].value = hex_rgb(st["horizon"])
        self.quads["bg"].render()
        ctx.enable(mgl.DEPTH_TEST)
        self.shadow_tex.use(0)
        gp = self.grid_prog
        self._common(gp, fr, vp, light_vp)
        gp["u_model"].write(np.eye(4, dtype=np.float32).tobytes())
        gp["u_floor"].value = hex_rgb(st["floor"])
        gp["u_grid"].value = hex_rgb(st["grid"])
        gp["u_center"].value = tuple(float(x) for x in fr.grid_center)
        gp["u_radius"].value = max(25.0, dist * 3.0)
        self._floor[0].render()
        p = self.prog
        self._common(p, fr, vp, light_vp)
        solid = [d for d in fr.draws if d.opacity >= 0.99 and not d.xray]
        thick = [d for d in fr.draws if 0.6 <= d.opacity < 0.99 and not d.xray]  # liquids, water: blended, but solid
        glass = [d for d in fr.draws if d.opacity < 0.6 or d.xray]  # glass, gas, x-ray shells
        eye = np.asarray(fr.eye)
        far_first = lambda d: -float(np.linalg.norm(d.model[:3, 3] - eye))  # noqa: E731
        thick.sort(key=far_first)
        glass.sort(key=far_first)
        for group, blend, write in ((solid, False, True), (thick, True, True), (glass, True, False)):
            if blend:
                ctx.enable(mgl.BLEND)
                ctx.blend_func = mgl.SRC_ALPHA, mgl.ONE_MINUS_SRC_ALPHA
                self.ms_fbo.depth_mask = write  # thin see-through parts don't hide what's behind or inside them
            for d in group:
                if d.key not in self.meshes:
                    continue
                p["u_model"].write(d.model.T.tobytes())
                p["u_color"].value = tuple(d.color)
                p["u_emissive"].value = float(d.emissive)
                p["u_opacity"].value = float(d.opacity)
                p["u_xray"].value = 1 if d.xray else 0
                p["u_clip_on"].value = 1 if d.clip is not None else 0
                if d.clip is not None:
                    p["u_clip"].value = tuple(float(x) for x in d.clip)
                    p["u_inner"].value = tuple(d.inner)
                self.meshes[d.key][0].render()
            if blend:
                ctx.disable(mgl.BLEND)
                self.ms_fbo.depth_mask = True
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
            self.bright_prog["u_tex"].value = 0
            self.quads["bright"].render()
            for _ in range(2):
                for src, dst, direction in ((self.bloom_a, self.bloom_fb, (1 / bw, 0)), (self.bloom_b, self.bloom_fa, (0, 1 / bh))):
                    dst.use()
                    src.use(0)
                    self.blur_prog["u_tex"].value = 0
                    self.blur_prog["u_dir"].value = direction
                    self.quads["blur"].render()
        else:
            self.bloom_fa.clear(0, 0, 0, 1)
        self.out_fbo.use()
        ctx.viewport = (0, 0, self.W, self.H)
        self.scene_tex.use(0)
        self.bloom_a.use(1)
        fp = self.final_prog
        fp["u_scene"].value, fp["u_bloom"].value = 0, 1
        fp["u_bloom_k"].value = float(fr.bloom)
        fp["u_fade_col"].value = hex_rgb(st["background"])
        fp["u_fade"].value = float(min(1.0, max(0.0, fr.fade)))
        fp["u_flash"].value = float(min(1.0, max(0.0, fr.flash)))
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
                self.label_prog["u_tex"].value = 0
                self.label_prog["u_rect"].value = rect
                self.label_prog["u_alpha"].value = float(lb.alpha)
                self.quads["label"].render()
            ctx.disable(mgl.BLEND)
        data = self.out_fbo.read(components=3)
        img = np.frombuffer(data, np.uint8).reshape(self.H, self.W, 3)
        return img[::-1]

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
        vao = self.ctx.vertex_array(self.part_prog, [(self._part_vbo, "3f 3f 3f 1f", "in_pos", "in_nrm", "in_col", "in_emi")])
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

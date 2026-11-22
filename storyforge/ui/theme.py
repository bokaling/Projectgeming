"""Dark neon theme: deep black-violet background, pink→purple gradients, glass cards, big rounded buttons."""

from __future__ import annotations

PINK = "#ff2e97"
PURPLE = "#8b5cf6"
VIOLET = "#b15cff"
BG = "#07050d"
TEXT = "#f4f1ff"
MUTED = "#a7a1c4"
GRADIENT = f"linear-gradient(100deg, {PINK} 0%, {VIOLET} 55%, {PURPLE} 100%)"


def build_theme():
    import gradio as gr  # noqa: PLC0415

    pink = gr.themes.Color(c50="#fff0f7", c100="#ffd6ea", c200="#ffadd5", c300="#ff7ab9", c400="#ff4fa3",
                           c500=PINK, c600="#e0177d", c700="#b80f65", c800="#8f0b4f", c900="#66073a", c950="#3d0423")
    base = gr.themes.Base(
        primary_hue=pink,
        secondary_hue=gr.themes.colors.violet,
        neutral_hue=gr.themes.colors.slate,
        radius_size=gr.themes.sizes.radius_lg,
        font=[gr.themes.GoogleFont("Inter"), "ui-sans-serif", "system-ui", "sans-serif"],
        font_mono=[gr.themes.GoogleFont("JetBrains Mono"), "ui-monospace", "monospace"],
    )
    v = {
        "body_background_fill": BG,
        "body_text_color": TEXT,
        "body_text_color_subdued": MUTED,
        "background_fill_primary": "#0d0a18",
        "background_fill_secondary": "#120e22",
        "border_color_primary": "rgba(255,255,255,0.09)",
        "block_background_fill": "rgba(255,255,255,0.035)",
        "block_border_color": "rgba(255,255,255,0.08)",
        "block_border_width": "1px",
        "block_label_background_fill": "rgba(255,255,255,0.06)",
        "block_label_text_color": MUTED,
        "block_title_text_color": TEXT,
        "block_radius": "20px",
        "block_shadow": "0 10px 40px rgba(0,0,0,0.35)",
        "panel_background_fill": "rgba(255,255,255,0.02)",
        "input_background_fill": "rgba(10,7,22,0.85)",
        "input_border_color": "rgba(255,255,255,0.12)",
        "input_border_color_focus": PINK,
        "input_radius": "14px",
        "input_placeholder_color": "#6f6a8a",
        "button_primary_background_fill": GRADIENT,
        "button_primary_background_fill_hover": f"linear-gradient(100deg, #ff4fa3 0%, #c27aff 55%, #9d74ff 100%)",
        "button_primary_text_color": "#ffffff",
        "button_primary_border_color": "transparent",
        "button_secondary_background_fill": "rgba(255,255,255,0.06)",
        "button_secondary_background_fill_hover": "rgba(255,255,255,0.11)",
        "button_secondary_text_color": TEXT,
        "button_secondary_border_color": "rgba(255,255,255,0.14)",
        "button_large_radius": "16px",
        "button_small_radius": "12px",
        "button_large_text_size": "17px",
        "button_large_text_weight": "700",
        "checkbox_background_color": "rgba(255,255,255,0.06)",
        "checkbox_background_color_selected": PINK,
        "checkbox_border_color": "rgba(255,255,255,0.25)",
        "checkbox_label_background_fill": "rgba(255,255,255,0.04)",
        "checkbox_label_background_fill_selected": "rgba(255,46,151,0.16)",
        "checkbox_label_border_color": "rgba(255,255,255,0.10)",
        "checkbox_label_border_color_selected": PINK,
        "checkbox_label_text_color": TEXT,
        "slider_color": PINK,
        "color_accent": PINK,
        "color_accent_soft": "rgba(255,46,151,0.18)",
        "link_text_color": "#ff7ab9",
        "table_border_color": "rgba(255,255,255,0.08)",
        "loader_color": PINK,
    }
    kwargs = {}
    for name, value in v.items():
        kwargs[name] = value
        kwargs[name + "_dark"] = value  # same look in light and dark mode: always dark
    ok = {}
    for k, val in kwargs.items():  # ignore names an older/newer Gradio doesn't know
        if hasattr(base, k):
            ok[k] = val
    return base.set(**ok)


HEAD = """
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#07050d">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=Vazirmatn:wght@400;700&display=swap" rel="stylesheet">
<script>document.documentElement.classList.add('dark');</script>
"""

CSS = f"""
:root {{ --sf-pink: {PINK}; --sf-purple: {PURPLE}; --sf-violet: {VIOLET}; --sf-grad: {GRADIENT}; --sf-muted: {MUTED}; }}
body, gradio-app, .gradio-container {{ background: {BG} !important; }}
.gradio-container {{
  max-width: 1180px !important; margin: 0 auto !important; padding: 12px 18px 90px !important;
  background:
    radial-gradient(900px 500px at 8% -8%, rgba(255,46,151,0.20), transparent 60%),
    radial-gradient(800px 520px at 100% 0%, rgba(139,92,246,0.22), transparent 60%),
    radial-gradient(700px 600px at 50% 110%, rgba(177,92,255,0.12), transparent 60%),
    {BG} !important;
}}
footer {{ display: none !important; }}
/* never wider than the phone screen */
.gradio-container > .main, .gradio-container .main > .wrap, .gradio-container main.contain {{
  max-width: 100vw !important; min-width: 0 !important; }}
.gradio-container {{ max-width: min(1180px, 100vw) !important; }}
.sf-steps .tab-container.visually-hidden {{ display: none !important; }}
h1, h2, h3, .sf-title {{ font-family: 'Space Grotesk', Inter, sans-serif; letter-spacing: -0.02em; }}

/* ---------- header ---------- */
.sf-header {{ display:flex; align-items:center; justify-content:space-between; gap:16px; flex-wrap:wrap; padding: 18px 4px 6px; }}
.sf-logo {{ display:flex; align-items:center; gap:12px; min-width:0; flex: 1 1 280px; }}
.sf-logo-mark {{ width:44px; height:44px; border-radius:14px; background: var(--sf-grad); display:grid; place-items:center;
  box-shadow: 0 0 30px rgba(255,46,151,0.55); font-size:22px; }}
.sf-logo h1 {{ margin:0; font-size: 30px; font-weight: 700; background: linear-gradient(90deg,#fff 0%,#ffd1ea 40%,#c9a7ff 100%);
  -webkit-background-clip:text; background-clip:text; color: transparent; }}
.sf-logo p {{ margin:2px 0 0; color: var(--sf-muted); font-size: 13.5px; }}
.sf-chips {{ display:flex; gap:8px; flex-wrap:wrap; }}
.sf-chip {{ font-size:12.5px; padding:7px 12px; border-radius:999px; background: rgba(255,255,255,0.05);
  border:1px solid rgba(255,255,255,0.10); color:#e9e4ff; white-space:nowrap; }}
.sf-chip.ok {{ border-color: rgba(57,255,136,0.35); }}
.sf-chip.warn {{ border-color: rgba(255,196,0,0.45); }}
.sf-chip.bad {{ border-color: rgba(255,80,80,0.6); background: rgba(255,60,60,0.12); }}
.sf-project {{ color: var(--sf-muted); font-size: 13px; padding: 0 4px 8px; }}
.sf-project b {{ color: #fff; }}

/* ---------- step bar (tabs) ---------- */
.sf-steps, .sf-steps .tab-wrapper, .sf-steps .tab-container {{ min-width: 0 !important; max-width: 100% !important; }}
.sf-steps .tab-container {{ overflow-x: auto !important; overflow-y: hidden !important; height: auto !important; }}
.sf-steps .overflow-menu, .sf-steps .overflow-item-selected {{ display: none !important; }}
.sf-steps > .tab-wrapper, .sf-steps [role="tablist"] {{ border:none !important; }}
.sf-steps [role="tablist"] {{
  width: 100%; box-sizing: border-box;
  display:flex !important; gap:8px; overflow-x:auto; flex-wrap:nowrap !important; scrollbar-width:none;
  padding: 6px; border-radius: 18px; background: rgba(255,255,255,0.035); border:1px solid rgba(255,255,255,0.07) !important;
}}
.sf-steps [role="tablist"]::-webkit-scrollbar {{ display:none; }}
.sf-steps button[role="tab"] {{
  flex: 1 0 auto; visibility: visible !important; position: static !important; border-radius: 13px !important; padding: 11px 16px !important; font-weight: 600; font-size: 14.5px;
  color: var(--sf-muted) !important; background: transparent !important; border: 1px solid transparent !important;
  white-space: nowrap; transition: all .2s ease;
}}
.sf-steps button[role="tab"]:hover {{ color:#fff !important; background: rgba(255,255,255,0.05) !important; }}
.sf-steps button[role="tab"][aria-selected="true"] {{
  color:#fff !important; background: var(--sf-grad) !important; box-shadow: 0 6px 24px rgba(255,46,151,0.35);
}}
.sf-steps button[role="tab"][aria-selected="true"]::after {{ display:none !important; }}
.sf-steps .tabitem, .sf-steps [role="tabpanel"] {{ border:none !important; background: transparent !important; padding: 14px 0 0 !important; }}

/* ---------- cards ---------- */
.sf-card {{
  background: linear-gradient(180deg, rgba(255,255,255,0.055), rgba(255,255,255,0.02)) !important;
  border: 1px solid rgba(255,255,255,0.09) !important; border-radius: 22px !important; padding: 18px !important;
  box-shadow: 0 20px 60px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.05);
}}
/* Gradio 6 puts elem_classes on two nested elements: only the outer one is the card */
.sf-card .sf-card {{ background: none !important; border: none !important; padding: 0 !important; box-shadow: none !important;
  border-radius: 0 !important; }}
.sf-card .sf-card::before {{ display: none !important; }}
.sf-card .sf-progress {{ background: transparent; border: none; padding: 2px 2px 6px; }}
.sf-card > .styler {{ background: transparent !important; gap: 12px !important; border: none !important; }}
.sf-card .block, .sf-card .form, .sf-card fieldset {{ background: transparent !important; border: none !important;
  box-shadow: none !important; }}
.sf-card .block.padded {{ padding: 4px 2px !important; }}
.sf-card .gr-accordion {{ background: rgba(255,255,255,0.03) !important; border-radius: 14px !important; }}
.sf-card-title {{ font-family:'Space Grotesk',Inter,sans-serif; font-size: 18px; font-weight:700; margin: 0 0 4px; color:#fff; }}
.sf-card-sub {{ color: var(--sf-muted); font-size: 13.5px; margin: 0 0 6px; }}
.sf-hero-card {{ position:relative; overflow:hidden; }}
.sf-hero-card::before {{ content:""; position:absolute; inset:-1px; border-radius: 22px; padding:1px;
  background: linear-gradient(120deg, rgba(255,46,151,0.7), rgba(139,92,246,0.5), transparent 70%);
  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0); -webkit-mask-composite: xor;
  mask-composite: exclude; pointer-events:none; }}

/* ---------- buttons ---------- */
button.lg, .sf-big {{ min-height: 54px !important; font-size: 17px !important; }}
button.primary {{ box-shadow: 0 10px 30px rgba(255,46,151,0.30); transition: transform .15s ease, box-shadow .2s ease; }}
button.primary:hover {{ transform: translateY(-1px); box-shadow: 0 14px 38px rgba(255,46,151,0.45); }}
button.secondary {{ backdrop-filter: blur(8px); }}
.sf-stop button, button.sf-stop {{ background: rgba(255,60,90,0.12) !important; border-color: rgba(255,60,90,0.45) !important; }}

/* ---------- progress ---------- */
.sf-progress {{ padding: 14px 16px; border-radius: 18px; background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); }}
.sf-progress-top {{ display:flex; justify-content:space-between; gap: 10px; font-weight:600; font-size: 14.5px; color:#fff; }}
.sf-progress-pct {{ font-variant-numeric: tabular-nums; color: #ffd1ea; }}
.sf-bar {{ height: 10px; border-radius: 999px; background: rgba(255,255,255,0.08); overflow:hidden; margin: 10px 0 8px; }}
.sf-fill {{ height:100%; border-radius:999px; background: var(--sf-grad); box-shadow: 0 0 18px rgba(255,46,151,0.65);
  transition: width .6s ease; background-size: 200% 100%; animation: sfmove 2.5s linear infinite; }}
@keyframes sfmove {{ 0% {{ background-position: 0 0; }} 100% {{ background-position: 200% 0; }} }}
.sf-progress-sub {{ color: var(--sf-muted); font-size: 12.5px; }}
.sf-progress.idle .sf-fill {{ animation:none; opacity:.35; }}
.sf-progress.failed {{ border-color: rgba(255,80,80,0.5); }}
.sf-progress.done {{ border-color: rgba(57,255,136,0.35); }}
.sf-log textarea {{ font-family: 'JetBrains Mono', ui-monospace, monospace !important; font-size: 12.5px !important;
  line-height: 1.5 !important; background: rgba(0,0,0,0.35) !important; }}

/* ---------- scene cards ---------- */
.sf-grid {{ display:grid !important; grid-template-columns: repeat(auto-fill, minmax(255px, 1fr)); gap: 16px; }}
.sf-grid > div {{ min-width: 0 !important; }}
.sf-scene {{ background: rgba(255,255,255,0.04) !important; border:1px solid rgba(255,255,255,0.09) !important;
  border-radius: 20px !important; padding: 10px !important; gap: 8px !important; }}
.sf-scene .image-container img, .sf-scene img {{ border-radius: 14px; }}
.sf-badges {{ display:flex; gap:6px; flex-wrap:wrap; align-items:center; font-size:12px; }}
.sf-badge {{ padding:4px 9px; border-radius:999px; background: rgba(255,255,255,0.07); color:#e9e4ff; font-weight:600; }}
.sf-badge.hook {{ background: rgba(255,46,151,0.22); color:#ffd1ea; }}
.sf-badge.cliff {{ background: rgba(139,92,246,0.28); color:#e3d6ff; }}
.sf-badge.hero {{ background: linear-gradient(90deg, rgba(255,46,151,0.35), rgba(139,92,246,0.35)); color:#fff; }}
.sf-badge.mine {{ background: rgba(57,255,136,0.18); color:#c8ffe0; }}
.sf-narr {{ font-size: 13.5px; color: #ddd8f5; line-height:1.45; min-height: 38px; }}
.sf-rtl {{ direction: rtl; text-align: right; font-family: Vazirmatn, Inter, sans-serif; }}
.sf-scene button {{ min-height: 42px !important; }}
.sf-scene .form, .sf-scene .block {{ background: transparent !important; border-color: rgba(255,255,255,0.06) !important; }}

/* ---------- misc ---------- */
.sf-note {{ font-size: 13px; color: var(--sf-muted); padding: 2px 4px; }}
.sf-doctor {{ font-size: 14px; line-height: 1.45; padding: 4px 6px; }}
.sf-doctor code {{ background: #ffffff12; border-radius: 6px; padding: 1px 6px; white-space: normal; }}
.sf-doctor td, .sf-doctor th {{ padding: 3px 6px; border-bottom: 1px solid #ffffff12; }}
.sf-warn {{ font-size: 13px; color: #ffe08a; background: rgba(255,196,0,0.08); border:1px solid rgba(255,196,0,0.25);
  padding: 10px 12px; border-radius: 14px; }}
.sf-check {{ list-style:none; padding:0; margin:0; }}
.sf-check li {{ padding: 8px 10px; border-radius: 12px; background: rgba(255,255,255,0.04); margin-bottom: 6px; font-size: 14px; }}
.sf-empty {{ text-align:center; color: var(--sf-muted); padding: 40px 10px; border: 1px dashed rgba(255,255,255,0.15); border-radius: 20px; }}
.sf-script textarea {{ font-family: 'JetBrains Mono', ui-monospace, monospace !important; font-size: 13.5px !important; line-height: 1.6 !important; }}
.sf-sticky {{ position: sticky; bottom: 10px; z-index: 50; }}

/* ---------- phone ---------- */
@media (max-width: 768px) {{
  .gradio-container {{ padding: 6px 10px 90px !important; }}
  .sf-logo h1 {{ font-size: 24px; }}
  .sf-chip {{ font-size: 11.5px; padding: 5px 9px; }}
  .sf-header {{ padding-top: 10px; }}
  .sf-logo-mark {{ width:38px; height:38px; }}
  .sf-steps button[role="tab"] {{ padding: 10px 12px !important; font-size: 13.5px; flex: 0 0 auto; }}
  .sf-card {{ padding: 14px !important; border-radius: 18px !important; }}
  .sf-grid {{ grid-template-columns: 1fr; }}
  .sf-row-stack {{ flex-direction: column !important; }}
  .sf-row-stack > * {{ width: 100% !important; min-width: 0 !important; }}
  button.lg, .sf-big {{ min-height: 56px !important; width: 100%; }}
}}
"""

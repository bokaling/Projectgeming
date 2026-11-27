"""Make a whole video from the command line (CPU or GPU), with your own plan if you have one.

    python -m storyforge.make --script script.txt --plan plan.json --res 720p --out video.mp4 [--sfx subtle]

--plan is optional: without it the planner makes the plan (Gemini with a free key, else the built-in planner).
The plan is checked and repaired exactly like a plan pasted in the app (docs/PLAN_CHEATSHEET.md).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m storyforge.make", description="Script (+ plan) → finished video")
    ap.add_argument("--script", required=True, help="the script text file ([TITLE], [SCENE], NARRATOR: …)")
    ap.add_argument("--plan", help="a scene plan JSON (optional)")
    ap.add_argument("--res", default="1080p", choices=["480p", "720p", "1080p"], help="output size (default 1080p)")
    ap.add_argument("--out", help="copy the finished video here")
    ap.add_argument("--format", default="auto", help="how_it_works, documentary, what_if, how_made, history, "
                                                     "top_list, story or auto")
    ap.add_argument("--seconds", type=int, default=0, help="target length (0 = the format's default)")
    ap.add_argument("--long", action="store_true", help="a long 16:9 video (default: vertical 9:16)")
    ap.add_argument("--root", help="StoryForge folder (default: the normal one for this computer)")
    ap.add_argument("--series", default="", help="series name (default: from the format)")
    ap.add_argument("--no-check", action="store_true", help="skip the quality check before the render")
    ap.add_argument("--sfx", default="subtle", choices=["off", "subtle", "full"],
                    help="sound effects: off, subtle (default: soft music, whooshes, a few soft hits) or full")
    args = ap.parse_args(argv)

    from . import config, pipeline, script
    from .messages import FriendlyError, Reporter
    from .project import EpisodeOptions, Series

    config.init(args.root) if args.root else config.init()
    text = Path(args.script).read_text(encoding="utf-8")
    opts = EpisodeOptions(script_text=text, length="long" if args.long else "short", resolution=args.res,
                          video_format=args.format, seconds=args.seconds, quality_check=not args.no_check,
                          sfx=args.sfx)
    rep = Reporter(echo=True)
    try:
        series = Series.create(args.series) if args.series else pipeline.auto_series(opts, text)
        number = pipeline.same_topic_episode(series, opts, text) or series.next_episode_number()
        ep = series.episode(number)
        ep.save_options(opts)
        script.script_from_text(series, ep, opts, text, rep)
        pipe = pipeline.Pipeline(series, ep, rep, opts)
        if args.plan:
            plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
            plan = pipe.save_plan(plan)
            rep.ok(f"Your plan is checked and used: {len(plan['scenes'])} shots")
        result = pipe.make_video(final=False)
    except FriendlyError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1
    video = Path(result["videos"][0])
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(video, args.out)
        print(f"🎬 {args.out}")
    else:
        print(f"🎬 {video}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

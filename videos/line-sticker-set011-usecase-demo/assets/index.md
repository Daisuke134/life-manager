# set-011 source assets

These are the creator's own approved set-011 sticker assets; no outside artwork or search results are used.

| Role | Frozen source | Frame sequence | Provenance |
|---|---|---|---|
| Thanks | `source/01-thanks.apng.png` | `frames/thanks/frame-00.png`–`frame-19.png` | Sticker #01 (`thanks`), original 320×270 RGBA APNG, 20 frames at 10 fps. Source SHA-256: `abfe4d91ad0eb697ca00c2269729fab49a72b3402756f4f000317404e429a7b6`. |
| Morning greeting | `source/03-goodmorning.apng.png` | `frames/goodmorning/frame-00.png`–`frame-19.png` | Sticker #03 (`goodmorning`), original 320×270 RGBA APNG, 20 frames at 10 fps. Source SHA-256: `15698f9e2468512f4de16ed960af041d0629149d0e596f1a90a3142693bc8eea`. |

Frame PNGs are decoded once from their source APNG with `ffmpeg -ignore_loop 1`; pixels and alpha are kept, and the timeline shows each 20-frame sequence once at its source cadence. The social-caption CTA points to `https://aniccaai.com/blog/line-sticker-set-011-2026-10-13-08`, whose article links to LINE STORE item `37168875`.

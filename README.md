# shorts-pipeline

Turn one YouTube source video into several short (9:16) narrated videos through
a resumable, command-driven pipeline with a human approval gate.

Design spec: [`docs/superpowers/specs/2026-09-06-shorts-pipeline-design.md`](docs/superpowers/specs/2026-09-06-shorts-pipeline-design.md)

## Pipeline

Run as `python -m shorts <command>` (activate the venv first, or use
`.venv/bin/python -m shorts`). `X` is the project name; omit it and the CLI
uses the sole / most-recent project.

```
python -m shorts fetch <url> --name X   # yt-dlp -> source video; also seeds ideas/prompt.json
python -m shorts transcribe X           # ffmpeg + OpenAI Whisper -> transcript
#   optional: edit ideas/prompt.json to steer idea generation (pt-BR brief by default)
python -m shorts ideate X               # prompt.json + transcript -> ideas/NN-slug.md (each with "- [ ] Approved")
#   review ideas/*.md, tick "- [x] Approved", edit narration if needed
python -m shorts voice X                # Gemini TTS -> voice/NN-slug.mp3 for approved ideas
python -m shorts plan X                 # ai-vedit plan -> renders/NN-slug.plan.json
#   review / edit renders/*.plan.json before rendering
python -m shorts render X               # ai-vedit render (from the plan) -> renders/NN-slug.mp4
python -m shorts youtube auth           # one-time Google OAuth consent -> saves a token
python -m shorts publish X              # upload approved+rendered shorts (private + scheduled)
python -m shorts status [X]             # show stage + per-idea state
```

`ideas/prompt.json` is `{"prompt": "..."}` — the creative brief sent to the
ideation model, pre-filled in Brazilian Portuguese. Edit it any time; after the
first `ideate` run, changes need `python -m shorts ideate X --force`.

Narration voice is tuned globally in `config.toml` under `[voice]`: `model`
(`gemini-2.5-pro-preview-tts` or `gemini-2.5-flash-preview-tts`), `voice` (one
of Gemini's 30 prebuilt voice names, e.g. `Kore`), and `instructions`
(free-text tone/style/pacing steering, prefixed onto the narration text before
synthesis). Changing any of them re-synthesizes affected clips on the next
`voice` run and regenerates their plan on the next `plan` run — no `--force`
needed.

`plan` and `render` are separate so you can inspect the shot list before
spending render time. `plan` writes one `renders/NN-slug.plan.json` per approved
idea (JSON: `audio_path` + a `beats` array); it won't overwrite a plan you've
hand-edited unless the narration, voice settings, or `[render]` options changed
(or you pass `--force`). `render` turns each reviewed plan into
`renders/NN-slug.mp4` and re-runs automatically when the plan file's contents
change.

`[render]` in `config.toml`: `min_beat_duration` tunes the plan; `aspect`
(top-level, `9:16` / `16:9`) is passed to `ai-vedit render`. The
`[render.subtitle]` table controls burned-in captions — `enabled` (default
`true`) plus optional styling: `font`, `font_size`, `primary_color` (`#RRGGBB`),
`bold`, `italic`, `uppercase`, `position` (`bottom`/`middle`/`top`),
`margin_vertical`, `max_chars_per_line`, `max_lines`, `max_duration`. Each maps
to an `ai-vedit plan --subtitle-*` flag and is only sent when set; changing any
of them regenerates the affected plan on the next `plan` run. Requires
**ai-vedit ≥ 0.2.0**.

## Web UI

A local browser UI over the same pipeline:

```bash
python -m shorts serve            # opens http://127.0.0.1:8765
python -m shorts serve --no-open  # don't open a browser
python -m shorts serve --port 9000
```

It lists projects, runs every stage with live-streamed output, and lets you
view/edit/approve ideas, edit `ideas/prompt.json`, and edit the
`renders/NN-slug.plan.json` shot lists. All files stay on disk exactly as the
CLI writes them — the server is only a front end, and runs each stage by
invoking `python -m shorts <stage>` as a subprocess.

**Localhost only.** There is no authentication. Do not pass `--host 0.0.0.0` or
otherwise expose the port: the server can start processes and serves data
derived from your `.env`. There is also no CSRF protection, so any web page open
in the same browser can fire simple cross-origin `POST`s at `127.0.0.1:8765`
(e.g. `POST /api/projects/<name>/run/<stage>`, which takes no body) — an accepted
risk for this local-only, single-user tool.

## Narration voice (Gemini TTS)

Narration is synthesized with the Gemini API's native TTS models
(`gemini-2.5-pro-preview-tts` / `gemini-2.5-flash-preview-tts`), not a
dedicated Cloud service — so setup is a single API key, no service account or
OAuth consent screen.

### One-time Google setup

1. Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey) and
   sign in with your Google account.
2. Click **Create API key** (choose or create any Google Cloud project when
   prompted — TTS billing rides on that project, no separate API to enable).
3. Copy the key and add it to `.env`:

   ```bash
   GEMINI_API_KEY=your-key-here
   ```

### Use

Nothing else to configure — `python -m shorts voice X` picks up
`GEMINI_API_KEY` automatically. Tune `model` / `voice` / `instructions` under
`[voice]` in `config.toml` (see above) and re-run `voice` to hear changes; no
`--force` needed since narration re-synthesizes when those settings change.

Pricing is per character of input text, billed to the Cloud project behind
the key ([ai.google.dev/pricing](https://ai.google.dev/pricing) has current
rates) — check it if you're narrating a high volume of shorts.

## YouTube publishing

Schedule rendered shorts to your own channel. Uploaded as **private + scheduled**
so YouTube publishes them at the chosen time.

### One-time Google setup

1. console.cloud.google.com → new project → enable **YouTube Data API v3**.
2. **OAuth consent screen**: User type **External**; add scope
   `.../auth/youtube.upload`; add your Google account under **Test users**; leave
   the publishing status at **Testing**.
3. **Credentials → Create OAuth client ID → Desktop app** → download the JSON.
4. Point `config.toml` at it:

   ```toml
   [youtube]
   client_secret = "client_secret.json"
   category_id   = 22
   ```

### Use

```bash
python -m shorts youtube auth       # one browser consent; re-run ~weekly (Testing mode)
python -m shorts youtube status     # is a token present?
python -m shorts publish X          # upload the whole approved+rendered queue
python -m shorts publish X --slug 01-foo   # just one
```

or the **Publish** panel in the web UI (cadence + per-idea override + Upload).

The Testing-mode refresh token lapses after ~7 days — re-run `youtube auth` when
`publish` says the token expired. Videos already uploaded and scheduled publish
on time regardless. Quota is ~6 uploads/day. Publishing is always an explicit
action; nothing else in the pipeline touches YouTube.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.toml config.toml   # then edit assets_dir etc.
cp .env.example .env                 # then fill in OPENAI_API_KEY and GEMINI_API_KEY
```

Requires `ffmpeg` and `ai-vedit` on `PATH`. `config.toml` and `.env` are read
from the current working directory (the repo root).

## Testing

Current: unit tests only.

```bash
python -m pytest
```

### TODO — expand test coverage

- [ ] Stage-level tests for `fetch` / `transcribe` / `ideate` / `voice` /
      `render` with the OpenAI/Gemini clients and `subprocess` (yt-dlp, ffmpeg,
      ai-vedit) mocked — assert the files written and the manifest transitions.
- [ ] End-to-end smoke test behind a `--runslow` marker: a ~20s clip through
      all five stages against the real OpenAI/Gemini APIs and `ai-vedit`.
- [ ] Browser/end-to-end test of the web UI (`shorts serve`): drive a project
      through the stages against a stubbed job runner.

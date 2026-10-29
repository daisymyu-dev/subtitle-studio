# Public Beta implementation plan — 2026-10-29

**Goal:** Publish a clean MIT-licensed Subtitle Studio Public Beta to daisymyu-dev/subtitle-studio with a Windows downloadable build, independent Word export, local learning history/profile, universal on-demand dictionary lookup, reliable existing video/subtitle/hover features and honest capability boundaries. Preserve the separate personal installation and all its private data.

**Architecture:** Existing Python loopback server and local HTML/CSS/JS retained. Program assets separate from per-user data. New local SQLite learning store and read-only retained-job history; no cloud accounts or paid calls. The 24 curated contextual highlights remain a transparent starter library, complemented by arbitrary English word lookup, user known/saved feedback and per-job progress. Full semantic AI auto-highlighting is roadmap, not claimed complete. Fixed-origin dictionary lookup only after explicit user action, with bounded response and attribution; no automatic uploads on hover.

**API contract for parallel implementation:**
- GET `/api/learning`: `{known: [canonical_key], saved: [{key,term,english,chinese,url,start,created_at}], progress: {jobid: seconds}}`.
- POST `/api/learning/term`: `{key,term,state:'known'|'learn'|'neutral',english?,chinese?,url?,start?}` → updated same profile. Key max120 ASCII letters/digits/spaces/hyphens, use curated item.id or lowercase looked-up word. Known removes saved; learn removes known/adds saved; neutral removes both.
- POST `/api/learning/progress`: `{job_id,time}` → `{ok:true}`; bounded existing retained job ID and finite0..604800 seconds.
- GET `/api/library`: `{items:[{id,title,url,created_at,cue_count,position}]}` from confined local results metadata only, never arbitrary paths.
- POST `/api/dictionary`: `{word}` (single English headword <=64 chars) → `{word,phonetic,definitions:[{part_of_speech,definition,example}],source_url,license}` or explicit error. Uses fixed `https://api.dictionaryapi.dev/api/v2/entries/en/` only; no response audio fetching and no Google fallback. Explicit first-click UI explains this external word lookup; no selected full sentence is uploaded.
- All APIs share existing token/origin/host guards; no remote arbitrary endpoints, external API keys, user accounts, microphone or cloud audio uploads.

## Work packages

1. Word worker: replace Codex/Node-bound DOCX generator with standard project dependency python-docx preserving exact API, text/source/time/layout/pagefooter/atomic writes/desktop collision safety. Own word module/tests only.
2. Learning UI worker: known/saved/history drawer, arbitrary selected-word dictionary query, source/IPA/definitions and browser-local optional pronunciation; integrate profile/known filtering/progress without altering original words, duplicate cap or no-autoplay. Own web files and JS tests only; parent provides API.
3. Packaging worker: per-user data paths and frozen runtime assets, PyInstaller Windows portable build, bundled local Node for yt-dlp where possible with licenses, minimal launch/test smoke, environment-independent dependency configs. Own app.py, runtime module, build files/CI dependency config, NativeTools command support, packaging tests. Never modify private install or publish remotely.
4. Parent: learning store/history/dictionary/API TDD, MIT/license/privacy/security/support/contribution docs, clean examples and release notes, GitHub workflows integration, safety scan and release manifest. Explicit source allowlist excludes private results/logs/models/uploads/cache/original docs/screenshots.

## Verification and publication

- Workers observe RED/GREEN and keep disjoint edits; parent spec review plus independent code review before publish.
- Run full Python+JS regression in clean release environment; build and launch portable executable with separate throwaway data dir, exercise local self-authored caption/Word/library/dictionary mock cases. Real network dictionary check only self-authored common word; do not claim machine-translation/YouTube network success from mocks.
- Build screenshots using self-authored demo and hide personal paths. No user's TomLee transcripts, thumbnails, Word documents, logs or old job IDs in source/public artifacts.
- Fresh Git repository only in this release directory; inspect exact staged file list, scan for private paths/credentials, commit. User selected MIT; authenticated login verified daisymyu-dev. Create new public repo only if absent, push main, run CI, publish prerelease with source/Windows archive/checksums and honest supported limits. Never overwrite existing repo/ref/history or publish unrelated work.

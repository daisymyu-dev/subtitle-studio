# 0.1.0-beta.1 — Public Beta

First public release of Subtitle Studio, a local-first English listening workspace for Chinese-speaking learners.

## Included

- Independent local DOCX export with declared Python dependency; no Codex or Node document runtime.
- Official isolated video player, per-new-video 1× default and full sentence-paired references. Local original-audio shadowing requires the source installation with optional audio dependencies; it is not bundled in Core.
- Local known/saved expression state, learning history/progress, and explicit arbitrary single-word dictionary queries with attribution.
- Single gold curated 24-expression starter library, hover explanations/reference IPA and offline pronunciation demonstrations.
- Windows x64 Core portable build; user data separate from installed assets, dependency/runtime checks, privacy and security documentation. Core intentionally excludes the optional ASR codec bundle pending separate redistribution review; source installation can enable local ASR.

## Important limits

- Prerelease, not code-signed and not independently certified in a clean VM. Keep the whole portable folder together; verify SHA-256.
- Requires network access to YouTube/translation/dictionary providers for those actions. No access controls are bypassed; unavailable content remains unavailable.
- Punctuation model weights download on first need. Core does not contain local ASR or the decoder needed by local original-audio shadowing; use the documented source installation and optional dependencies for these features. No cloud audio upload.
- Full semantic AI vocabulary recommendation is not included; automatic highlights use 24 curated expressions, while explicit single-word lookup is general.
- Translations, punctuation, timing estimates, dictionary coverage and demonstration pronunciation can be imperfect. No IELTS assessment, pronunciation scoring, cloud sync or hosted multi-user service.

Repository code is MIT. Dependencies, models, dictionary entries and content have their own licenses/rights; see bundled notices and privacy documents.

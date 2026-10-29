# Privacy and data handling

Subtitle Studio Public Beta is a single-user, loopback-only application. It has no account server, billing integration, cloud synchronization or default analytics. Do not expose its local server to the public internet.

## Data stored locally

Subtitle results, source provenance, optional downloaded original audio, learning.sqlite3 (known/saved expressions and per-video progress), model caches, temporary uploads and diagnostic logs are stored in the configured user-data directory. Word documents can additionally be saved to your OS Desktop with collision-safe numbered filenames. Program upgrades should not overwrite user data.

Browser storage may retain the current job/profile preferences and first-use consent. Library state is not an English ability assessment. Logs should never contain caption text, session tokens or API credentials. Report unexpected logging privately via SECURITY.md, not a public issue.

You can export Word and access retained result files. To clear learning history, close the application and back up or remove its user-data directory yourself; this release does not silently delete your media or results. Browser preferences can be cleared through browser settings. The app does not edit browser security or cookie settings.

## External connections

- **YouTube:** the official isolated embedded player and explicit caption/audio retrieval communicate with YouTube. Cookies are not automatically extracted. Login challenges, private videos, paywalls and access limits are not bypassed.
- **Google translation:** when explicitly creating new bilingual study material and Chinese is missing, English subtitle text goes to the fixed Google public web translation route. This is not a supported Cloud Translation API or an availability guarantee. No audio is sent. Existing completed local Word export does not retranslate.
- **Free Dictionary API:** an explicit query sends one English headword to api.dictionaryapi.dev. Returned definition/IPA/source/license are shown; no remote audio is downloaded or played by the server, and no full sentence or video is sent. The service may log requests under its own practices. Do not query secrets or private identifiers.
- **Model downloads:** optional local Whisper and punctuation models may contact their hosting providers on first use. Inference is local; audio and captions are not uploaded for inference.
- **Updates/source:** visiting GitHub is a normal external website visit. No background auto-update or telemetry is enabled by this release.

Bundled pronunciation clips were generated offline with Microsoft Zira Desktop en-US. They are synthetic demonstrations, not original-speaker or dictionary recordings. Optional browser pronunciation must use an installed local English voice only and an explicit click; if unavailable, the UI reports it rather than selecting an online provider.

## Limitations

No automatic upload to cloud transcription, no microphone access, no browser credential collection, no paid API generation. Any future provider or cloud sync must be separately disclosed and opted into. Keeping data local does not eliminate all risks from installing software, local malware, shared computers or user-triggered third-party requests.

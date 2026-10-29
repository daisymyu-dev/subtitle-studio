# Third-party notices and design research

## Public Beta runtimes and dependencies

The project's MIT license applies to project code only. The Windows Core archive
contains the actual installed dependency license texts under `licenses/`, a
`BUNDLED-DISTRIBUTIONS.json` inventory and `BUNDLED-LICENSES.md` summary. Keep these
with any redistributed archive. The bundled Python runtime, PyInstaller bootloader,
official Node executable and its third-party notices retain their own terms.

Core includes yt-dlp and its caption-extraction dependencies, python-docx/lxml for
DOCX, and ONNX Runtime/tokenizers/Hugging Face support for local punctuation.
These are declared in `requirements*.txt`; the packaged inventory identifies the
actual bundled distributions. Model weights are not bundled: see their pinned
sources and Apache-2.0 notice below. PyAV, FFmpeg/codec DLLs, CTranslate2,
faster-whisper and Mutagen are explicitly excluded from the public Core archive.
Optional source ASR installations have additional licenses; the Core notices do
not certify redistribution of a separate full-ASR binary. See `docs/build.md`.

Dictionary results are fetched only after explicit lookup from
https://dictionaryapi.dev/ and are not MIT-licensed project assets. The UI retains
the response's source link and license metadata (including Wiktionary attribution
when returned). English definitions are reference definitions, not guaranteed
translations of the video context. No returned dictionary audio is redistributed.

The small included pronunciation WAVs are locally synthesized demonstration
assets, not recordings extracted from any third-party video. Their provenance
and limitations are documented in `docs/pronunciation-sources.md`.

The redesigned UI is custom HTML/CSS for this local app, not a downloaded complete template. No commercial brand assets, logos, screenshots or code are copied into the app.

## Open Props — actual code reuse

Source: https://github.com/argyleink/open-props/blob/main/src/props.easing.js

Four selected easing variables are adapted to plain CSS in `web/vendor/open-props-easing.css`; this file is loaded locally by all three versions.

MIT License

Copyright (c) 2021 Adam Argyle

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Lucide — actual SVG reuse

Source: https://github.com/lucide-icons/lucide/tree/main/icons

The audio-lines, sliders-horizontal, arrow-up-right, download and shield-check SVG paths are adapted into local `<symbol>` definitions in `web/index.html`. No external script or remote icon service is used. Original license: https://github.com/lucide-icons/lucide/blob/main/LICENSE

ISC License

Copyright (c) 2026 Lucide Icons and Contributors

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

### Feather-derived Lucide icons — additional MIT notice

The arrow-up-right and download symbols are in Lucide's list of Feather-derived icons; retain this additional notice.

The MIT License (MIT)

Copyright (c) 2013-present Cole Bemis

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Design references — inspiration, not copied code or assets

- Teenage Engineering field system: https://teenage.engineering/products/field-system — control markings, equipment hierarchy, physical affordances.
- Studio Dumbar: https://studiodumbar.com/ — large typography, expressive visual rhythm.
- Raycast: https://www.raycast.com/ — clear task-focused tool hierarchy.
- HyperUI neobrutalism: https://hyperui.dev/components/neobrutalism/ — hard-edged layout and offset-shadow vocabulary; no Tailwind component source was incorporated.
- Magic UI: https://github.com/magicuidesign/magicui — examined as a component-library candidate but not adopted; the existing application remains framework-free.

Research date: 2026-10-28. Licensing notes identify the retrieved sources, not a legal warranty about unrelated files in those repositories.

## Optional local English punctuation assets

Public Apache-2.0 model assets are downloaded only on first need, stored in `.models/punctuation-en/`, and hash-verified before use. No upstream Python/pipeline code is executed. Original word/case output is not taken from the model; only punctuation insertions are used.

- Original ONNX: 1-800-BAD-CODE/punctuation_fullstop_truecase_english, https://huggingface.co/1-800-BAD-CODE/punctuation_fullstop_truecase_english, revision `b26fd1c40e88678859048898218ea4edcc24c84a`.
- Converted tokenizer mirror: inference4j/punctuation-fullstop-truecase-english, https://huggingface.co/inference4j/punctuation-fullstop-truecase-english, revision `22c0534d66a225dc97f1023b2777e948436bb9b7`.
- Apache License 2.0: https://www.apache.org/licenses/LICENSE-2.0

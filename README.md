# Subtitle Studio

**A local-first English listening workspace for Chinese-speaking learners.**

Watch English videos, read sentence-paired Chinese references, replay the original audio, and keep the expressions you want to learn.

[中文说明](#中文说明) · [Privacy](docs/PRIVACY.md) · [Security](SECURITY.md) · [Roadmap](docs/ROADMAP.md) · [Releases](https://github.com/daisymyu-dev/subtitle-studio/releases)

> **Public Beta · Windows x64 Core first.** The portable download includes subtitle learning, dictionary/profile/library, punctuation and Word export, but not optional audio ASR/codec components. Local Whisper transcription is available through the source installation with optional dependencies. This is a single-user local application, not a hosted SaaS, an official YouTube client, or a certified language assessment. YouTube access and machine translations can fail; no access restrictions are bypassed.

## What works

- Official embedded YouTube playback: no autoplay, default 1× on each new video, 0.75–2× speed and synchronized captions.
- Complete English sentences paired with independently translated Chinese references; clipped/uncertain ends are labeled. Original words remain unchanged.
- Restrained gold highlights, contextual explanations, reference IPA and local demonstration pronunciation. **The bundled automatic selection is a starter library of 24 curated advanced expressions, not universal AI vocabulary analysis.**
- Universal on-demand **single English word lookup**, local known/saved vocabulary, recent learning history and saved progress.
- Source installation with optional audio dependencies: original-audio sentence replay and shadowing, with an explicit first audio-download action, silence for practice, loop and slower playback. **The Core download does not include this local-audio feature**; embedded video playback remains available.
- Full bilingual Word export. No Microsoft Word, Codex, Node document runtime, or cloud document service is needed to create DOCX.
- Local SRT/VTT import. Optional local Whisper transcription requires the source installation with ASR dependencies; it is not bundled in the Windows Core download. No microphone permission or pronunciation scoring.

## Download and run

1. Download the Windows x64 portable archive from [Releases](https://github.com/daisymyu-dev/subtitle-studio/releases).
2. Extract the **whole folder**, then open `SubtitleStudio.exe`. Keep its `_internal` folder beside it.
3. Your browser opens a page at `127.0.0.1`. No login or API key is required for the local application.

Beta packages are not code-signed. Only download from this repository's Releases and compare SHA-256 checksums; do not disable security protections. If Windows requires an administrator or your organization blocks unsigned applications, stop and ask your administrator.

User data lives separately from the program. See [build/runtime documentation](docs/build.md) for source installation, data locations, model downloads and supported dependencies. A clean Windows VM and macOS/Linux installers are not yet certified; source runs on those platforms are experimental.

## 中文说明

面向已有一定英语基础、希望用科技／商业／访谈等英文视频练精听和积累表达的中文学习者。

### 推荐学习流程

粘贴链接 → 生成字幕 → 先听一小段 → 看逐句中英对照 → 重听／跟读 → 收藏表达 → 下次继续。

- **金色**：少量精选，每个已收录表达全文最多标注两次；雅思 7 只是初始选择方向，不是个人词汇测评。
- **悬停**：查看语境释义、音标与用法；点喇叭才发声。示范发音不是视频原声或词典录音。
- **已掌握／收藏**：保存在本机，已掌握表达以后不再主动标注。复习收藏内容时保留原句和来源。
- **查词**：选择字幕里的单个英文词后主动查询；首次查询说明外部词典服务。未查到会明确提示，不编造释义。
- **学习库**：查看本机整理过的内容，继续上次位置；不会自动播放或重新下载。
- **Word**：导出全文中英对照，而不是网页当前几句；同名文件编号保存，不覆盖旧文件。

### 数据与网络

“本地优先”**不等于完全离线**：

| 操作 | 数据去向 |
| --- | --- |
| 视频播放／字幕读取 | YouTube；读取优先使用 yt-dlp |
| 缺少中文的双语生成 | 英文字幕文字发送至 Google 公共网页翻译通路；非正式接口，可能限流或失效 |
| 主动单词查询 | 选中的一个单词发送至 Free Dictionary API；不发送整段字幕 |
| 本地听写／标点恢复 | 本机推理；首次需要下载模型，音频不会上传 |
| 学习记录、收藏和 Word | 本机保存；没有云同步或默认遥测 |

原音下载仅在明确点击准备后发生。已有英文／字幕文件保留；失败不会伪装成“无字幕”或完整成功。机器译文、人名、数字、分句和估算时间均需复核。[完整隐私说明](docs/PRIVACY.md)。

### 内容权限

请仅处理你有权使用的内容。公开视频不等于可以任意下载、复制或重新分发。遵守 YouTube 条款、权利人许可和当地法律；本项目不绕过登录、付费、地域或访问限制。官方播放器与下载／字幕工具的权限范围并不相同。

仓库只附自编示例、原创界面素材和本机合成的示范发音，不附任何个人学习结果或第三方视频全文。词典解释显示其来源与许可；不要把所有词典返回内容当作本项目 MIT 代码。

## Development

See [docs/build.md](docs/build.md). Project dependencies are declared and locally installed; no developer-specific runtimes are required. Tests use self-authored fixtures. Optional ASR dependency checks skip when those dependencies are absent. CI does not download arbitrary YouTube videos or upload audio.

## License

Project code: [MIT](LICENSE), copyright 2026 daisymyu-dev. Dependencies, model files, dictionary responses and bundled runtime components retain their own licenses. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). This license does not grant rights to third-party video/audio content.

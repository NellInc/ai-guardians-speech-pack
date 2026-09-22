# AI Guardians — Speech Pack

The Speech Pack for [AI Guardians](https://www.aiguardians.games), an
educational visual novel about AI ethics. Like the good old days: the full
spoken dialogue, one pack. The web build streams these clips on demand;
desktop and mobile builds bundle them.

- `v1/lines/` contains the immutable original release pack.
- `v2/lines/` contains the immutable 0.97 release-candidate pack, with its
  byte-level inventory in `v2/manifest.json`.
- `v3/lines/` contains the immutable 0.98.1 pack, including the approved
  All-ee pronunciation corrections, with its byte-level inventory in
  `v3/manifest.json`.

- `v4/lines/` contains the current 9,944-clip pack for the 0.99 web candidate,
  with its byte-level inventory in `v4/manifest.json`.

Each version has one Opus file per dialogue line (48 kbps mono, 24 kHz), keyed
by the game's translation identifiers. Published version directories are never
modified, so shipped builds cannot desynchronize from later renders.

## Provenance

Synthetic voices, human-directed: performances by Google Gemini 3.1 Flash
TTS and OpenAI gpt-realtime-2.1, cast, directed line by line, and
quality-checked by people. In a game about AI ethics, we disclose our own
AI use openly.

## License

(c) Nell Watson / EthicsNet. These clips are game assets for AI Guardians and
are not licensed for reuse outside the game.

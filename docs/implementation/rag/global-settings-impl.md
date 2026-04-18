# Implementation Guide: Global Settings

## Overview

The global settings system provides a server-side configuration store for user preferences that affect Daily Fetch output generation. Currently it manages audio language selection for four audio types (AI Briefing, World News, Chinese News, Knowledge).

**Backend**: `scripts/rag/agent.py` — `/api/settings` endpoint + `_GLOBAL_SETTINGS` dict
**Frontend**: Settings gear icon (⚙) in the page header, next to the model selector

## Architecture

```
┌──────────────────────┐      GET /api/settings      ┌──────────────────────┐
│   Settings Modal UI  │ ──────────────────────────→  │  _GLOBAL_SETTINGS    │
│   (gear icon ⚙)      │ ←──────────────────────────  │  (in-memory dict)    │
│                      │                              │                      │
│  [AI Audio: 中文 ▼]  │      POST /api/settings     │  audio_lang_ai: "zh" │
│  [World:    中文 ▼]  │ ──────────────────────────→  │  audio_lang_world: zh│
│  [China:    中文 ▼]  │      {audio_lang_ai: "en"}  │  audio_lang_china: zh│
│  [Knowledge:中文 ▼]  │                              │  audio_lang_know: zh │
└──────────────────────┘                              └──────┬───────────────┘
                                                             │
                                                    Used by _run_daily_fetch()
                                                             │
                              ┌───────────────┬──────────────┼──────────────┬───────────────┐
                              ▼               ▼              ▼              ▼               │
                       AI Briefing    World News      Chinese News    Knowledge Audio       │
                       (ai-briefing   (world-news     (china-news     (knowledge-audio      │
                        .mp3)          .mp3)           .mp3)           .mp3)                │
```

## Backend Implementation

### Settings Store

```python
_GLOBAL_SETTINGS = {
    "audio_lang_ai": "zh",          # AI Briefing audio language
    "audio_lang_world": "zh",       # World News (international) audio language
    "audio_lang_china": "zh",       # Chinese News audio language
    "audio_lang_knowledge": "zh",   # Knowledge audio language
}
```

Settings are stored in-memory and reset on server restart. Persistence can be added by writing to a JSON file if needed.

### API Endpoint

**`GET /api/settings`** — Returns current settings as JSON.

**`POST /api/settings`** — Partial update; only provided keys are changed.

```
POST /api/settings
Content-Type: application/json

{"audio_lang_world": "en"}

→ {"ok": true, "settings": {"audio_lang_ai": "zh", "audio_lang_world": "en", "audio_lang_knowledge": "zh"}}
```

### Usage in Daily Fetch

The `_run_daily_fetch` function reads settings at audio generation time:

**AI Briefing Audio:**
```python
ai_lang = _GLOBAL_SETTINGS.get("audio_lang_ai", "zh")
ai_voice = "en-US-AndrewNeural" if ai_lang == "en" else "zh-CN-YunxiNeural"
narrations = _generate_segmented_narrations(segments, "ai", lang=ai_lang)
_tts_segments_to_mp3(narrations, path, voice=ai_voice)
```

**World News Audio** (`world-news.mp3` — international only):
- Filters out China-sourced items; only includes BBC, Reuters, AP, DW, Guardian
- When `audio_lang_world` is `"zh"`, prefers `title_zh`/`summary_zh` fields
- TTS uses `zh-CN-YunxiNeural` (Chinese) or `en-US-AndrewNeural` (English)

**Chinese News Audio** (`china-news.mp3` — 中国新闻 only):
- Contains only China-sourced items (Sina, People's Daily)
- Controlled by `audio_lang_china` setting
- Up to 6 items per category (vs 4 for world news)

**Knowledge Audio:** Same pattern with `audio_lang_knowledge`.

### Narration Language Support

`_generate_segmented_narrations(segments, content_type, lang)` generates different prompts based on `lang`:

| `lang` | System Prompt | TTS Voice |
|--------|--------------|-----------|
| `"zh"` | 专业播报员/主播, 中文旁白 | `zh-CN-YunxiNeural` |
| `"en"` | Professional anchor/host, English narration | `en-US-AndrewNeural` |

## Frontend Implementation

### UI Components

1. **Gear Button (⚙)**: Added to the header toolbar, next to the model selector dropdown
2. **Settings Modal**: Popup overlay with three language dropdowns

### JavaScript Functions

| Function | Purpose |
|----------|---------|
| `openGlobalSettings()` | Fetches current settings via `GET /api/settings`, populates dropdowns, shows modal |
| `closeGlobalSettings()` | Hides the modal |
| `saveGlobalSettings()` | Reads dropdown values, sends `POST /api/settings`, closes modal on success |

### Modal HTML Structure

```html
<div id="globalSettingsModal" style="display:none">
  <div class="modal-overlay">
    <div class="modal-content">
      <h3>⚙ Global Settings</h3>
      
      <label>AI Briefing Audio Language</label>
      <select id="settAudioAi">
        <option value="zh">中文</option>
        <option value="en">English</option>
      </select>
      
      <label>World News Audio Language</label>
      <select id="settAudioWorld">...</select>
      
      <label>Knowledge Audio Language</label>
      <select id="settAudioKnowledge">...</select>
      
      <button onclick="saveGlobalSettings()">Save</button>
      <button onclick="closeGlobalSettings()">Cancel</button>
    </div>
  </div>
</div>
```

## Extension Points

### Adding New Settings

1. Add the key with default value to `_GLOBAL_SETTINGS`
2. The `/api/settings` endpoint automatically handles GET/POST for any key in the dict
3. Add a UI control in the `globalSettingsModal` HTML
4. Read the value from the dict where needed in `_run_daily_fetch` or other functions

### Adding Persistence

To persist settings across server restarts:

```python
SETTINGS_FILE = os.path.join(REPORTS_ROOT, "global-settings.json")

def _load_settings():
    if os.path.isfile(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            _GLOBAL_SETTINGS.update(json.load(f))

def _save_settings():
    with open(SETTINGS_FILE, "w") as f:
        json.dump(_GLOBAL_SETTINGS, f, indent=2)
```

### Adding More Languages

Add options to the `<select>` elements and extend the voice mapping in `_run_daily_fetch`:

```python
VOICE_MAP = {
    "zh": "zh-CN-YunxiNeural",
    "en": "en-US-AndrewNeural",
    "ja": "ja-JP-KeitaNeural",
    "de": "de-DE-ConradNeural",
}
```

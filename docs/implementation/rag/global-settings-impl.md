# Implementation Guide: Global Settings

## Overview

The global settings system provides a server-side configuration store for user preferences. It manages:
- **Audio language selection** for four audio types (AI Briefing, World News, Chinese News, Knowledge)
- **External API keys** (DeepSeek) with secure storage and connection testing

**Backend**: `scripts/rag/agent.py` — settings endpoints + `_GLOBAL_SETTINGS` dict
**Frontend**: Settings gear icon (⚙) in the page header, next to the model selector
**Persistence**: `.global_settings.json` (auto-saved on change, loaded on startup)

## Architecture

```
┌──────────────────────────┐      GET /api/settings      ┌──────────────────────────┐
│   Settings Modal UI      │ ──────────────────────────→  │  _GLOBAL_SETTINGS        │
│   (gear icon ⚙)          │ ←──────────────────────────  │  (in-memory + file)      │
│                          │                              │                          │
│  ── Audio Section ──     │      POST /api/settings     │  audio_lang_ai: "zh"     │
│  [AI Audio: 中文 ▼]     │ ──────────────────────────→  │  audio_lang_world: "zh"  │
│  [World:    中文 ▼]     │                              │  audio_lang_china: "zh"  │
│  [China:    中文 ▼]     │                              │  audio_lang_know: "zh"   │
│  [Knowledge:中文 ▼]     │                              │                          │
│                          │      POST /api/settings/    │  deepseek_api_key: "sk-" │
│  ── API Keys Section ── │      deepseek-key           │  (stored, masked in GET) │
│  [🔑 DeepSeek: sk-****] │ ──────────────────────────→  │                          │
│  [Save Key] [⚡Test]     │                              └──────┬───────────────────┘
│  [Clear]                 │      POST /api/deepseek/test        │
│                          │ ──────────────────────────→  DeepSeek API (cloud)
└──────────────────────────┘                              https://api.deepseek.com
```

## Backend Implementation

### Settings Store & Persistence

```python
_SETTINGS_FILE = os.path.join(os.path.dirname(__file__), ".global_settings.json")

_GLOBAL_SETTINGS_DEFAULTS = {
    "audio_lang_ai": "zh",
    "audio_lang_world": "zh",
    "audio_lang_china": "zh",
    "audio_lang_knowledge": "zh",
    "deepseek_api_key": "",
}

_GLOBAL_SETTINGS = _load_settings()   # Loads from file, merges with defaults
```

`_load_settings()` reads from `.global_settings.json` on startup, falling back to defaults.
`_save_settings()` writes to file on every change (POST).

### API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/settings` | Returns settings (API key **masked**: `sk-****xxxx`) |
| `POST` | `/api/settings` | Partial update for audio language settings |
| `POST` | `/api/settings/deepseek-key` | Set or clear the DeepSeek API key |
| `POST` | `/api/deepseek/test` | Test DeepSeek API connection |

**Security**: The `GET /api/settings` response never returns the raw API key. It returns `deepseek_api_key_masked` (e.g., `sk-1****5678`) and omits the actual key.

### DeepSeek API Integration

```python
def _get_deepseek_key() -> str:
    """Return configured DeepSeek API key (settings > env var fallback)."""
    return (_GLOBAL_SETTINGS.get("deepseek_api_key") or "").strip() \
        or os.environ.get("DEEPSEEK_API_KEY", "")
```

Key resolution order: settings file → `DEEPSEEK_API_KEY` environment variable.

### Test Endpoint

`POST /api/deepseek/test` uses the **OpenAI SDK** (`from openai import OpenAI`) with `base_url="https://api.deepseek.com"` to send a simple chat completion:

```python
client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
response = client.chat.completions.create(
    model="deepseek-v4-pro",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Say hello in one sentence."},
    ],
    max_tokens=50,
    stream=False,
    reasoning_effort="high",
    extra_body={"thinking": {"type": "enabled"}},
)
```

Returns `{ ok, model, reply, usage }` on success, `{ ok: false, error }` on failure.

### Usage in Daily Fetch

The `_run_daily_fetch` function reads audio settings at generation time:

| Setting | Audio File | Content Filter |
|---------|-----------|----------------|
| `audio_lang_ai` | `ai-briefing.mp3` | AI summary segments |
| `audio_lang_world` | `world-news.mp3` | International only (BBC, Reuters, etc.) |
| `audio_lang_china` | `china-news.mp3` | China only (Sina, People's Daily, etc.) |
| `audio_lang_knowledge` | `knowledge-audio.mp3` | Knowledge segments |

## Frontend Implementation

### UI Components

1. **Gear Button (⚙)**: In header toolbar, next to model selector
2. **Settings Modal** with two sections:
   - **Audio Language** — 4 dropdown selectors
   - **API Keys** — DeepSeek key input with save/test/clear buttons

### JavaScript Functions

| Function | Purpose |
|----------|---------|
| `openGlobalSettings()` | Fetches settings, populates fields (masked key as placeholder), shows modal |
| `closeGlobalSettings()` | Hides the modal |
| `saveGlobalSettings()` | Saves audio language settings via `POST /api/settings` |
| `saveDsKey()` | Saves DeepSeek API key via `POST /api/settings/deepseek-key` |
| `testDsKey()` | Tests connection via `POST /api/deepseek/test`, shows result inline |
| `clearDsKey()` | Clears the API key |
| `toggleDsKeyVisibility()` | Toggle password/text input type |

### Test Result Display

The test button shows inline results:
- **Success**: green checkmark, model name, reply text, token usage
- **Failure**: red X, HTTP status and error message

## Extension Points

### Adding New API Keys

1. Add the key to `_GLOBAL_SETTINGS_DEFAULTS`
2. Add `_settings_safe()` masking logic for the key
3. Add a separate POST endpoint for setting the key (don't mix with general settings)
4. Add UI section in the modal with input + save/test/clear buttons
5. Add a test endpoint that validates the key against the provider

### Adding New Settings

1. Add the key with default value to `_GLOBAL_SETTINGS_DEFAULTS`
2. The `/api/settings` endpoint handles GET/POST for any key in the dict
3. Add a UI control in the `globalSettingsModal` HTML
4. Update `openGlobalSettings()` and `saveGlobalSettings()` JS functions

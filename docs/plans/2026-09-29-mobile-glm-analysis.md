# Mobile GLM analysis pane Implementation Plan

> **For the implementing agent:** Follow this plan task-by-task. Complete each step, verify it works, then move to the next.

**Goal:** The Android intensive-reading app calls Zhipu GLM directly so the current passage can show 好词好句 and 社会文化, with the analysis on the right when the window is at least 600dp wide.

**Architecture:** Pure Kotlin builds the key mask, the chat JSON, the university/Chinese prompts, the 12000-character slice, and the SSE parser. `HttpURLConnection` is the only network piece. The reader split lives in `MainActivity` beside the existing pager. Local qwen gloss, TTS, and ECDICT stay unchanged.

**Tech Stack:** Kotlin, Jetpack Compose, JUnit4, `org.json` (already a unit-test dependency), Android `HttpURLConnection`. No new libraries. No `zai-sdk`.

**Do not:** commit, put a real API key in git or logs, add other analysis tabs, or change desktop Jarvis.

---

### Task 1: Key mask and missing-key message

**Files:**
- Create: `mobile/ir-android/app/src/main/java/com/jarvis/ir/glm/GlmKey.kt`
- Test: `mobile/ir-android/app/src/test/java/com/jarvis/ir/glm/GlmKeyTest.kt`

**Step 1: Write the failing test**

```kotlin
package com.jarvis.ir.glm

import org.junit.Assert.assertEquals
import org.junit.Test

class GlmKeyTest {
    @Test
    fun maskHidesTheMiddle() {
        assertEquals("sk-1****abcd", GlmKey.mask("sk-1234567890abcd"))
        assertEquals("", GlmKey.mask(""))
        assertEquals("****", GlmKey.mask("short"))
    }

    @Test
    fun blankKeyIsTheChineseMessage() {
        assertEquals("还没有 GLM 密钥", GlmKey.require("  "))
    }
}
```

`GlmKey.require` returns the trimmed key, or throws `GlmConfigException` whose message is exactly `还没有 GLM 密钥`. Adjust the test to expect that exception if a throwing API is clearer:

```kotlin
@Test
fun blankKeyThrowsBeforeAnyRequest() {
    try {
        GlmKey.require("  ")
        throw AssertionError("expected GlmConfigException")
    } catch (e: GlmConfigException) {
        assertEquals("还没有 GLM 密钥", e.message)
    }
}
```

**Step 2: Run test to verify it fails**

Run from `mobile/ir-android`:

```
gradlew.bat :app:testDebugUnitTest --tests com.jarvis.ir.glm.GlmKeyTest
```

Expected: FAIL, `GlmKey` unresolved.

**Step 3: Write minimal implementation**

```kotlin
package com.jarvis.ir.glm

class GlmConfigException(message: String) : IllegalStateException(message)

object GlmKey {
    const val PREFS = "ir"
    const val PREF_KEY = "glm_api_key"
    const val MISSING = "还没有 GLM 密钥"

    fun mask(key: String): String {
        if (key.isEmpty()) return ""
        if (key.length > 8) return key.take(4) + "****" + key.takeLast(4)
        return "****"
    }

    fun require(key: String?): String {
        val text = key?.trim().orEmpty()
        if (text.isEmpty()) throw GlmConfigException(MISSING)
        return text
    }
}
```

**Step 4: Run test to verify it passes**

Same command. Expected: PASS.

---

### Task 2: Public HTTP errors

**Files:**
- Modify: `mobile/ir-android/app/src/main/java/com/jarvis/ir/glm/GlmKey.kt` (add `GlmErrors` in the same file or a new `GlmErrors.kt`)
- Test: `mobile/ir-android/app/src/test/java/com/jarvis/ir/glm/GlmErrorsTest.kt`

**Step 1: Write the failing test**

```kotlin
package com.jarvis.ir.glm

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class GlmErrorsTest {
    @Test
    fun statusMapsWithoutTheBody() {
        assertEquals("GLM 请求过于频繁，请稍后再试", GlmErrors.forStatus(429))
        assertEquals("GLM 请求失败", GlmErrors.forStatus(500))
        assertEquals("没有返回内容", GlmErrors.EMPTY)
        assertFalse(GlmErrors.forStatus(401).contains("sk-"))
    }
}
```

**Step 2: Run test to verify it fails**

```
gradlew.bat :app:testDebugUnitTest --tests com.jarvis.ir.glm.GlmErrorsTest
```

Expected: FAIL, `GlmErrors` unresolved.

**Step 3: Write minimal implementation**

```kotlin
package com.jarvis.ir.glm

object GlmErrors {
    const val FAILED = "GLM 请求失败"
    const val BUSY = "GLM 请求过于频繁，请稍后再试"
    const val EMPTY = "没有返回内容"

    fun forStatus(status: Int): String = if (status == 429) BUSY else FAILED
}
```

Do not append `errorBody` to these strings.

**Step 4: Run test to verify it passes**

Same command. Expected: PASS.

---

### Task 3: Passage window

**Files:**
- Create: `mobile/ir-android/app/src/main/java/com/jarvis/ir/glm/PassageWindow.kt`
- Test: `mobile/ir-android/app/src/test/java/com/jarvis/ir/glm/PassageWindowTest.kt`

**Step 1: Write the failing test**

```kotlin
package com.jarvis.ir.glm

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PassageWindowTest {
    @Test
    fun shortPassageIsUnchanged() {
        val slice = PassageWindow.slice("Hello.\n\nWorld.")
        assertEquals("Hello.\n\nWorld.", slice.text)
        assertFalse(slice.hasMore)
    }

    @Test
    fun longPassageStopsOnAParagraph() {
        val para = "A".repeat(100) + "\n\n"
        val passage = para.repeat(200)
        val slice = PassageWindow.slice(passage)
        assertTrue(slice.text.length <= 12000)
        assertTrue(slice.text.endsWith("\n\n") || !slice.text.contains("\n\n").let { false })
        assertTrue(slice.hasMore)
        assertTrue(slice.text.endsWith("A") || slice.text.endsWith("\n\n"))
    }
}
```

Tighten the long-passage assertion: the slice must end at a `\n\n` boundary when one exists inside the window, and `text.length` must be `<= 12000`.

**Step 2: Run test to verify it fails**

```
gradlew.bat :app:testDebugUnitTest --tests com.jarvis.ir.glm.PassageWindowTest
```

Expected: FAIL.

**Step 3: Write minimal implementation**

Match `slice_passage` in `scripts/rag/intensive_reading/prompts.py` for offset 0 and window 12000: take up to 12000 characters, then if that cut is mid-text, walk back to the last `\n\n` or `. ` inside the second half of the window. Return `Slice(text, hasMore)`.

```kotlin
package com.jarvis.ir.glm

data class Slice(val text: String, val hasMore: Boolean)

object PassageWindow {
    const val WINDOW = 12000

    fun slice(passage: String, window: Int = WINDOW): Slice {
        if (passage.length <= window) return Slice(passage, false)
        var cut = window
        val minBreak = window / 2
        val para = passage.lastIndexOf("\n\n", cut)
        if (para >= minBreak) cut = para
        else {
            val sentence = passage.lastIndexOf(". ", cut)
            if (sentence >= minBreak) cut = sentence + 1
        }
        return Slice(passage.substring(0, cut), true)
    }
}
```

**Step 4: Run test to verify it passes**

Same command. Expected: PASS. Fix the test assertion so it checks `slice.text.endsWith` the boundary you actually cut on.

---

### Task 4: Prompts for 好词好句 and 社会文化

**Files:**
- Create: `mobile/ir-android/app/src/main/java/com/jarvis/ir/glm/AnalysisPrompts.kt`
- Test: `mobile/ir-android/app/src/test/java/com/jarvis/ir/glm/AnalysisPromptsTest.kt`

Copy the university + Simplified Chinese text from `scripts/rag/intensive_reading/prompts.py`:

- System for `vocab`: `_vocab_system_prompt("university", "zh")`. Learner line is `a university-level learner (approx. 6000-word vocabulary / CEFR B2–C1)`. Skip line is `Do NOT explain elementary vocabulary a B2 student already knows.` Chinese rules are the three `lang_rules` bullets in that function.
- System for `culture`: `system_prompt_for_kind("culture", "university", "zh")`, which is the coach sentence plus `_SYSTEM_CULTURE` with `_BASE_RULES` replaced by `_BASE_RULES_ZH`.
- User message: `analysis_user_message` with `book_type="novel"`, `part=1`, empty previous analysis, `learner_level="university"`, `output_lang="zh"`.

**Step 1: Write the failing test**

```kotlin
package com.jarvis.ir.glm

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class AnalysisPromptsTest {
    @Test
    fun onlyVocabAndCulture() {
        assertEquals(listOf("vocab", "culture"), AnalysisPrompts.kinds)
    }

    @Test
    fun vocabSystemIsUniversityChinese() {
        val system = AnalysisPrompts.system("vocab")
        assertTrue(system.contains("university-level learner"))
        assertTrue(system.contains("Simplified Chinese"))
        assertTrue(system.contains("Do NOT explain elementary vocabulary"))
    }

    @Test
    fun cultureSystemUsesChineseSharedRules() {
        val system = AnalysisPrompts.system("culture")
        assertTrue(system.contains("literary anthropologist"))
        assertTrue(system.contains("Write the full analysis in Simplified Chinese."))
        assertTrue(!system.contains("Do not use Chinese."))
    }

    @Test
    fun userMessageQuotesTheSlice() {
        val user = AnalysisPrompts.user(
            kind = "culture",
            title = "Emma",
            chunkIndex = 2,
            passage = "She walked.",
            hasMore = false,
        )
        assertTrue(user.contains("Book/section: Emma"))
        assertTrue(user.contains("Analysis tab: culture"))
        assertTrue(user.contains("Chunk index: 2"))
        assertTrue(user.contains("\"\"\"\nShe walked.\n\"\"\""))
        assertTrue(user.contains("socio-cultural annotations"))
        assertTrue(user.contains("Simplified Chinese"))
    }
}
```

**Step 2: Run test to verify it fails**

```
gradlew.bat :app:testDebugUnitTest --tests com.jarvis.ir.glm.AnalysisPromptsTest
```

Expected: FAIL.

**Step 3: Write minimal implementation**

`AnalysisPrompts.system` and `AnalysisPrompts.user` return the strings above. Unknown kind throws `IllegalArgumentException`. User task lines:

- vocab: `Extract advanced / interesting English usages from this passage. Write explanations and example notes in Simplified Chinese; keep quoted phrases in English.`
- culture: `Produce the socio-cultural annotations for this passage. Write the analysis in Simplified Chinese; keep quoted phrases in English.`

When `hasMore` is true, include the note `(Note: this is part of a longer chunk; more text follows after this excerpt.)` in the same place as `analysis_user_message`.

**Step 4: Run test to verify it passes**

Same command. Expected: PASS.

---

### Task 5: Request JSON and SSE deltas

**Files:**
- Create: `mobile/ir-android/app/src/main/java/com/jarvis/ir/glm/GlmProtocol.kt`
- Test: `mobile/ir-android/app/src/test/java/com/jarvis/ir/glm/GlmProtocolTest.kt`

**Step 1: Write the failing test**

```kotlin
package com.jarvis.ir.glm

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class GlmProtocolTest {
    @Test
    fun bodyDisablesThinkingAndOmitsTheKey() {
        val json = JSONObject(GlmProtocol.body("system text", "user text"))
        assertEquals("glm-4.7-flash", json.getString("model"))
        assertEquals(true, json.getBoolean("stream"))
        assertEquals(4096, json.getInt("max_tokens"))
        assertEquals("disabled", json.getJSONObject("thinking").getString("type"))
        assertEquals("system text", json.getJSONArray("messages").getJSONObject(0).getString("content"))
        assertFalse(json.toString().contains("sk-"))
    }

    @Test
    fun sseJoinsContentDeltasAndStops() {
        val lines = listOf(
            """data: {"choices":[{"delta":{"content":"好"}}]}""",
            """data: {"choices":[{"delta":{"content":"词"}}]}""",
            "data: [DONE]",
            """data: {"choices":[{"delta":{"content":"忽略"}}]}""",
        )
        assertEquals(listOf("好", "词"), GlmProtocol.deltas(lines))
    }
}
```

**Step 2: Run test to verify it fails**

```
gradlew.bat :app:testDebugUnitTest --tests com.jarvis.ir.glm.GlmProtocolTest
```

Expected: FAIL.

**Step 3: Write minimal implementation**

`GlmProtocol.body` builds the JSON with `org.json.JSONObject`. `GlmProtocol.deltas` skips blank lines and lines that do not start with `data:`. It stops at `data: [DONE]`. It reads `choices[0].delta.content` and skips objects with no content. Malformed JSON lines are skipped.

Endpoint constant: `https://open.bigmodel.cn/api/paas/v4/chat/completions`.

**Step 4: Run test to verify it passes**

Same command. Expected: PASS.

---

### Task 6: Analysis call uses the key and a fake transport

**Files:**
- Create: `mobile/ir-android/app/src/main/java/com/jarvis/ir/glm/GlmAnalysis.kt`
- Test: `mobile/ir-android/app/src/test/java/com/jarvis/ir/glm/GlmAnalysisTest.kt`

**Step 1: Write the failing test**

```kotlin
package com.jarvis.ir.glm

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class GlmAnalysisTest {
    @Test
    fun missingKeyDoesNotCallTransport() {
        var called = false
        val analysis = GlmAnalysis(key = { "" }) { _, _, _ -> called = true }
        try {
            analysis.run("vocab", "Emma", 0, "Hello.") {}
            throw AssertionError("expected missing key")
        } catch (e: GlmConfigException) {
            assertEquals(GlmKey.MISSING, e.message)
        }
        assertEquals(false, called)
    }

    @Test
    fun sendsSlicedPassageAndForwardsDeltas() {
        var seenKey = ""
        var seenBody = ""
        val analysis = GlmAnalysis(key = { "sk-1234567890abcd" }) { key, body, emit ->
            seenKey = key
            seenBody = body
            emit("句")
        }
        val parts = mutableListOf<String>()
        analysis.run("vocab", "Emma", 1, "She walked.", parts::add)
        assertEquals("sk-1234567890abcd", seenKey)
        val user = JSONObject(seenBody).getJSONArray("messages").getJSONObject(1).getString("content")
        assertTrue(user.contains("She walked."))
        assertEquals(listOf("句"), parts)
    }
}
```

**Step 2: Run test to verify it fails**

```
gradlew.bat :app:testDebugUnitTest --tests com.jarvis.ir.glm.GlmAnalysisTest
```

Expected: FAIL.

**Step 3: Write minimal implementation**

```kotlin
fun interface GlmTransport {
    fun post(apiKey: String, jsonBody: String, emit: (String) -> Unit)
}

class GlmAnalysis(
    private val key: () -> String,
    private val transport: GlmTransport,
) {
    fun run(kind: String, title: String, chunkIndex: Int, passage: String, emit: (String) -> Unit) {
        val apiKey = GlmKey.require(key())
        val slice = PassageWindow.slice(passage)
        val body = GlmProtocol.body(
            AnalysisPrompts.system(kind),
            AnalysisPrompts.user(kind, title, chunkIndex, slice.text, slice.hasMore),
        )
        transport.post(apiKey, body, emit)
    }
}
```

**Step 4: Run test to verify it passes**

Same command. Expected: PASS.

---

### Task 7: Width breakpoint

**Files:**
- Modify: `mobile/ir-android/app/src/main/java/com/jarvis/ir/ui/ReadingLayout.kt`
- Test: `mobile/ir-android/app/src/test/java/com/jarvis/ir/ui/ReadingLayoutTest.kt`

**Step 1: Write the failing test**

Add to `ReadingLayoutTest`:

```kotlin
@Test
fun analysisSitsBesideThePassageOnlyWhenWide() {
    assertEquals(false, analysisBesidePassage(599))
    assertEquals(true, analysisBesidePassage(600))
}
```

**Step 2: Run test to verify it fails**

```
gradlew.bat :app:testDebugUnitTest --tests com.jarvis.ir.ui.ReadingLayoutTest
```

Expected: FAIL, `analysisBesidePassage` unresolved.

**Step 3: Write minimal implementation**

```kotlin
const val ANALYSIS_PANE_MIN_DP = 600

fun analysisBesidePassage(widthDp: Int): Boolean = widthDp >= ANALYSIS_PANE_MIN_DP
```

599dp is the folded phone. 600dp is two or three panels of the tri-fold.

**Step 4: Run test to verify it passes**

Same command. Expected: PASS.

---

### Task 8: HTTP transport

**Files:**
- Create: `mobile/ir-android/app/src/main/java/com/jarvis/ir/glm/HttpGlmTransport.kt`

No live network test. This class is the only place that opens a socket.

Implementation:

- `POST` `GlmProtocol.ENDPOINT` with `Authorization: Bearer <apiKey>`, `Content-Type: application/json`, `Accept: text/event-stream`.
- On status other than 2xx, throw `GlmHttpException(GlmErrors.forStatus(status))`. Do not include the body in the exception message.
- Read the stream line by line, call `emit` for each delta from `GlmProtocol`. Stop when the caller’s `cancelled` lambda is true or the stream ends.
- If the joined text is blank after a successful status, throw `GlmHttpException(GlmErrors.EMPTY)`.

Keep the API key only in the header. Do not log the header or the body.

---

### Task 9: Settings key field

**Files:**
- Modify: `mobile/ir-android/app/src/main/java/com/jarvis/ir/ui/SettingsDialog.kt`
- Modify: `mobile/ir-android/app/src/main/java/com/jarvis/ir/MainActivity.kt`

Add to `SettingsDialog`, under the gloss bar:

- Text showing `已配置：` plus `GlmKey.mask(savedKey)`, or `未配置`.
- A password `OutlinedTextField` or `TextField` with `PasswordVisualTransformation`.
- Save writes `GlmKey.PREF_KEY` into the existing `ir` private preferences and clears the field.
- Test runs `GlmAnalysis` with `HttpGlmTransport` and the typed key if non-blank, otherwise the saved key. The user message is a one-sentence hello (`Analysis` is not required; a tiny `GlmAnalysis.probe` that posts `GlmProtocol.body("You are a helpful assistant.", "Say hello in one sentence.")` is enough). Show the reply, `GlmKey.MISSING`, or `GlmErrors` text. Never show the raw key or the HTTP body.

`MainActivity` loads the saved key once and passes the mask plus save/test callbacks into `SettingsDialog`.

---

### Task 10: Analysis pane beside the pager

**Files:**
- Create: `mobile/ir-android/app/src/main/java/com/jarvis/ir/ui/AnalysisPane.kt`
- Modify: `mobile/ir-android/app/src/main/java/com/jarvis/ir/MainActivity.kt`

`AnalysisPane` shows two buttons, 好词好句 (`vocab`) and 社会文化 (`culture`), a scrolling result, and 取消 while a call is running.

Wire it in the reader branch of `MainActivity` (the `chunks.isNotEmpty()` box), not inside `ReaderScreen`, so the pager stays the passage and gloss/TTS stay as they are.

```kotlin
BoxWithConstraints(Modifier.weight(1f)) {
    val wide = analysisBesidePassage(maxWidth.value.toInt())
    if (wide) {
        Row(Modifier.fillMaxSize()) {
            Box(Modifier.weight(1f)) { pager() }
            AnalysisPane(
                modifier = Modifier.width(360.dp).fillMaxHeight(),
                onRun = { kind -> startAnalysis(kind) },
                text = analysisText,
                error = analysisError,
                running = analysisRunning,
                onCancel = { analysisJob?.cancel() },
            )
        }
    } else {
        Box(Modifier.fillMaxSize()) {
            pager()
            TextButton(onClick = { showAnalysis = true }) { Text("分析") }
        }
        if (showAnalysis) {
            Dialog(onDismissRequest = { showAnalysis = false }) {
                AnalysisPane(...)
            }
        }
    }
}
```

`startAnalysis` launches a coroutine, clears the previous text, and calls `GlmAnalysis(...).run` for the current `bookTitle`, `chunkIndex`, and `chunks[chunkIndex]`. Append each delta on the main thread. On `GlmConfigException` or `GlmHttpException`, set `analysisError` to `e.message`. On cancel, keep the text already received.

Switching kind or chunk cancels the in-flight call.

---

### Task 11: Run the unit tests together

Run from `mobile/ir-android`:

```
gradlew.bat :app:testDebugUnitTest --tests com.jarvis.ir.glm.* --tests com.jarvis.ir.ui.ReadingLayoutTest
```

Expected: all PASS.

Manual check on the tri-fold, after installing the debug apk: save the GLM key, Test returns a sentence, unfolded width shows the pane on the right, folded width keeps the passage full width until 分析 is tapped, and both 好词好句 and 社会文化 stream Chinese text. A blank key shows `还没有 GLM 密钥` and does not change the gloss model.

---

## Notes for the executor

- Desktop prompt source: `scripts/rag/intensive_reading/prompts.py` functions `_vocab_system_prompt`, `system_prompt_for_kind`, and `analysis_user_message`.
- Existing prefs file is `GlossModelStore.PREFS` (`"ir"`). Store the GLM key in that same file under `glm_api_key`.
- `INTERNET` is already in `mobile/ir-android/app/src/main/AndroidManifest.xml`.
- Do not add GLM to `GlossSession.choices`.

# Needle Android Intensive Reading Implementation Plan

> **For the implementing agent:** Follow this plan task-by-task. Complete each step, verify it works, then move to the next.

**Goal:** Ship a standalone ARM64 Android APK whose only feature is intensive reading: import a book on the phone, select a word, show ECDICT 词性/中文释义 plus the original sentence as the example.

**Architecture:** One Kotlin/Compose + NDK app. Needle (`android-arm64` `libneedle.a` + `needle3.cact`) only extracts the headword and, when ECDICT has multiple senses, classifies `sense_id`. Definitions never come from the model. Windows is Android Studio only; inference runs on a USB ARM64 phone. Milestones stay in the same codebase: M1 bundled passage, M2 EPUB/TXT, M3 PDF.

**Tech Stack:** Kotlin 2, Jetpack Compose, Room/SQLite, CMake NDK, Needle 3 C API, ECDICT sqlite + `lemma.en.txt`, JUnit 4 on JVM, AndroidX instrumented tests on device.

**Approved decisions (do not re-litigate):**

- Structured fields only (pos / zh gloss / example). No Jarvis Analysis tabs, TTS, speaking, notes, or free-text explain.
- Single Android stack. No Windows `cactus-needle` inference harness.
- Windows = Android Studio compile + USB deploy. Default x86_64 emulator is not a Needle test target (no `android-x86_64` engine).
- `ndk.abiFilters += "arm64-v8a"` only, so Studio cannot silently install on an x86 AVD.
- Full ECDICT on device (same sqlite the tests use).
- Example sentence = grounded span from the passage, not a model-written example.
- Confidence &lt; 0.7 → show the card marked 不确定; do not invent a gloss.
- Missing dictionary entry → 「未收录」; do not call `select_sense`.
- Do not commit `needle3.cact`, `libneedle.a`, or full `ecdict.db` (gitignore).
- Do not port Jarvis magazine TOC heuristics.
- Telemetry off: `NEEDLE_TELEMETRY=0`, `DO_NOT_TRACK=1`.

**How the human tests on the Windows PC (standing procedure):**

1. Install Android Studio (SDK API 34, NDK, CMake).
2. Phone: developer options + USB debugging; confirm ARM64 (`adb shell getprop ro.product.cpu.abi` → `arm64-v8a`).
3. Studio Run → select that physical device (not an x86_64 AVD).
4. Logcat filter `NeedleIR`. After a selection you must see `headword`, `sense_id`, `confidence`.
5. Compose Preview may render UI without the model. Needle correctness is device-only.

---

### Task 1: Android project skeleton + gitignore

Scaffold only (generated Gradle). No production behavior yet.

**Files:**

- Create: `mobile/ir-android/` (Android Studio Empty Compose Activity, package `com.jarvis.ir`)
- Create: `mobile/ir-android/.gitignore`
- Modify: `c:\jarvis\.gitignore` — add the binary lines below if not already present

**Step 1: Create the project in Android Studio**

- Name: `ir-android`
- Save at `c:\jarvis\mobile\ir-android`
- Min SDK 26, compile/target 34
- Kotlin + Compose
- In `app/build.gradle.kts`:

```kotlin
android {
    defaultConfig {
        ndk {
            abiFilters += "arm64-v8a"
        }
        externalNativeBuild {
            cmake { cppFlags += "-std=c++17" }
        }
    }
    externalNativeBuild {
        cmake { path = file("src/main/cpp/CMakeLists.txt") }
    }
}
```

**Step 2: Gitignore binaries**

`mobile/ir-android/.gitignore`:

```
.gradle/
.idea/
build/
app/build/
local.properties
app/src/main/assets/needle3.cact
app/src/main/assets/ecdict.db
app/src/main/assets/lemma.en.txt
app/src/main/jniLibs/
app/src/main/cpp/needle.h
app/src/main/cpp/libneedle.a
```

Root `.gitignore` append:

```
mobile/ir-android/app/src/main/assets/needle3.cact
mobile/ir-android/app/src/main/assets/ecdict.db
mobile/ir-android/app/src/main/jniLibs/
```

**Step 3: Verify the empty app installs on the phone**

Run: Studio → Run on the USB ARM64 device.

Expected: default "Hello" Compose screen. If Gradle refuses because only `arm64-v8a` is enabled and the selected device is x86, that is correct — switch to the phone.

---

### Task 2: Split ECDICT `translation` into numbered senses

Pure Kotlin. This is the dictionary's multi-sense contract.

**Files:**

- Create: `mobile/ir-android/app/src/main/java/com/jarvis/ir/dict/SenseParser.kt`
- Create: `mobile/ir-android/app/src/test/java/com/jarvis/ir/dict/SenseParserTest.kt`

**Step 1: Write the failing tests**

```kotlin
package com.jarvis.ir.dict

import org.junit.Assert.assertEquals
import org.junit.Test

class SenseParserTest {
    @Test
    fun splitsNewlinePosGlosses() {
        val senses = SenseParser.parse(
            translation = "n. 银行\nvt. 把钱存入银行",
            posField = "n:8/v:2",
        )
        assertEquals(2, senses.size)
        assertEquals("n", senses[0].pos)
        assertEquals("银行", senses[0].translation)
        assertEquals(0, senses[0].id)
        assertEquals("vt", senses[1].pos)
        assertEquals("把钱存入银行", senses[1].translation)
    }

    @Test
    fun numberedLinesKeepOrder() {
        val senses = SenseParser.parse(
            translation = "1. n. 岸\n2. n. 银行",
            posField = null,
        )
        assertEquals(listOf("岸", "银行"), senses.map { it.translation })
        assertEquals(listOf("n", "n"), senses.map { it.pos })
    }

    @Test
    fun emptyTranslationIsEmptyList() {
        assertEquals(0, SenseParser.parse(translation = "  ", posField = null).size)
    }
}
```

**Step 2: Run test to verify it fails**

Run: `cd mobile/ir-android && .\gradlew.bat test --tests com.jarvis.ir.dict.SenseParserTest`

Expected: FAIL — `SenseParser` unresolved.

**Step 3: Write minimal implementation**

```kotlin
package com.jarvis.ir.dict

data class Sense(
    val id: Int,
    val pos: String?,
    val translation: String,
)

object SenseParser {
    private val numbered = Regex("""^\s*\d+\.\s*""")
    private val posPrefix = Regex("""^(n|v|vt|vi|adj|adv|prep|conj|pron|art|num|int|aux)\.\s+""", RegexOption.IGNORE_CASE)

    fun parse(translation: String, posField: String?): List<Sense> {
        val lines = translation.split('\n').map { it.trim() }.filter { it.isNotEmpty() }
        return lines.mapIndexed { idx, raw ->
            val unnumbered = raw.replace(numbered, "")
            val match = posPrefix.find(unnumbered)
            val pos = match?.groupValues?.get(1)?.lowercase()
            val text = (if (match != null) unnumbered.substring(match.range.last + 1) else unnumbered).trim()
            Sense(id = idx, pos = pos, translation = text)
        }
    }
}
```

Ignore `posField` in v1 if line prefixes already carry POS. Keep the parameter so Task 4 can pass the column through.

**Step 4: Run tests and make sure they pass**

Run: `.\gradlew.bat test --tests com.jarvis.ir.dict.SenseParserTest`

Expected: PASS

---

### Task 3: Lemma reduction (`running` → `run`)

**Files:**

- Create: `mobile/ir-android/app/src/main/java/com/jarvis/ir/dict/LemmaMap.kt`
- Create: `mobile/ir-android/app/src/test/java/com/jarvis/ir/dict/LemmaMapTest.kt`
- Create: `mobile/ir-android/app/src/test/resources/lemma-fixture.txt`

**Step 1: Write the failing tests**

`lemma-fixture.txt`:

```
run -> running, ran, runs
bank -> banks, banking, banked
```

```kotlin
package com.jarvis.ir.dict

import org.junit.Assert.assertEquals
import org.junit.Test

class LemmaMapTest {
    @Test
    fun inflectedFormMapsToStem() {
        val map = LemmaMap.load(
            javaClass.classLoader!!.getResourceAsStream("lemma-fixture.txt")!!
                .bufferedReader().readText(),
        )
        assertEquals("run", map.stem("running"))
        assertEquals("run", map.stem("Run"))
        assertEquals("bank", map.stem("banks"))
        assertEquals("ephemeral", map.stem("ephemeral")) // unknown: identity
    }
}
```

**Step 2: Run test to verify it fails**

Run: `.\gradlew.bat test --tests com.jarvis.ir.dict.LemmaMapTest`

Expected: FAIL — `LemmaMap` unresolved.

**Step 3: Write minimal implementation**

ECDICT `lemma.en.txt` uses `stem/freq -> form1, form2` (slash frequency is optional). Parser: skip `;` comments; split on `->`; left side take text before `/`.

```kotlin
package com.jarvis.ir.dict

class LemmaMap(private val inflectedToStem: Map<String, String>) {
    fun stem(word: String): String {
        val key = word.lowercase()
        return inflectedToStem[key] ?: key
    }

    companion object {
        fun load(text: String): LemmaMap {
            val map = HashMap<String, String>()
            text.lineSequence().forEach { line ->
                val trimmed = line.trim()
                if (trimmed.isEmpty() || trimmed.startsWith(";")) return@forEach
                val parts = trimmed.split("->", limit = 2)
                if (parts.size != 2) return@forEach
                val stem = parts[0].substringBefore("/").trim().lowercase()
                if (stem.isEmpty()) return@forEach
                map[stem] = stem
                parts[1].split(',').map { it.trim().lowercase() }.filter { it.isNotEmpty() }
                    .forEach { form -> map[form] = stem }
            }
            return LemmaMap(map)
        }
    }
}
```

**Step 4: Run tests and make sure they pass**

Run: `.\gradlew.bat test --tests com.jarvis.ir.dict.LemmaMapTest`

Expected: PASS

---

### Task 4: DictionaryRepository over sqlite

Use a tiny fixture DB in tests (not full ECDICT). Production will open `ecdict.db` from app files.

**Files:**

- Create: `mobile/ir-android/app/src/main/java/com/jarvis/ir/dict/DictionaryRepository.kt`
- Create: `mobile/ir-android/app/src/test/java/com/jarvis/ir/dict/DictionaryRepositoryTest.kt`

**Step 1: Write the failing tests**

Build an in-memory sqlite with the ECDICT `stardict` schema (columns we read: `word`, `pos`, `translation`). Robolectric is optional; prefer `org.xerial:sqlite-jdbc` on the JVM test classpath if Room is too heavy for unit tests. Simplest path: **do not use Android SQLite in this task**. Give `DictionaryRepository` an interface over a `Lookup` lambda / `DictDb` so JVM tests inject a map.

```kotlin
package com.jarvis.ir.dict

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class DictionaryRepositoryTest {
    private val lemma = LemmaMap.load("run -> running, ran, runs\n")
    private val rows = mapOf(
        "run" to DictRow(word = "run", pos = "v", translation = "n. 奔跑\nv. 跑步"),
        "bank" to DictRow(word = "bank", pos = "n", translation = "n. 岸\nn. 银行"),
    )
    private val repo = DictionaryRepository(
        lemma = lemma,
        lookupExact = { word -> rows[word.lowercase()] },
    )

    @Test
    fun inflectedWordUsesStem() {
        val hit = repo.lookup("running")!!
        assertEquals("run", hit.word)
        assertEquals(2, hit.senses.size)
    }

    @Test
    fun unknownWordIsNull() {
        assertNull(repo.lookup("xyzzy-not-a-word"))
    }

    @Test
    fun bankHasTwoSenses() {
        assertEquals(listOf("岸", "银行"), repo.lookup("bank")!!.senses.map { it.translation })
    }
}
```

**Step 2: Run test to verify it fails**

Expected: FAIL — `DictionaryRepository` / `DictRow` unresolved.

**Step 3: Write minimal implementation**

```kotlin
package com.jarvis.ir.dict

data class DictRow(val word: String, val pos: String?, val translation: String)

data class DictHit(val word: String, val senses: List<Sense>)

class DictionaryRepository(
    private val lemma: LemmaMap,
    private val lookupExact: (String) -> DictRow?,
) {
    fun lookup(raw: String): DictHit? {
        val trimmed = raw.trim()
        if (trimmed.isEmpty()) return null
        val stem = lemma.stem(trimmed)
        val row = lookupExact(stem) ?: lookupExact(trimmed.lowercase()) ?: return null
        val senses = SenseParser.parse(row.translation, row.pos)
        if (senses.isEmpty()) return null
        return DictHit(word = row.word, senses = senses)
    }
}
```

**Step 4: Run tests and make sure they pass**

Run: `.\gradlew.bat test --tests com.jarvis.ir.dict.DictionaryRepositoryTest`

Expected: PASS

---

### Task 5: Sense pipeline with a Fake Needle (no JNI yet)

This locks the product loop before NDK.

**Files:**

- Create: `mobile/ir-android/app/src/main/java/com/jarvis/ir/needle/NeedleClient.kt`
- Create: `mobile/ir-android/app/src/main/java/com/jarvis/ir/explain/ExplainPipeline.kt`
- Create: `mobile/ir-android/app/src/test/java/com/jarvis/ir/explain/ExplainPipelineTest.kt`

**Step 1: Write the failing tests**

```kotlin
package com.jarvis.ir.explain

import com.jarvis.ir.dict.DictHit
import com.jarvis.ir.dict.DictionaryRepository
import com.jarvis.ir.dict.LemmaMap
import com.jarvis.ir.dict.Sense
import com.jarvis.ir.needle.NeedleClient
import com.jarvis.ir.needle.NeedleTurn
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ExplainPipelineTest {
    private val repo = DictionaryRepository(
        lemma = LemmaMap.load(""),
        lookupExact = { w ->
            when (w) {
                "bank" -> com.jarvis.ir.dict.DictRow(
                    "bank", "n", "n. 岸\nn. 银行",
                )
                else -> null
            }
        },
    )

    @Test
    fun singleSenseSkipsSelectCall() {
        val oneSenseRepo = DictionaryRepository(
            lemma = LemmaMap.load(""),
            lookupExact = {
                com.jarvis.ir.dict.DictRow("ephemeral", "adj", "adj. 短暂的")
            },
        )
        val needle = object : NeedleClient {
            override fun complete(input: String): NeedleTurn =
                error("must not call Needle for a single sense")
        }
        val card = ExplainPipeline(oneSenseRepo, needle).explain(
            selected = "ephemeral",
            sentence = "Beauty is ephemeral.",
        )
        assertEquals("短暂的", card!!.translation)
        assertEquals("Beauty is ephemeral.", card.example)
        assertEquals(false, card.uncertain)
    }

    @Test
    fun multipleSensesAskNeedleForId() {
        val needle = object : NeedleClient {
            override fun complete(input: String): NeedleTurn {
                assertTrue(input.contains("岸"))
                assertTrue(input.contains("银行"))
                return NeedleTurn(
                    functionCalls = listOf(
                        mapOf("name" to "select_sense", "arguments" to mapOf("sense_id" to 0)),
                    ),
                    confidence = 0.91,
                )
            }
        }
        val card = ExplainPipeline(repo, needle).explain(
            selected = "bank",
            sentence = "They sat on the river bank.",
        )!!
        assertEquals("岸", card.translation)
        assertEquals("They sat on the river bank.", card.example)
        assertEquals(false, card.uncertain)
    }

    @Test
    fun missingWordReturnsNotInDict() {
        val needle = object : NeedleClient {
            override fun complete(input: String) = error("no needle")
        }
        val card = ExplainPipeline(repo, needle).explain("xyzzy", "hello xyzzy")
        assertEquals(ExplainStatus.NOT_IN_DICT, card!!.status)
    }

    @Test
    fun lowConfidenceMarksUncertain() {
        val needle = object : NeedleClient {
            override fun complete(input: String) = NeedleTurn(
                functionCalls = listOf(
                    mapOf("name" to "select_sense", "arguments" to mapOf("sense_id" to 1)),
                ),
                confidence = 0.4,
            )
        }
        val card = ExplainPipeline(repo, needle).explain(
            "bank",
            "They sat on the river bank.",
        )!!
        assertEquals(true, card.uncertain)
        assertEquals("银行", card.translation)
    }

    @Test
    fun emptyCallsRefuse() {
        val needle = object : NeedleClient {
            override fun complete(input: String) = NeedleTurn(functionCalls = emptyList(), confidence = 0.9)
        }
        val card = ExplainPipeline(repo, needle).explain("bank", "They sat on the river bank.")!!
        assertEquals(ExplainStatus.REFUSED, card.status)
    }
}
```

**Step 2: Run test to verify it fails**

Expected: FAIL — types unresolved.

**Step 3: Write minimal implementation**

```kotlin
package com.jarvis.ir.needle

data class NeedleTurn(
    val functionCalls: List<Map<String, Any?>>,
    val confidence: Double?,
)

interface NeedleClient {
    fun complete(input: String): NeedleTurn
}
```

```kotlin
package com.jarvis.ir.explain

import com.jarvis.ir.dict.DictionaryRepository
import com.jarvis.ir.needle.NeedleClient

enum class ExplainStatus { OK, NOT_IN_DICT, REFUSED }

data class ExplainCard(
    val status: ExplainStatus,
    val word: String = "",
    val pos: String? = null,
    val translation: String = "",
    val example: String = "",
    val uncertain: Boolean = false,
    val confidence: Double? = null,
)

class ExplainPipeline(
    private val dict: DictionaryRepository,
    private val needle: NeedleClient,
    private val confidenceFloor: Double = 0.7,
) {
    fun explain(selected: String, sentence: String): ExplainCard? {
        val hit = dict.lookup(selected) ?: return ExplainCard(status = ExplainStatus.NOT_IN_DICT, word = selected)
        if (hit.senses.size == 1) {
            val s = hit.senses[0]
            return ExplainCard(
                status = ExplainStatus.OK,
                word = hit.word,
                pos = s.pos,
                translation = s.translation,
                example = sentence,
                uncertain = false,
            )
        }
        val payload = buildString {
            append("sentence: ").append(sentence).append('\n')
            append("word: ").append(hit.word).append('\n')
            hit.senses.forEach { s ->
                append(s.id).append(". ").append(s.pos ?: "").append(" ").append(s.translation).append('\n')
            }
            append("Pick sense_id for this sentence.")
        }
        val turn = needle.complete(payload)
        val call = turn.functionCalls.firstOrNull()
        if (call == null) {
            return ExplainCard(status = ExplainStatus.REFUSED, word = hit.word, example = sentence)
        }
        val args = call["arguments"] as? Map<*, *> ?: return ExplainCard(status = ExplainStatus.REFUSED, word = hit.word)
        val id = (args["sense_id"] as? Number)?.toInt() ?: return ExplainCard(status = ExplainStatus.REFUSED, word = hit.word)
        val sense = hit.senses.getOrNull(id) ?: return ExplainCard(status = ExplainStatus.REFUSED, word = hit.word)
        val conf = turn.confidence
        return ExplainCard(
            status = ExplainStatus.OK,
            word = hit.word,
            pos = sense.pos,
            translation = sense.translation,
            example = sentence,
            uncertain = conf != null && conf < confidenceFloor,
            confidence = conf,
        )
    }
}
```

Needle tools later (JNI init) must declare exactly one tool for this turn:

```json
[{
  "name": "select_sense",
  "description": "Choose which dictionary sense matches the sentence",
  "parameters": {
    "type": "object",
    "properties": {
      "sense_id": { "type": "integer", "minimum": 0, "maximum": 63 }
    },
    "required": ["sense_id"]
  }
}]
```

Do **not** ask Needle to generate `translation`. M1 may skip `extract_headword` and pass the selection string through `LemmaMap` (already tested). Add `extract_headword` only if device tests show bad tokenization of hyphenated/possessive selections.

**Step 4: Run tests and make sure they pass**

Run: `.\gradlew.bat test --tests com.jarvis.ir.explain.ExplainPipelineTest`

Expected: PASS

---

### Task 6: Vendor Needle + ECDICT onto the machine (not into git)

**Files:**

- Create: `mobile/ir-android/scripts/fetch-assets.md` (commands only; no secrets)

**Step 1: Download Needle android-arm64**

On the Windows PC (network once):

```
pip install cactus-needle
set NEEDLE_TELEMETRY=0
set DO_NOT_TRACK=1
needle download needle3 --out c:\jarvis\mobile\ir-android\app\src\main\assets
needle download android-arm64 --out c:\jarvis\tmp\_needle_android_arm64
```

Copy from the platform folder:

- `needle.h` → `app/src/main/cpp/needle.h`
- `libneedle.a` → `app/src/main/jniLibs/arm64-v8a/libneedle.a` **and** keep a CMake IMPORTED path
- `needle3.cact` → `app/src/main/assets/needle3.cact`

If `needle download` layout differs, follow the printed folder; do not invent extra files.

**Step 2: Download ECDICT sqlite + lemma**

From https://github.com/skywind3000/ECDICT — use the published sqlite (`ecdict.db` / stardict sqlite) and `lemma.en.txt`.

Place:

- `app/src/main/assets/ecdict.db`
- `app/src/main/assets/lemma.en.txt`

**Step 3: Verify files exist and are gitignored**

```
git check-ignore -v mobile/ir-android/app/src/main/assets/needle3.cact
git check-ignore -v mobile/ir-android/app/src/main/jniLibs/arm64-v8a/libneedle.a
```

Expected: both ignored.

**Step 4: Confirm sizes**

- `needle3.cact` about 8–29 MB
- `libneedle.a` under ~1–2 MB
- `ecdict.db` tens of MB (expected; APK sideload is fine)

---

### Task 7: JNI wrapper matching the shipped `needle.h`

Do **not** guess prototypes. Open the downloaded `needle.h` and bind those symbols.

From public docs the surface is: `needle_init`, `needle_complete`, `needle_embed`, `needle_last_error`. After a negative return, call `needle_last_error()`. Init returns prefix token length on success. Process-global model — one instance.

**Files:**

- Create: `mobile/ir-android/app/src/main/cpp/CMakeLists.txt`
- Create: `mobile/ir-android/app/src/main/cpp/needle_jni.cpp`
- Create: `mobile/ir-android/app/src/main/java/com/jarvis/ir/needle/NativeNeedle.kt`
- Create: `mobile/ir-android/app/src/androidTest/java/com/jarvis/ir/needle/NativeNeedleInstrumentedTest.kt`

**Step 1: CMake**

```cmake
cmake_minimum_required(VERSION 3.22.1)
project(needle_jni)
add_library(needle STATIC IMPORTED)
set_target_properties(needle PROPERTIES IMPORTED_LOCATION
        ${CMAKE_SOURCE_DIR}/../jniLibs/${ANDROID_ABI}/libneedle.a)
add_library(needle_jni SHARED needle_jni.cpp)
target_include_directories(needle_jni PRIVATE ${CMAKE_SOURCE_DIR})
target_link_libraries(needle_jni needle android log)
```

Copy assets to internal storage on first run (Needle needs a real filesystem path, not an `assets://` URI).

**Step 2: Instrumented test (device required)**

```kotlin
package com.jarvis.ir.needle

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class NativeNeedleInstrumentedTest {
    @Test
    fun initAndSelectSenseOnBank() {
        val ctx = InstrumentationRegistry.getInstrumentation().targetContext
        val needle = NativeNeedle.load(ctx) // copies assets, needle_init
        val turn = needle.complete(
            """
            sentence: They sat on the river bank.
            word: bank
            0. n 岸
            1. n 银行
            Pick sense_id for this sentence.
            """.trimIndent(),
        )
        assertTrue(turn.functionCalls.isNotEmpty() || turn.raw.contains("sense_id"))
        needle.close()
    }
}
```

**Step 3: Run test to verify it fails**

Run: Studio → `NativeNeedleInstrumentedTest` on the USB phone.

Expected: FAIL — `NativeNeedle` unresolved or `.so` missing.

**Step 4: Implement JNI + Kotlin**

- Setenv `NEEDLE_TELEMETRY=0` and `DO_NOT_TRACK=1` before init.
- `tools.json` = the `select_sense` schema from Task 5.
- Parse `needle_complete` JSON into `NeedleTurn` (`function_calls`, `confidence`).
- Log `Log.i("NeedleIR", ...)` with headword/sense_id/confidence.

**Step 5: Re-run instrumented test on the phone**

Expected: PASS. If `sense_id` is wrong (picks 银行 for river bank), do **not** fine-tune in M1; record the miss in Logcat and still show the card as 不确定 when confidence is low. Fine-tune is out of this plan.

---

### Task 8: M1 reader UI (bundled passage, selection card)

**Files:**

- Create: `mobile/ir-android/app/src/main/assets/sample.txt` (short public-domain paragraph containing `bank` as river bank)
- Create: `mobile/ir-android/app/src/main/java/com/jarvis/ir/ui/ReaderScreen.kt`
- Create: `mobile/ir-android/app/src/main/java/com/jarvis/ir/ui/ExplainCardView.kt`
- Create: `mobile/ir-android/app/src/androidTest/java/com/jarvis/ir/ui/ReaderScreenTest.kt`

**Step 1: Write a Compose UI test that fails**

- Launch reader
- Long-press / select the word `bank`
- Assert a card appears with non-empty translation text **or** `未收录` / `不确定` states are distinct

Until JNI is wired, inject `ExplainPipeline` with the Fake Needle from Task 5 in debug builds; production uses `NativeNeedle`.

**Step 2: Run test to verify it fails**

Expected: FAIL — no `ReaderScreen`.

**Step 3: Minimal UI**

- Serif body text, tap-to-select a single word (v1: whitespace-delimited; punctuation stripped)
- Card fields: word, pos, zh gloss, example = the sentence containing the selection
- `NOT_IN_DICT` → 「未收录」
- `REFUSED` → 「这次没法确定」
- `uncertain` → badge 「不确定」
- No tabs, no TTS, no notes

**Step 4: Run on phone**

Manual: select `bank` in the sample, confirm card + Logcat `NeedleIR`.

---

### Task 9: Wire production DictionaryRepository to `ecdict.db`

**Files:**

- Create: `mobile/ir-android/app/src/main/java/com/jarvis/ir/dict/SqliteDict.kt`
- Modify: app `Application` / first-run copy from assets

**Step 1: JVM test against a **tiny** sqlite fixture** (3 rows, same schema as ECDICT `stardict`) copied into `src/test/resources/ecdict-fixture.db`.

Query:

```sql
SELECT word, pos, translation FROM stardict WHERE word = ? COLLATE NOCASE LIMIT 1;
```

**Step 2: Fail, then implement `SqliteDict.lookupExact`.

**Step 3: On device, first launch copies `ecdict.db` + `lemma.en.txt` + `needle3.cact` to `context.filesDir` if missing.

**Step 4: Phone smoke:** unknown word `xyzzy` → 未收录; `running` → stem `run` if ECDICT has `run`.

---

### Task 10: M2 EPUB + TXT import

Do this only after M1 device smoke is green.

**Files:**

- Create: `mobile/ir-android/app/src/main/java/com/jarvis/ir/books/Chunker.kt`
- Create: `mobile/ir-android/app/src/test/java/com/jarvis/ir/books/ChunkerTest.kt`
- Create: `mobile/ir-android/app/src/main/java/com/jarvis/ir/books/EpubImporter.kt`
- Create: `mobile/ir-android/app/src/main/java/com/jarvis/ir/books/BookStore.kt`

**Chunker contract (TDD first):**

- Split on blank lines into paragraphs
- Pack paragraphs until `wordCount >= 1200`, then new chunk
- Never split inside a paragraph
- Empty input → empty list

EPUB: unzip, read spine HTML in order, strip tags to text (Jsoup). SAF document picker. Failures mark the book `error`; other books stay readable.

TXT: UTF-8, same chunker.

No Jarvis novel-TOC port.

---

### Task 11: M3 PDF import

After M2.

**Files:**

- Create: `mobile/ir-android/app/src/main/java/com/jarvis/ir/books/PdfImporter.kt`
- Test: a 1-page fixture PDF in `src/test/resources` whose extracted text contains a known sentence

Use pdfbox-android **or** MuPDF — pick one in implementation; do not use `PdfRenderer` (bitmaps, no text).

Do not port magazine outline heuristics. If extraction is garbage, surface `error` and stop.

---

## Verification Summary

M1 is done when all of the following are true:

- `.\gradlew.bat test` unit tests PASS on Windows
- USB ARM64 phone runs the app
- Sample passage: select `bank` → card with ECDICT gloss + original sentence
- Unknown word → 「未收录」
- Logcat `NeedleIR` shows `sense_id` / `confidence` for multi-sense words
- x86 emulator cannot install the APK (`arm64-v8a` only)
- `needle3.cact`, `libneedle.a`, `ecdict.db` are gitignored

M2/M3 are later; do not start them until M1 verification is green.

---

## Notes for the implementer

- Copy C prototypes from the real `needle.h`. Public blogs name `needle_init` / `needle_complete` / `needle_embed` / `needle_last_error` but the header is the contract.
- Needle generates no free text. Empty `function_calls` is a refusal.
- Do not call Ollama or Jarvis `/api/intensive-reading/*`.
- Fine-tuning Needle is explicitly out of this plan.
- Temp downloads go under `c:\jarvis\tmp\` (project temp-file rule), then copy into the android module paths above.

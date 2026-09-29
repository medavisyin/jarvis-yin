# Memory: iOS Intensive-Reading App Prep

**Generated**: 2026-09-29 ~17:50 UTC+8
**Last updated**: 2026-09-29 ~18:20 UTC+8
**Project**: c:\jarvis
**Focus**: Prepare an iOS Xcode project on Windows that matches the Android IR app, for the user to copy to a Mac and open in Xcode

---

## Goal & Scope (required)

User has a Mac and will install Xcode. Prepare the iOS project on this Windows machine so they can copy the folder to the Mac, open the `.xcodeproj`, select their Team, and Run onto their iPhone and iPad.

Feature target matches `mobile/ir-android`: import English TXT / EPUB / PDF, shelf and paging, tap a word for an ECDICT card. Qwen3 stays an interface in this round; the on-device engine is connected later on the Mac. Offline. No Jarvis server. Android project stays unchanged.

---

## Key Decisions (required)

1. **Start fresh**: User declined loading `memory-20260929-mimo-api.md`, `memory-20260929-cn-llm-api-prices.md`, and `memory-20260929-monitor-constructive-label.md`.
2. **Write this memory file**: User confirmed a new file for the iOS prep checklist.
3. **iOS is a separate project**: Do not retarget the Android Studio project. APK cannot be installed on iPhone or iPad. Kotlin UI and `libcactus.so` (JNI, `cactus_complete`) stay on Android.
4. **User has a Mac**: They will download Xcode and copy the prepared folder onto that Mac. Rejected for this session: cloud Mac + TestFlight as the only path.
5. **First deliverable is a full reading project, Qwen stubbed**: User chose scope C. Include TXT/EPUB/PDF import, ECDICT lookup, and the explain card. Leave a Qwen call interface; do not vendor an iOS inference library in this round. Rejected: empty SwiftUI shell; rejected: TXT-only shelf.
6. **Project directory is a sibling of `mobile`**: User corrected the path. The Xcode project lives at `ir-ios/` (repo root of a future GitHub upload), not `mobile/ir-ios`. User said to generate it without further questions.
7. **Approach used**: One SwiftUI app, no Swift packages. EPUB unzip via zlib raw inflate. PDFKit for PDF. System SQLite for ECDICT. `QwenEngine` is unimplemented; the card says the runtime is not connected. Economist / GLM / Mimo from later Android work stay out.

---

## Confirmed Assumptions (required)

- User has an Apple Developer account (treated as the paid program: device install for the membership year, TestFlight, about 100 device slots).
- User has an iPhone and an iPad to use as dev devices.
- The development machine in this session is Windows. Xcode runs on macOS only. The user also has a Mac for the later open/build/install step.
- Feature target is the current Android IR app, not a new product scope.
- User confirmed scope C, then corrected the folder to sit beside `mobile`, and asked to generate without more questions.

---

## Constraints & Non-Goals

- Windows cannot sign or produce an installable iOS build.
- `libcactus.so`, Kotlin, and JNI do not move to iOS.
- Dictionary files `ecdict.db` and `lemma.en.txt` are gitignored; copy them from the Android tree.
- Qwen weights stay out of the app binary; download into the app's private files, same as Android (`qwen3-0.6` ~575MB, `qwen3-1.7` ~810MB).
- This round does not choose or vendor MLX vs llama.cpp. The Qwen engine is an interface only.
- Do not change the Android app.

---

## Key Discoveries (required)

- Android app name on device is `Y`, package `com.jarvis.ir`. Guide index: `mobile/ir-guide/首页.md`. iOS checklist already drafted in `mobile/ir-guide/15-iOS以后要什么.md`.
- Behavior to port: long-press word, drag to a span, double-tap clears; buttons 词 / 句 / 读; shelf; settings download of Qwen. ECDICT is the glossary; Qwen writes the Chinese line only. Prompts, temperature 0, and token caps are in `mobile/ir-guide/17-Qwen怎么用.md`.
- iOS replacements: SwiftUI reader; SQLite for the same `ecdict.db`; an iOS Qwen runtime (MLX or llama.cpp compiled in) instead of cactus; PDFKit; a third-party EPUB reader; `fileImporter` for import; `AVSpeechSynthesizer` for 读.
- Install path: Mac + Xcode, Automatically manage signing, Team = developer account, Bundle ID `com.jarvis.ir`. Enable Developer Mode on each device (Settings → Privacy & Security). USB trust once, Run from Xcode; trust the developer cert under Settings → General → VPN & Device Management if asked. Same project Run onto the iPad. After the first cable pair, Xcode can use Connect via network.
- Paid account also allows Archive → App Store Connect → TestFlight internal testing, so later installs do not need the cable. A cloud Mac can upload that build; USB install still needs the device plugged into the Mac that signs it.
- UI can be tried on the iOS Simulator. Qwen and tap-to-gloss should be verified on a real device.

---

## Open Risks

- This Windows machine cannot run `xcodebuild`. The project has not been compiled. The first Mac open is the real compile check.
- On-device Qwen engine for iOS is not chosen (MLX vs llama.cpp). `GlossSession` takes a `QwenEngine`.
- EPUB text is extracted with a small ZIP reader plus tag stripping, not a full EPUB renderer.

---

## Current State (required)

- **Working**: Android IR app. iOS sources are written at `ir-ios/` for copy to the Mac. Not compiled here.
- **Pending**: User installs Xcode, opens `ir-ios/ir-ios.xcodeproj`, selects the Team, copies `ecdict.db` and `lemma.en.txt` into `ir-ios/ir-ios/`, and Runs. Cmd+U runs `ir-iosTests`.
- **Blocked**: No iOS toolchain on the current Windows machine.

---

## Next Steps (required)

1. [ ] On the Mac: open `ir-ios/ir-ios.xcodeproj`, set the Team, Run on iPhone and iPad.
2. [ ] Copy `ecdict.db` and `lemma.en.txt` into `ir-ios/ir-ios/` before that Run if the card should show ECDICT.
3. [ ] Cmd+U. If the first build fails, fix from the Xcode error.
4. [ ] Later: implement `QwenEngine` (MLX or llama.cpp) and pass it to `GlossSession`.

---

## Notes for Next Session

Open `ir-ios/ir-ios.xcodeproj`, not the Jarvis root. Display name Y, bundle id `com.jarvis.ir`, deployment target iOS 17, Xcode 16 project format. Dictionary files are gitignored. Qwen buttons currently show that the runtime is not connected.

---

## References (required)

- `ir-ios/README.md` — how to open the Xcode project on the Mac
- `ir-ios/ir-ios.xcodeproj` — project to double-click
- `ir-ios/ir-ios/ReadingLogic.swift` — chunking, dictionary, gloss prompts, `QwenEngine`
- `mobile/ir-android/` — Android project (Android Studio opens this folder)
- `mobile/ir-guide/15-iOS以后要什么.md` — existing iOS resource list
- `mobile/ir-guide/01-这是什么.md` — what the app does
- `mobile/ir-guide/17-Qwen怎么用.md` — gloss prompts, cactus, model sizes
- `mobile/ir-guide/04-项目结构.md` — Kotlin modules and gitignored assets

---

**Confirmed at**: 2026-09-29 ~17:50 UTC+8

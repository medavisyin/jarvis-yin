# Local assets (not committed)

The app source does not include the dictionary, the lemma list, or the Qwen engine. Copy them in on the machine that builds the APK.

| File | Put it at | Notes |
|---|---|---|
| `ecdict.db` | `app/src/main/assets/ecdict.db` | ECDICT sqlite, table `stardict` with `word`, `pos`, `translation` |
| `lemma.en.txt` | `app/src/main/assets/lemma.en.txt` | From [skywind3000/ECDICT](https://github.com/skywind3000/ECDICT) |
| `libcactus.so` | `app/src/main/jniLibs/arm64-v8a/libcactus.so` | On-device Qwen runtime. arm64 only |

Qwen weights are not in the APK. The app downloads `qwen3-0.6` or `qwen3-1.7` into the phone's private `files/models/` directory the first time you tap download in Settings.

These paths are gitignored:

```bat
git check-ignore -v mobile/ir-android/app/src/main/assets/ecdict.db
git check-ignore -v mobile/ir-android/app/src/main/assets/lemma.en.txt
git check-ignore -v mobile/ir-android/app/src/main/jniLibs/arm64-v8a/libcactus.so
```

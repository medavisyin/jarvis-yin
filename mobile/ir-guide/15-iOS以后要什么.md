---
tags:
  - ir-guide
---

# iOS 以后要什么

← [[首页]] · Android 真机 [[09-如何测试-华为真机]]

## 现在：苹果手机用不了

当前工程是 Android APK。iPhone 装不上，Windows 上也没有 iOS 模拟器。Android Studio 的 Device 列表和 iPhone 无关。

同样的精读功能可以以后再做，但是 **另一个工程**，不是在 Android Studio 里换一台 Device。

## 资源清单

| 类别 | 要什么 |
|---|---|
| 电脑 | **一台 Mac**（最好 Apple Silicon）。这台 Windows 编不了 iOS。 |
| 软件 | Xcode（Mac App Store） |
| 账号 | Apple ID。只装自己手机可免费（证书约 7 天重签）。长期 / TestFlight 再买 Developer（$99/年） |
| 手机 | iPhone XS / XR 及更新（A12+，iOS 14+） |
| 模型 | 一份能在 iPhone 上跑的 Qwen 运行时，加上设置里下载的权重 |
| 词典 | 同一份 `ecdict.db` + `lemma.en.txt` |

## 必须新写的

- SwiftUI 阅读界面
- C 头文件的 Swift 桥（代替 JNI）
- PDF：系统 PDFKit
- EPUB：系统没有阅读器，要接第三方
- 文件导入：`UIDocumentPicker`

Kotlin 代码不能直接搬进 iOS。词典卡片和 Qwen 那一句中文可以按 [[05-选词如何工作]]、[[17-Qwen怎么用]] 重写一遍。

## 现阶段建议

先把华为真机上的 Android 路径跑通（[[09-如何测试-华为真机]]），再考虑买不买 Mac。没有 Mac，iOS 只能停在这篇的资源清单。

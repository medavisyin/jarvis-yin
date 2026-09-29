# Y（iOS 精读）

和 `mobile/ir-android` 对齐的 iPhone / iPad 阅读应用。桌面名称是 **Y**，Bundle ID 是 `com.jarvis.ir`。

这个文件夹和 `mobile` 同级，可以单独当作一个 Git 仓库上传。词典和模型权重已在 `.gitignore` 里，不会被提交。

## 在 Mac 上打开

1. 把整个 `ir-ios` 文件夹拷到 Mac。
2. 安装 Xcode 16 或更新版本（系统最低 iOS 17）。
3. 双击 `ir-ios.xcodeproj`。不要打开上一级的 Jarvis 仓库。
4. 左侧选中工程 `ir-ios`，目标 `ir-ios` → Signing & Capabilities → Team 选你的 Apple Developer 团队。Automatically manage signing 保持打开。
5. iPhone 和 iPad 打开「设置 → 隐私与安全性 → 开发者模式」，用数据线连上 Mac 并信任电脑。
6. Xcode 顶部运行目标选这台设备，按 Run。iPad 再选一次再 Run。
7. 菜单 Product → Test（或 Cmd+U）跑单元测试。

这台 Windows 上没有 Xcode，工程是按 Xcode 16 的工程格式写的。第一次能不能编过，以 Mac 上的编译结果为准。

## 词典

点词卡片用的是同一份 ECDICT。把这两个文件放进 `ir-ios/ir-ios/`（和 Swift 源码同一层），再 Run：

- `ecdict.db`
- `lemma.en.txt`

Android 工程里如果已经有，路径是 `mobile/ir-android/app/src/main/assets/`。App 第一次启动会把它们拷进自己的目录。没有这两份文件时，书架和阅读仍然可用，卡片上会说明词典还没放进来。

## 现在能做什么

- 导入 TXT、EPUB、PDF，书架，左右滑翻页，章节列表，删除一本书
- 点词、再点另一个词拉成一片，双击正文取消
- ECDICT 词条；「读」用系统英文语音
- 「词」「句」走和 Android 相同的提示词接口

Qwen 的运行时还没接。点「词」或「句」会显示「Qwen 还没接到这台手机上」。词典不依赖模型。Android 里的经济学人下载、GLM / Mimo 分析不在这个工程里。

以后在 Mac 上把一个实现 `QwenEngine` 的类型交给 `GlossSession` 即可。接口在 `ir-ios/ReadingLogic.swift`。

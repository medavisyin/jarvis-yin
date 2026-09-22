---
tags:
  - ir-guide
---

# 如何 Build

← [[首页]] · 打开工程 [[06-第一次打开工程]]

「Build」= 把 Kotlin + C++ + 资源打成一个 APK。不需要手机也能 Build；**装到手机才需要 USB**。

## 方法 A：Android Studio（新手用这个）

1. 顶部配置选 **app**（不要选某个单独的 Test）。
2. 菜单 **Build → Make Project**（Ctrl+F9），或 **Build → Build Bundle(s) / APK(s) → Build APK(s)**。
3. 成功后：`app/build/outputs/apk/debug/app-debug.apk`（大约 45MB）。

绿色 **Run** 按钮 = Build + 安装到当前选中的设备。设备选错（模拟器）就会在安装或启动时失败。

## 方法 B：命令行（和教材验证时用的一样）

PowerShell：

```bat
cd c:\jarvis\mobile\ir-android
.\gradlew.bat :app:assembleDebug
```

成功结尾是 `BUILD SUCCESSFUL`。APK 路径同上。

只编不跑测试；测试命令见 [[08-如何测试-电脑单测]]。

## 编译过了还要在手机上看

`assembleDebug` 成功只说明 Windows 能打出 APK。Qwen 是否能写中文，要真机，并且 `libcactus.so` 和词典都在本机。见 [[09-如何测试-华为真机]]、[[12-资源文件从哪来]]。

## 常见警告（可以暂时忽略）

`We recommend using a newer Android Gradle plugin to use compileSdk = 36`

工程用 AGP 8.8.2 + compileSdk 36，会有这条警告。**不是失败**。

Studio Gradle JDK 设成 21 也正常。`app/build.gradle.kts` 里仍是 `jvmTarget = "17"`，Build 时不必改。

下一篇：[[08-如何测试-电脑单测]]

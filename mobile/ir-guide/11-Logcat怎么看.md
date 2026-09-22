---
tags:
  - ir-guide
---

# Logcat 怎么看

← [[首页]] · 真机步骤 [[09-如何测试-华为真机]]

Logcat 是手机打出来的流水账。本 App 用标签 **`Y`**。

## 在 Studio 里打开

1. 底部标签 **Logcat**（没有就 View → Tool Windows → Logcat）
2. 设备选你的华为（不要选已经关掉的模拟器）
3. 进程下拉选 `com.jarvis.ir`
4. 过滤框输入 `Y` 或 `tag:Y`

## 导入失败

```text
Y  import failed
```

文件损坏、不是真的 EPUB/PDF、或抽出来是空的。换一个简单 TXT 先试。

## 模拟器

x86 模拟器对不上 arm64 的 `libcactus.so`。关掉模拟器，换真机。见 [[10-为什么模拟器不行]]。

## 模型打不开

卡片上的中文是「模型打不开。文件还在，不用重新下载。」时，看同一段里的异常。常见原因是 `libcactus.so` 不在 `jniLibs/arm64-v8a/`，或设置里的权重没下完。见 [[12-资源文件从哪来]]、[[17-Qwen怎么用]]。

## 命令行（Studio 滤不到时）

```bat
"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe" logcat -s Y:E AndroidRuntime:E
```

Ctrl+C 停止。

下一篇：[[12-资源文件从哪来]]

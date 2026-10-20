import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  BROWSER_CHUNK_CHARS,
  chunkIndexAt,
  chunkStarts,
  passageChunks,
  passageLang,
  pickBrowserVoice,
  playChunked,
  speakChoiceFromSettings,
  speakRequestBody,
  waitForVoices,
} from "./passageSpeak";

describe("passageLang", () => {
  it("uses Chinese when Han characters outnumber Latin letters", () => {
    expect(passageLang("这是一段很长的中文 only")).toBe("zh");
  });

  it("uses English when Latin letters are equal or greater", () => {
    expect(passageLang("Hello world")).toBe("en");
    expect(passageLang("中A")).toBe("en");
  });
});

describe("passageChunks", () => {
  it("keeps short paragraphs whole", () => {
    expect(passageChunks("First paragraph.\n\nSecond paragraph.")).toEqual([
      "First paragraph.",
      "Second paragraph.",
    ]);
  });

  it("packs sentences until the next one would pass 500 characters", () => {
    const first = `${"a".repeat(300)}.`;
    const second = `${"b".repeat(300)}.`;
    const chunks = passageChunks(`${first} ${second}`, 500);
    expect(chunks).toEqual([first, second]);
    expect(chunks.every((part) => part.length <= 500)).toBe(true);
  });

  it("splits a Chinese sentence that has no space after the period", () => {
    const first = `${"中".repeat(300)}。`;
    const second = `${"文".repeat(300)}。`;
    expect(passageChunks(`${first}${second}`, 500)).toEqual([first, second]);
  });

  it("does not insert a space when packing Chinese sentences", () => {
    const first = `${"句".repeat(200)}。`;
    const second = `${"文".repeat(200)}。`;
    const third = `${"字".repeat(200)}。`;
    const chunks = passageChunks(`${first}${second}${third}`, 500);
    expect(chunks[0]).toBe(`${first}${second}`);
  });

  it("hard-splits a sentence that is still over the limit", () => {
    const chunks = passageChunks("x".repeat(501), 500);
    expect(chunks).toEqual(["x".repeat(500), "x"]);
  });

  it("returns nothing for blank text", () => {
    expect(passageChunks("  \n\n  ")).toEqual([]);
  });

  it("resumes from the segment that contains the saved offset", () => {
    const starts = [0, 20, 48];
    expect(chunkIndexAt(starts, 0)).toBe(0);
    expect(chunkIndexAt(starts, 20)).toBe(1);
    expect(chunkIndexAt(starts, 33)).toBe(1);
    expect(chunkIndexAt(starts, 48)).toBe(2);
  });

  it("records where each spoken piece starts", () => {
    const text = "Alpha.\n\nBeta stays here.";
    const chunks = passageChunks(text, 500);
    expect(chunkStarts(text, chunks)).toEqual([text.indexOf("Alpha."), text.indexOf("Beta")]);
  });

  it("keeps each browser utterance short enough to finish", () => {
    const chunks = passageChunks(`${"word ".repeat(80)}`, BROWSER_CHUNK_CHARS);
    expect(chunks.length).toBeGreaterThan(1);
    expect(chunks.every((part) => part.length <= BROWSER_CHUNK_CHARS)).toBe(true);
  });
});

describe("pickBrowserVoice", () => {
  const voices = [
    { name: "Microsoft Xiaoxiao", lang: "zh-CN" },
    { name: "Microsoft Yunjian", lang: "zh-CN" },
    { name: "Jenny", lang: "en-US" },
    { name: "Andrew male", lang: "en-US" },
  ];

  it("prefers a voice whose name matches the gender", () => {
    expect(pickBrowserVoice(voices, "en", "male")?.name).toBe("Andrew male");
  });

  it("uses the first voice of that language when gender does not match", () => {
    expect(pickBrowserVoice(voices, "zh", "female")?.name).toBe("Microsoft Xiaoxiao");
  });

  it("returns null when the language is missing", () => {
    expect(pickBrowserVoice([{ name: "Jenny", lang: "en-US" }], "zh", "female")).toBeNull();
  });

  it("does not treat a female voice as male", () => {
    expect(pickBrowserVoice([{ name: "Female EN", lang: "en-US" }], "en", "male")?.name).toBe("Female EN");
  });

  it("prefers a local voice over Chrome's silent online voice", () => {
    const voices = [
      { name: "Google UK English Female", lang: "en-GB", localService: false },
      { name: "Google UK English Male", lang: "en-GB", localService: false },
      { name: "Microsoft Zira - English (United States)", lang: "en-US", localService: true },
      { name: "Microsoft David - English (United States)", lang: "en-US", localService: true },
    ];
    expect(pickBrowserVoice(voices, "en", "female")?.name).toBe("Microsoft Zira - English (United States)");
    expect(pickBrowserVoice(voices, "en", "male")?.name).toBe("Microsoft David - English (United States)");
  });

  it("does not treat Mandarin or woman as the male voice", () => {
    expect(
      pickBrowserVoice(
        [
          { name: "Microsoft Mandarin", lang: "zh-CN" },
          { name: "Yunjian male", lang: "zh-CN" },
        ],
        "zh",
        "male",
      )?.name,
    ).toBe("Yunjian male");
    expect(
      pickBrowserVoice(
        [
          { name: "Zira woman", lang: "en-US" },
          { name: "David male", lang: "en-US" },
        ],
        "en",
        "male",
      )?.name,
    ).toBe("David male");
  });
});

describe("speakRequestBody", () => {
  it("asks for the chosen engine, language, and gender without leading silence", () => {
    expect(
      speakRequestBody({
        text: "Hello.",
        engine: "edge",
        lang: "en",
        gender: "male",
      }),
    ).toEqual({
      text: "Hello.",
      engine: "edge",
      lang: "en",
      gender: "male",
      pad: false,
      rate: "slow",
    });
  });

  it("includes style only for MiMo", () => {
    expect(
      speakRequestBody({
        text: "Hello.",
        engine: "mimo",
        lang: "en",
        gender: "female",
        style: "平静",
      }).style,
    ).toBe("平静");
    expect(
      speakRequestBody({
        text: "Hello.",
        engine: "edge",
        lang: "en",
        gender: "female",
        style: "平静",
      }).style,
    ).toBeUndefined();
  });
});

describe("playChunked", () => {
  it("starts the next fetch while the current chunk is still playing", async () => {
    let secondStarted = false;
    await playChunked(
      ["one", "two"],
      async (text) => {
        if (text === "two") secondStarted = true;
        return new Blob([text]);
      },
      async (blob) => {
        const text = await blob.text();
        if (text === "one") expect(secondStarted).toBe(true);
      },
      new AbortController().signal,
    );
  });

  it("stops after the current chunk when aborted", async () => {
    const ac = new AbortController();
    const played: string[] = [];
    await playChunked(
      ["one", "two"],
      async (text) => new Blob([text]),
      async (blob) => {
        played.push(await blob.text());
        ac.abort();
      },
      ac.signal,
    );
    expect(played).toEqual(["one"]);
  });

  it("does not leave the prefetched request unhandled when playback stops", async () => {
    const ac = new AbortController();
    const unhandled: unknown[] = [];
    const onUnhandled = (reason: unknown) => {
      unhandled.push(reason);
    };
    process.on("unhandledRejection", onUnhandled);
    try {
      await playChunked(
        ["one", "two"],
        (text, signal) => {
          if (text === "one") return Promise.resolve(new Blob(["one"]));
          return new Promise((_resolve, reject) => {
            signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
          });
        },
        async () => {
          ac.abort();
          await new Promise((resolve) => setTimeout(resolve, 0));
        },
        ac.signal,
      );
      await new Promise((resolve) => setTimeout(resolve, 0));
      expect(unhandled).toEqual([]);
    } finally {
      process.off("unhandledRejection", onUnhandled);
    }
  });
});

describe("waitForVoices", () => {
  it("returns voices that are already loaded", async () => {
    const voices = [{ name: "Jenny", lang: "en-US" }];
    await expect(
      waitForVoices({
        getVoices: () => voices,
        addEventListener() {},
        removeEventListener() {},
      }),
    ).resolves.toEqual(voices);
  });

  it("uses the list from voiceschanged when the first read is empty", async () => {
    let handler = () => undefined;
    const synth = {
      voices: [] as { name: string; lang: string }[],
      getVoices() {
        return this.voices;
      },
      addEventListener(_name: string, fn: () => void) {
        handler = fn;
      },
      removeEventListener() {},
    };
    const pending = waitForVoices(synth, 1000);
    synth.voices = [{ name: "Yunjian", lang: "zh-CN" }];
    handler();
    await expect(pending).resolves.toEqual([{ name: "Yunjian", lang: "zh-CN" }]);
  });
});

describe("speakChoiceFromSettings", () => {
  it("keeps a choice the user already made", () => {
    expect(
      speakChoiceFromSettings(
        { audio_engine: "mimo", audio_voice_en: "male", audio_voice_zh: "female", audio_mimo_style: "磁性" },
        true,
      ),
    ).toBeNull();
  });

  it("still applies saved settings when playback was only stopped", () => {
    expect(
      speakChoiceFromSettings(
        { audio_engine: "mimo", audio_voice_en: "male", audio_voice_zh: "female", audio_mimo_style: "磁性" },
        false,
      ),
    ).toMatchObject({ engine: "mimo", voiceEn: "male", voiceZh: "female", style: "磁性" });
  });
});

describe("ReadingPage speak defaults", () => {
  const page = readFileSync(
    resolve(dirname(fileURLToPath(import.meta.url)), "../../pages/ReadingPage.tsx"),
    "utf8",
  );

  it("does not treat a stop as a saved-settings block", () => {
    const start = page.indexOf("speakChoiceFromSettings(");
    const call = page.slice(start, page.indexOf(");", start));
    expect(call).toBe("speakChoiceFromSettings(s, speakTouched.current");
    expect(call).not.toContain("readGen");
  });

  it("does not mark a voice choice before an empty page returns", () => {
    const fn = page.slice(page.indexOf("async function toggleRead"));
    const mark = fn.indexOf("speakTouched.current = true");
    const emptyReturn = fn.indexOf("if (!text.trim()) return");
    expect(emptyReturn).toBeGreaterThan(-1);
    expect(mark).toBeGreaterThan(emptyReturn);
  });

  it("starts browser speech in the click turn", () => {
    const fn = page.slice(page.indexOf("async function toggleRead"));
    const browser = fn.slice(fn.indexOf('speakEngine === "browser"'), fn.indexOf("const chunks = passageChunks"));
    const speakAt = browser.indexOf("synth.speak(");
    expect(speakAt).toBeGreaterThan(-1);
    expect(browser.indexOf("await ")).toBe(-1);
    expect(browser).toContain("passageChunks(text, BROWSER_CHUNK_CHARS)");
  });
});

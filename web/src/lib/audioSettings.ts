export const AUDIO_LANGS = ["zh", "en"] as const;
export const AUDIO_VOICES = ["female", "male"] as const;
export const AUDIO_ENGINES = ["edge", "mimo"] as const;
export const AUDIO_ENGINE_LABELS: Record<(typeof AUDIO_ENGINES)[number], string> = {
  edge: "Edge",
  mimo: "MiMo-V2.5-TTS",
};
export const MIMO_STYLES = [
  "开心", "悲伤", "愤怒", "恐惧", "惊讶", "兴奋", "委屈", "平静", "冷漠",
  "怅然", "欣慰", "无奈", "愧疚", "释然", "嫉妒", "厌倦", "忐忑", "动情",
  "温柔", "高冷", "活泼", "严肃", "慵懒", "俏皮", "深沉", "干练", "凌厉",
  "磁性", "醇厚", "清亮", "空灵", "稚嫩", "苍老", "甜美", "沙哑", "醇雅",
  "夹子音", "御姐音", "正太音", "大叔音", "台湾腔",
  "东北话", "四川话", "河南话", "粤语",
  "孙悟空", "林黛玉",
  "唱歌",
] as const;

export type AudioVoice = (typeof AUDIO_VOICES)[number];
export type AudioEngine = (typeof AUDIO_ENGINES)[number];

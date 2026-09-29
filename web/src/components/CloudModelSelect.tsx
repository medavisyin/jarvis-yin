export type CloudModel = "local" | "deepseek" | "glm" | "mimo";

export function cloudBody(model: CloudModel): { use_deepseek: boolean; llm: CloudModel } {
  return { use_deepseek: model !== "local", llm: model };
}

export function CloudModelSelect({
  value,
  onChange,
  disabled,
}: {
  value: CloudModel;
  onChange: (next: CloudModel) => void;
  disabled?: boolean;
}) {
  return (
    <label className="flex items-center gap-2 text-sm">
      模型
      <select
        className="border-input bg-background h-7 rounded-md border px-2 text-sm"
        value={value}
        disabled={disabled}
        onChange={(e) => {
          const next = e.target.value;
          onChange(next === "deepseek" || next === "glm" || next === "mimo" ? next : "local");
        }}
      >
        <option value="local">本地</option>
        <option value="deepseek">DeepSeek</option>
        <option value="glm">GLM</option>
        <option value="mimo">MiMo</option>
      </select>
    </label>
  );
}

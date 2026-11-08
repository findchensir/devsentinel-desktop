import type { Usage } from '../type';

// token 用量胶囊行：三个模式共用，抽成小组件避免重复
const UsageChips: React.FC<{ usage: Usage }> = ({ usage }) => {
  const items = [
    ['输入', usage.prompt_tokens],
    ['输出', usage.completion_tokens],
    ['合计', usage.total_tokens],
  ] as const;
  return (
    <div className="flex flex-wrap gap-2">
      {items.map(([label, n]) => (
        <span key={label} className="bg-slate-800/80 border border-slate-700/60 text-slate-400 rounded-md px-2 py-0.5 text-[11px] font-mono">
          {label} {n}
        </span>
      ))}
    </div>
  );
};

export default UsageChips;

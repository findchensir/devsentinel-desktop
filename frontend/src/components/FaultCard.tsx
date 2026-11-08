import type { FaultInfo, Usage } from '../type';
import UsageChips from './UsageChips';

const SEVERITY_COLOR = {
  low: 'bg-slate-600',
  medium: 'bg-yellow-600',
  high: 'bg-orange-600',
  critical: 'bg-red-600',
} as const;

// 故障要素卡片：severity 染色徽章 + 字段网格 + 关键词标签
export default function FaultCard({ data, usage }: { data: FaultInfo; usage: Usage | null }) {
  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-xl overflow-hidden text-sm">
      <div className="flex items-center justify-between px-5 py-3 border-b border-slate-800 bg-slate-900">
        <span className="text-amber-400 text-xs font-semibold tracking-wide">故障要素</span>
        <span className={`px-2.5 py-0.5 rounded-md text-xs font-medium text-white ${SEVERITY_COLOR[data.severity]}`}>
          {data.severity}
        </span>
      </div>
      <div className="px-5 py-4 space-y-3">
        <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2">
          <span className="text-slate-500 text-xs pt-0.5">服务</span>
          <code className="text-amber-200/90 text-sm">{data.service}</code>
          <span className="text-slate-500 text-xs pt-0.5">错误类型</span>
          <code className="text-slate-200 text-sm">{data.error_type}</code>
          <span className="text-slate-500 text-xs pt-1">关键词</span>
          <div className="flex flex-wrap gap-1.5">
            {data.keywords.map((k, i) => (
              <code key={i} className="bg-amber-950/60 text-amber-300/90 border border-amber-800/40 px-2 py-0.5 rounded-md text-xs">{k}</code>
            ))}
          </div>
        </div>
        {usage && <UsageChips usage={usage} />}
      </div>
    </div>
  );
}

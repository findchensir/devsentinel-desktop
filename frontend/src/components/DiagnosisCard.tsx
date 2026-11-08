import type { DiagnosisResult, Usage } from '../type';
import UsageChips from './UsageChips';

// 结构化诊断结果卡片：按字段渲染，不是一段文本
export default function DiagnosisCard({ data, usage }: { data: DiagnosisResult; usage: Usage | null }) {
  const pct = Math.round(data.confidence * 100);
  const barColor = data.confidence >= 0.7 ? 'bg-emerald-500' : data.confidence >= 0.4 ? 'bg-yellow-500' : 'bg-red-500';
  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-xl overflow-hidden text-sm">
      <div className="flex items-center justify-between px-5 py-3 border-b border-slate-800 bg-slate-900">
        <span className="text-emerald-400 text-xs font-semibold tracking-wide">诊断结论</span>
        <span className="text-xs text-slate-500">置信度 {pct}%</span>
      </div>
      <div className="px-5 py-4 space-y-4">
        <p className="text-slate-100 leading-relaxed">{data.root_cause}</p>
        <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
          <div className={`h-full rounded-full transition-all ${barColor}`} style={{ width: `${pct}%` }} />
        </div>
        <div>
          <span className="text-emerald-400/90 text-xs font-semibold">证据</span>
          <ul className="mt-2 space-y-1.5 text-slate-300">
            {data.evidence.map((item, i) => (
              <li key={i} className="flex gap-2">
                <span className="text-emerald-500/70 shrink-0">•</span>{item}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <span className="text-emerald-400/90 text-xs font-semibold">建议动作</span>
          <ol className="mt-2 space-y-1.5 text-slate-300">
            {data.suggested_actions.map((item, i) => (
              <li key={i} className="flex gap-2">
                <span className="text-slate-500 shrink-0">{i + 1}.</span>{item}
              </li>
            ))}
          </ol>
        </div>
        {usage && <UsageChips usage={usage} />}
      </div>
    </div>
  );
}

import type { Usage } from '../type';
import UsageChips from './UsageChips';

// 输出面板：头部状态指示 + 正文 + usage 胶囊行
export default function OutputPanel({ output, loading, streamMode, usage }: {
  output: string;
  loading: boolean;
  streamMode: boolean;
  usage: Usage | null;
}) {
  return (
    <div className="bg-slate-950 border border-slate-800 rounded-xl overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-800/80 bg-slate-900/60">
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${loading ? 'bg-sky-400 animate-pulse' : output ? 'bg-emerald-500' : 'bg-slate-600'}`} />
          <span className="text-xs text-slate-400 font-medium">
            {loading ? 'Agent 排查中…' : output ? '排查结果' : '输出面板'}
          </span>
        </div>
        <span className="text-[10px] text-slate-600 font-mono">{streamMode ? 'SSE · stream' : 'HTTP · json'}</span>
      </div>
      <div className="p-5 min-h-60 font-mono text-sm leading-relaxed whitespace-pre-wrap text-slate-200">
        {output || (
          <span className="text-slate-600">
            {loading
              ? (streamMode ? '正在接收响应…' : '模型生成中，请稍候…')
              : '输入故障描述，发起诊断'}
          </span>
        )}
        {loading && output && <span className="inline-block w-2 h-4 ml-0.5 bg-sky-400/80 animate-pulse align-text-bottom" />}
      </div>
      {usage && (
        <div className="px-5 py-3 border-t border-slate-800/80">
          <UsageChips usage={usage} />
        </div>
      )}
    </div>
  );
}

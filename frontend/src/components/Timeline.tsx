import { useState } from 'react';
import type { TimelineStep, ToolItem, ToolStatus } from '../timeline';

const TOOL_STATUS: Record<ToolStatus, { dot: string; text: string }> = {
  running: { dot: 'bg-sky-400 animate-pulse', text: '执行中' },
  done: { dot: 'bg-emerald-500', text: '完成' },
  error: { dot: 'bg-red-500', text: '失败' },
  cancelled: { dot: 'bg-slate-500', text: '已取消' },
};

// 参数是 JSON 字符串就格式化成多行，解析失败（模型给了非法 JSON）原样展示
function prettyArgs(args: string): string {
  try {
    return JSON.stringify(JSON.parse(args), null, 2);
  } catch {
    return args;
  }
}

const formatDuration = (ms: number) => (ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`);

function ToolRow({ tool }: { tool: ToolItem }) {
  const st = TOOL_STATUS[tool.status];
  return (
    <details className="group rounded-lg bg-slate-950/70 border border-slate-800">
      <summary className="flex items-center gap-2 px-3 py-2 cursor-pointer select-none list-none text-xs">
        <span className="text-slate-500 transition-transform group-open:rotate-90">▸</span>
        <span className={`w-1.5 h-1.5 rounded-full ${st.dot}`} />
        <span className="font-mono text-amber-300/90">{tool.name}</span>
        <span className="text-slate-500 ml-auto">{st.text}</span>
      </summary>
      <div className="px-3 pb-3 space-y-2 text-xs font-mono">
        <div>
          <div className="text-slate-500 mb-1">参数</div>
          <pre className="whitespace-pre-wrap text-slate-300 bg-slate-900 rounded p-2">{prettyArgs(tool.args)}</pre>
        </div>
        {tool.result !== undefined && (
          <div>
            <div className="text-slate-500 mb-1">结果</div>
            <pre className={`whitespace-pre-wrap rounded p-2 max-h-64 overflow-y-auto bg-slate-900 ${tool.status === 'error' ? 'text-red-300' : 'text-slate-300'}`}>
              {tool.result}
            </pre>
          </div>
        )}
      </div>
    </details>
  );
}

function StepItem({ step, index, isLast }: { step: TimelineStep; index: number; isLast: boolean }) {
  // 每一步自己管展开状态：默认展开，用户收起后不会被后续事件重置
  const [open, setOpen] = useState(true);
  const running = step.status === 'running';
  const duration = step.endedAt ? formatDuration(step.endedAt - step.startedAt) : null;
  // 一轮调用结束时没带工具：模型这一轮直接生成了最终答复
  const isAnswerRound = step.status === 'done' && step.tools.length === 0 && !step.thought;
  const hasBody = step.thought || step.tools.length > 0 || step.outputs.length > 0 || isAnswerRound;

  return (
    <li className="relative pl-7">
      {/* 竖线：连到下一步，最后一步不画 */}
      {!isLast && <span className="absolute left-[7px] top-5 bottom-0 w-px bg-slate-700" />}
      <span
        className={`absolute left-0 top-1.5 w-3.5 h-3.5 rounded-full border-2 ${
          running ? 'border-sky-400 bg-sky-400/30 animate-pulse' : 'border-emerald-500 bg-emerald-500/20'
        }`}
      />
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={!hasBody}
        className="flex w-full items-center gap-2 text-left text-sm disabled:cursor-default"
      >
        <span className="text-slate-500 text-xs">#{index + 1}</span>
        <span className="font-medium text-slate-200">{step.label}</span>
        {step.tools.length > 0 && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">{step.tools.length} 次工具调用</span>
        )}
        {isAnswerRound && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-900/60 text-emerald-300/90">给出结论</span>
        )}
        <span className="ml-auto text-xs text-slate-500">{running ? '进行中…' : duration}</span>
        {hasBody && <span className={`text-slate-500 text-xs transition-transform ${open ? 'rotate-90' : ''}`}>▸</span>}
      </button>

      {open && hasBody && (
        <div className="mt-2 mb-4 space-y-2">
          {step.thought && (
            <p className="text-xs text-violet-300/80 whitespace-pre-wrap border-l-2 border-violet-500/50 pl-3">{step.thought}</p>
          )}
          {isAnswerRound && (
            <p className="text-xs text-slate-500">模型本轮未调用工具，直接生成最终答复（见下方输出面板）</p>
          )}
          {step.tools.map((tool, i) => (
            <ToolRow key={tool.id ?? i} tool={tool} />
          ))}
          {step.outputs.map((data, i) => (
            <pre key={i} className="text-xs font-mono whitespace-pre-wrap text-slate-300 bg-slate-950/70 border border-slate-800 rounded-lg p-3 max-h-64 overflow-y-auto">
              {typeof data === 'string' ? data : JSON.stringify(data, null, 2)}
            </pre>
          ))}
        </div>
      )}
    </li>
  );
}

// 排查时间线：每一步的思考 / 工具调用 / 结果，可展开
export default function Timeline({ steps }: { steps: TimelineStep[] }) {
  if (steps.length === 0) return null;
  const toolCount = steps.reduce((n, s) => n + s.tools.length, 0);
  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-xl px-5 py-4">
      <div className="flex items-center justify-between mb-4">
        <span className="text-xs font-semibold text-sky-300/90">排查时间线</span>
        <span className="text-[10px] text-slate-500">
          {steps.length} 步 · {toolCount} 次工具调用
        </span>
      </div>
      <ol>
        {steps.map((step, i) => (
          <StepItem key={`${step.name}-${i}`} step={step} index={i} isLast={i === steps.length - 1} />
        ))}
      </ol>
    </div>
  );
}

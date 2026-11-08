// 思考过程：左侧强调线标识这是「过程」而非结论，原生 details 折叠
export default function ThinkingBlock({ thinking }: { thinking: string }) {
  if (!thinking) return null;
  return (
    <details className="group bg-slate-900/80 border border-slate-800 border-l-2 border-l-violet-500/60 rounded-xl px-5 py-4 text-sm">
      <summary className="text-violet-300/80 text-xs font-semibold cursor-pointer select-none list-none flex items-center gap-2">
        <span className="transition-transform group-open:rotate-90">▸</span>
        思考过程
      </summary>
      <p className="mt-3 text-slate-300/90 whitespace-pre-wrap leading-relaxed max-h-72 overflow-y-auto">{thinking}</p>
    </details>
  );
}

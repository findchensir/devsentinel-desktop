// 工具栏：输入框 + 全部操作按钮 + 故障注入下拉，纯展示组件，行为通过 props 回调
export default function Toolbar(props: {
  prompt: string;
  onPromptChange: (v: string) => void;
  loading: boolean;
  streamMode: boolean;
  onToggleStream: () => void;
  onDiagnose: () => void;
  onStop: () => void;
  onNewChat: () => void;
  onStructured: () => void;
  onExtract: () => void;
  onWorkflow: () => void;
  onAgent: () => void;
  mockError: string;
  onMockErrorChange: (v: string) => void;
}) {
  const btn = 'text-white font-medium px-6 py-2 rounded-lg text-sm transition disabled:opacity-50';
  return (
    <div className="flex gap-3 flex-wrap">
      <input
        type="text"
        className="flex-1 min-w-60 bg-slate-800 border border-slate-700 rounded-lg px-4 py-2 text-sm focus:outline-none focus:border-sky-500"
        value={props.prompt}
        onChange={(e) => props.onPromptChange(e.target.value)}
        placeholder="输入线上报错 / StackTrace..."
      />
      <button onClick={props.onDiagnose} disabled={props.loading} className={`bg-sky-600 hover:bg-sky-500 ${btn}`}>
        {props.loading ? '诊断中...' : '发起 Agent 诊断'}
      </button>
      <button disabled={props.loading} onClick={props.onToggleStream} className={`bg-slate-600 hover:bg-slate-500 ${btn}`}>
        {props.streamMode ? '流式模式' : '非流式模式'}
      </button>
      <button disabled={!props.loading} onClick={props.onStop} className={`bg-red-600 hover:bg-red-500 ${btn}`}>
        停止
      </button>
      <button disabled={props.loading} onClick={props.onNewChat} className={`bg-slate-600 hover:bg-slate-500 ${btn}`}>
        发起新对话
      </button>
      <button onClick={props.onStructured} disabled={props.loading} className={`bg-emerald-600 hover:bg-emerald-500 ${btn}`}>
        结构化诊断
      </button>
      <button onClick={props.onExtract} disabled={props.loading} className={`bg-amber-600 hover:bg-amber-500 ${btn}`}>
        提取故障要素
      </button>
      <button onClick={props.onWorkflow} disabled={props.loading} className={`bg-violet-600 hover:bg-violet-500 ${btn}`}>
        工作流诊断
      </button>
      <button onClick={props.onAgent} disabled={props.loading} className={`bg-fuchsia-600 hover:bg-fuchsia-500 ${btn}`}>
        Agent 诊断
      </button>
      {/* 调试：故障注入。选一种错误码，后端直接返回对应错误，不用真把 DeepSeek 打挂 */}
      <select
        disabled={props.loading}
        value={props.mockError}
        onChange={(e) => props.onMockErrorChange(e.target.value)}
        className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-300"
      >
        <option value="">正常请求</option>
        <option value="auth">模拟 401</option>
        <option value="rate_limit">模拟 429</option>
        <option value="upstream">模拟 5xx</option>
        <option value="timeout">模拟超时</option>
        <option value="connection">模拟断连</option>
      </select>
    </div>
  );
}

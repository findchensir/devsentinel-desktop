import type { LLMErrorInfo } from '../type';

// 错误态 banner：独立于 output 渲染，retryable 时才给「重试」按钮
export default function ErrorBanner({ error, loading, onRetry }: {
  error: LLMErrorInfo;
  loading: boolean;
  onRetry: () => void;
}) {
  return (
    <div className="bg-red-950/60 border border-red-800/60 rounded-lg px-4 py-3 text-sm flex items-center justify-between">
      <span className="text-red-200 flex items-center gap-2">
        <span className="w-1.5 h-1.5 rounded-full bg-red-500 shrink-0" />
        {error.message}
        <code className="ml-1 text-red-400 text-xs">[{error.code}]</code>
      </span>
      {error.retryable && (
        <button
          onClick={onRetry}
          disabled={loading}
          className="ml-4 shrink-0 bg-red-700/80 hover:bg-red-600 text-white px-3 py-1 rounded-md text-xs transition disabled:opacity-50"
        >
          重试
        </button>
      )}
    </div>
  );
}

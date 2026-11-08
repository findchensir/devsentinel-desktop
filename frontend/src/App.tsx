import { useState, useRef } from 'react';
import type { Message, LLMErrorInfo, StreamEvent, DiagnosisResult, FaultInfo, Usage } from './type';
import Toolbar from './components/Toolbar';
import ErrorBanner from './components/ErrorBanner';
import ThinkingBlock from './components/ThinkingBlock';
import DiagnosisCard from './components/DiagnosisCard';
import FaultCard from './components/FaultCard';
import OutputPanel from './components/OutputPanel';

const App: React.FC = () => {
  const [prompt, setPrompt] = useState('');
  const [output, setOutput] = useState('');
  // 思考过程
  const [thinking, setThinking] = useState('');
  const [loading, setLoading] = useState(false);
  const [usage, setUsage] = useState<Usage | null>(null);
  // 流式模式开关
  const [streamMode, setStreamMode] = useState(true);

  const [faultInfo, setFaultInfo] = useState<FaultInfo | null>(null);

  // 错误态：独立于 output——错误是「状态」不是文本，UI 上单独渲染成 banner
  const [error, setError] = useState<LLMErrorInfo | null>(null);
  // 调试：故障注入下拉框选的值（"" = 不注入），传给后端的 mock_error 字段
  const [mockError, setMockError] = useState('');

  // 维护历史对话记录
  const [history, setHistory] = useState<Message[]>([]);

  // 结构化诊断结果：独立状态，渲染成卡片而不是拼进 output 文本
  const [structured, setStructured] = useState<DiagnosisResult | null>(null);

  // 用于取消请求
  const abortRef = useRef<AbortController | null>(null);

  /**
   * 发送一条对话的核心逻辑（流式/非流式共用）。
   * 抽出来的原因：「重试」按钮要复用它——参数就是要发的完整消息列表，
   * 重试时直接把 history（末尾是没得到回复的 user message）再传进来即可。
   */
  const send = async (messagesToSend: Message[], url = 'http://127.0.0.1:8000/api/agent/chat') => {
    setOutput('');
    setLoading(true);
    setUsage(null);
    setError(null);
    setStructured(null);
    setFaultInfo(null);
    setThinking('');

    // ---------- 非流式 ----------
    if (!streamMode) {
      try {
        const res = await fetch('http://127.0.0.1:8000/api/agent/chat_once', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          // mockError 为空字符串时 undefined 字段会被 JSON.stringify 丢弃，不影响正常请求
          body: JSON.stringify({ messages: messagesToSend, mock_error: mockError || undefined }),
        });
        // 后端出错时返回 HTTPException，body 是 {detail: {code, message, retryable}}
        if (!res.ok) {
          const data = await res.json().catch(() => null);
          setError(
            data?.detail ?? { code: 'http_error', message: `HTTP ${res.status}`, retryable: false },
          );
          return;
        }
        const data = await res.json();
        setOutput(data.answer);
        setUsage(data.usage);
        // 成功才追加 assistant。user message 在 handleDiagnose 里已写进 history
        setHistory((prev) => [...prev, { role: 'assistant', content: data.answer }]);
      } catch (err) {
        setError({ code: 'client', message: `请求失败：${err}`, retryable: false });
      } finally {
        setLoading(false);
      }
      return;
    }

    // ---------- 流式（POST + 手动读流）----------
    abortRef.current = new AbortController();   // 每次请求都是新的，不能用旧的
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: messagesToSend, mock_error: mockError || undefined }),
        // body: JSON.stringify({ messages: messagesToSend, mock_error: mockError || undefined, stop: ["##", "-"] }),
        signal: abortRef.current.signal,        // 配合停止按钮（见最后）
      });

      if (!res.ok) {
        const data = await res.json().catch(() => null);
        setError(
          data?.detail ?? { code: 'http_error', message: `HTTP ${res.status}`, retryable: false },
        );
        return;
      }

      // 如果响应没有 body，抛出错误
      if (!res.body) throw new Error('响应没有 body');
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let fullText = '';
      let finished = false;

      /**
       * 真正的生产实现还会加一个保护：buffer 长度上限（比如 1MB）——如果后端出问题一直不发 \n\n，buffer 会无限膨胀撑爆内存
       * 如果出现撑爆现象：防御顺序：限上限（断连报错）→ 用更严谨的协议（长度前缀）→ 背压（让上游慢下来）
       */
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const parts = buffer.split('\n\n');
        buffer = parts.pop()!;

        for (const part of parts) {
          if (!part.startsWith('data: ')) continue;
          const raw = part.slice(6);
          // if (raw === '[DONE]') { finished = true; break; }

          const evt = JSON.parse(raw) as StreamEvent;
          if (evt.type === 'done') { finished = true; break; }
          if (evt.type === 'reasoning') {
            setThinking((prev) => prev + evt.text);   // 打字机效果靠累积
          }
          else if (evt.type === 'content') {
            fullText += evt.text;
            setOutput((prev) => prev + evt.text);   // 打字机效果靠累积
          } else if (evt.type === 'usage') {
            setUsage({
              prompt_tokens: evt.prompt_tokens,
              completion_tokens: evt.completion_tokens,
              total_tokens: evt.total_tokens,
            });
          } else if (evt.type === 'error') {
            // 后端协议内错误（SSE 仍是 200 + 正常收尾）：已显示的内容保留，
            // error 进独立状态渲染成 banner
            setError({ code: evt.code, message: evt.message, retryable: evt.retryable });
            finished = true;
            break;
          } else if (evt.type === 'step') {
            // 工作流走到哪一步：在输出里插一行步骤标记
            setOutput((prev) => prev + `\n⚙ ${evt.label}\n`);
          } else if (evt.type === 'step_result') {
            // 步骤产出（提取的要素 / 日志片段）：折叠显示在思考区
            setThinking((prev) => prev + `\n[${evt.name}] ${typeof evt.data === 'string' ? evt.data : JSON.stringify(evt.data)}\n`);
          }
        }
        if (finished) break;
      }

      // ★ 关键一步：成功才写回历史（模型才有"记忆"）。
      // 出错时不追加 assistant——此时 history 末尾还是那条 user message，
      // 正好留给重试复用。空回复（没收到任何 content）也不算成功
      if (fullText) {
        setHistory((prev) => [...prev, { role: 'assistant', content: fullText }]);
      }
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') {
        // 用户主动取消：已收到的内容保留
        setOutput((prev) => prev + '\n[已停止]');
      } else {
        setError({ code: 'client', message: `请求失败：${err}`, retryable: false });
      }
    } finally {
      setLoading(false);      // 流式没有 loading 自然结束的时机，在这里兜底
    }
  };

  // 工作流诊断：固定流水线（提取→grep→总结），走 diagnose_workflow 接口
  const handleWorkflow = () => {
    if (!prompt.trim()) {
      setError({ code: 'input_required', message: '请输入故障描述', retryable: false });
      return;
    }
    send([{ role: 'user', content: prompt }], 'http://127.0.0.1:8000/api/agent/diagnose_workflow');
  };

  const handleDiagnose = () => {
    if (!prompt.trim()) {
      setError({ code: 'input_required', message: '请输入故障描述', retryable: false });
      return;
    }
    // user message 一旦「发出」就先写进 history——即使后端报错，这句话也是
    // 对话的一部分；失败时它留在末尾，「重试」直接拿整个 history 重发
    const newHistory = [...history, { role: 'user', content: prompt } as Message];
    setHistory(newHistory);
    send(newHistory);
  };

  // 重试：history 末尾应该是上次失败的 user message，原样重发
  const handleRetry = () => {
    if (history[history.length - 1]?.role === 'user') {
      send(history);
    }
  };

  // 结构化诊断：调 /api/agent/diagnose_structured，返回字段级数据渲染卡片
  const handleStructuredDiagnose = async () => {
    if (!prompt.trim()) return;
    setOutput('');
    setThinking('');
    setStructured(null);
    setUsage(null);
    setError(null);
    setLoading(true);
    setFaultInfo(null);
    try {
      const res = await fetch('http://127.0.0.1:8000/api/agent/diagnose_structured', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: [{ role: 'user', content: prompt }],
          mock_error: mockError || undefined,
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        setError(data?.detail ?? { code: 'http_error', message: `HTTP ${res.status}`, retryable: false });
        return;
      }
      const data = await res.json();
      setStructured(data.data);
      setUsage(data.usage);
    } catch (err) {
      setError({ code: 'client', message: `请求失败：${err}`, retryable: false });
    } finally {
      setLoading(false);
    }
  };

  // 故障要素提取：调 /api/agent/extract_fault，返回故障要素数据
  const handleExtractFault = async () => {
    if (!prompt.trim()) return;
    setOutput('');
    setThinking('');
    setStructured(null);
    setUsage(null);
    setError(null);
    setLoading(true);
    try {
      const res = await fetch('http://127.0.0.1:8000/api/agent/extract_fault', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: [{ role: 'user', content: prompt }],
          mock_error: mockError || undefined,
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        setError(data?.detail ?? { code: 'http_error', message: `HTTP ${res.status}`, retryable: false });
        return;
      }
      const data = await res.json();
      setFaultInfo(data.data);
      setUsage(data.usage);
    } catch (err) {
      setError({ code: 'client', message: `请求失败：${err}`, retryable: false });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-oklch-150 text-slate-100 p-8 font-sans">
      <header className="mb-6 flex items-center justify-between border-b border-slate-700 pb-4">
        <h1 className="text-2xl font-bold text-sky-400">🛡️ DevSentinel Desktop</h1>
        <span className="text-xs px-2 py-1 bg-slate-800 rounded text-slate-400">v0.1.0</span>
      </header>

      <main className="max-w-3xl mx-auto space-y-6">
        <Toolbar
          prompt={prompt}
          onPromptChange={setPrompt}
          loading={loading}
          streamMode={streamMode}
          onToggleStream={() => setStreamMode(!streamMode)}
          onDiagnose={handleDiagnose}
          onStop={() => abortRef.current?.abort()}
          onNewChat={() => {
            setOutput('');
            setUsage(null);
            setHistory([]);
            setPrompt('');
            setError(null);
            setStructured(null);
            setFaultInfo(null);
            setThinking('');
          }}
          onStructured={handleStructuredDiagnose}
          onExtract={handleExtractFault}
          onWorkflow={handleWorkflow}
          mockError={mockError}
          onMockErrorChange={setMockError}
        />

        {error && <ErrorBanner error={error} loading={loading} onRetry={handleRetry} />}

        <ThinkingBlock thinking={thinking} />

        {structured && !faultInfo && <DiagnosisCard data={structured} usage={usage} />}

        {faultInfo && !structured && <FaultCard data={faultInfo} usage={usage} />}

        {!structured && !faultInfo && (
          <OutputPanel output={output} loading={loading} streamMode={streamMode} usage={usage} />
        )}
      </main>
    </div>
  );
}

export default App;
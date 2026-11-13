import type { StreamEvent } from './type';

// 排查时间线的数据模型：把扁平的 SSE 事件流折叠成「步骤 → 工具调用」两层结构。
// 和组件分开放：这里是纯函数，不碰 React，方便单测和复用。

export type ToolStatus = 'running' | 'done' | 'error' | 'cancelled';

export interface ToolItem {
  id?: string;              // tool_call_id，后端带了就按它配对，没带就按名字兜底
  name: string;
  args: string;             // 统一存成字符串，展示时再尝试格式化
  result?: string;
  status: ToolStatus;
}

export interface TimelineStep {
  name: string;
  label: string;
  thought: string;          // 模型在这一轮调工具前说的话（需要后端推 thought 事件）
  tools: ToolItem[];
  outputs: unknown[];       // 工作流的 step_result 产出
  status: 'running' | 'done';
  startedAt: number;
  endedAt?: number;
}

// 只有这几种事件属于时间线，其余（content / reasoning / usage ...）不归它管
export type TimelineEvent = Extract<
  StreamEvent,
  { type: 'step' | 'step_result' | 'tool_call' | 'tool_result' | 'thought' }
>;

export function isTimelineEvent(evt: StreamEvent): evt is TimelineEvent {
  return ['step', 'step_result', 'tool_call', 'tool_result', 'thought'].includes(evt.type);
}

// 工具结果是否算失败：和后端 call_tool 的错误前缀约定保持一致
const isErrorResult = (result: string) => result.startsWith('[错误]');

const toArgString = (args: unknown) => (typeof args === 'string' ? args : JSON.stringify(args));

// 不可变地替换最后一步：React 靠引用变化判断要不要重渲染，不能原地改
function updateLast(steps: TimelineStep[], fn: (s: TimelineStep) => TimelineStep): TimelineStep[] {
  if (steps.length === 0) return steps;
  return [...steps.slice(0, -1), fn(steps[steps.length - 1])];
}

// 事件没赶上任何 step（比如后端先推了 tool_call）时，补一个隐式步骤兜住
function ensureStep(steps: TimelineStep[]): TimelineStep[] {
  if (steps.length > 0) return steps;
  return [{ name: 'implicit', label: '排查', thought: '', tools: [], outputs: [], status: 'running', startedAt: Date.now() }];
}

export function applyEvent(steps: TimelineStep[], evt: TimelineEvent): TimelineStep[] {
  const now = Date.now();
  switch (evt.type) {
    case 'step': {
      // 新步骤开始 = 上一步结束
      const closed = updateLast(steps, (s) => ({ ...s, status: 'done', endedAt: s.endedAt ?? now }));
      return [...closed, { name: evt.name, label: evt.label, thought: '', tools: [], outputs: [], status: 'running', startedAt: now }];
    }
    case 'thought':
      return updateLast(ensureStep(steps), (s) => ({ ...s, thought: s.thought + evt.text }));
    case 'step_result':
      return updateLast(ensureStep(steps), (s) => ({ ...s, outputs: [...s.outputs, evt.data] }));
    case 'tool_call':
      return updateLast(ensureStep(steps), (s) => ({
        ...s,
        tools: [...s.tools, { id: evt.id, name: evt.name, args: toArgString(evt.args), status: 'running' }],
      }));
    case 'tool_result':
      return updateLast(ensureStep(steps), (s) => {
        // 配对规则：优先按 id；没有 id 时按先进先出，配给同名且还在 running 的第一个
        // （后端按 tool_calls 顺序逐个执行，结果到达顺序 = 调用顺序）
        let idx = evt.id ? s.tools.findIndex((t) => t.id === evt.id) : -1;
        if (idx === -1) idx = s.tools.findIndex((t) => t.name === evt.name && t.status === 'running');
        if (idx === -1) return s;
        const tools = [...s.tools];
        tools[idx] = { ...tools[idx], result: evt.result, status: isErrorResult(evt.result) ? 'error' : 'done' };
        return { ...s, tools };
      });
  }
}

// 流结束（正常 / 出错 / 用户停止）时收尾：没跑完的步骤关掉，没回结果的工具标成已取消
export function finalizeSteps(steps: TimelineStep[]): TimelineStep[] {
  const now = Date.now();
  return steps.map((s) =>
    s.status === 'done' && s.tools.every((t) => t.status !== 'running')
      ? s
      : {
          ...s,
          status: 'done',
          endedAt: s.endedAt ?? now,
          tools: s.tools.map((t) => (t.status === 'running' ? { ...t, status: 'cancelled' } : t)),
        },
  );
}

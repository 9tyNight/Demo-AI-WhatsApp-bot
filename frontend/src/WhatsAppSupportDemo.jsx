import { useEffect, useMemo, useRef, useState } from "react";
import {
  Bot,
  CheckCircle2,
  CircleAlert,
  Database,
  Loader2,
  MessageCircle,
  Send,
  ShieldCheck,
  UserRound,
} from "lucide-react";

const API_BASE_URL = "http://127.0.0.1:8000";

const initialMessages = [
  {
    id: "welcome",
    role: "bot",
    text: "Hi! I can check product stock, store locations, prices, promotions, or connect you to a human agent.",
    timestamp: new Date(),
  },
];

function getResponseText(payload) {
  return (
    payload?.reply ||
    payload?.message ||
    payload?.text ||
    payload?.data?.reply ||
    payload?.data?.message ||
    "I received your message, but the backend response did not include a reply field."
  );
}

function getToolCalls(payload) {
  return payload?.tool_calls || payload?.tools || payload?.events || payload?.data?.tool_calls || [];
}

function isHumanHandoff(payload, toolCalls) {
  return Boolean(
    payload?.human_handoff ||
      payload?.humanHandoff ||
      payload?.handoff_required ||
      toolCalls.some((call) => call.name === "human_handoff")
  );
}

function formatToolEvent(call) {
  const name = call.name || call.tool || "unknown_tool";
  const args = call.arguments || call.args || {};
  const argText = Object.entries(args)
    .map(([key, value]) => `${key}=${JSON.stringify(value)}`)
    .join(", ");

  return `[TOOL EXECUTED] ${name}(${argText})`;
}

function formatTime(date) {
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export default function WhatsAppSupportDemo() {
  const [messages, setMessages] = useState(initialMessages);
  const [input, setInput] = useState("");
  const [events, setEvents] = useState([
    {
      id: "boot",
      type: "status",
      text: "[API STATUS] Waiting for Mock Odoo ERP connection",
      timestamp: new Date(),
    },
  ]);
  const [isSending, setIsSending] = useState(false);
  const [handoffActive, setHandoffActive] = useState(false);
  const [apiOnline, setApiOnline] = useState(false);
  const bottomRef = useRef(null);

  const canSend = input.trim().length > 0 && !isSending && !handoffActive;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    let ignore = false;

    async function checkHealth() {
      try {
        const response = await fetch(`${API_BASE_URL}/health`);
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        if (!ignore) {
          setApiOnline(true);
          addEvent("[API STATUS] Connected to Mock Odoo ERP", "success");
        }
      } catch (error) {
        if (!ignore) {
          setApiOnline(false);
          addEvent(`[API STATUS] Backend unavailable: ${error.message}`, "error");
        }
      }
    }

    checkHealth();
    return () => {
      ignore = true;
    };
  }, []);

  function addEvent(text, type = "tool") {
    setEvents((current) => [
      {
        id: crypto.randomUUID(),
        type,
        text,
        timestamp: new Date(),
      },
      ...current,
    ]);
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const userText = input.trim();
    if (!userText || isSending || handoffActive) return;

    const userMessage = {
      id: crypto.randomUUID(),
      role: "user",
      text: userText,
      timestamp: new Date(),
    };

    setMessages((current) => [...current, userMessage]);
    setInput("");
    setIsSending(true);
    addEvent(`[CHAT EVENT] User message posted: ${JSON.stringify(userText)}`, "status");

    try {
      const response = await fetch(`${API_BASE_URL}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ message: userText }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const payload = await response.json();
      const toolCalls = getToolCalls(payload);

      toolCalls.forEach((call) => addEvent(formatToolEvent(call), call.name === "human_handoff" ? "handoff" : "tool"));

      const humanHandoff = isHumanHandoff(payload, toolCalls);
      if (humanHandoff) {
        setHandoffActive(true);
        addEvent("[HANDOFF] AI paused: Human agent paged", "handoff");
      }

      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "bot",
          text: getResponseText(payload),
          timestamp: new Date(),
        },
      ]);
    } catch (error) {
      addEvent(`[API ERROR] ${error.message}`, "error");
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "bot",
          text: "I could not reach the support backend. Please confirm FastAPI is running at http://127.0.0.1:8000.",
          timestamp: new Date(),
        },
      ]);
    } finally {
      setIsSending(false);
    }
  }

  const statusPill = useMemo(() => {
    if (handoffActive) {
      return {
        label: "Human agent needed",
        className: "bg-amber-100 text-amber-800 ring-amber-200",
        icon: CircleAlert,
      };
    }

    if (apiOnline) {
      return {
        label: "Mock Odoo connected",
        className: "bg-emerald-100 text-emerald-800 ring-emerald-200",
        icon: CheckCircle2,
      };
    }

    return {
      label: "Checking backend",
      className: "bg-slate-100 text-slate-700 ring-slate-200",
      icon: Loader2,
    };
  }, [apiOnline, handoffActive]);

  const StatusIcon = statusPill.icon;

  return (
    <main className="min-h-screen bg-[#f5f7f9] px-4 py-6 text-slate-950 sm:px-6 lg:px-8">
      <div className="mx-auto grid max-w-7xl gap-6 lg:grid-cols-[minmax(360px,480px)_1fr]">
        <section className="mx-auto w-full max-w-[440px]">
          <div className="rounded-[32px] border border-slate-300 bg-slate-950 p-3 shadow-2xl shadow-slate-300/60">
            <div className="overflow-hidden rounded-[24px] bg-[#efeae2]">
              <header className="flex items-center gap-3 bg-[#075e54] px-4 py-3 text-white">
                <div className="relative grid h-11 w-11 place-items-center rounded-full bg-white/15">
                  <MessageCircle className="h-6 w-6" />
                  <span className="absolute bottom-0 right-0 h-3 w-3 rounded-full border-2 border-[#075e54] bg-emerald-400" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold">BrightMart Support</p>
                  <p className="text-xs text-emerald-100">online • AI inventory assistant</p>
                </div>
                <ShieldCheck className="h-5 w-5 text-emerald-100" />
              </header>

              {handoffActive && (
                <div className="border-b border-amber-200 bg-amber-100 px-4 py-3 text-sm font-medium text-amber-900">
                  AI paused: Human agent paged
                </div>
              )}

              <div className="h-[620px] overflow-y-auto px-3 py-4">
                <div className="space-y-3">
                  {messages.map((message) => {
                    const isUser = message.role === "user";
                    return (
                      <div key={message.id} className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
                        <div
                          className={`max-w-[82%] rounded-lg px-3 py-2 text-sm shadow-sm ${
                            isUser
                              ? "rounded-tr-sm bg-[#dcf8c6] text-slate-950"
                              : "rounded-tl-sm bg-white text-slate-900"
                          }`}
                        >
                          <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-slate-500">
                            {isUser ? <UserRound className="h-3.5 w-3.5" /> : <Bot className="h-3.5 w-3.5" />}
                            {isUser ? "Customer" : "AI Bot"}
                          </div>
                          <p className="whitespace-pre-wrap leading-relaxed">{message.text}</p>
                          <p className="mt-1 text-right text-[11px] text-slate-500">{formatTime(message.timestamp)}</p>
                        </div>
                      </div>
                    );
                  })}

                  {isSending && (
                    <div className="flex justify-start">
                      <div className="rounded-lg rounded-tl-sm bg-white px-3 py-2 text-sm text-slate-500 shadow-sm">
                        <span className="inline-flex items-center gap-2">
                          <Loader2 className="h-4 w-4 animate-spin" />
                          Checking inventory...
                        </span>
                      </div>
                    </div>
                  )}
                  <div ref={bottomRef} />
                </div>
              </div>

              <form onSubmit={handleSubmit} className="flex items-center gap-2 border-t border-black/5 bg-[#f0f2f5] p-3">
                <input
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  disabled={handoffActive}
                  className="min-w-0 flex-1 rounded-full border border-transparent bg-white px-4 py-3 text-sm outline-none ring-0 transition focus:border-emerald-300 disabled:cursor-not-allowed disabled:bg-slate-100"
                  placeholder={handoffActive ? "Human handoff active" : "Ask about stock, price, location, or promos"}
                />
                <button
                  type="submit"
                  disabled={!canSend}
                  className="grid h-11 w-11 place-items-center rounded-full bg-[#25d366] text-white shadow-sm transition hover:bg-[#20bd5a] disabled:cursor-not-allowed disabled:bg-slate-300"
                  aria-label="Send message"
                >
                  <Send className="h-5 w-5" />
                </button>
              </form>
            </div>
          </div>
        </section>

        <aside className="min-h-[720px] rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
            <div>
              <h2 className="text-base font-semibold">Developer Debug Panel</h2>
              <p className="mt-1 text-sm text-slate-500">Live tool calls, API status, and handoff events</p>
            </div>
            <span className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium ring-1 ${statusPill.className}`}>
              <StatusIcon className={`h-3.5 w-3.5 ${StatusIcon === Loader2 ? "animate-spin" : ""}`} />
              {statusPill.label}
            </span>
          </div>

          <div className="grid gap-4 p-5 md:grid-cols-3">
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <div className="flex items-center gap-2 text-sm font-medium text-slate-700">
                <Database className="h-4 w-4 text-emerald-600" />
                Backend
              </div>
              <p className="mt-2 text-sm text-slate-500">{API_BASE_URL}</p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <div className="text-sm font-medium text-slate-700">Messages</div>
              <p className="mt-2 text-2xl font-semibold">{messages.length}</p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <div className="text-sm font-medium text-slate-700">Tool Events</div>
              <p className="mt-2 text-2xl font-semibold">{events.filter((event) => event.type === "tool").length}</p>
            </div>
          </div>

          <div className="mx-5 mb-5 h-[520px] overflow-y-auto rounded-lg border border-slate-200 bg-slate-950 p-4 font-mono text-xs text-slate-100">
            <div className="space-y-3">
              {events.map((event) => (
                <div key={event.id} className="grid grid-cols-[72px_1fr] gap-3">
                  <span className="text-slate-500">{formatTime(event.timestamp)}</span>
                  <span
                    className={
                      event.type === "handoff"
                        ? "text-amber-300"
                        : event.type === "error"
                          ? "text-rose-300"
                          : event.type === "success"
                            ? "text-emerald-300"
                            : event.type === "tool"
                              ? "text-cyan-300"
                              : "text-slate-300"
                    }
                  >
                    {event.text}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </aside>
      </div>
    </main>
  );
}

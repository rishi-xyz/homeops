'use client';

import { useState, useRef, useEffect } from 'react';
import Link from 'next/link';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000';

type Message = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  toolTrace?: any[];
};

const SUGGESTIONS = [
  "Is my washing machine still under warranty?",
  "Remind me a month before it expires",
  "Has the washing machine leaked before?",
  "Prepare a brief for the technician",
  "Help me contact a technician",
  "What appointment slots are available?",
];

export default function DemoPage() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      role: 'assistant',
      content: "Hi! I'm HomeOps, your AI household maintenance assistant. I can help you track warranties, manage reminders, look up maintenance history, prepare technician briefs, and connect you with service providers. What can I help you with today?"
    }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [conversationId] = useState(() => `demo-${Date.now()}`);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const sendMessage = async (text: string) => {
    if (!text.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: text,
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      const response = await fetch(`${API_BASE}/api/assistant/message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, conversation_id: conversationId }),
      });

      if (!response.ok) throw new Error('Failed to get response');

      const data = await response.json();
      
      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: data.reply,
        toolTrace: data.tool_trace,
      };

      setMessages(prev => [...prev, assistantMessage]);
    } catch (error) {
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: "I'm having trouble connecting to the HomeOps API. Make sure the services are running with `make dev` or `docker compose up`.",
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="glass border-b border-violet-500/20">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link href="/" className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center font-bold text-lg">
                HO
              </div>
              <div>
                <span className="text-xl font-bold font-[family-name:var(--font-space-grotesk)]">HomeOps</span>
                <span className="ml-2 text-xs px-2 py-1 rounded-full bg-violet-500/20 text-violet-300">Demo</span>
              </div>
            </Link>
          </div>
          <Link href="/" className="btn-ghost px-4 py-2 rounded-lg text-sm">
            ← Back to Home
          </Link>
        </div>
      </header>

      {/* Demo Banner */}
      <div className="bg-amber-500/10 border-b border-amber-500/30 px-6 py-2 text-center text-sm text-amber-300">
        ⚠️ Demo data only - All records, providers, and appointments are fictional
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-8">
        <div className="max-w-4xl mx-auto space-y-6">
          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex gap-4 ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              {message.role === 'assistant' && (
                <div className="w-10 h-10 rounded-full bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center text-sm font-bold flex-shrink-0">
                  AI
                </div>
              )}
              <div className={`max-w-2xl ${message.role === 'user' ? 'order-first' : ''}`}>
                <div
                  className={`rounded-2xl px-6 py-4 ${
                    message.role === 'user'
                      ? 'bg-gradient-to-br from-violet-600 to-indigo-600 rounded-tr-sm'
                      : 'glass-card rounded-tl-sm'
                  }`}
                >
                  <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>
                </div>
                {message.toolTrace && message.toolTrace.length > 0 && (
                  <div className="mt-2 ml-2 flex flex-wrap gap-2">
                    {message.toolTrace.map((tool: any, i: number) => (
                      <span key={i} className="text-xs px-2 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                        ✓ {tool.tool_name}
                      </span>
                    ))}
                  </div>
                )}
              </div>
              {message.role === 'user' && (
                <div className="w-10 h-10 rounded-full bg-gradient-to-br from-gray-600 to-gray-700 flex items-center justify-center text-sm font-bold flex-shrink-0">
                  U
                </div>
              )}
            </div>
          ))}
          {isLoading && (
            <div className="flex gap-4">
              <div className="w-10 h-10 rounded-full bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center text-sm font-bold flex-shrink-0">
                AI
              </div>
              <div className="glass-card rounded-2xl rounded-tl-sm px-6 py-4">
                <div className="flex gap-2">
                  <div className="w-2 h-2 rounded-full bg-violet-400 animate-bounce"></div>
                  <div className="w-2 h-2 rounded-full bg-violet-400 animate-bounce" style={{ animationDelay: '0.1s' }}></div>
                  <div className="w-2 h-2 rounded-full bg-violet-400 animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Suggestions */}
      {messages.length <= 2 && (
        <div className="px-6 pb-4">
          <div className="max-w-4xl mx-auto flex flex-wrap gap-2">
            {SUGGESTIONS.map((suggestion, i) => (
              <button
                key={i}
                onClick={() => sendMessage(suggestion)}
                className="btn-ghost px-4 py-2 rounded-lg text-sm"
                disabled={isLoading}
              >
                {suggestion}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input */}
      <div className="glass border-t border-violet-500/20 px-6 py-4">
        <div className="max-w-4xl mx-auto flex gap-3">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && sendMessage(input)}
            placeholder="Ask about your appliances, warranties, or maintenance..."
            className="flex-1 bg-white/5 border border-violet-500/30 rounded-xl px-4 py-3 focus:outline-none focus:border-violet-500/60 transition-colors"
            disabled={isLoading}
          />
          <button
            onClick={() => sendMessage(input)}
            disabled={isLoading || !input.trim()}
            className="btn-primary px-6 py-3 rounded-xl font-medium disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}

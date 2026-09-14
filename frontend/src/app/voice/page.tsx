'use client';

import React, { useState, useEffect, useRef } from 'react';
import { 
  Mic, MicOff, Sparkles, Volume2, 
  ShieldCheck, Radio, AlertCircle, ArrowLeft, RefreshCw,
  MessageSquare, User, Bot, Play, Pause, Square, Trash2, Send
} from 'lucide-react';
import Link from 'next/link';

interface TranscriptItem {
  id: string;
  sender: 'user' | 'agent';
  text: string;
  timestamp: string;
}

export default function WebVoiceAssistantPage() {
  const [listening, setListening] = useState(false);
  const [isDictating, setIsDictating] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [agentSpeaking, setAgentSpeaking] = useState(false);
  const [statusText, setStatusText] = useState('Click "Start Listening" or tap the Mic button in chat bar');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [textInput, setTextInput] = useState('');
  const [sessionId, setSessionId] = useState<string>('');

  // Dynamically resolve backend URL based on browser hostname
  const getBackendUrl = () => {
    if (typeof window === 'undefined') return 'http://localhost:8000/api/v1';
    const host = window.location.hostname;
    return `http://${host}:8000/api/v1`;
  };
  const [backendUrl] = useState(getBackendUrl);

  // Live Transcripts
  const [liveUserQuery, setLiveUserQuery] = useState<string>('');
  const [transcripts, setTranscripts] = useState<TranscriptItem[]>([]);

  const recognitionRef = useRef<any>(null);
  const transcriptEndRef = useRef<HTMLDivElement>(null);
  const synthRef = useRef<SpeechSynthesis | null>(null);

  // Generate session ID on mount
  useEffect(() => {
    const sId = `SESSION_WEB_${Math.random().toString(36).substring(2, 10)}`;
    setSessionId(sId);
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      synthRef.current = window.speechSynthesis;
    }
  }, []);

  // Initialize Speech Recognition for Live User Query & Dictation
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
      if (SpeechRecognition) {
        const rec = new SpeechRecognition();
        rec.continuous = true;
        rec.interimResults = true;
        rec.lang = 'hi-IN';

        rec.onresult = (event: any) => {
          let interim = '';
          let final = '';
          for (let i = event.resultIndex; i < event.results.length; i++) {
            const transcriptText = event.results[i][0].transcript;
            if (event.results[i].isFinal) {
              final += transcriptText;
            } else {
              interim += transcriptText;
            }
          }

          const currentText = final || interim;
          if (currentText.trim()) {
            setLiveUserQuery(currentText);
            // Also fill into text input box in real-time (WhatsApp style!)
            setTextInput(currentText);
          }
        };

        rec.onerror = (err: any) => {
          const code = err?.error || 'unknown';
          if (['no-speech', 'not-allowed', 'audio-capture', 'aborted'].includes(code)) return;
          console.warn('Speech recognition error:', code);
        };

        rec.onend = () => {
          setIsDictating(false);
        };

        recognitionRef.current = rec;
      }
    }
  }, []);

  // Auto-scroll transcript container
  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [transcripts, liveUserQuery]);

  // Speak AI Response using Web Speech Synthesis
  const speakText = (text: string) => {
    if (!synthRef.current) return;
    try {
      synthRef.current.cancel(); // Stop any previous speech
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = 'hi-IN';
      utterance.rate = 1.0;
      utterance.pitch = 1.0;

      utterance.onstart = () => {
        setAgentSpeaking(true);
        setStatusText('🗣️ AI Assistant is speaking...');
      };
      utterance.onend = () => {
        setAgentSpeaking(false);
        setStatusText(listening ? '🎙️ Listening to you...' : 'Ready for your query');
      };
      utterance.onerror = () => {
        setAgentSpeaking(false);
      };

      synthRef.current.speak(utterance);
    } catch (e) {
      console.warn('Speech synthesis error:', e);
    }
  };

  // Send query directly to RestaurantAgentGraph FastAPI endpoint
  const sendQueryToGraph = async (queryText: string) => {
    if (!queryText.trim() || processing) return;

    // Stop dictation if active
    if (isDictating && recognitionRef.current) {
      try { recognitionRef.current.stop(); } catch (_) {}
      setIsDictating(false);
    }

    setErrorMsg(null);
    setProcessing(true);
    setStatusText('🤖 Thinking & running Restaurant Agent Graph...');

    // 1. Append User Message to Transcript Timeline
    const userMsg: TranscriptItem = {
      id: Date.now().toString(),
      sender: 'user',
      text: queryText,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };
    setTranscripts(prev => [...prev, userMsg]);
    setLiveUserQuery('');
    setTextInput('');

    try {
      // 2. Call Direct RestaurantAgentGraph Endpoint
      const res = await fetch(`${backendUrl}/voice/direct-agent`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_input: queryText,
          session_id: sessionId,
        }),
      });

      if (!res.ok) {
        throw new Error(`Backend returned HTTP ${res.status}`);
      }

      const json = await res.json();
      if (!json.success || !json.data) {
        throw new Error('Invalid response format from agent');
      }

      const aiResponse = json.data.response;

      // 3. Append AI Response to Transcript Timeline
      const agentMsg: TranscriptItem = {
        id: (Date.now() + 1).toString(),
        sender: 'agent',
        text: aiResponse,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setTranscripts(prev => [...prev, agentMsg]);

      // 4. Speak response out loud via voice
      speakText(aiResponse);

    } catch (err: any) {
      console.error('Direct Graph Query Error:', err);
      setErrorMsg(err.message || 'Failed to connect to Restaurant Agent backend.');
      setStatusText('⚠️ Error processing query');
    } finally {
      setProcessing(false);
    }
  };

  // Toggle Hands-free Listening Mode (Big Orb Button)
  const toggleListening = () => {
    if (listening) {
      setListening(false);
      setStatusText('Ready for your query');
      if (recognitionRef.current) {
        try { recognitionRef.current.stop(); } catch (_) {}
      }
      if (liveUserQuery.trim()) {
        sendQueryToGraph(liveUserQuery);
      }
    } else {
      setListening(true);
      setStatusText('🎙️ Hands-free Listening... Speak your query');
      if (recognitionRef.current) {
        try {
          setLiveUserQuery('');
          recognitionRef.current.start();
        } catch (_) {}
      }
    }
  };

  // Toggle Voice Dictation Mode (WhatsApp style inside Chat Bar)
  const toggleDictation = () => {
    if (isDictating) {
      setIsDictating(false);
      setStatusText('Dictation paused');
      if (recognitionRef.current) {
        try { recognitionRef.current.stop(); } catch (_) {}
      }
    } else {
      setIsDictating(true);
      setStatusText('🎙️ Speaking into chat input... Text is filling live');
      if (recognitionRef.current) {
        try {
          recognitionRef.current.start();
        } catch (_) {}
      }
    }
  };

  // Handle Manual Text Input Submit
  const handleTextSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!textInput.trim()) return;
    sendQueryToGraph(textInput);
  };

  // Clear Transcripts
  const handleClearHistory = () => {
    setTranscripts([]);
    setLiveUserQuery('');
    setTextInput('');
    if (synthRef.current) synthRef.current.cancel();
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-indigo-500 selection:text-white">
      {/* Dynamic Background Glows */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden z-0">
        <div className={`absolute -top-40 -left-40 w-96 h-96 rounded-full blur-[128px] transition-all duration-700 ${
          agentSpeaking ? 'bg-emerald-500/20' : listening || isDictating ? 'bg-indigo-500/20' : 'bg-blue-600/10'
        }`} />
        <div className={`absolute top-1/2 -right-40 w-96 h-96 rounded-full blur-[128px] transition-all duration-700 ${
          agentSpeaking ? 'bg-teal-500/20' : processing ? 'bg-purple-500/20' : 'bg-indigo-600/10'
        }`} />
      </div>

      {/* Top Navbar */}
      <header className="sticky top-0 z-20 bg-slate-900/80 backdrop-blur-xl border-b border-slate-800/80 px-4 py-3 sm:px-6">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link 
              href="/"
              className="p-2 rounded-xl bg-slate-800/80 hover:bg-slate-700 text-slate-300 hover:text-white transition-colors"
            >
              <ArrowLeft className="w-5 h-5" />
            </Link>
            <div>
              <div className="flex items-center gap-2">
                <Sparkles className="w-5 h-5 text-indigo-400 animate-pulse" />
                <h1 className="font-semibold text-lg text-white tracking-wide">
                  Direct AI Restaurant Assistant
                </h1>
              </div>
              <p className="text-xs text-slate-400">
                Voice & WhatsApp-Style Chat Dictation
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium border ${
              listening || isDictating 
                ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                : 'bg-slate-800 text-slate-400 border-slate-700'
            }`}>
              <Radio className={`w-3.5 h-3.5 ${listening || isDictating ? 'animate-pulse text-emerald-400' : ''}`} />
              <span>{listening ? 'Hands-Free' : isDictating ? 'Dictating' : 'Standby'}</span>
            </div>

            {transcripts.length > 0 && (
              <button
                onClick={handleClearHistory}
                className="p-2 rounded-xl bg-slate-800/80 hover:bg-red-500/20 text-slate-400 hover:text-red-400 transition-colors"
                title="Clear Chat History"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-4xl w-full mx-auto p-4 sm:p-6 flex flex-col gap-6 z-10">
        
        {/* Error Banner */}
        {errorMsg && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-2xl p-4 flex items-start gap-3 text-red-300 text-sm animate-in fade-in slide-in-from-top-2">
            <AlertCircle className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="font-medium text-red-200">Connection Error</p>
              <p className="text-xs text-red-300/80 mt-0.5">{errorMsg}</p>
            </div>
          </div>
        )}

        {/* Visualizer & Controls Card */}
        <div className="bg-slate-900/90 border border-slate-800 rounded-3xl p-6 sm:p-8 flex flex-col items-center justify-center gap-6 shadow-2xl relative overflow-hidden">
          
          {/* Animated Glowing Orb Visualizer */}
          <div className="relative flex items-center justify-center my-4">
            <div className={`w-36 h-36 sm:w-44 sm:h-44 rounded-full flex items-center justify-center transition-all duration-500 ${
              agentSpeaking
                ? 'bg-gradient-to-tr from-emerald-600 to-teal-400 shadow-[0_0_60px_rgba(16,185,129,0.5)] scale-105'
                : listening || isDictating
                ? 'bg-gradient-to-tr from-indigo-600 to-purple-500 shadow-[0_0_60px_rgba(99,102,241,0.5)] scale-105 animate-pulse'
                : processing
                ? 'bg-gradient-to-tr from-purple-600 to-pink-500 shadow-[0_0_50px_rgba(168,85,247,0.4)] animate-spin'
                : 'bg-gradient-to-tr from-slate-800 to-slate-700 border border-slate-700 shadow-inner'
            }`}>
              <div className="w-28 h-28 sm:w-36 sm:h-36 rounded-full bg-slate-950/80 backdrop-blur-md flex items-center justify-center">
                {agentSpeaking ? (
                  <Volume2 className="w-12 h-12 text-emerald-400 animate-bounce" />
                ) : listening || isDictating ? (
                  <Mic className="w-12 h-12 text-indigo-400 animate-pulse" />
                ) : processing ? (
                  <RefreshCw className="w-10 h-10 text-purple-400 animate-spin" />
                ) : (
                  <Sparkles className="w-10 h-10 text-slate-500" />
                )}
              </div>
            </div>
          </div>

          {/* Status Bar */}
          <div className="text-center space-y-1">
            <p className="text-sm sm:text-base font-medium text-slate-200">
              {statusText}
            </p>
            {sessionId && (
              <p className="text-[11px] font-mono text-slate-500">
                Session: {sessionId}
              </p>
            )}
          </div>

          {/* Hands-Free Start/Stop Toggle Button */}
          <div className="flex items-center gap-4 w-full sm:w-auto">
            <button
              onClick={toggleListening}
              className={`flex-1 sm:flex-none px-8 py-4 rounded-2xl font-semibold text-base flex items-center justify-center gap-3 transition-all duration-300 shadow-lg active:scale-95 ${
                listening
                  ? 'bg-red-500/20 hover:bg-red-500/30 text-red-300 border border-red-500/40 shadow-red-500/10'
                  : 'bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white shadow-indigo-500/25'
              }`}
            >
              {listening ? (
                <>
                  <Square className="w-5 h-5 fill-current" />
                  <span>Stop Hands-Free</span>
                </>
              ) : (
                <>
                  <Mic className="w-5 h-5" />
                  <span>Start Hands-Free Voice</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Live User Query Preview */}
        {liveUserQuery && (
          <div className="bg-indigo-500/10 border border-indigo-500/30 rounded-2xl p-4 flex items-center gap-3 text-indigo-200 text-sm animate-in fade-in">
            <Mic className="w-5 h-5 text-indigo-400 animate-pulse shrink-0" />
            <div className="flex-1">
              <span className="text-xs text-indigo-400 font-medium block">Live Speech Transcription:</span>
              <span className="font-medium text-white">{liveUserQuery}</span>
            </div>
          </div>
        )}

        {/* Chat Transcript Timeline */}
        <div className="bg-slate-900/60 border border-slate-800/80 rounded-3xl p-4 sm:p-6 flex-1 flex flex-col min-h-[300px]">
          <div className="flex items-center justify-between pb-3 mb-3 border-b border-slate-800">
            <div className="flex items-center gap-2">
              <MessageSquare className="w-4 h-4 text-indigo-400" />
              <h2 className="text-sm font-semibold text-slate-300">Conversation History</h2>
            </div>
            <span className="text-xs text-slate-500">{transcripts.length} turns</span>
          </div>

          <div className="flex-1 overflow-y-auto space-y-4 max-h-[400px] pr-2">
            {transcripts.length === 0 ? (
              <div className="h-48 flex flex-col items-center justify-center text-center text-slate-500 space-y-2">
                <Bot className="w-10 h-10 text-slate-600" />
                <p className="text-sm font-medium text-slate-400">No conversation yet</p>
                <p className="text-xs text-slate-500 max-w-xs">
                  Speak via hands-free mic or tap the mic icon in the chat bar below to type with your voice!
                </p>
              </div>
            ) : (
              transcripts.map(item => (
                <div
                  key={item.id}
                  className={`flex gap-3 text-sm ${
                    item.sender === 'user' ? 'justify-end' : 'justify-start'
                  }`}
                >
                  {item.sender === 'agent' && (
                    <div className="w-8 h-8 rounded-full bg-indigo-500/20 border border-indigo-500/30 flex items-center justify-center shrink-0 text-indigo-400 mt-1">
                      <Bot className="w-4 h-4" />
                    </div>
                  )}

                  <div
                    className={`max-w-[80%] rounded-2xl p-4 shadow-sm ${
                      item.sender === 'user'
                        ? 'bg-indigo-600 text-white rounded-tr-none'
                        : 'bg-slate-800/90 text-slate-100 border border-slate-700/60 rounded-tl-none'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-4 mb-1">
                      <span className="text-[11px] font-medium opacity-75">
                        {item.sender === 'user' ? 'You' : 'AI Assistant'}
                      </span>
                      <span className="text-[10px] opacity-50">{item.timestamp}</span>
                    </div>
                    <p className="leading-relaxed whitespace-pre-wrap">{item.text}</p>
                  </div>

                  {item.sender === 'user' && (
                    <div className="w-8 h-8 rounded-full bg-purple-500/20 border border-purple-500/30 flex items-center justify-center shrink-0 text-purple-400 mt-1">
                      <User className="w-4 h-4" />
                    </div>
                  )}
                </div>
              ))
            )}
            <div ref={transcriptEndRef} />
          </div>

          {/* WhatsApp Style Chat Input Bar with Voice Dictation Button */}
          <form onSubmit={handleTextSubmit} className="mt-4 pt-3 border-t border-slate-800/80 flex items-center gap-2">
            <div className="relative flex-1 flex items-center">
              <input
                type="text"
                value={textInput}
                onChange={(e) => setTextInput(e.target.value)}
                placeholder={isDictating ? "🎙️ Speaking... text is filling live..." : "💬 Type query or tap mic to dictate..."}
                disabled={processing}
                className={`w-full bg-slate-950 border rounded-2xl pl-4 pr-12 py-3 text-sm text-slate-100 placeholder-slate-500 focus:outline-none transition-all disabled:opacity-50 ${
                  isDictating 
                    ? 'border-emerald-500/60 ring-2 ring-emerald-500/20 bg-emerald-950/20 text-emerald-200' 
                    : 'border-slate-800 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500'
                }`}
              />
              
              {/* WhatsApp Voice Typing / Pause Toggle Icon */}
              <button
                type="button"
                onClick={toggleDictation}
                disabled={processing}
                className={`absolute right-2 p-2 rounded-xl transition-all ${
                  isDictating
                    ? 'bg-emerald-500 text-white animate-pulse shadow-md shadow-emerald-500/30'
                    : 'text-slate-400 hover:text-white hover:bg-slate-800'
                }`}
                title={isDictating ? "Pause / Stop Dictation" : "Tap to Speak into Input Box"}
              >
                {isDictating ? <Pause className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
              </button>
            </div>

            {/* Send Button */}
            <button
              type="submit"
              disabled={!textInput.trim() || processing}
              className="bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-800 text-white disabled:text-slate-600 p-3.5 rounded-2xl transition-all shadow-md shrink-0 flex items-center justify-center active:scale-95"
              title="Send Message"
            >
              <Send className="w-5 h-5" />
            </button>
          </form>
        </div>

      </main>
    </div>
  );
}

"use client";

import { useEffect, useRef, useState } from "react";
import { Mic, MicOff, PhoneOff, Phone } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { voiceWsUrl } from "@/lib/voice-api";
import type { Agent } from "@/lib/types";

const INPUT_RATE = 16_000;
const INPUT_FRAME_SAMPLES = 320;
const OUTPUT_RATE = 24_000;

type CallState = "idle" | "connecting" | "listening" | "thinking" | "speaking" | "ended" | "error";

type VoiceEvent =
  | { type: "listening" }
  | { type: "speaking_started" }
  | { type: "speaking_ended"; interrupted?: boolean }
  | { type: "interrupted" }
  | { type: "transcript"; text?: string; interrupted?: boolean }
  | { type: "agent_text"; text?: string }
  | { type: "turn_end"; conversationId?: string | null }
  | { type: "done" };

interface VoiceControlsProps {
  agent?: Agent;
  thinkingEnabled: boolean;
  conversationId: string | null;
  onConversationIdChange: (conversationId: string | null) => void;
  onUserTranscript: (text: string) => void;
  onAgentText: (text: string) => void;
}

export function VoiceControls({
  agent,
  thinkingEnabled,
  conversationId,
  onConversationIdChange,
  onUserTranscript,
  onAgentText,
}: VoiceControlsProps) {
  const [muted, setMuted] = useState(false);
  const [calling, setCalling] = useState(false);
  const [callState, setCallState] = useState<CallState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [bars, setBars] = useState<number[]>(() => new Array(28).fill(8));

  const wsRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const outputSourcesRef = useRef<Set<AudioBufferSourceNode>>(new Set());
  const inputCarryRef = useRef<Float32Array>(new Float32Array(0));
  const outputTimeRef = useRef(0);
  const mutedRef = useRef(false);

  const active = calling && !muted && (callState === "listening" || callState === "speaking");
  const agentName = agent?.name ?? "Agent";

  useEffect(() => {
    mutedRef.current = muted;
  }, [muted]);

  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => {
      setBars((b) => b.map(() => 6 + Math.round(Math.random() * 36)));
    }, 110);
    return () => {
      clearInterval(id);
      setBars((b) => b.map(() => 8));
    };
  }, [active]);

  async function startCall() {
    if (!agent || calling) return;
    if (!navigator.mediaDevices?.getUserMedia) {
      setError("Microphone capture is not available in this browser.");
      setCallState("error");
      return;
    }

    setError(null);
    setMuted(false);
    setCalling(true);
    setCallState("connecting");

    try {
      const audioContext = new AudioContext();
      audioContextRef.current = audioContext;
      await audioContext.resume();

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      micStreamRef.current = stream;

      const ws = new WebSocket(voiceWsUrl("/ws/voice"));
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;

      ws.onmessage = (event) => {
        if (typeof event.data === "string") {
          handleControlMessage(event.data);
        } else {
          playPcmFrame(event.data, audioContext);
        }
      };
      ws.onclose = (event) => {
        if (event.reason) setError(event.reason);
        setCalling(false);
        setCallState((state) => (state === "error" ? state : "ended"));
        cleanupAudio();
      };
      ws.onerror = () => {
        setError("Voice connection failed.");
        setCallState("error");
      };

      await waitForOpen(ws);
      ws.onerror = () => {
        setError("Voice connection failed.");
        setCallState("error");
      };
      ws.send(JSON.stringify(buildStartFrame(agent, thinkingEnabled, conversationId)));
      startMicStreaming(stream, audioContext, ws);
      setCallState("thinking");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start the voice call.");
      setCalling(false);
      setCallState("error");
      wsRef.current?.close();
      cleanupAudio();
    }
  }

  function endCall() {
    wsRef.current?.close();
    cleanupAudio();
    setCalling(false);
    setCallState("ended");
    setMuted(false);
  }

  function handleControlMessage(raw: string) {
    let event: VoiceEvent;
    try {
      event = JSON.parse(raw) as VoiceEvent;
    } catch {
      return;
    }

    if (event.type === "listening") {
      setCallState("listening");
    } else if (event.type === "speaking_started") {
      setCallState("speaking");
    } else if (event.type === "speaking_ended") {
      setCallState("thinking");
      if (event.interrupted) stopPlayback();
    } else if (event.type === "interrupted") {
      stopPlayback();
      setCallState("listening");
    } else if (event.type === "transcript" && event.text) {
      setCallState("thinking");
      onUserTranscript(event.interrupted ? `Interrupted: ${event.text}` : event.text);
    } else if (event.type === "agent_text" && event.text) {
      onAgentText(event.text);
    } else if (event.type === "turn_end") {
      onConversationIdChange(event.conversationId ?? null);
    } else if (event.type === "done") {
      endCall();
    }
  }

  function startMicStreaming(stream: MediaStream, audioContext: AudioContext, ws: WebSocket) {
    const source = audioContext.createMediaStreamSource(stream);
    const processor = audioContext.createScriptProcessor(4096, 1, 1);
    sourceRef.current = source;
    processorRef.current = processor;

    processor.onaudioprocess = (event) => {
      const output = event.outputBuffer.getChannelData(0);
      output.fill(0);
      if (mutedRef.current || ws.readyState !== WebSocket.OPEN) return;

      const input = event.inputBuffer.getChannelData(0);
      const downsampled = downsample(input, audioContext.sampleRate, INPUT_RATE);
      const samples = concatFloat32(inputCarryRef.current, downsampled);
      let offset = 0;
      while (offset + INPUT_FRAME_SAMPLES <= samples.length) {
        const frame = samples.subarray(offset, offset + INPUT_FRAME_SAMPLES);
        ws.send(floatToInt16(frame));
        offset += INPUT_FRAME_SAMPLES;
      }
      inputCarryRef.current = samples.slice(offset);
    };

    source.connect(processor);
    processor.connect(audioContext.destination);
  }

  function playPcmFrame(data: ArrayBuffer, audioContext: AudioContext) {
    const int16 = new Int16Array(data);
    if (!int16.length) return;
    const pcm = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i += 1) {
      pcm[i] = Math.max(-1, int16[i] / 32768);
    }
    const samples = resample(pcm, OUTPUT_RATE, audioContext.sampleRate);
    const buffer = audioContext.createBuffer(1, samples.length, audioContext.sampleRate);
    buffer.copyToChannel(samples, 0);

    const source = audioContext.createBufferSource();
    source.buffer = buffer;
    source.connect(audioContext.destination);
    outputSourcesRef.current.add(source);
    source.onended = () => {
      outputSourcesRef.current.delete(source);
    };

    const startAt = Math.max(audioContext.currentTime + 0.04, outputTimeRef.current);
    source.start(startAt);
    outputTimeRef.current = startAt + buffer.duration;
  }

  function cleanupAudio() {
    const ws = wsRef.current;
    wsRef.current = null;
    if (ws && ws.readyState !== WebSocket.CLOSED && ws.readyState !== WebSocket.CLOSING) {
      ws.close();
    }

    processorRef.current?.disconnect();
    sourceRef.current?.disconnect();
    processorRef.current = null;
    sourceRef.current = null;
    inputCarryRef.current = new Float32Array(0);
    stopPlayback();

    micStreamRef.current?.getTracks().forEach((track) => track.stop());
    micStreamRef.current = null;

    const context = audioContextRef.current;
    audioContextRef.current = null;
    if (context && context.state !== "closed") {
      void context.close();
    }
  }

  function stopPlayback() {
    outputSourcesRef.current.forEach((source) => {
      try {
        source.stop();
      } catch {
        return;
      }
    });
    outputSourcesRef.current.clear();
    outputTimeRef.current = audioContextRef.current?.currentTime ?? 0;
  }

  useEffect(() => {
    const outputSources = outputSourcesRef.current;
    return () => {
      const ws = wsRef.current;
      wsRef.current = null;
      if (ws && ws.readyState !== WebSocket.CLOSED && ws.readyState !== WebSocket.CLOSING) {
        ws.close();
      }

      processorRef.current?.disconnect();
      sourceRef.current?.disconnect();
      micStreamRef.current?.getTracks().forEach((track) => track.stop());
      outputSources.forEach((source) => {
        try {
          source.stop();
        } catch {
          return;
        }
      });
      outputSources.clear();
      const context = audioContextRef.current;
      audioContextRef.current = null;
      if (context && context.state !== "closed") {
        void context.close();
      }
    };
  }, []);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Live voice test</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col items-center gap-5 pb-6">
        <div className="flex h-20 w-full items-center justify-center gap-1 overflow-hidden rounded-lg bg-[var(--muted)] px-3">
          {bars.map((h, i) => (
            <span
              key={i}
              className={cn(
                "w-1 rounded-full bg-[var(--foreground)]/70 transition-[height]",
                active ? "duration-100" : "duration-300",
              )}
              style={{ height: `${h}px` }}
            />
          ))}
        </div>

        <div className="text-center">
          <div className="text-sm font-medium">{agentName}</div>
          <div className="text-xs text-[var(--muted-foreground)]">
            {calling ? statusText(callState, muted) : agent ? "Ready to call" : "Select an agent first"}
          </div>
        </div>

        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="icon"
            className="h-11 w-11 rounded-full"
            disabled={!calling}
            onClick={() => setMuted((m) => !m)}
          >
            {muted ? <MicOff /> : <Mic />}
          </Button>
          <Button
            size="lg"
            className={cn(
              "h-12 gap-2 rounded-full px-6",
              calling && "bg-[var(--destructive)] text-[var(--destructive-foreground)] hover:bg-[var(--destructive)]/90",
            )}
            disabled={!agent && !calling}
            onClick={calling ? endCall : startCall}
          >
            {calling ? <PhoneOff /> : <Phone />}
            {calling ? "End call" : "Start call"}
          </Button>
        </div>

        {error && (
          <div className="w-full rounded-lg border border-[var(--border)] p-3 text-xs text-[var(--destructive)]">
            {error}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function buildStartFrame(agent: Agent, thinkingEnabled: boolean, conversationId: string | null) {
  return {
    type: "start",
    agent: agent.backendAgent || "runtime",
    agent_config: {
      config: {
        agent_id: agent.id,
        system_prompt: agent.systemPrompt,
        provider: agent.provider,
        model: agent.model,
        temperature: agent.temperature,
        max_tokens: agent.maxTokens ?? null,
        thinking_enabled: thinkingEnabled,
        history_limit: agent.historyLimit ?? 30,
        tool_groups: agent.toolGroups ?? [],
        ack: agent.ack ?? { enabled: false, phrases: [] },
        mcp_servers: agent.mcpServers ?? [],
        timeouts: agent.timeouts ?? {},
        tracing: agent.tracing ?? {},
      },
      greeting: `Hi, this is ${agent.name}.`,
      user_id: agent.userId,
    },
    params: {
      user_id: agent.userId,
      conversation_id: conversationId,
    },
    voice_config: agent.voiceConfig ?? {},
  };
}

function waitForOpen(ws: WebSocket) {
  return new Promise<void>((resolve, reject) => {
    ws.onopen = () => resolve();
    ws.onerror = () => reject(new Error("Voice connection failed."));
  });
}

function statusText(state: CallState, muted: boolean) {
  if (muted) return "Muted";
  if (state === "connecting") return "Connecting...";
  if (state === "listening") return "Listening...";
  if (state === "speaking") return "Speaking...";
  if (state === "thinking") return "Thinking...";
  if (state === "error") return "Call error";
  return "Call ended";
}

function downsample(input: Float32Array, fromRate: number, toRate: number) {
  if (fromRate === toRate) return new Float32Array(input);
  return resample(input, fromRate, toRate);
}

function resample(input: Float32Array, fromRate: number, toRate: number) {
  if (fromRate === toRate) return new Float32Array(input);
  const ratio = fromRate / toRate;
  const outputLength = Math.max(1, Math.floor(input.length / ratio));
  const output = new Float32Array(outputLength);
  for (let i = 0; i < outputLength; i += 1) {
    const position = i * ratio;
    const left = Math.floor(position);
    const right = Math.min(left + 1, input.length - 1);
    const weight = position - left;
    output[i] = input[left] * (1 - weight) + input[right] * weight;
  }
  return output;
}

function concatFloat32(a: Float32Array, b: Float32Array) {
  if (!a.length) return b;
  const out = new Float32Array(a.length + b.length);
  out.set(a, 0);
  out.set(b, a.length);
  return out;
}

function floatToInt16(input: Float32Array) {
  const out = new Int16Array(input.length);
  for (let i = 0; i < input.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, input[i]));
    out[i] = sample < 0 ? sample * 32768 : sample * 32767;
  }
  return out.buffer;
}

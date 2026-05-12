"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createLocalAudioTrack, LocalAudioTrack, RemoteAudioTrack, Room, RoomEvent } from "livekit-client";
import { Mic, MicOff, Phone, PhoneOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { Agent } from "@/lib/types";

type CallState = "idle" | "connecting" | "listening" | "thinking" | "speaking" | "ended" | "error";

interface LiveKitTokenResponse {
  token: string;
  serverUrl: string;
  roomName: string;
  participantName: string;
}

interface LiveKitVoiceControlsProps {
  agent?: Agent;
  thinkingEnabled: boolean;
  conversationId: string | null;
  onConversationIdChange: (conversationId: string | null) => void;
  onUserTranscript: (text: string) => void;
  onAgentText: (text: string) => void;
}

export function LiveKitVoiceControls({
  agent,
  thinkingEnabled,
  conversationId,
  onUserTranscript,
  onAgentText,
}: LiveKitVoiceControlsProps) {
  const [muted, setMuted] = useState(false);
  const [calling, setCalling] = useState(false);
  const [callState, setCallState] = useState<CallState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [bars, setBars] = useState<number[]>(() => new Array(28).fill(8));
  const roomRef = useRef<Room | null>(null);
  const micTrackRef = useRef<LocalAudioTrack | null>(null);
  const audioElementsRef = useRef<Set<HTMLMediaElement>>(new Set());
  const seenTranscriptIdsRef = useRef<Set<string>>(new Set());
  const mutedRef = useRef(false);

  const active = calling && !muted && (callState === "listening" || callState === "speaking");
  const agentName = agent?.name ?? "Agent";

  const detachAudioElements = useCallback(() => {
    audioElementsRef.current.forEach((element) => {
      element.remove();
    });
    audioElementsRef.current.clear();
  }, []);

  const cleanup = useCallback(() => {
    const mic = micTrackRef.current;
    micTrackRef.current = null;
    if (mic) {
      mic.stop();
      mic.detach();
    }
    detachAudioElements();
    const room = roomRef.current;
    roomRef.current = null;
    if (room?.state !== "disconnected") {
      room?.disconnect();
    }
    seenTranscriptIdsRef.current.clear();
  }, [detachAudioElements]);

  useEffect(() => {
    mutedRef.current = muted;
    if (!calling || muted) {
      micTrackRef.current?.mute();
    } else {
      micTrackRef.current?.unmute();
    }
  }, [calling, muted]);

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

  useEffect(() => () => cleanup(), [cleanup]);

  async function startCall() {
    if (!agent || calling) return;
    setError(null);
    setMuted(false);
    setCalling(true);
    setCallState("connecting");

    try {
      const tokenRes = await fetch("/api/livekit/token", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          agentId: agent.id,
          conversationId,
          thinkingEnabled,
        }),
      });
      if (!tokenRes.ok) throw new Error(await readError(tokenRes));
      const tokenData = (await tokenRes.json()) as LiveKitTokenResponse;

      const room = new Room({ adaptiveStream: true, dynacast: true });
      roomRef.current = room;
      wireRoomEvents(room);
      await room.connect(tokenData.serverUrl, tokenData.token);
      const mic = await createLocalAudioTrack({
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      });
      micTrackRef.current = mic;
      await room.localParticipant.publishTrack(mic);
      if (mutedRef.current) mic.mute();
      await room.startAudio();
      setCallState("listening");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start the LiveKit call.");
      setCallState("error");
      setCalling(false);
      cleanup();
    }
  }

  function endCall() {
    cleanup();
    setCalling(false);
    setCallState("ended");
    setMuted(false);
  }

  function wireRoomEvents(room: Room) {
    room
      .on(RoomEvent.ParticipantConnected, () => setCallState((state) => (state === "connecting" ? "listening" : state)))
      .on(RoomEvent.TrackSubscribed, (track) => {
        if (track.kind !== "audio") return;
        const element = (track as RemoteAudioTrack).attach();
        element.autoplay = true;
        audioElementsRef.current.add(element);
        document.body.appendChild(element);
        setCallState("speaking");
      })
      .on(RoomEvent.TrackUnsubscribed, (track) => {
        if (track.kind === "audio") (track as RemoteAudioTrack).detach();
        detachAudioElements();
        setCallState("listening");
      })
      .on(RoomEvent.Disconnected, () => {
        setCalling(false);
        setCallState((state) => (state === "error" ? state : "ended"));
        cleanup();
      });

    const transcriptionEvent =
      (RoomEvent as unknown as Record<string, string>).TranscriptionReceived || "transcriptionReceived";
    room.on(transcriptionEvent as RoomEvent, handleTranscription as (...args: unknown[]) => void);
  }

  function handleTranscription(segments: unknown, participant: unknown) {
    const rows = Array.isArray(segments) ? segments : [segments];
    for (const segment of rows) {
      if (!segment || typeof segment !== "object") continue;
      const data = segment as { id?: string; text?: string; final?: boolean; isFinal?: boolean };
      if (!data.text?.trim()) continue;
      if (data.final === false || data.isFinal === false) continue;
      const id = data.id || `${data.text}-${seenTranscriptIdsRef.current.size}`;
      if (seenTranscriptIdsRef.current.has(id)) continue;
      seenTranscriptIdsRef.current.add(id);

      const isLocal =
        typeof participant === "object" &&
        participant !== null &&
        "isLocal" in participant &&
        Boolean((participant as { isLocal?: boolean }).isLocal);
      if (isLocal) {
        setCallState("thinking");
        onUserTranscript(data.text);
      } else {
        setCallState("speaking");
        onAgentText(data.text);
      }
    }
  }

  return (
    <Card className="overflow-hidden">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm">LiveKit voice</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="rounded-lg border border-[var(--border)] bg-[var(--muted)] p-4">
          <div className="mb-4 flex items-center justify-between gap-4">
            <div>
              <p className="text-sm font-medium">{agentName}</p>
              <p className="text-xs capitalize text-[var(--muted-foreground)]">{callState.replace("-", " ")}</p>
            </div>
            <div
              className={cn(
                "size-3 rounded-full",
                calling && callState !== "error" ? "bg-emerald-500" : "bg-[var(--muted-foreground)]",
              )}
            />
          </div>
          <div className="flex h-16 items-end gap-1">
            {bars.map((height, i) => (
              <span
                key={i}
                className="w-full rounded-full bg-[var(--primary)] opacity-80 transition-all"
                style={{ height }}
              />
            ))}
          </div>
        </div>

        {error && <p className="text-xs text-[var(--destructive)]">{error}</p>}

        <div className="grid grid-cols-[1fr_auto] gap-2">
          {calling ? (
            <Button type="button" variant="destructive" onClick={endCall}>
              <PhoneOff /> End call
            </Button>
          ) : (
            <Button type="button" onClick={startCall} disabled={!agent}>
              <Phone /> Start call
            </Button>
          )}
          <Button
            type="button"
            variant="outline"
            size="icon"
            disabled={!calling}
            onClick={() => setMuted((value) => !value)}
            aria-label={muted ? "Unmute microphone" : "Mute microphone"}
          >
            {muted ? <MicOff /> : <Mic />}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

async function readError(res: Response) {
  const body = await res.json().catch(() => null);
  if (body?.error) return String(body.error);
  if (body?.detail) return String(body.detail);
  return `LiveKit call failed (${res.status})`;
}

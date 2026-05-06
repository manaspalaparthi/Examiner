import { Mic2, Play } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { voices } from "@/lib/mock-data";

const PROVIDER_LABEL: Record<string, string> = {
  elevenlabs: "ElevenLabs",
  openai: "OpenAI",
  deepgram: "Deepgram",
  playht: "PlayHT",
};

export default function VoiceSettingsPage() {
  return (
    <>
      <PageHeader
        title="Voice Settings"
        description="Manage the voice library and global defaults applied to new agents."
      />

      <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <section>
          <h2 className="mb-3 text-sm font-semibold">Voice library</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            {voices.map((v) => (
              <Card key={v.id}>
                <CardContent className="flex items-center gap-4 p-5">
                  <div className="flex size-10 items-center justify-center rounded-lg bg-[var(--muted)]">
                    <Mic2 className="size-5 text-[var(--muted-foreground)]" strokeWidth={1.75} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-sm font-semibold">{v.name}</span>
                      <Badge variant="muted" className="text-[10px]">
                        {PROVIDER_LABEL[v.provider]}
                      </Badge>
                    </div>
                    <div className="text-xs capitalize text-[var(--muted-foreground)]">
                      {[v.gender, v.accent].filter(Boolean).join(" · ")}
                    </div>
                  </div>
                  <Button variant="outline" size="icon" aria-label="Play sample">
                    <Play />
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>

        <Card className="self-start">
          <CardHeader>
            <CardTitle className="text-sm">Global defaults</CardTitle>
            <CardDescription>Applied to new agents unless overridden.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-5">
            <div className="grid gap-2">
              <Label>Default voice</Label>
              <Select defaultValue={voices[0]?.id}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {voices.map((v) => (
                    <SelectItem key={v.id} value={v.id}>
                      {v.name} · {PROVIDER_LABEL[v.provider]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <div className="flex items-center justify-between">
                <Label>Speech rate</Label>
                <span className="font-mono text-xs text-[var(--muted-foreground)]">1.00×</span>
              </div>
              <Slider min={0.5} max={1.5} step={0.05} defaultValue={[1]} />
            </div>
            <div className="grid gap-2">
              <div className="flex items-center justify-between">
                <Label>Stability</Label>
                <span className="font-mono text-xs text-[var(--muted-foreground)]">0.65</span>
              </div>
              <Slider min={0} max={1} step={0.05} defaultValue={[0.65]} />
            </div>
            <div className="flex items-center justify-between">
              <div>
                <Label>Background noise suppression</Label>
                <p className="text-xs text-[var(--muted-foreground)]">Reduce ambient noise on inbound audio.</p>
              </div>
              <Switch defaultChecked />
            </div>
            <div className="flex items-center justify-between">
              <div>
                <Label>Allow interruptions</Label>
                <p className="text-xs text-[var(--muted-foreground)]">Stop the agent when the caller speaks.</p>
              </div>
              <Switch defaultChecked />
            </div>
          </CardContent>
        </Card>
      </div>
    </>
  );
}

import type {
  Agent,
  AnalyticsSummary,
  Conversation,
  Integration,
  Voice,
} from "./types";

// Dev-only in-memory store. Replace with a real DB in production.

const now = Date.now();
const isoFromOffset = (mins: number) => new Date(now - mins * 60_000).toISOString();

export const voices: Voice[] = [
  { id: "af_heart", name: "Heart", provider: "kokoro", gender: "female", accent: "American" },
  { id: "v_aria", name: "Aria", provider: "elevenlabs", gender: "female", accent: "American" },
  { id: "v_orion", name: "Orion", provider: "elevenlabs", gender: "male", accent: "British" },
  { id: "v_nova", name: "Nova", provider: "openai", gender: "female", accent: "American" },
  { id: "v_alloy", name: "Alloy", provider: "openai", gender: "neutral" },
  { id: "v_river", name: "River", provider: "playht", gender: "neutral", accent: "American" },
  { id: "v_atlas", name: "Atlas", provider: "deepgram", gender: "male", accent: "Australian" },
  { id: "v_lumen", name: "Lumen", provider: "elevenlabs", gender: "female", accent: "Irish" },
  { id: "v_quill", name: "Quill", provider: "playht", gender: "male", accent: "American" },
];

export const agents: Agent[] = [
  {
    id: "agt_01",
    userId: "admin",
    name: "Sales Concierge",
    description: "Qualifies inbound leads and books demos on the calendar.",
    status: "active",
    backendAgent: "runtime",
    voiceId: "v_aria",
    provider: "openai",
    model: "gpt-4o",
    systemPrompt:
      "You are a friendly B2B sales concierge. Qualify leads using BANT and offer to book a demo on Tuesdays or Thursdays.",
    temperature: 0.4,
    tools: ["calendar.book", "crm.create_contact"],
    createdAt: isoFromOffset(60 * 24 * 14),
    updatedAt: isoFromOffset(45),
  },
  {
    id: "agt_02",
    userId: "admin",
    name: "Support Triage",
    description: "Routes incoming support calls and collects context.",
    status: "active",
    backendAgent: "runtime",
    voiceId: "v_orion",
    provider: "anthropic",
    model: "claude-sonnet-4-6",
    systemPrompt:
      "You are a calm support triage agent. Collect the customer's account email, the issue summary, and severity, then transfer to a human if urgent.",
    temperature: 0.2,
    tools: ["zendesk.create_ticket", "transfer.human"],
    createdAt: isoFromOffset(60 * 24 * 30),
    updatedAt: isoFromOffset(60 * 6),
  },
  {
    id: "agt_03",
    userId: "admin",
    name: "Appointment Reminder",
    description: "Confirms and reschedules appointments via outbound calls.",
    status: "active",
    backendAgent: "runtime",
    voiceId: "v_nova",
    provider: "openai",
    model: "gpt-4o-mini",
    systemPrompt:
      "Confirm the appointment for the caller. Offer two reschedule options if needed.",
    temperature: 0.3,
    tools: ["calendar.reschedule"],
    createdAt: isoFromOffset(60 * 24 * 7),
    updatedAt: isoFromOffset(60 * 24),
  },
  {
    id: "agt_04",
    userId: "admin",
    name: "Restaurant Host",
    description: "Takes reservations and answers menu questions.",
    status: "draft",
    backendAgent: "runtime",
    voiceId: "v_lumen",
    provider: "openai",
    model: "gpt-4o-mini",
    systemPrompt:
      "You are the host at Bistro Volta. Take reservations, share today's specials, and politely deflect off-topic questions.",
    temperature: 0.6,
    tools: ["opentable.book"],
    createdAt: isoFromOffset(60 * 24 * 2),
    updatedAt: isoFromOffset(60 * 2),
  },
  {
    id: "agt_05",
    userId: "admin",
    name: "Survey Caller",
    description: "Runs short post-purchase NPS surveys.",
    status: "archived",
    backendAgent: "runtime",
    voiceId: "v_river",
    provider: "openai",
    model: "gpt-4o-mini",
    systemPrompt: "Run a 3-question NPS survey. Be brief and respectful.",
    temperature: 0.3,
    tools: [],
    createdAt: isoFromOffset(60 * 24 * 60),
    updatedAt: isoFromOffset(60 * 24 * 30),
  },
];

const sampleTranscript = (agentName: string) => [
  { id: "m1", role: "agent" as const, content: `Hi, this is ${agentName}. How can I help you today?`, timestamp: isoFromOffset(15) },
  { id: "m2", role: "user" as const, content: "I'd like to schedule a demo for next week.", timestamp: isoFromOffset(14) },
  { id: "m3", role: "agent" as const, content: "Wonderful — I have Tuesday at 10am or Thursday at 2pm. Which works better?", timestamp: isoFromOffset(14) },
  { id: "m4", role: "user" as const, content: "Thursday at 2 sounds good.", timestamp: isoFromOffset(13) },
  { id: "m5", role: "agent" as const, content: "Great. I'll send a calendar invite to your email. Anything else I can help with?", timestamp: isoFromOffset(13) },
  { id: "m6", role: "user" as const, content: "That's all, thanks.", timestamp: isoFromOffset(12) },
];

export const conversations: Conversation[] = [
  {
    id: "cv_01",
    agentId: "agt_01",
    agentName: "Sales Concierge",
    callerNumber: "+1 (415) 555-2104",
    startedAt: isoFromOffset(12),
    durationSec: 184,
    status: "completed",
    messages: sampleTranscript("Sales Concierge"),
  },
  {
    id: "cv_02",
    agentId: "agt_02",
    agentName: "Support Triage",
    callerNumber: "+1 (212) 555-9012",
    startedAt: isoFromOffset(34),
    durationSec: 412,
    status: "completed",
    messages: sampleTranscript("Support Triage"),
  },
  {
    id: "cv_03",
    agentId: "agt_03",
    agentName: "Appointment Reminder",
    callerNumber: "+1 (646) 555-7781",
    startedAt: isoFromOffset(72),
    durationSec: 98,
    status: "completed",
    messages: sampleTranscript("Appointment Reminder"),
  },
  {
    id: "cv_04",
    agentId: "agt_01",
    agentName: "Sales Concierge",
    callerNumber: "+1 (917) 555-3344",
    startedAt: isoFromOffset(120),
    durationSec: 31,
    status: "failed",
    messages: sampleTranscript("Sales Concierge").slice(0, 2),
  },
  {
    id: "cv_05",
    agentId: "agt_02",
    agentName: "Support Triage",
    callerNumber: "+1 (305) 555-2200",
    startedAt: isoFromOffset(2),
    durationSec: 0,
    status: "in-progress",
    messages: sampleTranscript("Support Triage").slice(0, 3),
  },
  {
    id: "cv_06",
    agentId: "agt_03",
    agentName: "Appointment Reminder",
    callerNumber: "+1 (510) 555-7711",
    startedAt: isoFromOffset(220),
    durationSec: 142,
    status: "completed",
    messages: sampleTranscript("Appointment Reminder"),
  },
];

export const integrations: Integration[] = [
  { id: "int_twilio", name: "Twilio", description: "Programmable voice and SMS for inbound and outbound calls.", category: "telephony", connected: true, iconKey: "phone" },
  { id: "int_vonage", name: "Vonage", description: "Carrier-grade voice and SIP trunking.", category: "telephony", connected: false, iconKey: "phone" },
  { id: "int_slack", name: "Slack", description: "Send call summaries and transcripts to channels.", category: "messaging", connected: true, iconKey: "messages" },
  { id: "int_hubspot", name: "HubSpot", description: "Sync contacts and call activity to your CRM.", category: "crm", connected: false, iconKey: "users" },
  { id: "int_salesforce", name: "Salesforce", description: "Log calls and create opportunities automatically.", category: "crm", connected: false, iconKey: "users" },
  { id: "int_zapier", name: "Zapier", description: "Connect to 5000+ apps via Zapier triggers.", category: "automation", connected: true, iconKey: "zap" },
  { id: "int_webhook", name: "Webhooks", description: "POST events to your endpoint on every call.", category: "automation", connected: false, iconKey: "webhook" },
  { id: "int_segment", name: "Segment", description: "Stream call events into your warehouse.", category: "analytics", connected: false, iconKey: "chart" },
];

export const analyticsSummary: AnalyticsSummary = {
  activeAgents: agents.filter((a) => a.status === "active").length,
  callsToday: 248,
  avgDurationSec: 162,
  successRate: 0.927,
  callsLast7Days: [
    { date: "Mon", count: 184 },
    { date: "Tue", count: 221 },
    { date: "Wed", count: 248 },
    { date: "Thu", count: 196 },
    { date: "Fri", count: 263 },
    { date: "Sat", count: 132 },
    { date: "Sun", count: 248 },
  ],
  topAgents: [
    { agentId: "agt_01", name: "Sales Concierge", calls: 412 },
    { agentId: "agt_02", name: "Support Triage", calls: 298 },
    { agentId: "agt_03", name: "Appointment Reminder", calls: 187 },
  ],
};

export const TOOL_LIBRARY: { id: string; label: string; description: string }[] = [
  { id: "calendar.book", label: "Calendar — Book", description: "Create events on a connected calendar." },
  { id: "calendar.reschedule", label: "Calendar — Reschedule", description: "Move existing events to a new slot." },
  { id: "crm.create_contact", label: "CRM — Create Contact", description: "Push new leads into your CRM." },
  { id: "zendesk.create_ticket", label: "Zendesk — Create Ticket", description: "File a support ticket from a call." },
  { id: "transfer.human", label: "Transfer to Human", description: "Hand off the call to a live agent." },
  { id: "opentable.book", label: "OpenTable — Book", description: "Make a restaurant reservation." },
];

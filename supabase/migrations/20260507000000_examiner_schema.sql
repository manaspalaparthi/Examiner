create extension if not exists pgcrypto;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create table if not exists public.agents (
  id text primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  description text not null default '',
  status text not null default 'draft'
    check (status in ('active', 'draft', 'archived')),
  backend_agent text not null default 'runtime',
  config_path text,
  voice_id text not null default 'af_heart',
  provider text not null,
  model text not null,
  system_prompt text not null default '',
  temperature double precision not null default 0.3,
  max_tokens int,
  history_limit int not null default 30,
  tools text[] not null default array[]::text[],
  tool_groups text[] not null default array[]::text[],
  ack jsonb not null default '{}',
  mcp_servers jsonb not null default '[]',
  timeouts jsonb not null default '{}',
  tracing jsonb not null default '{}',
  voice_config jsonb not null default '{}',
  agent_config jsonb not null default '{}',
  start_params jsonb not null default '{}',
  metadata jsonb not null default '{}',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists agents_status_updated_idx
  on public.agents (status, updated_at desc);

create index if not exists agents_user_updated_idx
  on public.agents (user_id, updated_at desc);

create index if not exists agents_backend_idx
  on public.agents (backend_agent);

drop trigger if exists agents_set_updated_at on public.agents;
create trigger agents_set_updated_at
before update on public.agents
for each row execute function public.set_updated_at();

create table if not exists public.conversations (
  id uuid primary key default gen_random_uuid(),
  agent_id text not null references public.agents(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  system_prompt text not null,
  provider text not null,
  model text not null,
  metadata jsonb not null default '{}',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists conversations_user_updated_idx
  on public.conversations (user_id, updated_at desc);

create index if not exists conversations_agent_updated_idx
  on public.conversations (agent_id, updated_at desc);

drop trigger if exists conversations_set_updated_at on public.conversations;
create trigger conversations_set_updated_at
before update on public.conversations
for each row execute function public.set_updated_at();

create table if not exists public.messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.conversations(id) on delete cascade,
  parent_id uuid references public.messages(id),
  role text not null,
  kind text not null,
  content text,
  content_json jsonb,
  tool_name text,
  tool_call_id text,
  latency_ms int,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  metadata jsonb not null default '{}'
);

create index if not exists messages_conversation_created_idx
  on public.messages (conversation_id, created_at);

drop trigger if exists messages_set_updated_at on public.messages;
create trigger messages_set_updated_at
before update on public.messages
for each row execute function public.set_updated_at();

create table if not exists public.traces (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.conversations(id) on delete cascade,
  message_id uuid references public.messages(id),
  event text not null,
  started_at timestamptz not null default now(),
  ended_at timestamptz,
  latency_ms int,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  metadata jsonb not null default '{}'
);

create index if not exists traces_conversation_started_idx
  on public.traces (conversation_id, started_at);

drop trigger if exists traces_set_updated_at on public.traces;
create trigger traces_set_updated_at
before update on public.traces
for each row execute function public.set_updated_at();

alter table public.agents enable row level security;
alter table public.conversations enable row level security;
alter table public.messages enable row level security;
alter table public.traces enable row level security;

drop policy if exists "agents owner access" on public.agents;
create policy "agents owner access"
on public.agents
for all
to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

drop policy if exists "conversations owner access" on public.conversations;
create policy "conversations owner access"
on public.conversations
for all
to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

drop policy if exists "messages owner access" on public.messages;
create policy "messages owner access"
on public.messages
for all
to authenticated
using (
  exists (
    select 1 from public.conversations c
    where c.id = messages.conversation_id
      and c.user_id = (select auth.uid())
  )
)
with check (
  exists (
    select 1 from public.conversations c
    where c.id = messages.conversation_id
      and c.user_id = (select auth.uid())
  )
);

drop policy if exists "traces owner access" on public.traces;
create policy "traces owner access"
on public.traces
for all
to authenticated
using (
  exists (
    select 1 from public.conversations c
    where c.id = traces.conversation_id
      and c.user_id = (select auth.uid())
  )
)
with check (
  exists (
    select 1 from public.conversations c
    where c.id = traces.conversation_id
      and c.user_id = (select auth.uid())
  )
);

alter table public.agents replica identity full;
alter table public.conversations replica identity full;
alter table public.messages replica identity full;
alter table public.traces replica identity full;

alter publication supabase_realtime add table public.agents;
alter publication supabase_realtime add table public.conversations;
alter publication supabase_realtime add table public.messages;
alter publication supabase_realtime add table public.traces;

comment on publication supabase_realtime is
  'Examiner uses an explicit realtime allowlist. For future synced tables: add owner-aware RLS, then add the table to this publication in a migration.';

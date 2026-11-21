-- Run once in the Supabase SQL Editor (adds what the agent and UI need)
alter table messages add column if not exists sources jsonb;
alter table messages add column if not exists meta jsonb;
alter table companies add column if not exists handled_by text not null default 'agent';
alter table companies add column if not exists needs_human boolean not null default false;
alter table companies add column if not exists score_breakdown jsonb;
alter table evidence add column if not exists trigger_kind text;

create table if not exists events (
  id uuid primary key default gen_random_uuid(),
  company_id uuid references companies(id) on delete cascade,
  kind text not null,
  detail text,
  created_at timestamptz default now()
);
alter table events enable row level security;

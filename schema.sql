-- Full database schema (Supabase / Postgres). Row security is on, so only the backend's secret key can read it.
create extension if not exists pgcrypto;

create table companies (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  website text,
  domain text unique,
  description text,
  est_revenue text,
  est_employees text,
  sales_channels text[],
  contact_name text,
  contact_role text,
  contact_email text,
  score int check (score between 0 and 100),
  score_breakdown jsonb,
  status text not null default 'new' check (status in
    ('new','qualified','rejected','email_drafted','contacted','replied','booked','do_not_contact')),
  handled_by text not null default 'agent',
  needs_human boolean not null default false,
  created_at timestamptz default now()
);

create table evidence (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references companies(id) on delete cascade,
  kind text not null check (kind in ('fit','trigger','fact')),
  trigger_kind text,
  claim text not null,
  quote text,
  source_url text not null,
  created_at timestamptz default now()
);

create table messages (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references companies(id) on delete cascade,
  direction text not null check (direction in ('out','in')),
  subject text,
  body text not null,
  status text not null default 'draft' check (status in ('draft','approved','rejected','sent','received')),
  author text not null default 'agent' check (author in ('agent','human','prospect')),
  needs_human boolean default false,
  flags jsonb default '[]'::jsonb,
  sources jsonb,
  meta jsonb,
  created_at timestamptz default now()
);

create table bookings (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references companies(id) on delete cascade,
  start_time timestamptz not null,
  calcom_uid text,
  status text default 'booked',
  created_at timestamptz default now()
);

create table do_not_contact (
  id uuid primary key default gen_random_uuid(),
  company_id uuid references companies(id) on delete cascade,
  email text,
  reason text,
  created_at timestamptz default now()
);

create table events (
  id uuid primary key default gen_random_uuid(),
  company_id uuid references companies(id) on delete cascade,
  kind text not null,
  detail text,
  created_at timestamptz default now()
);

alter table companies enable row level security;
alter table evidence enable row level security;
alter table messages enable row level security;
alter table bookings enable row level security;
alter table do_not_contact enable row level security;
alter table events enable row level security;

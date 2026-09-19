-- Chai Hai order receiver: run this once in the Supabase SQL editor.

create table if not exists customers (
  id bigint generated always as identity primary key,
  phone text not null unique,
  wa_profile_name text default '',
  shop_name text,
  preferred_language text,
  created_at timestamptz not null default now()
);

create table if not exists products (
  id text primary key,
  name text not null,
  price numeric,              -- not used in the MVP
  active boolean not null default true
);

create table if not exists product_aliases (
  id bigint generated always as identity primary key,
  product_id text not null references products(id),
  alias text not null,
  customer_id bigint references customers(id),   -- null = applies to everyone
  source text not null default 'seed',
  unique (product_id, alias, customer_id)
);

create table if not exists messages (
  id bigint generated always as identity primary key,
  wa_message_id text unique,
  customer_id bigint references customers(id),
  direction text not null check (direction in ('in','out')),
  type text not null,
  body text default '',
  raw_payload jsonb,
  created_at timestamptz not null default now()
);
create index if not exists messages_customer_idx on messages (customer_id, direction, created_at desc);

create table if not exists orders (
  id bigint generated always as identity primary key,
  customer_id bigint not null references customers(id),
  status text not null default 'pending_review'
    check (status in ('pending_review','approved','rejected','cancelled')),
  language text,
  original_text text default '',
  approval_wa_message_id text,
  approval_history text[] not null default '{}',
  created_at timestamptz not null default now(),
  approved_at timestamptz
);
create index if not exists orders_customer_status_idx on orders (customer_id, status);

create table if not exists order_items (
  id bigint generated always as identity primary key,
  order_id bigint not null references orders(id) on delete cascade,
  product_id text references products(id),      -- null = unknown flavour
  packs integer check (packs is null or packs > 0),
  raw_text text default '',
  confidence real
);
create index if not exists order_items_order_idx on order_items (order_id);

create table if not exists order_events (
  id bigint generated always as identity primary key,
  order_id bigint not null references orders(id) on delete cascade,
  type text not null,
  message_id bigint references messages(id),
  before jsonb,
  after jsonb,
  created_at timestamptz not null default now()
);

create table if not exists config (
  key text primary key,
  value text
);

-- The service uses the service-role key, which bypasses RLS. Enabling RLS with no
-- policies blocks the public anon key from reading customer data.
alter table customers enable row level security;
alter table products enable row level security;
alter table product_aliases enable row level security;
alter table messages enable row level security;
alter table orders enable row level security;
alter table order_items enable row level security;
alter table order_events enable row level security;
alter table config enable row level security;

-- Seed the 7 flavours and starter aliases.
insert into products (id, name) values
  ('masala','Masala'),('ginger','Ginger'),('cardamom','Cardamom'),('pink','Pink'),
  ('karak','Karak'),('classic','Classic'),('coffee','Coffee')
on conflict (id) do nothing;

insert into product_aliases (product_id, alias) values
  ('masala','masala'),('masala','masale wali'),('masala','ਮਸਾਲਾ'),
  ('ginger','ginger'),('ginger','adrak'),('ginger','adrak wali'),('ginger','ਅਦਰਕ'),
  ('cardamom','cardamom'),('cardamom','elaichi'),('cardamom','ilaichi'),('cardamom','elachi'),('cardamom','ਇਲਾਇਚੀ'),
  ('pink','pink'),('pink','pink chai'),('pink','kashmiri'),('pink','gulabi'),
  ('karak','karak'),('karak','kadak'),('karak','kadak chai'),('karak','ਕੜਕ'),
  ('classic','classic'),('classic','regular'),('classic','plain'),('classic','sada'),('classic','normal'),
  ('coffee','coffee'),('coffee','kaafi'),('coffee','ਕੌਫੀ')
on conflict do nothing;

-- Phase 2: device credentials + pairing support.
-- Devices authenticate to /ws/agent with a scoped credential; only its
-- SHA-256 hash is stored. Pairing codes likewise stored as SHA-256 hex text.

alter table public.devices
  add column if not exists credential_hash text;

-- Store code hashes as hex text (simpler PostgREST equality matching).
alter table public.device_pairing_requests
  alter column code_hash type text using encode(code_hash, 'hex');

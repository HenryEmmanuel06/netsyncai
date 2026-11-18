-- Stable PC fingerprint for devices: lets a re-paired machine resume its
-- existing device record (same device_id) instead of minting a duplicate
-- that stays offline forever.
ALTER TABLE devices
  ADD COLUMN IF NOT EXISTS machine_id TEXT;

CREATE INDEX IF NOT EXISTS devices_machine_idx
  ON devices (owner_id, machine_id);

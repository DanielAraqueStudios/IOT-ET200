-- AlterTable: remote kill-switch for device access — a disabled device
-- fails MQTT auth (see cloud/broker/auth.py:check_device_token) without
-- needing its token rotated/re-issued.
ALTER TABLE "User" ADD COLUMN "enabled" BOOLEAN NOT NULL DEFAULT true;

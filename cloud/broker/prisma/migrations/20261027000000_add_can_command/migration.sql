-- AlterTable: topic ACL flag — only identities with canCommand=true may
-- PUBLISH to a "/command" topic (see cloud/broker/broker.py).
ALTER TABLE "User" ADD COLUMN "canCommand" BOOLEAN NOT NULL DEFAULT false;

CREATE TABLE "url_outbox" (
	"event_id" uuid PRIMARY KEY NOT NULL,
	"topic" text NOT NULL,
	"aggregate_key" text NOT NULL,
	"payload" jsonb NOT NULL,
	"created_at" timestamp with time zone NOT NULL,
	"published_at" timestamp with time zone,
	"attempts" integer DEFAULT 0 NOT NULL,
	"next_attempt_at" timestamp with time zone DEFAULT now() NOT NULL,
	"locked_until" timestamp with time zone,
	"lock_owner" uuid,
	"last_error" text
);
--> statement-breakpoint
ALTER TABLE "urls" ADD COLUMN "owner_id" uuid;--> statement-breakpoint
CREATE INDEX "url_outbox_pending_idx" ON "url_outbox" USING btree ("next_attempt_at") WHERE "url_outbox"."published_at" is null;
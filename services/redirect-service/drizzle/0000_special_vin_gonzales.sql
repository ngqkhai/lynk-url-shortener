CREATE TABLE "redirect_urls" (
	"short_code" text PRIMARY KEY NOT NULL,
	"original_url" text NOT NULL,
	"expires_at" timestamp with time zone,
	"synced_at" timestamp with time zone DEFAULT now() NOT NULL
);

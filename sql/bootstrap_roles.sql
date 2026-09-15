-- Run as ShaktiDB administrator in your dedicated eaildb database.
-- Review names and ownership locally. No passwords are embedded here.
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='eail_runtime') THEN
  CREATE ROLE eail_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
 END IF;
END $$;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO eail_runtime;
GRANT SELECT,INSERT,UPDATE,DELETE ON eail_documents,eail_chunks,eail_ingestion,eail_facts,eail_actions,eail_tasks TO eail_runtime;
-- In interactive psql: \password eail_runtime
-- Schema ownership remains with the administrative owner.
-- Application ACLs are enforced by EAIL; this script does not claim database RLS.

-- Run once as a Postgres superuser (make db-setup does this locally; docker-compose mounts it
-- into /docker-entrypoint-initdb.d). Creates the two roles and the two databases.
--
--   groundwork_owner  owns the tables, runs migrations and fixture loads. Row-level security does
--                     not apply to a table's owner, so admin tasks (seed, reset) work across orgs
--                     without BYPASSRLS, which managed Postgres will not grant (ADR 0007).
--   groundwork_app    what the API and worker use. No BYPASSRLS, not a table owner, so
--                     row-level security always applies. Grants are set in the migrations.
--
-- Passwords are development-only defaults, matching .env.example. The hosted demo creates the
-- same roles with random passwords: `groundwork hosted-bootstrap` (docs/HOSTING.md).

SELECT 'CREATE ROLE groundwork_owner LOGIN NOBYPASSRLS PASSWORD ''groundwork_owner_dev'''
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'groundwork_owner')\gexec

-- Earlier versions gave the owner BYPASSRLS; take it away so local matches hosted.
SELECT 'ALTER ROLE groundwork_owner NOBYPASSRLS'
WHERE EXISTS (SELECT FROM pg_roles WHERE rolname = 'groundwork_owner' AND rolbypassrls)\gexec

SELECT 'CREATE ROLE groundwork_app LOGIN NOBYPASSRLS PASSWORD ''groundwork_app_dev'''
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'groundwork_app')\gexec

SELECT 'CREATE DATABASE groundwork OWNER groundwork_owner'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'groundwork')\gexec

SELECT 'CREATE DATABASE groundwork_test OWNER groundwork_owner'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'groundwork_test')\gexec

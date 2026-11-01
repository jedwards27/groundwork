-- Run once as a Postgres superuser (make db-setup does this locally; docker-compose mounts it
-- into /docker-entrypoint-initdb.d). Creates the two roles and the two databases.
--
--   groundwork_owner  owns the tables, runs migrations and fixture loads. BYPASSRLS so admin
--                     tasks (seed, reset) can work across orgs.
--   groundwork_app    what the API and worker use. No BYPASSRLS, not a table owner, so
--                     row-level security always applies. Grants are set in the migrations.
--
-- Passwords are development-only defaults, matching .env.example.

SELECT 'CREATE ROLE groundwork_owner LOGIN BYPASSRLS PASSWORD ''groundwork_owner_dev'''
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'groundwork_owner')\gexec

SELECT 'CREATE ROLE groundwork_app LOGIN NOBYPASSRLS PASSWORD ''groundwork_app_dev'''
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'groundwork_app')\gexec

SELECT 'CREATE DATABASE groundwork OWNER groundwork_owner'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'groundwork')\gexec

SELECT 'CREATE DATABASE groundwork_test OWNER groundwork_owner'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'groundwork_test')\gexec

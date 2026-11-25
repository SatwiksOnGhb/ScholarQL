\set ON_ERROR_STOP on
\getenv reader_password SCHOLARQL_READER_PASSWORD
SELECT format('CREATE ROLE scholarql_reader LOGIN PASSWORD %L', :'reader_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'scholarql_reader')
\gexec
SELECT format('ALTER ROLE scholarql_reader LOGIN PASSWORD %L', :'reader_password')
\gexec

ALTER ROLE scholarql_reader SET default_transaction_read_only = on;
ALTER ROLE scholarql_reader SET statement_timeout = '8s';
ALTER ROLE scholarql_reader SET idle_in_transaction_session_timeout = '15s';
SELECT format('GRANT CONNECT ON DATABASE %I TO scholarql_reader', current_database())
\gexec
GRANT USAGE ON SCHEMA public TO scholarql_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO scholarql_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO scholarql_reader;
REVOKE EXECUTE ON PROCEDURE compute_pagerank(integer, double precision) FROM PUBLIC;
REVOKE EXECUTE ON PROCEDURE refresh_analytics() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION citation_chain(text, integer) TO scholarql_reader;
GRANT EXECUTE ON FUNCTION coauthors(text) TO scholarql_reader;

-- Capture before/after an approved backup while idle; no database writes.
BEGIN READ ONLY;
SET LOCAL search_path = public, pg_catalog;
SET LOCAL TIME ZONE 'UTC';
WITH table_data AS (
 SELECT 'users' AS name, count(*) AS count,
   md5(coalesce(string_agg(md5(row_to_json(t)::text), '' ORDER BY id), '')) AS fingerprint FROM users t
 UNION ALL SELECT 'posts', count(*), md5(coalesce(string_agg(md5(row_to_json(t)::text), '' ORDER BY id), '')) FROM posts t
 UNION ALL SELECT 'comments', count(*), md5(coalesce(string_agg(md5(row_to_json(t)::text), '' ORDER BY id), '')) FROM comments t
 UNION ALL SELECT 'founder_identity', count(*), md5(coalesce(string_agg(md5(row_to_json(t)::text), '' ORDER BY id), '')) FROM founder_identity t
 UNION ALL SELECT 'role_change_audit', count(*), md5(coalesce(string_agg(md5(row_to_json(t)::text), '' ORDER BY id), '')) FROM role_change_audit t
 UNION ALL SELECT 'flyway_schema_history', count(*), md5(coalesce(string_agg(md5(row_to_json(t)::text), '' ORDER BY installed_rank), '')) FROM flyway_schema_history t
), structure AS (
 SELECT 'column:'||table_name||':'||ordinal_position AS key,
   concat_ws('|', column_name, data_type, character_maximum_length, datetime_precision,
             is_nullable, column_default, is_identity, identity_generation) AS definition
 FROM information_schema.columns WHERE table_schema='public'
 UNION ALL SELECT 'constraint:'||c.relname||':'||con.conname, pg_get_constraintdef(con.oid)
 FROM pg_constraint con JOIN pg_class c ON c.oid=con.conrelid
 JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public'
 UNION ALL SELECT 'constraint_flags:'||c.relname||':'||con.conname,
   concat_ws('|', con.contype, con.convalidated, con.condeferrable, con.condeferred,
             con.connoinherit, con.confmatchtype, con.confupdtype, con.confdeltype)
 FROM pg_constraint con JOIN pg_class c ON c.oid=con.conrelid
 JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public'
 UNION ALL SELECT 'index:'||tablename||':'||indexname, indexdef FROM pg_indexes WHERE schemaname='public'
 UNION ALL SELECT 'sequence:'||sequencename,
   concat_ws('|', start_value, min_value, max_value, increment_by, cycle, cache_size)
 FROM pg_sequences WHERE schemaname='public'
)
SELECT json_build_object(
 'database_name', current_database(),
 'tables', (SELECT json_object_agg(name,json_build_object('count',count,'fingerprint',fingerprint)) FROM table_data),
 'schema_fingerprint', (SELECT md5(coalesce(string_agg(key||':'||definition, '|' ORDER BY key),'')) FROM structure),
 'schema_definitions', (SELECT json_object_agg(key,definition ORDER BY key) FROM structure),
 'sequences', (SELECT coalesce(json_agg(json_build_object('name',sequencename,'last_value',last_value) ORDER BY sequencename),'[]') FROM pg_sequences WHERE schemaname='public'),
 'identities', (SELECT coalesce(json_agg(json_build_object('id',id,'username',username,'role',role) ORDER BY id),'[]') FROM users),
 'founders', (SELECT coalesce(json_agg(json_build_object('id',id,'user_id',user_id) ORDER BY id),'[]') FROM founder_identity),
 'role_counts', (SELECT coalesce(json_object_agg(role,total),'{}') FROM (SELECT role,count(*) AS total FROM users GROUP BY role) r),
 'migrations', (SELECT coalesce(json_agg(json_build_object('version',version,'checksum',checksum,'success',success) ORDER BY installed_rank),'[]') FROM flyway_schema_history),
 'invalid_links', (SELECT count(*) FROM posts p LEFT JOIN users u ON u.id=p.author_id WHERE u.id IS NULL)
   + (SELECT count(*) FROM comments c LEFT JOIN posts p ON p.id=c.post_id WHERE p.id IS NULL)
   + (SELECT count(*) FROM comments c LEFT JOIN users u ON u.id=c.user_id WHERE c.user_id IS NOT NULL AND u.id IS NULL)
   + (SELECT count(*) FROM role_change_audit a LEFT JOIN users u ON u.id=a.actor_id LEFT JOIN users v ON v.id=a.target_user_id WHERE u.id IS NULL OR v.id IS NULL),
 'database_size_bytes', pg_database_size(current_database())
);
COMMIT;

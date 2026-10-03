\set ON_ERROR_STOP on

BEGIN TRANSACTION READ ONLY;

\echo 'Day 5 schema check: required tables and view'
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN ('workspaces', 'users', 'catalog_items', 'workspace_catalog_summary')
ORDER BY table_name;

\echo 'Day 5 seed check: workspace summary'
SELECT slug, workspace_name, item_count, catalog_value_cents
FROM workspace_catalog_summary
ORDER BY workspace_id;

\echo 'Day 5 read-only join check: active Atlas catalog'
SELECT w.slug, i.sku, i.name, i.price_cents
FROM workspaces AS w
JOIN catalog_items AS i ON i.workspace_id = w.id
WHERE w.slug = 'atlas'
  AND i.status = 'active'
ORDER BY i.sku;

DO $$
DECLARE
    workspace_count INTEGER;
    user_count INTEGER;
    item_count INTEGER;
    atlas_active_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO workspace_count FROM workspaces;
    SELECT COUNT(*) INTO user_count FROM users;
    SELECT COUNT(*) INTO item_count FROM catalog_items;
    SELECT COUNT(*) INTO atlas_active_count
    FROM catalog_items AS i
    JOIN workspaces AS w ON w.id = i.workspace_id
    WHERE w.slug = 'atlas'
      AND i.status = 'active';

    IF workspace_count <> 2 THEN
        RAISE EXCEPTION 'expected 2 workspaces, found %', workspace_count;
    END IF;
    IF user_count <> 3 THEN
        RAISE EXCEPTION 'expected 3 users, found %', user_count;
    END IF;
    IF item_count <> 4 THEN
        RAISE EXCEPTION 'expected 4 catalog items, found %', item_count;
    END IF;
    IF atlas_active_count <> 2 THEN
        RAISE EXCEPTION 'expected 2 active Atlas items, found %', atlas_active_count;
    END IF;
END
$$;

\echo 'Day 5 database verification: PASS'

ROLLBACK;

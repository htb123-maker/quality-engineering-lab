\set ON_ERROR_STOP on

INSERT INTO workspaces (id, slug, name)
VALUES
    (1, 'atlas', 'Atlas Workspace'),
    (2, 'orbit', 'Orbit Workspace')
ON CONFLICT (id) DO NOTHING;

INSERT INTO users (id, workspace_id, email, display_name, role, status)
VALUES
    (1, 1, 'owner@atlas.example', 'Atlas Owner', 'owner', 'active'),
    (2, 1, 'viewer@atlas.example', 'Atlas Viewer', 'viewer', 'active'),
    (3, 2, 'admin@orbit.example', 'Orbit Admin', 'admin', 'active')
ON CONFLICT (id) DO NOTHING;

INSERT INTO catalog_items (id, workspace_id, sku, name, price_cents, status)
VALUES
    (1, 1, 'LAB-001', 'Starter Sensor', 1299, 'active'),
    (2, 1, 'LAB-002', 'Calibration Kit', 4599, 'active'),
    (3, 1, 'LAB-003', 'Retired Probe', 999, 'archived'),
    (4, 2, 'ORB-001', 'Orbit Controller', 7999, 'active')
ON CONFLICT (id) DO NOTHING;

SELECT setval(
    pg_get_serial_sequence('workspaces', 'id'),
    COALESCE((SELECT MAX(id) FROM workspaces), 1),
    true
);

SELECT setval(
    pg_get_serial_sequence('users', 'id'),
    COALESCE((SELECT MAX(id) FROM users), 1),
    true
);

SELECT setval(
    pg_get_serial_sequence('catalog_items', 'id'),
    COALESCE((SELECT MAX(id) FROM catalog_items), 1),
    true
);

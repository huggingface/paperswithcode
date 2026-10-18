-- mHC now has its own method (add_mhc_method.sql); stop tagging
-- manifold-constrained hyper-connections papers as plain Hyper-Connections.
UPDATE methods
SET keywords = 'Hyper-Connections, Hyper Connections, HyperConnections, hyper-connection, dynamic hyper-connections, static hyper-connections',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'hyper-connections';

-- Export vehicle master rows in the DispatchVehicle JSON/table shape used by
-- the dispatch optimizer, CLI sample, and front-end sample input.

SELECT
    v.`vehicle_id`,
    v.`vehicle_type`,
    1 AS `is_available`,
    COALESCE(v.`capacity`, 0.00) AS `kg_capacity`,
    v.`pallet_capacity`,
    v.`tub_capacity`,
    v.`trolley_capacity`,
    v.`stillage_capacity`,
    JSON_OBJECT(
        'rego', v.`rego`,
        'source', 'vehicle master export',
        'raw_capacity', v.`capacity`,
        'shelf_count', v.`shelf_count`,
        'fuel_card_shell', v.`fuel_card_shell`,
        'fuel_card_bp_plus', v.`fuel_card_bp_plus`,
        'linkt_ref', v.`linkt_ref`,
        'service_period', v.`service_period`
    ) AS `metadata`
FROM `vehicle` v
ORDER BY v.`vehicle_id`;

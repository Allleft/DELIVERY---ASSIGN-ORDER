-- Populate dispatch_vehicle_snapshot from vehicle master data.
-- Requires @dispatch_batch_id to be set before running this script.
-- Vehicle availability defaults to 1 at snapshot time.

SET @dispatch_batch_id = COALESCE(@dispatch_batch_id, 1);

INSERT INTO `dispatch_vehicle_snapshot` (
    `dispatch_batch_id`,
    `vehicle_id`,
    `vehicle_type`,
    `is_available`,
    `kg_capacity`,
    `pallet_capacity`,
    `tub_capacity`,
    `trolley_capacity`,
    `stillage_capacity`
)
SELECT
    @dispatch_batch_id AS `dispatch_batch_id`,
    v.`vehicle_id`,
    v.`vehicle_type`,
    1 AS `is_available`,
    COALESCE(v.`capacity`, 0.00) AS `kg_capacity`,
    v.`pallet_capacity`,
    v.`tub_capacity`,
    v.`trolley_capacity`,
    v.`stillage_capacity`
FROM `vehicle` v
ON DUPLICATE KEY UPDATE
    `vehicle_type` = VALUES(`vehicle_type`),
    `is_available` = VALUES(`is_available`),
    `kg_capacity` = VALUES(`kg_capacity`),
    `pallet_capacity` = VALUES(`pallet_capacity`),
    `tub_capacity` = VALUES(`tub_capacity`),
    `trolley_capacity` = VALUES(`trolley_capacity`),
    `stillage_capacity` = VALUES(`stillage_capacity`);

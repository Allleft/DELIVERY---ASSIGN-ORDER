-- Import vehicle base master data from data/raw/vehicle-raw-data.csv.
-- Flow: raw CSV -> vehicle_raw_import staging -> vehicle master table.
-- Duplicate rego rows are treated as the same vehicle; the last imported row wins.

DROP TABLE IF EXISTS `vehicle_raw_import`;

CREATE TABLE `vehicle_raw_import` (
    `vehicle_raw_import_id` BIGINT NOT NULL AUTO_INCREMENT,
    `rego` VARCHAR(50) NULL,
    `vehicle_type` VARCHAR(100) NULL,
    `capacity` VARCHAR(50) NULL,
    `tub_capacity` VARCHAR(50) NULL,
    `pallet_capacity` VARCHAR(50) NULL,
    `trolley_capacity` VARCHAR(50) NULL,
    `stillage_capacity` VARCHAR(50) NULL,
    `shelf_count` VARCHAR(50) NULL,
    `fuel_card_shell` VARCHAR(100) NULL,
    `fuel_card_bp_plus` VARCHAR(100) NULL,
    `linkt_ref` VARCHAR(100) NULL,
    `service_period` VARCHAR(100) NULL,
    `imported_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`vehicle_raw_import_id`),
    KEY `idx_vehicle_raw_import_rego` (`rego`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET @vehicle_raw_csv_path = 'C:/Users/Albert Fang/Desktop/Delivery/data/raw/vehicle-raw-data.csv';
TRUNCATE TABLE `vehicle_raw_import`;

SET @vehicle_raw_load_sql = CONCAT(
    "LOAD DATA LOCAL INFILE '",
    REPLACE(@vehicle_raw_csv_path, "\\", "\\\\"),
    "' INTO TABLE `vehicle_raw_import` ",
    "CHARACTER SET utf8mb4 ",
    "FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '\"' ",
    "LINES TERMINATED BY '\\r\\n' ",
    "IGNORE 1 LINES ",
    "(`rego`, `vehicle_type`, `capacity`, `tub_capacity`, `pallet_capacity`, `trolley_capacity`, `stillage_capacity`, `shelf_count`, `fuel_card_shell`, `fuel_card_bp_plus`, `linkt_ref`, `service_period`)"
);

PREPARE vehicle_raw_load_stmt FROM @vehicle_raw_load_sql;
EXECUTE vehicle_raw_load_stmt;
DEALLOCATE PREPARE vehicle_raw_load_stmt;

-- Sanity check: inspect duplicate rego rows before the upsert if needed.
SELECT
    TRIM(`rego`) AS `rego`,
    COUNT(*) AS `duplicate_row_count`
FROM `vehicle_raw_import`
WHERE NULLIF(TRIM(`rego`), '') IS NOT NULL
GROUP BY TRIM(`rego`)
HAVING COUNT(*) > 1;

INSERT INTO `vehicle` (
    `rego`,
    `vehicle_type`,
    `capacity`,
    `tub_capacity`,
    `pallet_capacity`,
    `trolley_capacity`,
    `stillage_capacity`,
    `shelf_count`,
    `fuel_card_shell`,
    `fuel_card_bp_plus`,
    `linkt_ref`,
    `service_period`
)
SELECT
    deduped.`rego`,
    deduped.`vehicle_type`,
    deduped.`capacity_value`,
    deduped.`tub_capacity_value`,
    deduped.`pallet_capacity_value`,
    deduped.`trolley_capacity_value`,
    deduped.`stillage_capacity_value`,
    deduped.`shelf_count_value`,
    deduped.`fuel_card_shell_value`,
    deduped.`fuel_card_bp_plus_value`,
    deduped.`linkt_ref_value`,
    deduped.`service_period_value`
FROM (
    SELECT
        TRIM(`rego`) AS `rego`,
        TRIM(`vehicle_type`) AS `vehicle_type`,
        CAST(NULLIF(TRIM(`capacity`), '') AS DECIMAL(10, 2)) AS `capacity_value`,
        COALESCE(CAST(NULLIF(TRIM(`tub_capacity`), '') AS UNSIGNED), 0) AS `tub_capacity_value`,
        COALESCE(CAST(NULLIF(TRIM(`pallet_capacity`), '') AS UNSIGNED), 0) AS `pallet_capacity_value`,
        COALESCE(CAST(NULLIF(TRIM(`trolley_capacity`), '') AS UNSIGNED), 0) AS `trolley_capacity_value`,
        COALESCE(CAST(NULLIF(TRIM(`stillage_capacity`), '') AS UNSIGNED), 0) AS `stillage_capacity_value`,
        COALESCE(CAST(NULLIF(TRIM(`shelf_count`), '') AS UNSIGNED), 0) AS `shelf_count_value`,
        NULLIF(TRIM(`fuel_card_shell`), '') AS `fuel_card_shell_value`,
        NULLIF(TRIM(`fuel_card_bp_plus`), '') AS `fuel_card_bp_plus_value`,
        NULLIF(TRIM(`linkt_ref`), '') AS `linkt_ref_value`,
        NULLIF(TRIM(`service_period`), '') AS `service_period_value`,
        ROW_NUMBER() OVER (
            PARTITION BY TRIM(`rego`)
            ORDER BY `vehicle_raw_import_id` DESC
        ) AS `row_rank`
    FROM `vehicle_raw_import`
    WHERE NULLIF(TRIM(`rego`), '') IS NOT NULL
) AS deduped
WHERE deduped.`row_rank` = 1
ON DUPLICATE KEY UPDATE
    `vehicle_type` = VALUES(`vehicle_type`),
    `capacity` = VALUES(`capacity`),
    `tub_capacity` = VALUES(`tub_capacity`),
    `pallet_capacity` = VALUES(`pallet_capacity`),
    `trolley_capacity` = VALUES(`trolley_capacity`),
    `stillage_capacity` = VALUES(`stillage_capacity`),
    `shelf_count` = VALUES(`shelf_count`),
    `fuel_card_shell` = VALUES(`fuel_card_shell`),
    `fuel_card_bp_plus` = VALUES(`fuel_card_bp_plus`),
    `linkt_ref` = VALUES(`linkt_ref`),
    `service_period` = VALUES(`service_period`);

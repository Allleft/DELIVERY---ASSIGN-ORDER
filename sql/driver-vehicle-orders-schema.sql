-- Driver / Vehicle / Orders schema
-- Assumption: MySQL 8.0+ using InnoDB and utf8mb4.
-- Table names use snake_case while preserving the ERD structure.
-- Includes zone, postcode, and laundry master seed data.

CREATE TABLE `driver` (
    `driver_id` INT NOT NULL AUTO_INCREMENT,
    `name` VARCHAR(255) NOT NULL,
    `license_no` VARCHAR(100) NOT NULL,
    `email` VARCHAR(255) NULL,
    `phone_number` VARCHAR(100) NULL,
    `branch_no` VARCHAR(50) NULL,
    `default_start_location` VARCHAR(255) NULL,
    `default_end_location` VARCHAR(255) NULL,
    PRIMARY KEY (`driver_id`),
    UNIQUE KEY `uq_driver_license_no` (`license_no`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `vehicle` (
    `vehicle_id` INT NOT NULL AUTO_INCREMENT,
    `rego` VARCHAR(50) NOT NULL,
    `vehicle_type` VARCHAR(100) NOT NULL,
    `capacity` DECIMAL(10, 2) NULL,
    `tub_capacity` INT UNSIGNED NOT NULL DEFAULT 0,
    `pallet_capacity` INT UNSIGNED NOT NULL DEFAULT 0,
    `trolley_capacity` INT UNSIGNED NOT NULL DEFAULT 0,
    `stillage_capacity` INT UNSIGNED NOT NULL DEFAULT 0,
    `shelf_count` INT UNSIGNED NOT NULL DEFAULT 0,
    `fuel_card_shell` VARCHAR(100) NULL,
    `fuel_card_bp_plus` VARCHAR(100) NULL,
    `linkt_ref` VARCHAR(100) NULL,
    `service_period` VARCHAR(100) NULL,
    PRIMARY KEY (`vehicle_id`),
    UNIQUE KEY `uq_vehicle_rego` (`rego`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `zone` (
    `zone_id` INT NOT NULL AUTO_INCREMENT,
    `zone_code` VARCHAR(50) NOT NULL,
    `zone_name` VARCHAR(100) NOT NULL,
    `notes` TEXT NULL,
    `is_active` TINYINT(1) NOT NULL DEFAULT 1,
    PRIMARY KEY (`zone_id`),
    UNIQUE KEY `uq_zone_code` (`zone_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `driver_vehicle_assignment` (
    `assignment_id` INT NOT NULL AUTO_INCREMENT,
    `driver_id` INT NOT NULL,
    `vehicle_id` INT NOT NULL,
    `assigned_from` DATE NOT NULL,
    `assigned_to` DATE NULL,
    `is_active` TINYINT(1) NOT NULL DEFAULT 1,
    PRIMARY KEY (`assignment_id`),
    KEY `idx_assignment_driver_id` (`driver_id`),
    KEY `idx_assignment_vehicle_id` (`vehicle_id`),
    CONSTRAINT `fk_assignment_driver`
        FOREIGN KEY (`driver_id`) REFERENCES `driver` (`driver_id`),
    CONSTRAINT `fk_assignment_vehicle`
        FOREIGN KEY (`vehicle_id`) REFERENCES `vehicle` (`vehicle_id`),
    CONSTRAINT `chk_assignment_dates`
        CHECK (`assigned_to` IS NULL OR `assigned_to` >= `assigned_from`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `dispatch_run` (
    `dispatch_run_id` INT NOT NULL AUTO_INCREMENT,
    `assignment_id` INT NOT NULL,
    `zone_id` INT NOT NULL,
    `run_date` DATE NOT NULL,
    PRIMARY KEY (`dispatch_run_id`),
    KEY `idx_dispatch_run_assignment_id` (`assignment_id`),
    KEY `idx_dispatch_run_zone_id` (`zone_id`),
    KEY `idx_dispatch_run_run_date` (`run_date`),
    CONSTRAINT `fk_dispatch_run_assignment`
        FOREIGN KEY (`assignment_id`) REFERENCES `driver_vehicle_assignment` (`assignment_id`),
    CONSTRAINT `fk_dispatch_run_zone`
        FOREIGN KEY (`zone_id`) REFERENCES `zone` (`zone_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `orders` (
    `order_id` INT NOT NULL AUTO_INCREMENT,
    `dispatch_run_id` INT NULL,
    `zone_id` INT NULL,
    `customer_name` VARCHAR(255) NULL,
    `invoice_id` VARCHAR(100) NOT NULL,
    `delivery_address` VARCHAR(255) NOT NULL,
    `suburb` VARCHAR(100) NULL,
    `postcode` VARCHAR(20) NULL,
    `products` TEXT NULL,
    `kg_count` DECIMAL(10, 2) NULL,
    `pallet_count` INT UNSIGNED NOT NULL DEFAULT 0,
    `bag_count` INT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (`order_id`),
    KEY `idx_orders_dispatch_run_id` (`dispatch_run_id`),
    KEY `idx_orders_zone_id` (`zone_id`),
    KEY `idx_orders_invoice_id` (`invoice_id`),
    CONSTRAINT `fk_orders_dispatch_run`
        FOREIGN KEY (`dispatch_run_id`) REFERENCES `dispatch_run` (`dispatch_run_id`),
    CONSTRAINT `fk_orders_zone`
        FOREIGN KEY (`zone_id`) REFERENCES `zone` (`zone_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `daily_run_sheet` (
    `daily_run_sheet_id` INT NOT NULL AUTO_INCREMENT,
    `run_date` DATE NOT NULL,
    `driver_id` INT NOT NULL,
    `start_time` TIME NULL,
    `loading_started_time` TIME NULL,
    `loading_completed_time` TIME NULL,
    `finish_time` TIME NULL,
    PRIMARY KEY (`daily_run_sheet_id`),
    KEY `idx_daily_run_sheet_driver_id` (`driver_id`),
    KEY `idx_daily_run_sheet_run_date` (`run_date`),
    CONSTRAINT `fk_daily_run_sheet_driver`
        FOREIGN KEY (`driver_id`) REFERENCES `driver` (`driver_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `daily_run_sheet_item` (
    `daily_run_sheet_item_id` INT NOT NULL AUTO_INCREMENT,
    `daily_run_sheet_id` INT NOT NULL,
    `order_id` INT NOT NULL,
    `line_no` INT NOT NULL,
    `time_in` TIME NULL,
    `time_out` TIME NULL,
    `print_name` VARCHAR(255) NULL,
    `comments` TEXT NULL,
    `signature_text` VARCHAR(255) NULL,
    `pallets_returned` INT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (`daily_run_sheet_item_id`),
    UNIQUE KEY `uq_daily_run_sheet_item_line_no` (`daily_run_sheet_id`, `line_no`),
    UNIQUE KEY `uq_daily_run_sheet_item_order` (`daily_run_sheet_id`, `order_id`),
    KEY `idx_daily_run_sheet_item_order_id` (`order_id`),
    CONSTRAINT `fk_daily_run_sheet_item_sheet`
        FOREIGN KEY (`daily_run_sheet_id`) REFERENCES `daily_run_sheet` (`daily_run_sheet_id`),
    CONSTRAINT `fk_daily_run_sheet_item_order`
        FOREIGN KEY (`order_id`) REFERENCES `orders` (`order_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `op_shop` (
    `op_shop_id` INT NOT NULL AUTO_INCREMENT,
    `name` VARCHAR(255) NOT NULL,
    `suburb` VARCHAR(100) NOT NULL,
    `is_active` TINYINT(1) NOT NULL DEFAULT 1,
    PRIMARY KEY (`op_shop_id`),
    UNIQUE KEY `uq_op_shop_name_suburb` (`name`, `suburb`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `op_shop_collection_sheet` (
    `op_shop_collection_sheet_id` INT NOT NULL AUTO_INCREMENT,
    `pick_up_date` DATE NOT NULL,
    `driver_id` INT NOT NULL,
    `vehicle_id` INT NOT NULL,
    PRIMARY KEY (`op_shop_collection_sheet_id`),
    KEY `idx_op_shop_collection_sheet_pick_up_date` (`pick_up_date`),
    KEY `idx_op_shop_collection_sheet_driver_id` (`driver_id`),
    KEY `idx_op_shop_collection_sheet_vehicle_id` (`vehicle_id`),
    CONSTRAINT `fk_op_shop_collection_sheet_driver`
        FOREIGN KEY (`driver_id`) REFERENCES `driver` (`driver_id`),
    CONSTRAINT `fk_op_shop_collection_sheet_vehicle`
        FOREIGN KEY (`vehicle_id`) REFERENCES `vehicle` (`vehicle_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `op_shop_collection_item` (
    `op_shop_collection_item_id` INT NOT NULL AUTO_INCREMENT,
    `op_shop_collection_sheet_id` INT NOT NULL,
    `op_shop_id` INT NOT NULL,
    `line_no` INT NOT NULL,
    `time_in` TIME NULL,
    `time_out` TIME NULL,
    `clothing_kg` DECIMAL(10, 2) NULL,
    `shoes_kg` DECIMAL(10, 2) NULL,
    `trolleys_out_to_opshops` INT UNSIGNED NOT NULL DEFAULT 0,
    `trolleys_in_to_mccc` INT UNSIGNED NOT NULL DEFAULT 0,
    `hard_toys` INT UNSIGNED NOT NULL DEFAULT 0,
    `soft_toys` INT UNSIGNED NOT NULL DEFAULT 0,
    `black_bags` INT UNSIGNED NOT NULL DEFAULT 0,
    `shoe_bags` INT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (`op_shop_collection_item_id`),
    UNIQUE KEY `uq_op_shop_collection_item_line_no` (`op_shop_collection_sheet_id`, `line_no`),
    KEY `idx_op_shop_collection_item_op_shop_id` (`op_shop_id`),
    CONSTRAINT `fk_op_shop_collection_item_sheet`
        FOREIGN KEY (`op_shop_collection_sheet_id`) REFERENCES `op_shop_collection_sheet` (`op_shop_collection_sheet_id`),
    CONSTRAINT `fk_op_shop_collection_item_op_shop`
        FOREIGN KEY (`op_shop_id`) REFERENCES `op_shop` (`op_shop_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `laundry_site` (
    `laundry_site_id` INT NOT NULL AUTO_INCREMENT,
    `supplier_name` VARCHAR(255) NOT NULL,
    `site_name` VARCHAR(255) NOT NULL,
    `address_line1` VARCHAR(255) NULL,
    `suburb` VARCHAR(100) NULL,
    `postcode` VARCHAR(20) NULL,
    `hours_notes` TEXT NULL,
    `contact_name` VARCHAR(255) NULL,
    `contact_phone` VARCHAR(100) NULL,
    `contact_email` VARCHAR(255) NULL,
    `access_notes` TEXT NULL,
    `pricing_notes` TEXT NULL,
    `general_notes` TEXT NULL,
    `is_active` TINYINT(1) NOT NULL DEFAULT 1,
    PRIMARY KEY (`laundry_site_id`),
    UNIQUE KEY `uq_laundry_site_supplier_site_suburb` (`supplier_name`, `site_name`, `suburb`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `laundry_pickup_route` (
    `laundry_pickup_route_id` INT NOT NULL AUTO_INCREMENT,
    `route_name` VARCHAR(255) NOT NULL,
    `sheet_variant` ENUM('STANDARD', 'WEIGHT_ONLY', 'HYBRID') NOT NULL DEFAULT 'STANDARD',
    `default_vehicle_note` VARCHAR(255) NULL,
    `general_notes` TEXT NULL,
    `is_active` TINYINT(1) NOT NULL DEFAULT 1,
    PRIMARY KEY (`laundry_pickup_route_id`),
    UNIQUE KEY `uq_laundry_pickup_route_name` (`route_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `laundry_container_type` (
    `laundry_container_type_id` INT NOT NULL AUTO_INCREMENT,
    `code` VARCHAR(50) NOT NULL,
    `name` VARCHAR(100) NOT NULL,
    PRIMARY KEY (`laundry_container_type_id`),
    UNIQUE KEY `uq_laundry_container_type_code` (`code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `laundry_action_type` (
    `laundry_action_type_id` INT NOT NULL AUTO_INCREMENT,
    `code` VARCHAR(100) NOT NULL,
    `name` VARCHAR(150) NOT NULL,
    PRIMARY KEY (`laundry_action_type_id`),
    UNIQUE KEY `uq_laundry_action_type_code` (`code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `laundry_weight_category` (
    `laundry_weight_category_id` INT NOT NULL AUTO_INCREMENT,
    `code` VARCHAR(100) NOT NULL,
    `name` VARCHAR(150) NOT NULL,
    PRIMARY KEY (`laundry_weight_category_id`),
    UNIQUE KEY `uq_laundry_weight_category_code` (`code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `laundry_pickup_route_stop` (
    `laundry_pickup_route_stop_id` INT NOT NULL AUTO_INCREMENT,
    `laundry_pickup_route_id` INT NOT NULL,
    `laundry_site_id` INT NOT NULL,
    `stop_no` INT NOT NULL,
    `display_title` VARCHAR(255) NULL,
    `stop_notes` TEXT NULL,
    PRIMARY KEY (`laundry_pickup_route_stop_id`),
    UNIQUE KEY `uq_laundry_pickup_route_stop_route_stop_no` (`laundry_pickup_route_id`, `stop_no`),
    KEY `idx_laundry_pickup_route_stop_site_id` (`laundry_site_id`),
    CONSTRAINT `fk_laundry_pickup_route_stop_route`
        FOREIGN KEY (`laundry_pickup_route_id`) REFERENCES `laundry_pickup_route` (`laundry_pickup_route_id`),
    CONSTRAINT `fk_laundry_pickup_route_stop_site`
        FOREIGN KEY (`laundry_site_id`) REFERENCES `laundry_site` (`laundry_site_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `laundry_pickup_route_stop_action_type` (
    `laundry_pickup_route_stop_action_type_id` INT NOT NULL AUTO_INCREMENT,
    `laundry_pickup_route_stop_id` INT NOT NULL,
    `laundry_action_type_id` INT NOT NULL,
    PRIMARY KEY (`laundry_pickup_route_stop_action_type_id`),
    UNIQUE KEY `uq_laundry_route_stop_action_type` (`laundry_pickup_route_stop_id`, `laundry_action_type_id`),
    KEY `idx_laundry_route_stop_action_type_action_id` (`laundry_action_type_id`),
    CONSTRAINT `fk_laundry_route_stop_action_type_stop`
        FOREIGN KEY (`laundry_pickup_route_stop_id`) REFERENCES `laundry_pickup_route_stop` (`laundry_pickup_route_stop_id`),
    CONSTRAINT `fk_laundry_route_stop_action_type_action`
        FOREIGN KEY (`laundry_action_type_id`) REFERENCES `laundry_action_type` (`laundry_action_type_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `laundry_pickup_route_stop_weight_category` (
    `laundry_pickup_route_stop_weight_category_id` INT NOT NULL AUTO_INCREMENT,
    `laundry_pickup_route_stop_id` INT NOT NULL,
    `laundry_weight_category_id` INT NOT NULL,
    PRIMARY KEY (`laundry_pickup_route_stop_weight_category_id`),
    UNIQUE KEY `uq_laundry_route_stop_weight_category` (`laundry_pickup_route_stop_id`, `laundry_weight_category_id`),
    KEY `idx_laundry_route_stop_weight_category_weight_id` (`laundry_weight_category_id`),
    CONSTRAINT `fk_laundry_route_stop_weight_category_stop`
        FOREIGN KEY (`laundry_pickup_route_stop_id`) REFERENCES `laundry_pickup_route_stop` (`laundry_pickup_route_stop_id`),
    CONSTRAINT `fk_laundry_route_stop_weight_category_weight`
        FOREIGN KEY (`laundry_weight_category_id`) REFERENCES `laundry_weight_category` (`laundry_weight_category_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `laundry_pickup_sheet` (
    `laundry_pickup_sheet_id` INT NOT NULL AUTO_INCREMENT,
    `laundry_pickup_route_id` INT NOT NULL,
    `pick_up_date` DATE NOT NULL,
    `driver_id` INT NOT NULL,
    `vehicle_id` INT NOT NULL,
    `sheet_notes` TEXT NULL,
    PRIMARY KEY (`laundry_pickup_sheet_id`),
    KEY `idx_laundry_pickup_sheet_route_id` (`laundry_pickup_route_id`),
    KEY `idx_laundry_pickup_sheet_pick_up_date` (`pick_up_date`),
    KEY `idx_laundry_pickup_sheet_driver_id` (`driver_id`),
    KEY `idx_laundry_pickup_sheet_vehicle_id` (`vehicle_id`),
    CONSTRAINT `fk_laundry_pickup_sheet_route`
        FOREIGN KEY (`laundry_pickup_route_id`) REFERENCES `laundry_pickup_route` (`laundry_pickup_route_id`),
    CONSTRAINT `fk_laundry_pickup_sheet_driver`
        FOREIGN KEY (`driver_id`) REFERENCES `driver` (`driver_id`),
    CONSTRAINT `fk_laundry_pickup_sheet_vehicle`
        FOREIGN KEY (`vehicle_id`) REFERENCES `vehicle` (`vehicle_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `laundry_pickup_sheet_stop` (
    `laundry_pickup_sheet_stop_id` INT NOT NULL AUTO_INCREMENT,
    `laundry_pickup_sheet_id` INT NOT NULL,
    `laundry_pickup_route_stop_id` INT NOT NULL,
    `weighed_by` VARCHAR(255) NULL,
    `total_weight_kg` DECIMAL(10, 2) NULL,
    `stop_execution_notes` TEXT NULL,
    PRIMARY KEY (`laundry_pickup_sheet_stop_id`),
    UNIQUE KEY `uq_laundry_pickup_sheet_stop_route_stop` (`laundry_pickup_sheet_id`, `laundry_pickup_route_stop_id`),
    KEY `idx_laundry_pickup_sheet_stop_route_stop_id` (`laundry_pickup_route_stop_id`),
    CONSTRAINT `fk_laundry_pickup_sheet_stop_sheet`
        FOREIGN KEY (`laundry_pickup_sheet_id`) REFERENCES `laundry_pickup_sheet` (`laundry_pickup_sheet_id`),
    CONSTRAINT `fk_laundry_pickup_sheet_stop_route_stop`
        FOREIGN KEY (`laundry_pickup_route_stop_id`) REFERENCES `laundry_pickup_route_stop` (`laundry_pickup_route_stop_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `laundry_pickup_sheet_stop_swap` (
    `laundry_pickup_sheet_stop_swap_id` INT NOT NULL AUTO_INCREMENT,
    `laundry_pickup_sheet_stop_id` INT NOT NULL,
    `direction` ENUM('IN_TO_MCC', 'OUT_TO_SUPPLIER') NOT NULL,
    `laundry_container_type_id` INT NOT NULL,
    `qty` INT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (`laundry_pickup_sheet_stop_swap_id`),
    UNIQUE KEY `uq_laundry_sheet_stop_swap` (`laundry_pickup_sheet_stop_id`, `direction`, `laundry_container_type_id`),
    KEY `idx_laundry_sheet_stop_swap_container_id` (`laundry_container_type_id`),
    CONSTRAINT `fk_laundry_sheet_stop_swap_stop`
        FOREIGN KEY (`laundry_pickup_sheet_stop_id`) REFERENCES `laundry_pickup_sheet_stop` (`laundry_pickup_sheet_stop_id`),
    CONSTRAINT `fk_laundry_sheet_stop_swap_container`
        FOREIGN KEY (`laundry_container_type_id`) REFERENCES `laundry_container_type` (`laundry_container_type_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `laundry_pickup_sheet_stop_action` (
    `laundry_pickup_sheet_stop_action_id` INT NOT NULL AUTO_INCREMENT,
    `laundry_pickup_sheet_stop_id` INT NOT NULL,
    `laundry_action_type_id` INT NOT NULL,
    `is_required` TINYINT(1) NOT NULL DEFAULT 0,
    `notes` TEXT NULL,
    PRIMARY KEY (`laundry_pickup_sheet_stop_action_id`),
    UNIQUE KEY `uq_laundry_sheet_stop_action` (`laundry_pickup_sheet_stop_id`, `laundry_action_type_id`),
    KEY `idx_laundry_sheet_stop_action_type_id` (`laundry_action_type_id`),
    CONSTRAINT `fk_laundry_sheet_stop_action_stop`
        FOREIGN KEY (`laundry_pickup_sheet_stop_id`) REFERENCES `laundry_pickup_sheet_stop` (`laundry_pickup_sheet_stop_id`),
    CONSTRAINT `fk_laundry_sheet_stop_action_type`
        FOREIGN KEY (`laundry_action_type_id`) REFERENCES `laundry_action_type` (`laundry_action_type_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `laundry_pickup_sheet_stop_weight` (
    `laundry_pickup_sheet_stop_weight_id` INT NOT NULL AUTO_INCREMENT,
    `laundry_pickup_sheet_stop_id` INT NOT NULL,
    `laundry_weight_category_id` INT NOT NULL,
    `kg_value` DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    PRIMARY KEY (`laundry_pickup_sheet_stop_weight_id`),
    UNIQUE KEY `uq_laundry_sheet_stop_weight` (`laundry_pickup_sheet_stop_id`, `laundry_weight_category_id`),
    KEY `idx_laundry_sheet_stop_weight_category_id` (`laundry_weight_category_id`),
    CONSTRAINT `fk_laundry_sheet_stop_weight_stop`
        FOREIGN KEY (`laundry_pickup_sheet_stop_id`) REFERENCES `laundry_pickup_sheet_stop` (`laundry_pickup_sheet_stop_id`),
    CONSTRAINT `fk_laundry_sheet_stop_weight_category`
        FOREIGN KEY (`laundry_weight_category_id`) REFERENCES `laundry_weight_category` (`laundry_weight_category_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `zone_postcode` (
    `zone_postcode_id` INT NOT NULL AUTO_INCREMENT,
    `zone_id` INT NOT NULL,
    `postcode` CHAR(4) NOT NULL,
    `notes` VARCHAR(255) NULL,
    PRIMARY KEY (`zone_postcode_id`),
    UNIQUE KEY `uq_zone_postcode` (`zone_id`, `postcode`),
    KEY `idx_zone_postcode_postcode` (`postcode`),
    KEY `idx_zone_postcode_zone_id` (`zone_id`),
    CONSTRAINT `fk_zone_postcode_zone`
        FOREIGN KEY (`zone_id`) REFERENCES `zone` (`zone_id`),
    CONSTRAINT `chk_zone_postcode_format`
        CHECK (`postcode` REGEXP '^[0-9]{4}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO zone (zone_code, zone_name, notes, is_active)
VALUES
    ('LOCAL', 'Local', NULL, 1),
    ('WEST', 'West', '3011-3077 (full VIC west mapping in current raw source).', 1),
    ('MAJOR_EAST', 'Major East', 'Source rules recorded in zone-postcode-raw-data.csv. Source ranges: 312x, 313x.', 1),
    ('SOUTH_EAST', 'South East', 'Source rules recorded in zone-postcode-raw-data.csv. Source ranges: 314x-316x, 317x, 318x-320x, 380x-397x.', 1);

INSERT INTO zone_postcode (zone_id, postcode, notes)
SELECT z.zone_id, p.postcode, p.notes
FROM zone z
JOIN (
    SELECT 'MAJOR_EAST' AS zone_code, '3120' AS postcode, '312x' AS notes
    UNION ALL SELECT 'MAJOR_EAST', '3121', '312x'
    UNION ALL SELECT 'MAJOR_EAST', '3122', '312x'
    UNION ALL SELECT 'MAJOR_EAST', '3123', '312x'
    UNION ALL SELECT 'MAJOR_EAST', '3124', '312x'
    UNION ALL SELECT 'MAJOR_EAST', '3125', '312x'
    UNION ALL SELECT 'MAJOR_EAST', '3126', '312x'
    UNION ALL SELECT 'MAJOR_EAST', '3127', '312x'
    UNION ALL SELECT 'MAJOR_EAST', '3128', '312x'
    UNION ALL SELECT 'MAJOR_EAST', '3129', '312x'
    UNION ALL SELECT 'MAJOR_EAST', '3130', '313x'
    UNION ALL SELECT 'MAJOR_EAST', '3131', '313x'
    UNION ALL SELECT 'MAJOR_EAST', '3132', '313x'
    UNION ALL SELECT 'MAJOR_EAST', '3133', '313x'
    UNION ALL SELECT 'MAJOR_EAST', '3134', '313x'
    UNION ALL SELECT 'MAJOR_EAST', '3135', '313x'
    UNION ALL SELECT 'MAJOR_EAST', '3136', '313x'
    UNION ALL SELECT 'MAJOR_EAST', '3137', '313x'
    UNION ALL SELECT 'MAJOR_EAST', '3138', '313x'
    UNION ALL SELECT 'MAJOR_EAST', '3139', '313x'
    UNION ALL SELECT 'SOUTH_EAST', '3140', '314x-316x'
    UNION ALL SELECT 'SOUTH_EAST', '3141', '314x-316x'
    UNION ALL SELECT 'SOUTH_EAST', '3142', '314x-316x'
    UNION ALL SELECT 'SOUTH_EAST', '3143', '314x-316x'
    UNION ALL SELECT 'SOUTH_EAST', '3144', '314x-316x'
    UNION ALL SELECT 'SOUTH_EAST', '3145', '314x-316x'
    UNION ALL SELECT 'SOUTH_EAST', '3146', '314x-316x'
    UNION ALL SELECT 'SOUTH_EAST', '3147', '314x-316x'
    UNION ALL SELECT 'SOUTH_EAST', '3148', '314x-316x'
    UNION ALL SELECT 'SOUTH_EAST', '3149', '314x-316x'
    UNION ALL SELECT 'SOUTH_EAST', '3150', '314x-316x'
    UNION ALL SELECT 'SOUTH_EAST', '3151', '314x-316x'
    UNION ALL SELECT 'SOUTH_EAST', '3152', '314x-316x'
    UNION ALL SELECT 'SOUTH_EAST', '3153', '314x-316x'
    UNION ALL SELECT 'SOUTH_EAST', '3154', '314x-316x'
    UNION ALL SELECT 'SOUTH_EAST', '3155', '314x-316x'
    UNION ALL SELECT 'SOUTH_EAST', '3156', '314x-316x'
    UNION ALL SELECT 'SOUTH_EAST', '3157', '314x-316x'
    UNION ALL SELECT 'SOUTH_EAST', '3158', '314x-316x'
    UNION ALL SELECT 'SOUTH_EAST', '3159', '314x-316x'
    UNION ALL SELECT 'SOUTH_EAST', '3160', '314x-316x'
    UNION ALL SELECT 'SOUTH_EAST', '3161', '314x-316x'
    UNION ALL SELECT 'SOUTH_EAST', '3162', '314x-316x'
    UNION ALL SELECT 'SOUTH_EAST', '3163', '314x-316x'
    UNION ALL SELECT 'SOUTH_EAST', '3164', '314x-316x'
    UNION ALL SELECT 'SOUTH_EAST', '3165', '314x-316x'
    UNION ALL SELECT 'SOUTH_EAST', '3166', '314x-316x'
    UNION ALL SELECT 'SOUTH_EAST', '3167', '314x-316x'
    UNION ALL SELECT 'SOUTH_EAST', '3168', '314x-316x'
    UNION ALL SELECT 'SOUTH_EAST', '3169', '314x-316x'
    UNION ALL SELECT 'SOUTH_EAST', '3170', '317x'
    UNION ALL SELECT 'SOUTH_EAST', '3171', '317x'
    UNION ALL SELECT 'SOUTH_EAST', '3172', '317x'
    UNION ALL SELECT 'SOUTH_EAST', '3173', '317x'
    UNION ALL SELECT 'SOUTH_EAST', '3174', '317x'
    UNION ALL SELECT 'SOUTH_EAST', '3175', '317x'
    UNION ALL SELECT 'SOUTH_EAST', '3176', '317x'
    UNION ALL SELECT 'SOUTH_EAST', '3177', '317x'
    UNION ALL SELECT 'SOUTH_EAST', '3178', '317x'
    UNION ALL SELECT 'SOUTH_EAST', '3179', '317x'
    UNION ALL SELECT 'SOUTH_EAST', '3180', '318x-320x'
    UNION ALL SELECT 'SOUTH_EAST', '3181', '318x-320x'
    UNION ALL SELECT 'SOUTH_EAST', '3182', '318x-320x'
    UNION ALL SELECT 'SOUTH_EAST', '3183', '318x-320x'
    UNION ALL SELECT 'SOUTH_EAST', '3184', '318x-320x'
    UNION ALL SELECT 'SOUTH_EAST', '3185', '318x-320x'
    UNION ALL SELECT 'SOUTH_EAST', '3186', '318x-320x'
    UNION ALL SELECT 'SOUTH_EAST', '3187', '318x-320x'
    UNION ALL SELECT 'SOUTH_EAST', '3188', '318x-320x'
    UNION ALL SELECT 'SOUTH_EAST', '3189', '318x-320x'
    UNION ALL SELECT 'SOUTH_EAST', '3190', '318x-320x'
    UNION ALL SELECT 'SOUTH_EAST', '3191', '318x-320x'
    UNION ALL SELECT 'SOUTH_EAST', '3192', '318x-320x'
    UNION ALL SELECT 'SOUTH_EAST', '3193', '318x-320x'
    UNION ALL SELECT 'SOUTH_EAST', '3194', '318x-320x'
    UNION ALL SELECT 'SOUTH_EAST', '3195', '318x-320x'
    UNION ALL SELECT 'SOUTH_EAST', '3196', '318x-320x'
    UNION ALL SELECT 'SOUTH_EAST', '3197', '318x-320x'
    UNION ALL SELECT 'SOUTH_EAST', '3198', '318x-320x'
    UNION ALL SELECT 'SOUTH_EAST', '3199', '318x-320x'
    UNION ALL SELECT 'SOUTH_EAST', '3200', '318x-320x'
    UNION ALL SELECT 'SOUTH_EAST', '3201', '318x-320x'
    UNION ALL SELECT 'SOUTH_EAST', '3202', '318x-320x'
    UNION ALL SELECT 'SOUTH_EAST', '3203', '318x-320x'
    UNION ALL SELECT 'SOUTH_EAST', '3204', '318x-320x'
    UNION ALL SELECT 'SOUTH_EAST', '3205', '318x-320x'
    UNION ALL SELECT 'SOUTH_EAST', '3206', '318x-320x'
    UNION ALL SELECT 'SOUTH_EAST', '3207', '318x-320x'
    UNION ALL SELECT 'SOUTH_EAST', '3208', '318x-320x'
    UNION ALL SELECT 'SOUTH_EAST', '3209', '318x-320x'
    UNION ALL SELECT 'SOUTH_EAST', '3800', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3801', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3802', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3803', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3804', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3805', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3806', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3807', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3808', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3809', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3810', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3811', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3812', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3813', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3814', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3815', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3816', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3817', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3818', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3819', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3820', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3821', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3822', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3823', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3824', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3825', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3826', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3827', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3828', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3829', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3830', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3831', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3832', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3833', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3834', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3835', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3836', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3837', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3838', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3839', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3840', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3841', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3842', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3843', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3844', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3845', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3846', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3847', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3848', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3849', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3850', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3851', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3852', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3853', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3854', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3855', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3856', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3857', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3858', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3859', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3860', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3861', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3862', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3863', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3864', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3865', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3866', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3867', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3868', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3869', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3870', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3871', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3872', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3873', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3874', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3875', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3876', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3877', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3878', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3879', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3880', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3881', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3882', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3883', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3884', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3885', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3886', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3887', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3888', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3889', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3890', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3891', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3892', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3893', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3894', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3895', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3896', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3897', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3898', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3899', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3900', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3901', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3902', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3903', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3904', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3905', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3906', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3907', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3908', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3909', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3910', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3911', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3912', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3913', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3914', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3915', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3916', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3917', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3918', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3919', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3920', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3921', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3922', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3923', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3924', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3925', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3926', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3927', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3928', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3929', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3930', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3931', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3932', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3933', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3934', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3935', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3936', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3937', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3938', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3939', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3940', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3941', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3942', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3943', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3944', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3945', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3946', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3947', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3948', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3949', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3950', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3951', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3952', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3953', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3954', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3955', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3956', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3957', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3958', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3959', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3960', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3961', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3962', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3963', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3964', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3965', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3966', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3967', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3968', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3969', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3970', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3971', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3972', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3973', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3974', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3975', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3976', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3977', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3978', '380x-397x'
    UNION ALL SELECT 'SOUTH_EAST', '3979', '380x-397x'
    UNION ALL SELECT 'WEST', '3011', '3011'
    UNION ALL SELECT 'WEST', '3012', '3012'
    UNION ALL SELECT 'WEST', '3013', '3013'
    UNION ALL SELECT 'WEST', '3014', '3014'
    UNION ALL SELECT 'WEST', '3015', '3015'
    UNION ALL SELECT 'WEST', '3016', '3016'
    UNION ALL SELECT 'WEST', '3017', '3017'
    UNION ALL SELECT 'WEST', '3018', '3018'
    UNION ALL SELECT 'WEST', '3019', '3019'
    UNION ALL SELECT 'WEST', '3020', '3020'
    UNION ALL SELECT 'WEST', '3021', '3021'
    UNION ALL SELECT 'WEST', '3022', '3022'
    UNION ALL SELECT 'WEST', '3023', '3023'
    UNION ALL SELECT 'WEST', '3024', '3024'
    UNION ALL SELECT 'WEST', '3025', '3025'
    UNION ALL SELECT 'WEST', '3026', '3026'
    UNION ALL SELECT 'WEST', '3027', '3027'
    UNION ALL SELECT 'WEST', '3028', '3028'
    UNION ALL SELECT 'WEST', '3029', '3029'
    UNION ALL SELECT 'WEST', '3030', '3030'
    UNION ALL SELECT 'WEST', '3031', '3031'
    UNION ALL SELECT 'WEST', '3032', '3032'
    UNION ALL SELECT 'WEST', '3033', '3033'
    UNION ALL SELECT 'WEST', '3034', '3034'
    UNION ALL SELECT 'WEST', '3035', '3035'
    UNION ALL SELECT 'WEST', '3036', '3036'
    UNION ALL SELECT 'WEST', '3037', '3037'
    UNION ALL SELECT 'WEST', '3038', '3038'
    UNION ALL SELECT 'WEST', '3039', '3039'
    UNION ALL SELECT 'WEST', '3040', '3040'
    UNION ALL SELECT 'WEST', '3041', '3041'
    UNION ALL SELECT 'WEST', '3042', '3042'
    UNION ALL SELECT 'WEST', '3043', '3043'
    UNION ALL SELECT 'WEST', '3044', '3044'
    UNION ALL SELECT 'WEST', '3045', '3045'
    UNION ALL SELECT 'WEST', '3046', '3046'
    UNION ALL SELECT 'WEST', '3047', '3047'
    UNION ALL SELECT 'WEST', '3048', '3048'
    UNION ALL SELECT 'WEST', '3049', '3049'
    UNION ALL SELECT 'WEST', '3050', '3050'
    UNION ALL SELECT 'WEST', '3051', '3051'
    UNION ALL SELECT 'WEST', '3052', '3052'
    UNION ALL SELECT 'WEST', '3053', '3053'
    UNION ALL SELECT 'WEST', '3054', '3054'
    UNION ALL SELECT 'WEST', '3055', '3055'
    UNION ALL SELECT 'WEST', '3056', '3056'
    UNION ALL SELECT 'WEST', '3057', '3057'
    UNION ALL SELECT 'WEST', '3058', '3058'
    UNION ALL SELECT 'WEST', '3059', '3059'
    UNION ALL SELECT 'WEST', '3060', '3060'
    UNION ALL SELECT 'WEST', '3061', '3061'
    UNION ALL SELECT 'WEST', '3062', '3062'
    UNION ALL SELECT 'WEST', '3063', '3063'
    UNION ALL SELECT 'WEST', '3064', '3064'
    UNION ALL SELECT 'WEST', '3065', '3065'
    UNION ALL SELECT 'WEST', '3066', '3066'
    UNION ALL SELECT 'WEST', '3067', '3067'
    UNION ALL SELECT 'WEST', '3068', '3068'
    UNION ALL SELECT 'WEST', '3069', '3069'
    UNION ALL SELECT 'WEST', '3070', '3070'
    UNION ALL SELECT 'WEST', '3071', '3071'
    UNION ALL SELECT 'WEST', '3072', '3072'
    UNION ALL SELECT 'WEST', '3073', '3073'
    UNION ALL SELECT 'WEST', '3074', '3074'
    UNION ALL SELECT 'WEST', '3075', '3075'
    UNION ALL SELECT 'WEST', '3076', '3076'
    UNION ALL SELECT 'WEST', '3077', '3077'
    UNION ALL SELECT 'LOCAL', '3000', '3000'
    UNION ALL SELECT 'LOCAL', '3006', '3006'
    UNION ALL SELECT 'LOCAL', '3008', '3008'
) p
    ON p.zone_code = z.zone_code;
INSERT INTO `laundry_container_type` (`code`, `name`)
VALUES
    ('TUB', 'Tub'),
    ('TROLLEY', 'Trolley'),
    ('BALE', 'Bale');

INSERT INTO `laundry_action_type` (`code`, `name`)
VALUES
    ('EMPTY_BOARD_BOXES', 'Empty board boxes'),
    ('CABLE_TIES', 'Cable ties'),
    ('CLEAR_EMPTY_BAGS', 'Clear empty bags'),
    ('BLACK_GARBAGE_BAGS', 'Black garbage bags');

INSERT INTO `laundry_weight_category` (`code`, `name`)
VALUES
    ('WHITE_SHEET', 'White Sheet'),
    ('WHITE_PC', 'White PC'),
    ('WHITE_TOWEL', 'White Towel'),
    ('WHITE_HOSPITAL_BLANKET', 'White Hospital Blanket'),
    ('CLOTHING_KG', 'Clothing KG'),
    ('SHOES_KG', 'Shoes KG');




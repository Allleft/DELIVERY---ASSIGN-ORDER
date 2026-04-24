-- Dispatch snapshot and output tables for the automatic dispatch optimizer.
-- This layer is intentionally separated from the core driver / vehicle / orders tables.

CREATE TABLE `dispatch_batch` (
    `dispatch_batch_id` BIGINT NOT NULL AUTO_INCREMENT,
    `dispatch_date` DATE NOT NULL,
    `trigger_mode` ENUM('DAILY_BATCH', 'MANUAL_RERUN') NOT NULL DEFAULT 'DAILY_BATCH',
    `status` ENUM('PENDING', 'PLANNED', 'PARTIAL', 'FAILED') NOT NULL DEFAULT 'PENDING',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`dispatch_batch_id`),
    KEY `idx_dispatch_batch_dispatch_date` (`dispatch_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `dispatch_order_snapshot` (
    `dispatch_order_snapshot_id` BIGINT NOT NULL AUTO_INCREMENT,
    `dispatch_batch_id` BIGINT NOT NULL,
    `order_id` INT NOT NULL,
    `dispatch_date` DATE NOT NULL,
    `delivery_address` VARCHAR(255) NOT NULL,
    `lat` DECIMAL(10, 7) NOT NULL,
    `lng` DECIMAL(10, 7) NOT NULL,
    `postcode` CHAR(4) NOT NULL,
    `zone_code` VARCHAR(50) NOT NULL,
    `urgency` ENUM('URGENT', 'NORMAL') NOT NULL DEFAULT 'NORMAL',
    `window_start` TIME NOT NULL,
    `window_end` TIME NOT NULL,
    `designated_driver_id` INT NULL,
    `load_type` ENUM('MIXED', 'ON_PALLET', 'LOOSE') NOT NULL DEFAULT 'MIXED',
    `kg_count` DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    `pallet_count` INT UNSIGNED NOT NULL DEFAULT 0,
    `bag_count` INT UNSIGNED NOT NULL DEFAULT 0,
    `service_minutes` INT UNSIGNED NOT NULL DEFAULT 10,
    PRIMARY KEY (`dispatch_order_snapshot_id`),
    KEY `idx_dispatch_order_snapshot_batch` (`dispatch_batch_id`),
    KEY `idx_dispatch_order_snapshot_zone_code` (`zone_code`),
    KEY `idx_dispatch_order_snapshot_postcode` (`postcode`),
    KEY `idx_dispatch_order_snapshot_order` (`order_id`),
    CONSTRAINT `fk_dispatch_order_snapshot_batch`
        FOREIGN KEY (`dispatch_batch_id`) REFERENCES `dispatch_batch` (`dispatch_batch_id`),
    CONSTRAINT `fk_dispatch_order_snapshot_driver`
        FOREIGN KEY (`designated_driver_id`) REFERENCES `driver` (`driver_id`),
    CONSTRAINT `chk_dispatch_order_snapshot_service_minutes`
        CHECK (`service_minutes` >= 1 AND `service_minutes` <= 10)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `dispatch_driver_snapshot` (
    `dispatch_driver_snapshot_id` BIGINT NOT NULL AUTO_INCREMENT,
    `dispatch_batch_id` BIGINT NOT NULL,
    `driver_id` INT NOT NULL,
    `shift_start` TIME NOT NULL,
    `shift_end` TIME NOT NULL,
    `is_available` TINYINT(1) NOT NULL DEFAULT 1,
    `start_location` VARCHAR(255) NOT NULL,
    `end_location` VARCHAR(255) NOT NULL,
    `start_lat` DECIMAL(10, 7) NOT NULL,
    `start_lng` DECIMAL(10, 7) NOT NULL,
    `end_lat` DECIMAL(10, 7) NOT NULL,
    `end_lng` DECIMAL(10, 7) NOT NULL,
    PRIMARY KEY (`dispatch_driver_snapshot_id`),
    KEY `idx_dispatch_driver_snapshot_batch` (`dispatch_batch_id`),
    KEY `idx_dispatch_driver_snapshot_driver` (`driver_id`),
    CONSTRAINT `fk_dispatch_driver_snapshot_batch`
        FOREIGN KEY (`dispatch_batch_id`) REFERENCES `dispatch_batch` (`dispatch_batch_id`),
    CONSTRAINT `fk_dispatch_driver_snapshot_driver`
        FOREIGN KEY (`driver_id`) REFERENCES `driver` (`driver_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `dispatch_driver_zone_preference` (
    `dispatch_driver_zone_preference_id` BIGINT NOT NULL AUTO_INCREMENT,
    `dispatch_driver_snapshot_id` BIGINT NOT NULL,
    `zone_code` VARCHAR(50) NOT NULL,
    `preference_rank` INT UNSIGNED NOT NULL DEFAULT 1,
    PRIMARY KEY (`dispatch_driver_zone_preference_id`),
    UNIQUE KEY `uq_dispatch_driver_zone_preference` (`dispatch_driver_snapshot_id`, `zone_code`),
    CONSTRAINT `fk_dispatch_driver_zone_preference_snapshot`
        FOREIGN KEY (`dispatch_driver_snapshot_id`) REFERENCES `dispatch_driver_snapshot` (`dispatch_driver_snapshot_id`),
    CONSTRAINT `fk_dispatch_driver_zone_preference_zone`
        FOREIGN KEY (`zone_code`) REFERENCES `zone` (`zone_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `dispatch_driver_vehicle_history` (
    `dispatch_driver_vehicle_history_id` BIGINT NOT NULL AUTO_INCREMENT,
    `dispatch_driver_snapshot_id` BIGINT NOT NULL,
    `vehicle_id` INT NOT NULL,
    `continuity_weight` INT UNSIGNED NOT NULL DEFAULT 1,
    PRIMARY KEY (`dispatch_driver_vehicle_history_id`),
    UNIQUE KEY `uq_dispatch_driver_vehicle_history` (`dispatch_driver_snapshot_id`, `vehicle_id`),
    CONSTRAINT `fk_dispatch_driver_vehicle_history_snapshot`
        FOREIGN KEY (`dispatch_driver_snapshot_id`) REFERENCES `dispatch_driver_snapshot` (`dispatch_driver_snapshot_id`),
    CONSTRAINT `fk_dispatch_driver_vehicle_history_vehicle`
        FOREIGN KEY (`vehicle_id`) REFERENCES `vehicle` (`vehicle_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `dispatch_vehicle_snapshot` (
    `dispatch_vehicle_snapshot_id` BIGINT NOT NULL AUTO_INCREMENT,
    `dispatch_batch_id` BIGINT NOT NULL,
    `vehicle_id` INT NOT NULL,
    `vehicle_type` VARCHAR(100) NOT NULL,
    `is_available` TINYINT(1) NOT NULL DEFAULT 1,
    `kg_capacity` DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    `pallet_capacity` INT UNSIGNED NOT NULL DEFAULT 0,
    `tub_capacity` INT UNSIGNED NOT NULL DEFAULT 0,
    `trolley_capacity` INT UNSIGNED NOT NULL DEFAULT 0,
    `stillage_capacity` INT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (`dispatch_vehicle_snapshot_id`),
    UNIQUE KEY `uq_dispatch_vehicle_snapshot_batch_vehicle` (`dispatch_batch_id`, `vehicle_id`),
    KEY `idx_dispatch_vehicle_snapshot_batch` (`dispatch_batch_id`),
    KEY `idx_dispatch_vehicle_snapshot_vehicle` (`vehicle_id`),
    CONSTRAINT `fk_dispatch_vehicle_snapshot_batch`
        FOREIGN KEY (`dispatch_batch_id`) REFERENCES `dispatch_batch` (`dispatch_batch_id`),
    CONSTRAINT `fk_dispatch_vehicle_snapshot_vehicle`
        FOREIGN KEY (`vehicle_id`) REFERENCES `vehicle` (`vehicle_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `dispatch_plan` (
    `dispatch_plan_id` BIGINT NOT NULL AUTO_INCREMENT,
    `dispatch_batch_id` BIGINT NOT NULL,
    `run_code` VARCHAR(64) NOT NULL,
    `driver_id` INT NOT NULL,
    `vehicle_id` INT NOT NULL,
    `planned_start` TIME NOT NULL,
    `planned_finish` TIME NOT NULL,
    `objective_score` BIGINT NOT NULL DEFAULT 0,
    `load_summary_json` JSON NOT NULL,
    `explanation_json` JSON NOT NULL,
    PRIMARY KEY (`dispatch_plan_id`),
    UNIQUE KEY `uq_dispatch_plan_run_code` (`dispatch_batch_id`, `run_code`),
    CONSTRAINT `fk_dispatch_plan_batch`
        FOREIGN KEY (`dispatch_batch_id`) REFERENCES `dispatch_batch` (`dispatch_batch_id`),
    CONSTRAINT `fk_dispatch_plan_driver`
        FOREIGN KEY (`driver_id`) REFERENCES `driver` (`driver_id`),
    CONSTRAINT `fk_dispatch_plan_vehicle`
        FOREIGN KEY (`vehicle_id`) REFERENCES `vehicle` (`vehicle_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `dispatch_plan_stop` (
    `dispatch_plan_stop_id` BIGINT NOT NULL AUTO_INCREMENT,
    `dispatch_plan_id` BIGINT NOT NULL,
    `order_id` INT NOT NULL,
    `stop_sequence` INT UNSIGNED NOT NULL,
    `eta` TIME NOT NULL,
    `departure_time` TIME NOT NULL,
    `travel_from_previous_minutes` INT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (`dispatch_plan_stop_id`),
    UNIQUE KEY `uq_dispatch_plan_stop_sequence` (`dispatch_plan_id`, `stop_sequence`),
    CONSTRAINT `fk_dispatch_plan_stop_plan`
        FOREIGN KEY (`dispatch_plan_id`) REFERENCES `dispatch_plan` (`dispatch_plan_id`),
    CONSTRAINT `fk_dispatch_plan_stop_order`
        FOREIGN KEY (`order_id`) REFERENCES `orders` (`order_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `dispatch_order_assignment` (
    `dispatch_order_assignment_id` BIGINT NOT NULL AUTO_INCREMENT,
    `dispatch_batch_id` BIGINT NOT NULL,
    `order_id` INT NOT NULL,
    `postcode` CHAR(4) NULL,
    `zone_code` VARCHAR(50) NULL,
    `run_code` VARCHAR(64) NOT NULL,
    `driver_id` INT NOT NULL,
    `vehicle_id` INT NOT NULL,
    `stop_sequence` INT UNSIGNED NOT NULL,
    `planned_start` TIME NOT NULL,
    `planned_finish` TIME NOT NULL,
    `eta` TIME NOT NULL,
    `departure_time` TIME NOT NULL,
    `assignment_status` ENUM('ASSIGNED', 'MANUAL_REVIEW') NOT NULL DEFAULT 'ASSIGNED',
    `reason_json` JSON NOT NULL,
    PRIMARY KEY (`dispatch_order_assignment_id`),
    UNIQUE KEY `uq_dispatch_order_assignment_order` (`dispatch_batch_id`, `order_id`),
    KEY `idx_dispatch_order_assignment_run` (`dispatch_batch_id`, `run_code`),
    KEY `idx_dispatch_order_assignment_driver` (`driver_id`),
    KEY `idx_dispatch_order_assignment_vehicle` (`vehicle_id`),
    CONSTRAINT `fk_dispatch_order_assignment_batch`
        FOREIGN KEY (`dispatch_batch_id`) REFERENCES `dispatch_batch` (`dispatch_batch_id`),
    CONSTRAINT `fk_dispatch_order_assignment_order`
        FOREIGN KEY (`order_id`) REFERENCES `orders` (`order_id`),
    CONSTRAINT `fk_dispatch_order_assignment_driver`
        FOREIGN KEY (`driver_id`) REFERENCES `driver` (`driver_id`),
    CONSTRAINT `fk_dispatch_order_assignment_vehicle`
        FOREIGN KEY (`vehicle_id`) REFERENCES `vehicle` (`vehicle_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `dispatch_exception` (
    `dispatch_exception_id` BIGINT NOT NULL AUTO_INCREMENT,
    `dispatch_batch_id` BIGINT NOT NULL,
    `scope` ENUM('SYSTEM', 'ORDER', 'RUN', 'DRIVER', 'VEHICLE') NOT NULL,
    `entity_id` VARCHAR(64) NOT NULL,
    `reason_code` VARCHAR(100) NOT NULL,
    `reason_text` TEXT NOT NULL,
    `suggested_action` TEXT NOT NULL,
    `is_urgent` TINYINT(1) NOT NULL DEFAULT 0,
    PRIMARY KEY (`dispatch_exception_id`),
    KEY `idx_dispatch_exception_batch` (`dispatch_batch_id`),
    KEY `idx_dispatch_exception_reason_code` (`reason_code`),
    CONSTRAINT `fk_dispatch_exception_batch`
        FOREIGN KEY (`dispatch_batch_id`) REFERENCES `dispatch_batch` (`dispatch_batch_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

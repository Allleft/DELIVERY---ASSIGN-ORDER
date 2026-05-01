-- Office Dispatch Workbench MVP - Phase 1 database foundation
-- MySQL 8+ / InnoDB / utf8mb4

SET NAMES utf8mb4;

CREATE TABLE `dispatch_batches` (
  `batch_id` BIGINT NOT NULL AUTO_INCREMENT,
  `dispatch_date` DATE NOT NULL,
  `status` ENUM('DRAFT', 'GENERATED', 'ADJUSTED', 'LOCKED', 'CANCELLED') NOT NULL DEFAULT 'DRAFT',
  `created_by` VARCHAR(128) NOT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `generated_at` DATETIME NULL,
  `locked_at` DATETIME NULL,
  `locked_by` VARCHAR(128) NULL,
  `notes` TEXT NULL,
  PRIMARY KEY (`batch_id`),
  KEY `idx_dispatch_batches_dispatch_date` (`dispatch_date`),
  KEY `idx_dispatch_batches_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `drivers` (
  `driver_id` BIGINT NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(128) NOT NULL,
  `phone` VARCHAR(32) NULL,
  `is_active` TINYINT(1) NOT NULL DEFAULT 1,
  `default_shift_start` TIME NULL,
  `default_shift_end` TIME NULL,
  `preferred_zone_codes` JSON NULL,
  `start_location` VARCHAR(255) NULL,
  `end_location` VARCHAR(255) NULL,
  `branch_no` VARCHAR(64) NULL,
  `notes` TEXT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`driver_id`),
  KEY `idx_drivers_is_active` (`is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `vehicles` (
  `vehicle_id` BIGINT NOT NULL AUTO_INCREMENT,
  `rego` VARCHAR(32) NOT NULL,
  `vehicle_type` VARCHAR(64) NULL,
  `is_active` TINYINT(1) NOT NULL DEFAULT 1,
  `kg_capacity` DECIMAL(10,2) NOT NULL DEFAULT 0.00,
  `pallet_capacity` INT NOT NULL DEFAULT 0,
  `tub_capacity` INT NOT NULL DEFAULT 0,
  `trolley_capacity` INT NOT NULL DEFAULT 0,
  `stillage_capacity` INT NOT NULL DEFAULT 0,
  `notes` TEXT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`vehicle_id`),
  UNIQUE KEY `uq_vehicles_rego` (`rego`),
  KEY `idx_vehicles_is_active` (`is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `dispatch_orders` (
  `dispatch_order_id` BIGINT NOT NULL AUTO_INCREMENT,
  `batch_id` BIGINT NOT NULL,
  `order_id` VARCHAR(64) NOT NULL,
  `customer_name` VARCHAR(255) NULL,
  `delivery_address` VARCHAR(255) NOT NULL,
  `suburb` VARCHAR(128) NULL,
  `postcode` CHAR(4) NOT NULL,
  `zone_code` VARCHAR(64) NULL,
  `urgency` ENUM('NORMAL', 'URGENT') NOT NULL DEFAULT 'NORMAL',
  `designated_driver_id` BIGINT NULL,
  `pallet_count` INT NOT NULL DEFAULT 0,
  `bag_count` INT NOT NULL DEFAULT 0,
  `kg_count` DECIMAL(10,2) NOT NULL DEFAULT 0.00,
  `window_start` TIME NULL,
  `window_end` TIME NULL,
  `notes` TEXT NULL,
  `status` VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`dispatch_order_id`),
  UNIQUE KEY `uq_dispatch_orders_batch_order` (`batch_id`, `order_id`),
  KEY `idx_dispatch_orders_batch` (`batch_id`),
  KEY `idx_dispatch_orders_zone` (`zone_code`),
  KEY `idx_dispatch_orders_urgency` (`urgency`),
  KEY `idx_dispatch_orders_designated_driver` (`designated_driver_id`),
  CONSTRAINT `fk_dispatch_orders_batch`
    FOREIGN KEY (`batch_id`) REFERENCES `dispatch_batches` (`batch_id`),
  CONSTRAINT `fk_dispatch_orders_designated_driver`
    FOREIGN KEY (`designated_driver_id`) REFERENCES `drivers` (`driver_id`),
  CONSTRAINT `chk_dispatch_orders_postcode`
    CHECK (`postcode` REGEXP '^[0-9]{4}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `dispatch_plans` (
  `dispatch_plan_id` BIGINT NOT NULL AUTO_INCREMENT,
  `batch_id` BIGINT NOT NULL,
  `plan_id` VARCHAR(64) NOT NULL,
  `dispatch_date` DATE NOT NULL,
  `driver_id` BIGINT NULL,
  `driver_name_snapshot` VARCHAR(128) NULL,
  `vehicle_id` BIGINT NULL,
  `vehicle_rego_snapshot` VARCHAR(32) NULL,
  `order_ids_json` JSON NOT NULL,
  `total_orders` INT NOT NULL DEFAULT 0,
  `load_summary_json` JSON NULL,
  `zone_code` VARCHAR(64) NULL,
  `time_window_start` TIME NULL,
  `time_window_end` TIME NULL,
  `urgent_order_count` INT NOT NULL DEFAULT 0,
  `objective_score` DECIMAL(18,4) NULL,
  `explanation_json` JSON NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`dispatch_plan_id`),
  UNIQUE KEY `uq_dispatch_plans_batch_plan` (`batch_id`, `plan_id`),
  KEY `idx_dispatch_plans_batch` (`batch_id`),
  KEY `idx_dispatch_plans_driver` (`driver_id`),
  KEY `idx_dispatch_plans_vehicle` (`vehicle_id`),
  KEY `idx_dispatch_plans_date` (`dispatch_date`),
  CONSTRAINT `fk_dispatch_plans_batch`
    FOREIGN KEY (`batch_id`) REFERENCES `dispatch_batches` (`batch_id`),
  CONSTRAINT `fk_dispatch_plans_driver`
    FOREIGN KEY (`driver_id`) REFERENCES `drivers` (`driver_id`),
  CONSTRAINT `fk_dispatch_plans_vehicle`
    FOREIGN KEY (`vehicle_id`) REFERENCES `vehicles` (`vehicle_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `dispatch_order_assignments` (
  `assignment_id` BIGINT NOT NULL AUTO_INCREMENT,
  `batch_id` BIGINT NOT NULL,
  `order_id` VARCHAR(64) NOT NULL,
  `plan_id` VARCHAR(64) NULL,
  `dispatch_date` DATE NOT NULL,
  `driver_id` BIGINT NULL,
  `driver_name_snapshot` VARCHAR(128) NULL,
  `vehicle_id` BIGINT NULL,
  `vehicle_rego_snapshot` VARCHAR(32) NULL,
  `status` ENUM('ASSIGNED', 'UNASSIGNED', 'MANUALLY_ASSIGNED', 'REMOVED') NOT NULL DEFAULT 'ASSIGNED',
  `assignment_source` ENUM('AUTO', 'MANUAL') NOT NULL DEFAULT 'AUTO',
  `manual_reason` TEXT NULL,
  `objective_score` DECIMAL(18,4) NULL,
  `postcode` CHAR(4) NULL,
  `zone_code` VARCHAR(64) NULL,
  `explanation_json` JSON NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`assignment_id`),
  KEY `idx_dispatch_order_assignments_batch` (`batch_id`),
  KEY `idx_dispatch_order_assignments_plan` (`batch_id`, `plan_id`),
  KEY `idx_dispatch_order_assignments_order` (`batch_id`, `order_id`),
  KEY `idx_dispatch_order_assignments_driver` (`driver_id`),
  KEY `idx_dispatch_order_assignments_vehicle` (`vehicle_id`),
  CONSTRAINT `fk_dispatch_order_assignments_order`
    FOREIGN KEY (`batch_id`, `order_id`)
    REFERENCES `dispatch_orders` (`batch_id`, `order_id`),
  CONSTRAINT `fk_dispatch_order_assignments_plan`
    FOREIGN KEY (`batch_id`, `plan_id`)
    REFERENCES `dispatch_plans` (`batch_id`, `plan_id`),
  CONSTRAINT `fk_dispatch_order_assignments_driver`
    FOREIGN KEY (`driver_id`) REFERENCES `drivers` (`driver_id`),
  CONSTRAINT `fk_dispatch_order_assignments_vehicle`
    FOREIGN KEY (`vehicle_id`) REFERENCES `vehicles` (`vehicle_id`),
  CONSTRAINT `chk_dispatch_order_assignments_plan_status`
    CHECK (
      (`status` IN ('ASSIGNED', 'MANUALLY_ASSIGNED') AND `plan_id` IS NOT NULL)
      OR (`status` IN ('UNASSIGNED', 'REMOVED'))
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `dispatch_exceptions` (
  `exception_id` BIGINT NOT NULL AUTO_INCREMENT,
  `batch_id` BIGINT NOT NULL,
  `scope` VARCHAR(64) NOT NULL,
  `entity_id` VARCHAR(128) NULL,
  `reason_code` VARCHAR(128) NOT NULL,
  `reason_text` TEXT NOT NULL,
  `suggested_action` TEXT NULL,
  `is_urgent` TINYINT(1) NOT NULL DEFAULT 0,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`exception_id`),
  KEY `idx_dispatch_exceptions_batch` (`batch_id`),
  KEY `idx_dispatch_exceptions_reason` (`reason_code`),
  CONSTRAINT `fk_dispatch_exceptions_batch`
    FOREIGN KEY (`batch_id`) REFERENCES `dispatch_batches` (`batch_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `audit_log` (
  `audit_id` BIGINT NOT NULL AUTO_INCREMENT,
  `batch_id` BIGINT NOT NULL,
  `user_name` VARCHAR(128) NOT NULL,
  `action` VARCHAR(128) NOT NULL,
  `entity_type` VARCHAR(64) NOT NULL,
  `entity_id` VARCHAR(128) NULL,
  `before_json` JSON NULL,
  `after_json` JSON NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`audit_id`),
  KEY `idx_audit_log_batch` (`batch_id`),
  KEY `idx_audit_log_action` (`action`),
  KEY `idx_audit_log_created_at` (`created_at`),
  CONSTRAINT `fk_audit_log_batch`
    FOREIGN KEY (`batch_id`) REFERENCES `dispatch_batches` (`batch_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

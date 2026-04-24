(function registerDriverAssignmentSummaryModule(globalScope) {
  if (!globalScope || typeof globalScope !== "object") {
    return;
  }

  function asText(value) {
    if (value === undefined || value === null) {
      return "";
    }
    return String(value);
  }

  function compareText(left, right) {
    return asText(left).localeCompare(asText(right), undefined, { numeric: true, sensitivity: "base" });
  }

  function normalizeMap(rawMap) {
    if (!rawMap || typeof rawMap !== "object") {
      return {};
    }
    const result = {};
    for (const [key, value] of Object.entries(rawMap)) {
      const normalizedKey = asText(key).trim();
      const normalizedValue = asText(value).trim();
      if (normalizedKey !== "" && normalizedValue !== "") {
        result[normalizedKey] = normalizedValue;
      }
    }
    return result;
  }

  function buildDriverAssignmentSummary(orderAssignments, plans, displayLookups) {
    const assignments = Array.isArray(orderAssignments) ? orderAssignments : [];
    const normalizedLookups = displayLookups && typeof displayLookups === "object" ? displayLookups : {};
    const driverById = normalizeMap(normalizedLookups.driverById);
    const vehicleById = normalizeMap(normalizedLookups.vehicleById);

    const drivers = new Map();
    for (const item of assignments) {
      const driverId = asText(item.driver_id).trim() || "UNASSIGNED";
      const vehicleId = asText(item.vehicle_id).trim() || "-";
      const dispatchDate = asText(item.dispatch_date).trim();
      const driverDisplay = asText(item.driver_name).trim() || driverById[driverId] || driverId;
      const vehicleDisplay = asText(item.vehicle_rego).trim() || vehicleById[vehicleId] || vehicleId;

      let driverBucket = drivers.get(driverId);
      if (!driverBucket) {
        driverBucket = {
          driver_id: driverId,
          driver_display: driverDisplay,
          total_orders: 0,
          vehicles: new Map(),
        };
        drivers.set(driverId, driverBucket);
      }
      if (!driverBucket.driver_display || driverBucket.driver_display === driverBucket.driver_id) {
        driverBucket.driver_display = driverDisplay;
      }

      driverBucket.total_orders += 1;

      let vehicleBucket = driverBucket.vehicles.get(vehicleId);
      if (!vehicleBucket) {
        vehicleBucket = {
          vehicle_id: vehicleId,
          vehicle_display: vehicleDisplay,
          total_orders: 0,
          orders: [],
        };
        driverBucket.vehicles.set(vehicleId, vehicleBucket);
      }
      if (!vehicleBucket.vehicle_display || vehicleBucket.vehicle_display === vehicleBucket.vehicle_id) {
        vehicleBucket.vehicle_display = vehicleDisplay;
      }

      vehicleBucket.total_orders += 1;
      vehicleBucket.orders.push({
        ...item,
        driver_display: driverDisplay,
        vehicle_display: vehicleDisplay,
        _sort_dispatch_date: dispatchDate,
        _sort_order_id: asText(item.order_id).trim(),
      });
    }

    const summaries = Array.from(drivers.values()).map((driverBucket) => {
      const vehicles = Array.from(driverBucket.vehicles.values()).map((vehicleBucket) => {
        const orders = [...vehicleBucket.orders].sort((left, right) => {
          const dateDiff = compareText(left._sort_dispatch_date, right._sort_dispatch_date);
          if (dateDiff !== 0) return dateDiff;
          return compareText(left._sort_order_id, right._sort_order_id);
        });

        return {
          vehicle_id: vehicleBucket.vehicle_id,
          vehicle_display: vehicleBucket.vehicle_display || vehicleBucket.vehicle_id,
          total_orders: vehicleBucket.total_orders,
          orders,
        };
      });

      vehicles.sort((left, right) => {
        const displayDiff = compareText(left.vehicle_display, right.vehicle_display);
        if (displayDiff !== 0) return displayDiff;
        return compareText(left.vehicle_id, right.vehicle_id);
      });
      return {
        driver_id: driverBucket.driver_id,
        driver_display: driverBucket.driver_display || driverBucket.driver_id,
        total_orders: driverBucket.total_orders,
        vehicle_count: vehicles.length,
        vehicles,
      };
    });

    summaries.sort((left, right) => {
      const displayDiff = compareText(left.driver_display, right.driver_display);
      if (displayDiff !== 0) return displayDiff;
      return compareText(left.driver_id, right.driver_id);
    });
    return summaries;
  }

  globalScope.DeliveryDriverAssignmentSummary = {
    buildDriverAssignmentSummary,
  };
})(typeof window !== "undefined" ? window : globalThis);

(function attachDeliveryRenderUtils(globalObject) {
  const root = globalObject || (typeof window !== "undefined" ? window : globalThis);

  function asText(value) {
    return value === null || value === undefined ? "" : String(value);
  }

  function safeArray(value) {
    return Array.isArray(value) ? value : [];
  }

  function buildResultDisplayLookups(view) {
    const driverById = {};
    const vehicleById = {};
    for (const driver of safeArray(view?.drivers)) {
      const driverId = asText(driver.driver_id).trim();
      if (!driverId) continue;
      const metadataName = asText(driver?._extra?.metadata?.name).trim();
      driverById[driverId] = asText(driver.name).trim() || metadataName || driverId;
    }
    for (const vehicle of safeArray(view?.vehicles)) {
      const vehicleId = asText(vehicle.vehicle_id).trim();
      if (!vehicleId) continue;
      const metadataRego = asText(vehicle?._extra?.metadata?.rego).trim() || asText(vehicle?._metadataExtra?.rego).trim();
      vehicleById[vehicleId] = asText(vehicle.rego).trim() || metadataRego || vehicleId;
    }
    return { driverById, vehicleById };
  }

  function resolveDriverDisplay(driverId, lookups) {
    const key = asText(driverId).trim();
    if (!key) return "-";
    return asText(lookups?.driverById?.[key]).trim() || key;
  }

  function resolveVehicleDisplay(vehicleId, lookups) {
    const key = asText(vehicleId).trim();
    if (!key) return "-";
    return asText(lookups?.vehicleById?.[key]).trim() || key;
  }

  function toBusinessExplanation(value) {
    const raw = Array.isArray(value) ? value.join(" / ") : asText(value);
    return raw.replace(/\bTrip\s+RUN-\d+\b/gi, "Assignment group").replace(/\bRUN-\d+\b/gi, "").trim();
  }

  root.DeliveryRenderUtils = Object.freeze({
    buildResultDisplayLookups,
    resolveDriverDisplay,
    resolveVehicleDisplay,
    toBusinessExplanation
  });
})(typeof window !== "undefined" ? window : globalThis);

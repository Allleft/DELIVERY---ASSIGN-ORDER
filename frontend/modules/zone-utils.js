(function registerZoneUtilsModule(globalScope) {
  if (!globalScope || typeof globalScope !== "object") {
    return;
  }

  function asText(value) {
    if (value === undefined || value === null) {
      return "";
    }
    return String(value);
  }

  function isObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function resolveZoneCodeByPostcode(postcode, zoneByPostcode) {
    const normalizedPostcode = asText(postcode).trim();
    if (normalizedPostcode === "" || !isObject(zoneByPostcode)) {
      return "";
    }
    const mapped = zoneByPostcode[normalizedPostcode];
    return asText(mapped).trim();
  }

  function resolveZoneLabelByCode(zoneCode, zoneLabelByCode) {
    const normalizedCode = asText(zoneCode).trim();
    if (normalizedCode === "") {
      return "-";
    }
    if (isObject(zoneLabelByCode) && normalizedCode in zoneLabelByCode) {
      const label = asText(zoneLabelByCode[normalizedCode]).trim();
      return label || normalizedCode;
    }
    return normalizedCode;
  }

  globalScope.DeliveryZoneUtils = {
    resolveZoneCodeByPostcode,
    resolveZoneLabelByCode,
  };
})(typeof window !== "undefined" ? window : globalThis);

/* Compatibility shim kept for historical references.
 * Core frontend behavior now lives in frontend/app.js.
 * This file intentionally does not override runtime logic.
 */
(function registerFrontendOverrideShim(globalScope) {
  if (!globalScope || typeof globalScope !== "object") {
    return;
  }
  globalScope.__deliveryFrontendOverrideShim = {
    active: false,
    version: "20260422-shim"
  };
})(typeof window !== "undefined" ? window : globalThis);

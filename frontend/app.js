const FIXED_STOP_MINUTES = 10;

const VEHICLE_SEED = [
  [1, "1HF8JY", "van", 0, 3, 6, 0, 0],
  [2, "1KM8KM", "van", 0, 3, 6, 0, 0],
  [3, "1SZ7KG", "van", 0, 3, 6, 0, 0],
  [4, "2DO8MK", "van", 0, 3, 0, 0, 0],
  [5, "2DOSLG", "van", 0, 1, 0, 0, 0],
  [6, "XW36ID", "small", 0, 6, 12, 15, 3],
  [7, "XW97GH", "medium", 0, 8, 24, 18, 8],
  [8, "XW22UT", "medium", 0, 10, 30, 21, 10],
  [9, "1AW4P1", "big", 0, 14, 42, 33, 14]
];

const DRIVER_SEED = [
  ["Epaminondas Tsatsoulis", "089140833", "nonda_tsatsoulis123@hotmail.com", "0489854436"],
  ["Guanlin Li", "091843577", "guanlinx88@gmail.com", "0455896888"],
  ["John Georgiadis", "048467870", "john50111@hotmail.com", "0465988477"],
  ["Thomas L Ward", "022250292", "tom@teamsaustralia.com.au", "0485222739"],
  ["Xiaoyan Fu", "054454692", "fushi56_fxy@126.com", "0409620769"],
  ["Yong Fang", "089875085", "duephyfang@gmail.com", "0430926662"],
  ["Yutong Wu", "036316530", "wyt2616@gmail.com", "0421174611"]
];

function buildAppBuiltinZoneByPostcode() {
  const map = {};
  const addPostcodes = (zoneCode, postcodes) => {
    for (const postcode of postcodes) {
      map[String(postcode).padStart(4, "0")] = zoneCode;
    }
  };
  const addRange = (zoneCode, start, end) => {
    for (let postcode = start; postcode <= end; postcode += 1) {
      map[String(postcode).padStart(4, "0")] = zoneCode;
    }
  };
  addRange("MAJOR_EAST", 3120, 3139);
  addRange("SOUTH_EAST", 3140, 3209);
  addRange("SOUTH_EAST", 3800, 3979);
  addRange("WEST", 3011, 3077);
  addPostcodes("LOCAL", [3000, 3006, 3008]);
  return map;
}

const APP_BUILTIN_ZONE_BY_POSTCODE = buildAppBuiltinZoneByPostcode();

const DEFAULT_CONFIG = {
  bucket_minutes: 120,
  loose_units_per_tub: 4,
  average_speed_kph: 35,
  minimum_travel_minutes: 3,
  max_repair_iterations: 3,
  zone_by_postcode: deepClone(APP_BUILTIN_ZONE_BY_POSTCODE),
  zone_label_by_code: {
    LOCAL: "Local",
    WEST: "West",
    MAJOR_EAST: "Major East",
    SOUTH_EAST: "South East"
  },
  legacy_zone_code_by_id: {},
  geocoder: {
    Depot: [-37.78, 144.93],
    SouthHub: [-37.84, 144.98],
    WestHub: [-37.88, 144.7],
    "328 Swanston Street, Melbourne VIC 3000": [-37.8097, 144.9653],
    "1341 Dandenong Road, Chadstone VIC 3148": [-37.886, 145.0836],
    "100 St Kilda Road, Melbourne VIC 3004": [-37.8216, 144.9689],
    "180 St Kilda Road, Melbourne VIC 3006": [-37.8227, 144.9684],
    "K Road, Werribee VIC 3030": [-37.9286, 144.674],
    "75 Lake Road, Kyabram VIC 3620": [-36.3065, 145.0549]
  },
  branch_locations: {
    MEL: [-37.78, 144.93, "Depot"]
  }
};

const EMPTY_RESULT = { plans: [], order_assignments: [], exceptions: [] };

const CONFIG_INPUT_MAP = {
  cfgBucketMinutes: "bucket_minutes",
  cfgLooseUnitsPerTub: "loose_units_per_tub",
  cfgAverageSpeed: "average_speed_kph",
  cfgMinTravel: "minimum_travel_minutes",
  cfgMaxRepair: "max_repair_iterations"
};

const ORDER_HEADER_ALIAS = {
  order_id: ["order_id", "orderid", "id"],
  dispatch_date: ["dispatch_date", "date", "dispatchday", "dispatch_day"],
  delivery_address: ["delivery_address", "address", "delivery_addr"],
  postcode: ["postcode", "post_code", "postal_code", "zip", "zip_code"],
  zone_code: ["zone_code", "zone", "zonecode", "zone_label"],
  urgency: ["urgency", "priority", "urgent"],
  preferred_driver_id: ["preferred_driver_id", "designated_driver_id", "driver_id", "preferred_driver"],
  pallet_qty: ["pallet_qty", "pallet_count", "pallets"],
  loose_bags: ["loose_bags", "loose_units", "bag_count", "loose_qty"],
  window_start: ["window_start", "start_window", "from_time", "window_from"],
  window_end: ["window_end", "end_window", "to_time", "window_to"]
};

const appState = {
  snapshot: createInitialSnapshot(),
  view: null,
  validation: createEmptyValidation(),
  result: deepClone(EMPTY_RESULT)
};

let rowSequence = 1;

document.addEventListener("DOMContentLoaded", bootstrap);

function bootstrap() {
  bindEvents();
  applySnapshotToState(createInitialSnapshot());
  appState.result = deepClone(EMPTY_RESULT);
  renderResult(appState.result);
  setImportReport("");
  banner("当前订单为空，请手动新增订单或导入 CSV；司机和车辆已直接展示。", "info");
}

function bindEvents() {
  onIf("loadSampleBtn", "click", loadSampleData);
  onIf("runPlannerBtn", "click", handleRunPlanner);
  onIf("exportSnapshotBtn", "click", handleExportSnapshot);
  onIf("addOrderBtn", "click", handleAddOrder);
  onIf("addDriverBtn", "click", handleAddDriver);
  onIf("addVehicleBtn", "click", handleAddVehicle);
  onIf("importOrdersBtn", "click", () => get("orderCsvInput")?.click());
  onIf("orderCsvInput", "change", handleOrderFileImport);
  onIf("syncSnapshotBtn", "click", handleSyncSnapshotJson);
  onIf("applySnapshotBtn", "click", handleApplySnapshotJson);

  const ordersBody = get("ordersTableBody");
  const driversBody = get("driversTableBody");
  const vehiclesBody = get("vehiclesTableBody");
  if (ordersBody) {
    ordersBody.addEventListener("input", handleOrderTableInput);
    ordersBody.addEventListener("change", handleOrderTableInput);
    ordersBody.addEventListener("click", handleOrderTableClick);
  }
  if (driversBody) {
    driversBody.addEventListener("input", handleDriverTableInput);
    driversBody.addEventListener("change", handleDriverTableInput);
    driversBody.addEventListener("click", handleDriverTableClick);
  }
  if (vehiclesBody) {
    vehiclesBody.addEventListener("input", handleVehicleTableInput);
    vehiclesBody.addEventListener("change", handleVehicleTableInput);
    vehiclesBody.addEventListener("click", handleVehicleTableClick);
  }

  for (const [id, key] of Object.entries(CONFIG_INPUT_MAP)) {
    onIf(id, "input", (event) => {
      appState.view.config[key] = event.target.value;
    });
  }
}

function createSampleSnapshot() {
  const sampleConfig = deepClone(DEFAULT_CONFIG);
  sampleConfig.zone_by_postcode = Object.assign({}, sampleConfig.zone_by_postcode, {
    "3004": "LOCAL",
    "3030": "WEST",
    "3052": "LOCAL"
  });
  return {
    config: sampleConfig,
    orders: [
      {
        order_id: 2001,
        dispatch_date: "2026-04-22",
        delivery_address: "328 Swanston Street, Melbourne VIC 3000",
        lat: -37.8097,
        lng: 144.9653,
        postcode: "3000",
        zone_code: "LOCAL",
        urgency: "URGENT",
        window_start: "08:00",
        window_end: "12:00",
        load_type: "MIXED",
        kg_count: 140,
        pallet_count: 2,
        bag_count: 6
      },
      {
        order_id: 2002,
        dispatch_date: "2026-04-22",
        delivery_address: "200 Bourke Street, Melbourne VIC 3000",
        lat: -37.8127,
        lng: 144.9646,
        postcode: "3000",
        zone_code: "LOCAL",
        urgency: "NORMAL",
        window_start: "09:00",
        window_end: "13:30",
        load_type: "ON_PALLET",
        kg_count: 210,
        pallet_count: 3,
        bag_count: 0
      },
      {
        order_id: 2003,
        dispatch_date: "2026-04-22",
        delivery_address: "333 Collins Street, Melbourne VIC 3000",
        lat: -37.8161,
        lng: 144.961,
        postcode: "3000",
        zone_code: "LOCAL",
        urgency: "NORMAL",
        window_start: "08:30",
        window_end: "12:30",
        load_type: "MIXED",
        kg_count: 105,
        pallet_count: 1,
        bag_count: 7
      },
      {
        order_id: 2004,
        dispatch_date: "2026-04-22",
        delivery_address: "500 Bourke Street, Melbourne VIC 3000",
        lat: -37.8153,
        lng: 144.9589,
        postcode: "3000",
        zone_code: "LOCAL",
        urgency: "URGENT",
        window_start: "07:45",
        window_end: "11:30",
        load_type: "ON_PALLET",
        kg_count: 180,
        pallet_count: 2,
        bag_count: 0
      },
      {
        order_id: 2005,
        dispatch_date: "2026-04-22",
        delivery_address: "120 Spencer Street, Melbourne VIC 3000",
        lat: -37.8183,
        lng: 144.9524,
        postcode: "3000",
        zone_code: "LOCAL",
        urgency: "NORMAL",
        window_start: "10:00",
        window_end: "16:00",
        load_type: "LOOSE",
        kg_count: 70,
        pallet_count: 0,
        bag_count: 13
      },
      {
        order_id: 2006,
        dispatch_date: "2026-04-22",
        delivery_address: "250 Flinders Street, Melbourne VIC 3000",
        lat: -37.818,
        lng: 144.9675,
        postcode: "3000",
        zone_code: "LOCAL",
        urgency: "NORMAL",
        window_start: "11:00",
        window_end: "17:00",
        load_type: "MIXED",
        kg_count: 110,
        pallet_count: 1,
        bag_count: 9
      },
      {
        order_id: 2007,
        dispatch_date: "2026-04-22",
        delivery_address: "100 St Kilda Road, Melbourne VIC 3004",
        lat: -37.8216,
        lng: 144.9689,
        postcode: "3004",
        zone_code: "LOCAL",
        urgency: "URGENT",
        window_start: "08:00",
        window_end: "12:30",
        load_type: "ON_PALLET",
        kg_count: 190,
        pallet_count: 3,
        bag_count: 0
      },
      {
        order_id: 2008,
        dispatch_date: "2026-04-22",
        delivery_address: "1 Linlithgow Avenue, Melbourne VIC 3004",
        lat: -37.8305,
        lng: 144.9746,
        postcode: "3004",
        zone_code: "LOCAL",
        urgency: "NORMAL",
        window_start: "09:00",
        window_end: "14:00",
        load_type: "MIXED",
        kg_count: 95,
        pallet_count: 1,
        bag_count: 8
      },
      {
        order_id: 2009,
        dispatch_date: "2026-04-22",
        delivery_address: "452 St Kilda Road, Melbourne VIC 3004",
        lat: -37.8362,
        lng: 144.9721,
        postcode: "3004",
        zone_code: "LOCAL",
        urgency: "NORMAL",
        window_start: "10:30",
        window_end: "16:30",
        load_type: "LOOSE",
        kg_count: 68,
        pallet_count: 0,
        bag_count: 12
      },
      {
        order_id: 2010,
        dispatch_date: "2026-04-22",
        delivery_address: "180 St Kilda Road, Melbourne VIC 3006",
        lat: -37.8227,
        lng: 144.9684,
        postcode: "3006",
        zone_code: "LOCAL",
        urgency: "URGENT",
        window_start: "07:30",
        window_end: "11:00",
        load_type: "ON_PALLET",
        kg_count: 175,
        pallet_count: 2,
        bag_count: 0
      },
      {
        order_id: 2011,
        dispatch_date: "2026-04-22",
        delivery_address: "8 Whiteman Street, Southbank VIC 3006",
        lat: -37.8214,
        lng: 144.9574,
        postcode: "3006",
        zone_code: "LOCAL",
        urgency: "NORMAL",
        window_start: "09:30",
        window_end: "15:30",
        load_type: "MIXED",
        kg_count: 115,
        pallet_count: 1,
        bag_count: 9
      },
      {
        order_id: 2012,
        dispatch_date: "2026-04-22",
        delivery_address: "2 Southbank Boulevard, Southbank VIC 3006",
        lat: -37.8218,
        lng: 144.9651,
        postcode: "3006",
        zone_code: "LOCAL",
        urgency: "NORMAL",
        window_start: "11:00",
        window_end: "17:00",
        load_type: "MIXED",
        kg_count: 120,
        pallet_count: 1,
        bag_count: 8
      },
      {
        order_id: 2013,
        dispatch_date: "2026-04-22",
        delivery_address: "Elliott Avenue, Parkville VIC 3052",
        lat: -37.784,
        lng: 144.9514,
        postcode: "3052",
        zone_code: "LOCAL",
        urgency: "URGENT",
        window_start: "08:00",
        window_end: "13:30",
        load_type: "ON_PALLET",
        kg_count: 230,
        pallet_count: 3,
        bag_count: 0
      },
      {
        order_id: 2014,
        dispatch_date: "2026-04-22",
        delivery_address: "1 Royal Parade, Parkville VIC 3052",
        lat: -37.7957,
        lng: 144.9594,
        postcode: "3052",
        zone_code: "LOCAL",
        urgency: "NORMAL",
        window_start: "09:00",
        window_end: "14:30",
        load_type: "MIXED",
        kg_count: 108,
        pallet_count: 1,
        bag_count: 7
      },
      {
        order_id: 2015,
        dispatch_date: "2026-04-22",
        delivery_address: "300 Grattan Street, Parkville VIC 3052",
        lat: -37.7989,
        lng: 144.9552,
        postcode: "3052",
        zone_code: "LOCAL",
        urgency: "NORMAL",
        window_start: "10:30",
        window_end: "16:30",
        load_type: "LOOSE",
        kg_count: 72,
        pallet_count: 0,
        bag_count: 11
      },
      {
        order_id: 2016,
        dispatch_date: "2026-04-22",
        delivery_address: "1341 Dandenong Road, Chadstone VIC 3148",
        lat: -37.886,
        lng: 145.0836,
        postcode: "3148",
        zone_code: "SOUTH_EAST",
        urgency: "NORMAL",
        window_start: "09:00",
        window_end: "15:00",
        load_type: "ON_PALLET",
        kg_count: 220,
        pallet_count: 3,
        bag_count: 0
      },
      {
        order_id: 2017,
        dispatch_date: "2026-04-22",
        delivery_address: "1 Warrigal Road, Chadstone VIC 3148",
        lat: -37.8855,
        lng: 145.0838,
        postcode: "3148",
        zone_code: "SOUTH_EAST",
        urgency: "URGENT",
        window_start: "08:00",
        window_end: "12:00",
        load_type: "ON_PALLET",
        kg_count: 240,
        pallet_count: 3,
        bag_count: 0
      },
      {
        order_id: 2018,
        dispatch_date: "2026-04-22",
        delivery_address: "695 Warrigal Road, Chadstone VIC 3148",
        lat: -37.8769,
        lng: 145.0897,
        postcode: "3148",
        zone_code: "SOUTH_EAST",
        urgency: "NORMAL",
        window_start: "10:00",
        window_end: "16:30",
        load_type: "MIXED",
        kg_count: 125,
        pallet_count: 1,
        bag_count: 8
      },
      {
        order_id: 2019,
        dispatch_date: "2026-04-22",
        delivery_address: "50 Watton Street, Werribee VIC 3030",
        lat: -37.9002,
        lng: 144.6598,
        postcode: "3030",
        zone_code: "WEST",
        urgency: "NORMAL",
        window_start: "10:00",
        window_end: "17:30",
        load_type: "LOOSE",
        kg_count: 64,
        pallet_count: 0,
        bag_count: 12
      },
      {
        order_id: 2020,
        dispatch_date: "2026-04-22",
        delivery_address: "275 Princes Highway, Werribee VIC 3030",
        lat: -37.9008,
        lng: 144.6612,
        postcode: "3030",
        zone_code: "WEST",
        urgency: "NORMAL",
        window_start: "11:00",
        window_end: "18:00",
        load_type: "MIXED",
        kg_count: 132,
        pallet_count: 1,
        bag_count: 7
      }
    ],
    drivers: DRIVER_SEED.map((seed, index) => ({
      driver_id: index + 1,
      name: seed[0],
      shift_start: "08:00",
      shift_end: "17:00",
      is_available: true,
      start_location: "Depot",
      end_location: "Depot",
      preferred_zone_codes: [],
      historical_vehicle_ids: [],
      branch_no: "MEL",
      metadata: {
        name: seed[0],
        license_no: seed[1],
        email: seed[2],
        phone_number: seed[3],
        source: "driver master export"
      }
    })),
    vehicles: VEHICLE_SEED.map((seed) => ({
      vehicle_id: seed[0],
      vehicle_type: seed[2],
      is_available: true,
      kg_capacity: seed[3],
      pallet_capacity: seed[4],
      tub_capacity: seed[5],
      trolley_capacity: seed[6],
      stillage_capacity: seed[7],
      metadata: {
        rego: seed[1],
        source: "vehicle master export",
        raw_capacity: null,
        shelf_count: 0,
        fuel_card_shell: null,
        fuel_card_bp_plus: null,
        linkt_ref: null,
        service_period: null
      }
    }))
  };
}

function createInitialSnapshot() {
  const snapshot = createSampleSnapshot();
  snapshot.orders = [];
  return snapshot;
}

function createEmptyValidation() {
  return {
    errors: [],
    warnings: [],
    rowErrors: {
      orders: new Set(),
      drivers: new Set(),
      vehicles: new Set()
    }
  };
}

function normalizeSnapshotShape(rawSnapshot) {
  if (!isObject(rawSnapshot)) {
    throw new Error("Snapshot 必须是 JSON 对象。");
  }
  const config = isObject(rawSnapshot.config) ? rawSnapshot.config : extractLegacyConfig(rawSnapshot);
  return {
    config: normalizeConfig(config),
    orders: safeArray(rawSnapshot.orders).map((item) => deepClone(item)),
    drivers: safeArray(rawSnapshot.drivers).map((item) => deepClone(item)),
    vehicles: safeArray(rawSnapshot.vehicles).map((item) => deepClone(item))
  };
}

function extractLegacyConfig(snapshot) {
  const keys = [
    "zone_by_postcode",
    "zone_label_by_code",
    "legacy_zone_code_by_id",
    "geocoder",
    "branch_locations",
    "bucket_minutes",
    "loose_units_per_tub",
    "average_speed_kph",
    "minimum_travel_minutes",
    "max_repair_iterations"
  ];
  const config = {};
  for (const key of keys) {
    if (key in snapshot) {
      config[key] = deepClone(snapshot[key]);
    }
  }
  return config;
}

function normalizeConfig(rawConfig) {
  const config = isObject(rawConfig) ? deepClone(rawConfig) : {};
  config.bucket_minutes = positiveInt(config.bucket_minutes, DEFAULT_CONFIG.bucket_minutes);
  config.loose_units_per_tub = positiveInt(config.loose_units_per_tub, DEFAULT_CONFIG.loose_units_per_tub);
  config.average_speed_kph = positiveInt(config.average_speed_kph, DEFAULT_CONFIG.average_speed_kph);
  config.minimum_travel_minutes = positiveInt(config.minimum_travel_minutes, DEFAULT_CONFIG.minimum_travel_minutes);
  config.max_repair_iterations = nonNegativeInt(config.max_repair_iterations, DEFAULT_CONFIG.max_repair_iterations);

  if (!isObject(config.zone_by_postcode)) config.zone_by_postcode = deepClone(DEFAULT_CONFIG.zone_by_postcode);
  if (!isObject(config.zone_label_by_code)) config.zone_label_by_code = deepClone(DEFAULT_CONFIG.zone_label_by_code);
  if (!isObject(config.legacy_zone_code_by_id)) config.legacy_zone_code_by_id = {};
  if (!isObject(config.geocoder)) config.geocoder = deepClone(DEFAULT_CONFIG.geocoder);
  if (!isObject(config.branch_locations)) config.branch_locations = deepClone(DEFAULT_CONFIG.branch_locations);

  config.zone_by_postcode = Object.assign(
    {},
    APP_BUILTIN_ZONE_BY_POSTCODE,
    Object.fromEntries(
      Object.entries(config.zone_by_postcode)
        .map(([postcode, zoneCode]) => [asText(postcode).trim(), asText(zoneCode).trim()])
        .filter(([postcode, zoneCode]) => postcode !== "" && zoneCode !== "")
    )
  );
  config.zone_label_by_code = Object.fromEntries(
    Object.entries(config.zone_label_by_code)
      .map(([zoneCode, label]) => [asText(zoneCode).trim(), asText(label).trim()])
      .filter(([zoneCode]) => zoneCode !== "")
  );
  config.legacy_zone_code_by_id = Object.fromEntries(
    Object.entries(config.legacy_zone_code_by_id)
      .map(([zoneId, zoneCode]) => [asText(zoneId).trim(), asText(zoneCode).trim()])
      .filter(([zoneId, zoneCode]) => zoneId !== "" && zoneCode !== "")
  );
  return config;
}

function snapshotToViewModel(snapshot) {
  const config = normalizeConfig(snapshot.config);
  const configExtra = omitKeys(config, Object.values(CONFIG_INPUT_MAP));
  const compatibilityNotes = [];

  const orders = safeArray(snapshot.orders).map((order, index) => {
    const known = [
      "order_id",
      "dispatch_date",
      "delivery_address",
      "postcode",
      "zone_code",
      "zone_id",
      "urgency",
      "window_start",
      "window_end",
      "designated_driver_id",
      "load_type",
      "kg_count",
      "pallet_count",
      "bag_count"
    ];
    const postcode = asText(order.postcode).trim();
    const mappedByPostcode = resolveZoneCodeByPostcode(postcode, config.zone_by_postcode);
    const explicitZoneCode = asText(order.zone_code).trim();
    const legacyZoneId = asText(order.zone_id).trim();
    const mappedByLegacyId = asText(config.legacy_zone_code_by_id?.[legacyZoneId]).trim();
    const zoneCode = mappedByPostcode;
    if (!mappedByPostcode && explicitZoneCode) {
      compatibilityNotes.push(`Order ${index + 1}: zone_code exists but postcode mapping is missing, zone display cleared.`);
    }
    if (!mappedByPostcode && legacyZoneId && mappedByLegacyId) {
      compatibilityNotes.push(`Order ${index + 1}: legacy zone converted code exists but postcode mapping is missing, zone display cleared.`);
    }
    if (mappedByPostcode && explicitZoneCode && explicitZoneCode !== mappedByPostcode) {
      compatibilityNotes.push(`Order ${index + 1}: zone_code conflicts with postcode mapping, using ${mappedByPostcode}.`);
    }
    return createOrderRow({
      order_id: asText(order.order_id),
      dispatch_date: asText(order.dispatch_date) || todayISO(),
      delivery_address: asText(order.delivery_address),
      postcode,
      zone_code: zoneCode,
      urgency: normalizeUrgency(order.urgency),
      preferred_driver_id: asText(order.designated_driver_id),
      pallet_qty: asText(order.pallet_count ?? 0),
      loose_bags: asText(order.bag_count ?? 0),
      window_start: asText(order.window_start) || "08:00",
      window_end: asText(order.window_end) || "10:00",
      _extra: omitKeys(order, known)
    });
  });

  const drivers = safeArray(snapshot.drivers).map((driver, index) => {
    const known = [
      "driver_id",
      "name",
      "shift_start",
      "shift_end",
      "is_available",
      "preferred_zone_codes",
      "preferred_zone_ids",
      "start_location",
      "end_location",
      "metadata"
    ];
    const metadata = isObject(driver.metadata) ? driver.metadata : {};
    const driverName = asText(driver.name).trim() || asText(metadata.name).trim();
    let preferredCodes = [];
    if (Array.isArray(driver.preferred_zone_codes)) {
      preferredCodes = driver.preferred_zone_codes.map((item) => asText(item).trim()).filter((item) => item !== "");
    } else if (Array.isArray(driver.preferred_zone_ids)) {
      preferredCodes = driver.preferred_zone_ids
        .map((zoneId) => asText(config.legacy_zone_code_by_id?.[String(zoneId)]).trim())
        .filter((item) => item !== "");
      if (driver.preferred_zone_ids.length > 0) {
        compatibilityNotes.push(
          preferredCodes.length > 0
            ? `司机第 ${index + 1} 行：preferred_zone_ids 已转换为 preferred_zone_codes。`
            : `司机第 ${index + 1} 行：preferred_zone_ids 无法转换，已置空。`
        );
      }
    }
    return createDriverRow({
      driver_id: asText(driver.driver_id),
      name: driverName,
      shift_start: asText(driver.shift_start) || "08:00",
      shift_end: asText(driver.shift_end) || "17:00",
      is_available: driver.is_available !== false,
      preferred_zone_codes: preferredCodes.join(","),
      start_location: asText(driver.start_location),
      end_location: asText(driver.end_location),
      _extra: omitKeys(driver, known)
    });
  });

  const sourceVehicles = safeArray(snapshot.vehicles).length > 0 ? safeArray(snapshot.vehicles) : createSampleSnapshot().vehicles;
  const vehicles = sourceVehicles.map((vehicle) => {
    const known = [
      "vehicle_id",
      "vehicle_type",
      "is_available",
      "kg_capacity",
      "pallet_capacity",
      "tub_capacity",
      "trolley_capacity",
      "stillage_capacity",
      "metadata"
    ];
    const metadata = isObject(vehicle.metadata) ? vehicle.metadata : {};
    const metadataExtra = omitKeys(metadata, ["rego", "source"]);
    return createVehicleRow({
      vehicle_id: asText(vehicle.vehicle_id),
      rego: asText(metadata.rego),
      vehicle_type: asText(vehicle.vehicle_type) || "van",
      is_available: vehicle.is_available !== false,
      kg_capacity: asText(vehicle.kg_capacity ?? 0),
      pallet_capacity: asText(vehicle.pallet_capacity ?? 0),
      tub_capacity: asText(vehicle.tub_capacity ?? 0),
      trolley_capacity: asText(vehicle.trolley_capacity ?? 0),
      stillage_capacity: asText(vehicle.stillage_capacity ?? 0),
      source: asText(metadata.source || "vehicle master export"),
      _extra: omitKeys(vehicle, known),
      _metadataExtra: metadataExtra
    });
  });

  return {
    config: {
      bucket_minutes: String(config.bucket_minutes),
      loose_units_per_tub: String(config.loose_units_per_tub),
      average_speed_kph: String(config.average_speed_kph),
      minimum_travel_minutes: String(config.minimum_travel_minutes),
      max_repair_iterations: String(config.max_repair_iterations),
      _extra: configExtra
    },
    orders,
    drivers,
    vehicles,
    _compatibility_notes: compatibilityNotes
  };
}

function viewModelToSnapshot(view) {
  const mergedConfig = normalizeConfig(deepClone(view.config._extra || {}));
  mergedConfig.bucket_minutes = positiveInt(view.config.bucket_minutes, DEFAULT_CONFIG.bucket_minutes);
  mergedConfig.loose_units_per_tub = positiveInt(view.config.loose_units_per_tub, DEFAULT_CONFIG.loose_units_per_tub);
  mergedConfig.average_speed_kph = positiveInt(view.config.average_speed_kph, DEFAULT_CONFIG.average_speed_kph);
  mergedConfig.minimum_travel_minutes = positiveInt(view.config.minimum_travel_minutes, DEFAULT_CONFIG.minimum_travel_minutes);
  mergedConfig.max_repair_iterations = nonNegativeInt(view.config.max_repair_iterations, DEFAULT_CONFIG.max_repair_iterations);

  const orders = view.orders.map((row) => {
    const extra = deepClone(row._extra || {});
    const postcode = asText(row.postcode).trim();
    const mappedZoneCode = resolveZoneCodeByPostcode(postcode, mergedConfig.zone_by_postcode);
    const zoneCode = mappedZoneCode || null;
    return Object.assign(extra, {
      order_id: normalizeIdentifier(row.order_id),
      dispatch_date: asText(row.dispatch_date) || todayISO(),
      delivery_address: asText(row.delivery_address).trim(),
      postcode: postcode || null,
      zone_code: zoneCode,
      urgency: normalizeUrgency(row.urgency),
      window_start: normalizeTimeString(row.window_start, "08:00"),
      window_end: normalizeTimeString(row.window_end, "10:00"),
      designated_driver_id: parseOptionalInt(row.preferred_driver_id),
      load_type: asText(extra.load_type || "MIXED").toUpperCase(),
      kg_count: Number.isFinite(toNumber(extra.kg_count)) ? toNumber(extra.kg_count) : 0,
      pallet_count: nonNegativeInt(row.pallet_qty, 0),
      bag_count: nonNegativeInt(row.loose_bags, 0)
    });
  });

  const drivers = view.drivers.map((row) => {
    const extra = deepClone(row._extra || {});
    const metadata = isObject(extra.metadata) ? deepClone(extra.metadata) : {};
    const driverName = asText(row.name).trim();
    if (driverName) metadata.name = driverName;
    else if ("name" in metadata) delete metadata.name;
    const parsedZones = parseZoneList(row.preferred_zone_codes);
    return Object.assign(extra, {
      driver_id: normalizeIdentifier(row.driver_id),
      shift_start: normalizeTimeString(row.shift_start, "08:00"),
      shift_end: normalizeTimeString(row.shift_end, "17:00"),
      is_available: row.is_available !== false,
      preferred_zone_codes: parsedZones.values,
      start_location: asText(row.start_location).trim(),
      end_location: asText(row.end_location).trim(),
      metadata
    });
  });

  const vehicles = view.vehicles.map((row) => {
    const extra = deepClone(row._extra || {});
    const metadata = deepClone(row._metadataExtra || {});
    metadata.rego = asText(row.rego).trim();
    metadata.source = asText(row.source).trim() || "vehicle master export";
    return Object.assign(extra, {
      vehicle_id: normalizeIdentifier(row.vehicle_id),
      vehicle_type: asText(row.vehicle_type).trim() || "van",
      is_available: row.is_available !== false,
      kg_capacity: nonNegativeNumber(row.kg_capacity, 0),
      pallet_capacity: nonNegativeInt(row.pallet_capacity, 0),
      tub_capacity: nonNegativeInt(row.tub_capacity, 0),
      trolley_capacity: nonNegativeInt(row.trolley_capacity, 0),
      stillage_capacity: nonNegativeInt(row.stillage_capacity, 0),
      metadata
    });
  });

  return { config: mergedConfig, orders, drivers, vehicles };
}

function applySnapshotToState(rawSnapshot) {
  appState.snapshot = normalizeSnapshotShape(rawSnapshot);
  appState.view = snapshotToViewModel(appState.snapshot);
  appState.validation = createEmptyValidation();
  renderWorkbench();
  renderValidationPanel(appState.validation);
  renderSnapshotEditor();
}

function loadSampleData() {
  applySnapshotToState(createSampleSnapshot());
  appState.result = deepClone(EMPTY_RESULT);
  renderResult(appState.result);
  setImportReport("");
  banner("样例数据已加载，可直接生成计划。", "info");
}

function renderWorkbench() {
  renderConfigInputs();
  renderOrdersTable();
  renderDriversTable();
  renderVehiclesTable();
}

function renderConfigInputs() {
  const cfg = appState.view.config;
  setIf("cfgBucketMinutes", cfg.bucket_minutes);
  setIf("cfgLooseUnitsPerTub", cfg.loose_units_per_tub);
  setIf("cfgAverageSpeed", cfg.average_speed_kph);
  setIf("cfgMinTravel", cfg.minimum_travel_minutes);
  setIf("cfgMaxRepair", cfg.max_repair_iterations);
}

function renderOrdersTable() {
  const tbody = get("ordersTableBody");
  if (!tbody) return;
  const zoneLabelByCode = appState.view.config._extra?.zone_label_by_code || {};
  const rowErrors = appState.validation.rowErrors.orders;
  tbody.innerHTML = appState.view.orders
    .map((row, index) => {
      const hasError = rowErrors.has(index);
      const zoneCode = asText(row.zone_code).trim();
      const zoneLabel = resolveZoneLabelByCode(zoneCode, zoneLabelByCode);
      return `
        <tr data-index="${index}" class="${hasError ? "row-error" : ""}">
          <td><input data-field="order_id" value="${escapeHtml(asText(row.order_id))}" /></td>
          <td><input data-field="dispatch_date" type="date" value="${escapeHtml(asText(row.dispatch_date))}" /></td>
          <td><input data-field="delivery_address" value="${escapeHtml(asText(row.delivery_address))}" /></td>
          <td><input data-field="postcode" value="${escapeHtml(asText(row.postcode))}" /></td>
          <td title="${escapeHtml(zoneCode)}">${escapeHtml(zoneLabel)}</td>
          <td>
            <select data-field="urgency">
              <option value="NORMAL" ${row.urgency === "NORMAL" ? "selected" : ""}>NORMAL</option>
              <option value="URGENT" ${row.urgency === "URGENT" ? "selected" : ""}>URGENT</option>
            </select>
          </td>
          <td><input data-field="preferred_driver_id" value="${escapeHtml(asText(row.preferred_driver_id))}" placeholder="可选" /></td>
          <td><input data-field="pallet_qty" type="number" min="0" value="${escapeHtml(asText(row.pallet_qty))}" /></td>
          <td><input data-field="loose_bags" type="number" min="0" value="${escapeHtml(asText(row.loose_bags))}" /></td>
          <td><input data-field="window_start" value="${escapeHtml(asText(row.window_start))}" /></td>
          <td><input data-field="window_end" value="${escapeHtml(asText(row.window_end))}" /></td>
          <td><button class="button button-mini button-danger" data-action="delete-order" data-index="${index}">删除</button></td>
        </tr>
      `;
    })
    .join("");
}

function renderDriversTable() {
  const tbody = get("driversTableBody");
  if (!tbody) return;
  const rowErrors = appState.validation.rowErrors.drivers;
  tbody.innerHTML = appState.view.drivers
    .map((row, index) => {
      const hasError = rowErrors.has(index);
      return `
        <tr data-index="${index}" class="${hasError ? "row-error" : ""}">
          <td><input data-field="driver_id" value="${escapeHtml(asText(row.driver_id))}" /></td>
          <td><input data-field="name" value="${escapeHtml(asText(row.name))}" /></td>
          <td><input data-field="shift_start" value="${escapeHtml(asText(row.shift_start))}" /></td>
          <td><input data-field="shift_end" value="${escapeHtml(asText(row.shift_end))}" /></td>
          <td><input data-field="is_available" type="checkbox" ${row.is_available ? "checked" : ""} /></td>
          <td><input data-field="preferred_zone_codes" value="${escapeHtml(asText(row.preferred_zone_codes))}" placeholder="LOCAL,WEST" /></td>
          <td><input data-field="start_location" value="${escapeHtml(asText(row.start_location))}" /></td>
          <td><input data-field="end_location" value="${escapeHtml(asText(row.end_location))}" /></td>
          <td><button class="button button-mini button-danger" data-action="delete-driver" data-index="${index}">删除</button></td>
        </tr>
      `;
    })
    .join("");
}

function renderVehiclesTable() {
  const tbody = get("vehiclesTableBody");
  if (!tbody) return;
  const rowErrors = appState.validation.rowErrors.vehicles;
  tbody.innerHTML = appState.view.vehicles
    .map((row, index) => {
      const hasError = rowErrors.has(index);
      return `
        <tr data-index="${index}" class="${hasError ? "row-error" : ""}">
          <td><input data-field="vehicle_id" value="${escapeHtml(asText(row.vehicle_id))}" /></td>
          <td><input data-field="rego" value="${escapeHtml(asText(row.rego))}" /></td>
          <td><input data-field="vehicle_type" value="${escapeHtml(asText(row.vehicle_type))}" /></td>
          <td><input data-field="is_available" type="checkbox" ${row.is_available ? "checked" : ""} /></td>
          <td><input data-field="kg_capacity" type="number" min="0" value="${escapeHtml(asText(row.kg_capacity))}" /></td>
          <td><input data-field="pallet_capacity" type="number" min="0" value="${escapeHtml(asText(row.pallet_capacity))}" /></td>
          <td><input data-field="tub_capacity" type="number" min="0" value="${escapeHtml(asText(row.tub_capacity))}" /></td>
          <td><input data-field="trolley_capacity" type="number" min="0" value="${escapeHtml(asText(row.trolley_capacity))}" /></td>
          <td><input data-field="stillage_capacity" type="number" min="0" value="${escapeHtml(asText(row.stillage_capacity))}" /></td>
          <td><input data-field="source" value="${escapeHtml(asText(row.source))}" /></td>
          <td><button class="button button-mini button-danger" data-action="delete-vehicle" data-index="${index}">删除</button></td>
        </tr>
      `;
    })
    .join("");
  const badge = get("vehiclesCountBadge");
  if (badge) badge.textContent = `${appState.view.vehicles.length} 台`;
}

function handleAddOrder() {
  appState.view.orders.push(createOrderRow({}));
  renderOrdersTable();
}

function handleAddDriver() {
  appState.view.drivers.push(createDriverRow({}));
  renderDriversTable();
}

function handleAddVehicle() {
  appState.view.vehicles.push(createVehicleRow({}));
  renderVehiclesTable();
}

function handleOrderTableClick(event) {
  const button = event.target.closest("button[data-action='delete-order']");
  if (!button) return;
  const index = Number(button.dataset.index);
  appState.view.orders.splice(index, 1);
  renderOrdersTable();
}

function handleDriverTableClick(event) {
  const button = event.target.closest("button[data-action='delete-driver']");
  if (!button) return;
  const index = Number(button.dataset.index);
  appState.view.drivers.splice(index, 1);
  renderDriversTable();
}

function handleVehicleTableClick(event) {
  const button = event.target.closest("button[data-action='delete-vehicle']");
  if (!button) return;
  const index = Number(button.dataset.index);
  appState.view.vehicles.splice(index, 1);
  renderVehiclesTable();
}

function handleOrderTableInput(event) {
  const target = event.target;
  if (!target || !target.dataset.field) return;
  const row = target.closest("tr");
  if (!row) return;
  const index = Number(row.dataset.index);
  const field = target.dataset.field;
  const current = appState.view.orders[index];
  if (!current) return;
  current[field] = target.type === "checkbox" ? target.checked : target.value;
  if (field === "postcode") {
    current.zone_code = resolveZoneCodeByPostcode(current.postcode, appState.view.config._extra?.zone_by_postcode || {});
    const zoneCell = row.querySelector("td:nth-child(5)");
    if (zoneCell) {
      const zoneLabelByCode = appState.view.config._extra?.zone_label_by_code || {};
      zoneCell.title = asText(current.zone_code);
      zoneCell.textContent = resolveZoneLabelByCode(current.zone_code, zoneLabelByCode);
    }
  }
}

function handleDriverTableInput(event) {
  const target = event.target;
  if (!target || !target.dataset.field) return;
  const row = target.closest("tr");
  if (!row) return;
  const index = Number(row.dataset.index);
  const field = target.dataset.field;
  const current = appState.view.drivers[index];
  if (!current) return;
  current[field] = target.type === "checkbox" ? target.checked : target.value;
}

function handleVehicleTableInput(event) {
  const target = event.target;
  if (!target || !target.dataset.field) return;
  const row = target.closest("tr");
  if (!row) return;
  const index = Number(row.dataset.index);
  const field = target.dataset.field;
  const current = appState.view.vehicles[index];
  if (!current) return;
  current[field] = target.type === "checkbox" ? target.checked : target.value;
}

function validateViewModel(view, options = { normalize: false }) {
  const report = createEmptyValidation();
  const normalize = options?.normalize === true;
  const config = view.config;
  config.bucket_minutes = String(positiveInt(config.bucket_minutes, DEFAULT_CONFIG.bucket_minutes));
  config.loose_units_per_tub = String(positiveInt(config.loose_units_per_tub, DEFAULT_CONFIG.loose_units_per_tub));
  config.average_speed_kph = String(positiveInt(config.average_speed_kph, DEFAULT_CONFIG.average_speed_kph));
  config.minimum_travel_minutes = String(positiveInt(config.minimum_travel_minutes, DEFAULT_CONFIG.minimum_travel_minutes));
  config.max_repair_iterations = String(nonNegativeInt(config.max_repair_iterations, DEFAULT_CONFIG.max_repair_iterations));

  for (let index = 0; index < view.orders.length; index += 1) {
    const row = view.orders[index];
    if (isBlank(row.delivery_address)) {
      report.errors.push(`Orders 第 ${index + 1} 行：delivery_address 不能为空。`);
      report.rowErrors.orders.add(index);
    }
    const postcode = asText(row.postcode).trim();
    if (postcode === "") {
      report.errors.push(`Orders 第 ${index + 1} 行：postcode 不能为空。`);
      report.rowErrors.orders.add(index);
      continue;
    }
    const mappedZone = resolveZoneCodeByPostcode(postcode, view.config._extra?.zone_by_postcode || {});
    if (!mappedZone) {
      report.errors.push(`Orders 第 ${index + 1} 行：postcode 未命中 zone 映射。`);
      report.rowErrors.orders.add(index);
      continue;
    }
    if (normalize) row.zone_code = mappedZone;

    const start = parseTimeToMinutes(row.window_start);
    const end = parseTimeToMinutes(row.window_end);
    if (start === null || end === null || start >= end) {
      report.errors.push(`Orders 第 ${index + 1} 行：window_start / window_end 无效。`);
      report.rowErrors.orders.add(index);
    }
    if (normalize) {
      row.dispatch_date = asText(row.dispatch_date) || todayISO();
      row.urgency = normalizeUrgency(row.urgency);
      row.pallet_qty = String(nonNegativeInt(row.pallet_qty, 0));
      row.loose_bags = String(nonNegativeInt(row.loose_bags, 0));
      row.window_start = normalizeTimeString(row.window_start, "08:00");
      row.window_end = normalizeTimeString(row.window_end, "10:00");
    }
  }

  for (let index = 0; index < view.drivers.length; index += 1) {
    const row = view.drivers[index];
    const start = parseTimeToMinutes(row.shift_start);
    const end = parseTimeToMinutes(row.shift_end);
    if (start === null || end === null || start >= end) {
      report.errors.push(`Drivers 第 ${index + 1} 行：shift_start / shift_end 无效。`);
      report.rowErrors.drivers.add(index);
    }
    const zoneParse = parseZoneList(row.preferred_zone_codes);
    if (zoneParse.invalid) {
      report.errors.push(`Drivers 第 ${index + 1} 行：preferred_zone_codes 仅支持逗号分隔编码。`);
      report.rowErrors.drivers.add(index);
    } else if (normalize) {
      row.preferred_zone_codes = zoneParse.values.join(",");
    }
  }

  for (let index = 0; index < view.vehicles.length; index += 1) {
    const row = view.vehicles[index];
    if (normalize) {
      row.kg_capacity = String(nonNegativeNumber(row.kg_capacity, 0));
      row.pallet_capacity = String(nonNegativeInt(row.pallet_capacity, 0));
      row.tub_capacity = String(nonNegativeInt(row.tub_capacity, 0));
      row.trolley_capacity = String(nonNegativeInt(row.trolley_capacity, 0));
      row.stillage_capacity = String(nonNegativeInt(row.stillage_capacity, 0));
    }
  }
  return report;
}

function handleSyncSnapshotJson() {
  const report = validateViewModel(appState.view, { normalize: true });
  appState.validation = report;
  renderValidationPanel(report);
  renderWorkbench();
  if (report.errors.length > 0) {
    banner("存在阻断错误，无法生成 JSON。请先修复高亮行。", "error");
    return;
  }
  appState.snapshot = viewModelToSnapshot(appState.view);
  renderSnapshotEditor();
  banner("已从表格生成最新 Snapshot JSON。", "success");
}

function handleApplySnapshotJson() {
  const raw = asText(get("snapshotEditor")?.value).trim();
  if (!raw) {
    banner("开发者模式 JSON 为空，无法回填。", "error");
    return;
  }
  try {
    applySnapshotToState(JSON.parse(raw));
    banner("已根据 JSON 回填表格。", "success");
  } catch (error) {
    banner(`JSON 回填失败：${error.message}`, "error");
  }
}

function handleExportSnapshot() {
  const report = validateViewModel(appState.view, { normalize: true });
  appState.validation = report;
  renderValidationPanel(report);
  renderWorkbench();
  if (report.errors.length > 0) {
    banner("存在阻断错误，无法导出 Snapshot。", "error");
    return;
  }
  appState.snapshot = viewModelToSnapshot(appState.view);
  renderSnapshotEditor();
  const blob = new Blob([prettyJson(appState.snapshot)], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "dispatch-snapshot.json";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
  banner("Snapshot 已导出。", "success");
}

function handleRunPlanner() {
  const report = validateViewModel(appState.view, { normalize: true });
  appState.validation = report;
  renderValidationPanel(report);
  renderWorkbench();
  if (report.errors.length > 0) {
    banner(`存在 ${report.errors.length} 条阻断错误，无法生成计划。`, "error");
    return;
  }
  appState.snapshot = viewModelToSnapshot(appState.view);
  renderSnapshotEditor();
  appState.result = planDispatch(appState.snapshot);
  renderResult(appState.result);
  const warningSuffix = report.warnings.length > 0 ? `，并自动规范了 ${report.warnings.length} 处输入` : "";
  banner(
    `已生成 ${appState.result.plans.length} 个计划，订单分配 ${appState.result.order_assignments.length} 条，异常 ${appState.result.exceptions.length} 条${warningSuffix}。`,
    "success"
  );
}

function normalizePlannerInput(snapshot) {
  const config = normalizeConfig(snapshot.config);
  const exceptions = [];

  const orders = safeArray(snapshot.orders)
    .map((order) => {
      if (isBlank(order.delivery_address)) {
        exceptions.push(makeException("ORDER", order.order_id, "MISSING_ADDRESS", "订单缺少 delivery_address。", "请补齐地址。", normalizeUrgency(order.urgency) === "URGENT"));
        return null;
      }
      const postcode = asText(order.postcode).trim();
      const mappedZoneCode = resolveZoneCodeByPostcode(postcode, config.zone_by_postcode);
      const zoneCode = mappedZoneCode;
      if (!zoneCode) {
        exceptions.push(makeException("ORDER", order.order_id, "POSTCODE_NOT_MAPPED", "No zone mapping found for postcode.", "请补充 postcode 或完善 zone_by_postcode 映射。", normalizeUrgency(order.urgency) === "URGENT"));
        return null;
      }
      const windowStart = parseTimeToMinutes(order.window_start);
      const windowEnd = parseTimeToMinutes(order.window_end);
      if (windowStart === null || windowEnd === null || windowStart >= windowEnd) {
        exceptions.push(makeException("ORDER", order.order_id, "INVALID_TIME_WINDOW", "订单时间窗无效。", "请修正窗口时间。", normalizeUrgency(order.urgency) === "URGENT"));
        return null;
      }
      const location = resolveLocation(order.delivery_address, order.lat, order.lng, config.geocoder);
      if (!location) {
        exceptions.push(makeException("ORDER", order.order_id, "MISSING_COORDINATES", "订单地址无法解析坐标。", "请在 geocoder 中维护地址坐标或提供 lat/lng。", normalizeUrgency(order.urgency) === "URGENT"));
        return null;
      }
      return {
        order_id: normalizeIdentifier(order.order_id),
        dispatch_date: asText(order.dispatch_date) || todayISO(),
        delivery_address: asText(order.delivery_address),
        lat: location.lat,
        lng: location.lng,
        postcode: postcode || null,
        zone_code: zoneCode,
        urgency: normalizeUrgency(order.urgency),
        window_start: windowStart,
        window_end: windowEnd,
        designated_driver_id: parseOptionalInt(order.designated_driver_id),
        load_type: asText(order.load_type || "MIXED").toUpperCase(),
        kg_count: nonNegativeNumber(order.kg_count, 0),
        pallet_count: nonNegativeInt(order.pallet_count, 0),
        bag_count: nonNegativeInt(order.bag_count, 0)
      };
    })
    .filter(Boolean);

  const drivers = safeArray(snapshot.drivers)
    .map((driver) => {
      const shiftStart = parseTimeToMinutes(driver.shift_start);
      const shiftEnd = parseTimeToMinutes(driver.shift_end);
      if (shiftStart === null || shiftEnd === null || shiftStart >= shiftEnd) {
        exceptions.push(makeException("DRIVER", driver.driver_id, "INVALID_SHIFT", "司机班次时间无效。", "请检查 shift_start / shift_end。"));
        return null;
      }
      const startRef = resolveDriverRef(driver.start_location, driver.start_lat, driver.start_lng, driver.branch_no, config);
      const endRef = resolveDriverRef(driver.end_location, driver.end_lat, driver.end_lng, driver.branch_no, config);
      if (!startRef || !endRef) {
        exceptions.push(makeException("DRIVER", driver.driver_id, "MISSING_DRIVER_LOCATION", "司机缺少可解析起终点。", "请补充起终点地址或 branch_locations。"));
        return null;
      }
      const preferredZoneCodes = Array.isArray(driver.preferred_zone_codes)
        ? driver.preferred_zone_codes.map((item) => asText(item).trim()).filter((item) => item !== "")
        : Array.isArray(driver.preferred_zone_ids)
          ? driver.preferred_zone_ids
              .map((item) => asText(config.legacy_zone_code_by_id?.[String(item)]).trim())
              .filter((item) => item !== "")
          : [];
      const metadataName = asText(driver?.metadata?.name).trim();
      return {
        driver_id: normalizeIdentifier(driver.driver_id),
        display_name: asText(driver.name).trim() || metadataName || normalizeIdentifier(driver.driver_id),
        shift_start: shiftStart,
        shift_end: shiftEnd,
        is_available: driver.is_available !== false,
        start_ref: startRef,
        end_ref: endRef,
        preferred_zone_codes: preferredZoneCodes,
        historical_vehicle_ids: Array.isArray(driver.historical_vehicle_ids) ? driver.historical_vehicle_ids.map((item) => normalizeIdentifier(item)) : []
      };
    })
    .filter((driver) => driver && driver.is_available);

  const vehicles = safeArray(snapshot.vehicles)
    .map((vehicle) => {
      const tub = nonNegativeInt(vehicle.tub_capacity, 0);
      return {
        vehicle_id: normalizeIdentifier(vehicle.vehicle_id),
        is_available: vehicle.is_available !== false,
        capacity: {
          kg: nonNegativeNumber(vehicle.kg_capacity, 0),
          pallets: nonNegativeInt(vehicle.pallet_capacity, 0),
          tubs: tub,
          loose_units: Number.isFinite(toNumber(vehicle.loose_capacity)) ? nonNegativeInt(vehicle.loose_capacity, 0) : tub * positiveInt(config.loose_units_per_tub, 4),
          trolleys: nonNegativeInt(vehicle.trolley_capacity, 0),
          stillages: nonNegativeInt(vehicle.stillage_capacity, 0)
        }
      };
    })
    .filter((vehicle) => vehicle && vehicle.is_available);

  if (drivers.length === 0) {
    exceptions.push(makeException("SYSTEM", "drivers", "NO_AVAILABLE_DRIVERS", "当前没有可用司机。", "请检查司机可用状态与班次。"));
  }
  if (vehicles.length === 0) {
    exceptions.push(makeException("SYSTEM", "vehicles", "NO_AVAILABLE_VEHICLES", "当前没有可用车辆。", "请检查车辆可用状态。"));
  }

  return { config, orders, drivers, vehicles, exceptions };
}

function maxVehicleCapacity(vehicles) {
  const base = { kg: 0, pallets: 0, tubs: 0, loose_units: 0, trolleys: 0, stillages: 0 };
  for (const vehicle of safeArray(vehicles)) {
    const capacity = vehicle.capacity || {};
    base.kg = Math.max(base.kg, nonNegativeNumber(capacity.kg, 0));
    base.pallets = Math.max(base.pallets, nonNegativeInt(capacity.pallets, 0));
    base.tubs = Math.max(base.tubs, nonNegativeInt(capacity.tubs, 0));
    base.loose_units = Math.max(base.loose_units, nonNegativeInt(capacity.loose_units, 0));
    base.trolleys = Math.max(base.trolleys, nonNegativeInt(capacity.trolleys, 0));
    base.stillages = Math.max(base.stillages, nonNegativeInt(capacity.stillages, 0));
  }
  return base;
}

function groupEntityId(group) {
  return `orders:${safeArray(group.orders).map((order) => asText(order.order_id)).join(",")}`;
}

function canMergeOrderIntoGroup(group, order, config) {
  if (safeArray(group.orders).length >= positiveInt(config.max_stops_per_run, 12)) return false;
  if (group.designated_driver_id && order.designated_driver_id && group.designated_driver_id !== order.designated_driver_id) return false;
  const overlap = Math.min(group.window_end, order.window_end) - Math.max(group.window_start, order.window_start);
  return overlap > 0;
}

function buildGroupFromOrder(order, config) {
  const load = orderToLoad(order, config);
  return {
    plan_group_id: "",
    dispatch_date: order.dispatch_date,
    zone_code: order.zone_code,
    bucket_start: Math.floor(order.window_start / positiveInt(config.bucket_minutes, 120)) * positiveInt(config.bucket_minutes, 120),
    bucket_end: Math.min(
      Math.floor(order.window_start / positiveInt(config.bucket_minutes, 120)) * positiveInt(config.bucket_minutes, 120) +
        positiveInt(config.bucket_minutes, 120),
      24 * 60
    ),
    orders: [order],
    load,
    designated_driver_id: order.designated_driver_id,
    urgent_count: order.urgency === "URGENT" ? 1 : 0,
    window_start: order.window_start,
    window_end: order.window_end,
    estimated_service_minutes: FIXED_STOP_MINUTES
  };
}

function cloneMergedGroup(group, order, config) {
  const orderLoad = orderToLoad(order, config);
  const orders = [...group.orders, order];
  const designatedDriverIds = [...new Set(orders.map((item) => item.designated_driver_id).filter((item) => item !== null))];
  return {
    ...group,
    orders,
    load: sumLoad(group.load, orderLoad),
    designated_driver_id: designatedDriverIds.length === 1 ? designatedDriverIds[0] : null,
    urgent_count: orders.filter((item) => item.urgency === "URGENT").length,
    window_start: Math.min(group.window_start, order.window_start),
    window_end: Math.max(group.window_end, order.window_end),
    estimated_service_minutes: orders.length * FIXED_STOP_MINUTES
  };
}

function existsFeasibleVehicleForGroup(group, vehicles) {
  return safeArray(vehicles).some((vehicle) => loadFits(group.load, vehicle.capacity));
}

function existsFeasibleDriverVehicleForGroup(group, drivers, vehicles, config) {
  for (const driver of safeArray(drivers)) {
    if (group.designated_driver_id !== null && driver.driver_id !== group.designated_driver_id) continue;
    const estimate = estimateTripWindow(group, driver, config);
    if (!estimate.feasible) continue;
    for (const vehicle of safeArray(vehicles)) {
      if (!loadFits(group.load, vehicle.capacity)) continue;
      return true;
    }
  }
  return false;
}

function minCapacityWasteForGroup(group, vehicles) {
  let best = Number.POSITIVE_INFINITY;
  for (const vehicle of safeArray(vehicles)) {
    if (!loadFits(group.load, vehicle.capacity)) continue;
    best = Math.min(best, capacityWaste(group.load, vehicle.capacity));
  }
  return Number.isFinite(best) ? best : Number.POSITIVE_INFINITY;
}

function buildPlanGroups(orders, config, drivers, vehicles) {
  const grouped = new Map();
  const bucketSize = positiveInt(config.bucket_minutes, 120);
  for (const order of orders) {
    const bucketStart = Math.floor(order.window_start / bucketSize) * bucketSize;
    const bucketEnd = Math.min(bucketStart + bucketSize, 24 * 60);
    const key = `${order.dispatch_date}|${order.zone_code}|${bucketStart}|${bucketEnd}`;
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key).push(order);
  }

  const groups = [];
  let sequence = 1;
  const fleetMax = maxVehicleCapacity(vehicles);
  for (const [key, bucketOrders] of grouped.entries()) {
    const [dispatchDate, zoneCode, bucketStartText, bucketEndText] = key.split("|");
    bucketOrders.sort((left, right) => {
      const urgencyDelta = urgencyRank(right.urgency) - urgencyRank(left.urgency);
      if (urgencyDelta !== 0) return urgencyDelta;
      if (left.window_end !== right.window_end) return left.window_end - right.window_end;
      if (left.designated_driver_id && !right.designated_driver_id) return -1;
      if (!left.designated_driver_id && right.designated_driver_id) return 1;
      return asText(left.order_id).localeCompare(asText(right.order_id), undefined, { numeric: true, sensitivity: "base" });
    });

    const bucketGroups = [];
    for (const order of bucketOrders) {
      let bestIndex = -1;
      let bestWaste = Number.POSITIVE_INFINITY;
      for (let index = 0; index < bucketGroups.length; index += 1) {
        const candidate = bucketGroups[index];
        if (!canMergeOrderIntoGroup(candidate, order, config)) continue;
        const merged = cloneMergedGroup(candidate, order, config);
        if (!loadFits(merged.load, fleetMax)) continue;
        if (!existsFeasibleVehicleForGroup(merged, vehicles)) continue;
        if (!existsFeasibleDriverVehicleForGroup(merged, drivers, vehicles, config)) continue;
        const waste = minCapacityWasteForGroup(merged, vehicles);
        if (waste < bestWaste) {
          bestWaste = waste;
          bestIndex = index;
        }
      }

      if (bestIndex >= 0) {
        bucketGroups[bestIndex] = cloneMergedGroup(bucketGroups[bestIndex], order, config);
      } else {
        bucketGroups.push(buildGroupFromOrder(order, config));
      }
    }

    for (const group of bucketGroups) {
      group.plan_group_id = `PLAN-GROUP-${String(sequence).padStart(4, "0")}`;
      group.dispatch_date = dispatchDate;
      group.zone_code = zoneCode;
      group.bucket_start = Number(bucketStartText);
      group.bucket_end = Number(bucketEndText);
      groups.push(group);
      sequence += 1;
    }
  }
  return groups;
}

function planDispatch(snapshot) {
  const prepared = normalizePlannerInput(snapshot);
  const exceptions = [...prepared.exceptions];
  if (prepared.orders.length === 0 || prepared.drivers.length === 0 || prepared.vehicles.length === 0) {
    return { plans: [], order_assignments: [], exceptions };
  }

  const groups = buildPlanGroups(prepared.orders, prepared.config, prepared.drivers, prepared.vehicles);
  const selectedGroups = [];
  const driverSchedule = new Map(prepared.drivers.map((driver) => [driver.driver_id, []]));
  const vehicleSchedule = new Map(prepared.vehicles.map((vehicle) => [vehicle.vehicle_id, []]));
  const selectedByDriverDay = new Map();
  const driverRunCount = new Map(prepared.drivers.map((driver) => [driver.driver_id, 0]));
  const driverMinutes = new Map(prepared.drivers.map((driver) => [driver.driver_id, 0]));
  const candidateStats = new Map(prepared.drivers.map((driver) => [driver.driver_id, { candidateCount: 0, selectedCount: 0 }]));

  const sortedGroups = [...groups].sort(
    (left, right) =>
      (right.urgent_count - left.urgent_count) ||
      (left.window_start - right.window_start) ||
      asText(left.plan_group_id).localeCompare(asText(right.plan_group_id), undefined, { numeric: true, sensitivity: "base" })
  );

  for (const group of sortedGroups) {
    if (group.designated_driver_id !== null && !prepared.drivers.some((driver) => driver.driver_id === group.designated_driver_id)) {
      exceptions.push(
        makeException(
          "GROUP",
          groupEntityId(group),
          "DESIGNATED_DRIVER_UNAVAILABLE",
          "存在指定司机，但该司机当前不可用。",
          "调整指定司机限制或改为人工调度。",
          group.urgent_count > 0,
          { order_ids: group.orders.map((order) => order.order_id), dispatch_date: group.dispatch_date, zone_code: group.zone_code }
        )
      );
      continue;
    }

    const candidates = [];
    const runPriorityScore = computeRunPriorityScore(group);
    for (const driver of prepared.drivers) {
      if (group.designated_driver_id !== null && driver.driver_id !== group.designated_driver_id) continue;
      const estimate = estimateTripWindow(group, driver, prepared.config);
      if (!estimate.feasible) continue;
      for (const vehicle of prepared.vehicles) {
        if (!loadFits(group.load, vehicle.capacity)) continue;
        const preferredZoneMatch = driver.preferred_zone_codes.includes(group.zone_code) ? 1 : 0;
        const driverHasZonePreference = driver.preferred_zone_codes.length > 0;
        const zoneMismatch = driverHasZonePreference && !preferredZoneMatch ? 1 : 0;
        const continuityMatch = driver.historical_vehicle_ids.includes(vehicle.vehicle_id) ? 1 : 0;
        const waste = Math.round(capacityWaste(group.load, vehicle.capacity) * 100);
        const efficiencyScore =
          -(estimate.travel_minutes * 120) -
          (estimate.deadhead_minutes * 45) -
          waste +
          preferredZoneMatch * 3000 -
          zoneMismatch * 2500 +
          continuityMatch * 160;
        const objectiveScore = runPriorityScore * 10_000 + efficiencyScore;
        candidates.push({
          group,
          driver,
          vehicle,
          estimate,
          preferred_zone_match: preferredZoneMatch,
          zone_mismatch: zoneMismatch,
          objective_score: objectiveScore,
          explanation: [
            `Assignment group ${group.plan_group_id} satisfies vehicle ${vehicle.vehicle_id} capacity`,
            `Coarse time check ${minutesToHHMM(estimate.estimated_start)}-${minutesToHHMM(estimate.estimated_finish)} within shift`,
            preferredZoneMatch
              ? "Preferred zone matched."
              : (zoneMismatch ? "Driver preferred zone mismatch applied" : "Driver has no preferred zone constraint"),
            continuityMatch ? "Matched historical driver-vehicle continuity" : "No historical driver-vehicle continuity match"
          ]
        });
        const stats = candidateStats.get(driver.driver_id);
        if (stats) stats.candidateCount += 1;
      }
    }

    if (candidates.length === 0) {
      exceptions.push(
        makeException(
          "GROUP",
          groupEntityId(group),
          "NO_FEASIBLE_ASSIGNMENT",
          "没有任何司机-车辆组合可满足 trip 的容量与粗粒度时间约束。",
          "请补充资源或放宽约束后重试。",
          group.urgent_count > 0,
          { order_ids: group.orders.map((order) => order.order_id), dispatch_date: group.dispatch_date, zone_code: group.zone_code }
        )
      );
      continue;
    }

    candidates.sort((left, right) => {
      const leftPreferredRank = left.preferred_zone_match ? 0 : 1;
      const rightPreferredRank = right.preferred_zone_match ? 0 : 1;
      if (leftPreferredRank !== rightPreferredRank) return leftPreferredRank - rightPreferredRank;

      const leftSameZoneRank = sameZoneContinuityHit(left, selectedByDriverDay) ? 0 : 1;
      const rightSameZoneRank = sameZoneContinuityHit(right, selectedByDriverDay) ? 0 : 1;
      if (leftSameZoneRank !== rightSameZoneRank) return leftSameZoneRank - rightSameZoneRank;

      const leftMismatchRank = zoneMismatchRank(left);
      const rightMismatchRank = zoneMismatchRank(right);
      if (leftMismatchRank !== rightMismatchRank) return leftMismatchRank - rightMismatchRank;

      const leftSwitch = switchDeltaForCandidate(left, selectedByDriverDay);
      const rightSwitch = switchDeltaForCandidate(right, selectedByDriverDay);
      if (leftSwitch !== rightSwitch) return leftSwitch - rightSwitch;

      const leftRuns = driverRunCount.get(left.driver.driver_id) || 0;
      const rightRuns = driverRunCount.get(right.driver.driver_id) || 0;
      const leftMinutes = driverMinutes.get(left.driver.driver_id) || 0;
      const rightMinutes = driverMinutes.get(right.driver.driver_id) || 0;

      const leftBusiness =
        left.objective_score +
        (leftRuns === 0 ? 800 : 0) -
        leftRuns * 180 -
        leftMinutes * 25;
      const rightBusiness =
        right.objective_score +
        (rightRuns === 0 ? 800 : 0) -
        rightRuns * 180 -
        rightMinutes * 25;
      if (leftBusiness !== rightBusiness) return rightBusiness - leftBusiness;

      if (left.estimate.estimated_finish !== right.estimate.estimated_finish) {
        return left.estimate.estimated_finish - right.estimate.estimated_finish;
      }
      const groupDiff = asText(left.group.plan_group_id).localeCompare(
        asText(right.group.plan_group_id),
        undefined,
        { numeric: true, sensitivity: "base" }
      );
      if (groupDiff !== 0) return groupDiff;
      return asText(left.vehicle.vehicle_id).localeCompare(asText(right.vehicle.vehicle_id), undefined, { numeric: true, sensitivity: "base" });
    });
    const picked = candidates.find((candidate) => {
      const driverIntervals = driverSchedule.get(candidate.driver.driver_id);
      const vehicleIntervals = vehicleSchedule.get(candidate.vehicle.vehicle_id);
      return !hasTripOverlap(driverIntervals, candidate.estimate) && !hasTripOverlap(vehicleIntervals, candidate.estimate);
    });

    if (!picked) {
      exceptions.push(
        makeException(
          "GROUP",
          groupEntityId(group),
          "PLAN_UNASSIGNED",
          "候选资源与已有任务时间重叠，trip 无法自动分配。",
          "建议人工调整，或增加可用司机/车辆。",
          group.urgent_count > 0,
          { order_ids: group.orders.map((order) => order.order_id), dispatch_date: group.dispatch_date, zone_code: group.zone_code }
        )
      );
      const latestPlanUnassigned = exceptions[exceptions.length - 1];
      if (latestPlanUnassigned && latestPlanUnassigned.reason_code === "PLAN_UNASSIGNED") {
        latestPlanUnassigned.reason_text = group.urgent_count > 0
          ? "No feasible assignment remained after applying urgent/zone/continuity priorities under current resource conflicts."
          : "Normal order left unassigned after higher-priority zone/vehicle continuity optimization under existing constraints.";
        latestPlanUnassigned.suggested_action = "Review resource overlaps or add compatible drivers/vehicles.";
      }
      continue;
    }

    const priorRunCount = driverRunCount.get(picked.driver.driver_id) || 0;
    const pickedExplanation = [...picked.explanation];
    if (priorRunCount === 0) {
      pickedExplanation.push("Selected to improve driver utilization.");
    }
    if (group.urgent_count > 0) {
      pickedExplanation.push("Selected due to urgent coverage priority.");
    }
    if (group.designated_driver_id !== null) {
      pickedExplanation.push("Selected due to designated driver requirement.");
    }
    if (picked.preferred_zone_match) {
      pickedExplanation.push("Selected to preserve preferred-zone alignment.");
    } else if (picked.driver.preferred_zone_codes.length > 0) {
      pickedExplanation.push("Cross-zone assignment allowed because higher-priority coverage or feasibility required it.");
    }
    const driverDayKey = `${picked.driver.driver_id}|${picked.group.dispatch_date}`;
    const existingDriverDay = selectedByDriverDay.get(driverDayKey) || [];
    if (existingDriverDay.length > 0) {
      const hasSameVehicle = existingDriverDay.some((item) => asText(item.vehicle.vehicle_id) === asText(picked.vehicle.vehicle_id));
      if (hasSameVehicle) {
        pickedExplanation.push("Kept same vehicle for this driver on the same dispatch date.");
      } else {
        pickedExplanation.push("Vehicle switch required due to capacity/time/resource constraints.");
      }
    }
    driverSchedule.get(picked.driver.driver_id).push([picked.estimate.estimated_start, picked.estimate.estimated_finish]);
    vehicleSchedule.get(picked.vehicle.vehicle_id).push([picked.estimate.estimated_start, picked.estimate.estimated_finish]);
    if (!selectedByDriverDay.has(driverDayKey)) selectedByDriverDay.set(driverDayKey, []);
    selectedByDriverDay.get(driverDayKey).push(picked);
    driverRunCount.set(picked.driver.driver_id, (driverRunCount.get(picked.driver.driver_id) || 0) + 1);
    driverMinutes.set(picked.driver.driver_id, (driverMinutes.get(picked.driver.driver_id) || 0) + (picked.estimate.work_minutes || 0));
    const pickedStats = candidateStats.get(picked.driver.driver_id);
    if (pickedStats) pickedStats.selectedCount += 1;

    selectedGroups.push({
      group,
      candidate: picked,
      explanation: pickedExplanation
    });
  }

  const plans = [];
  const assignments = [];
  const plansByKey = new Map();
  for (const selected of selectedGroups) {
    const group = selected.group;
    const candidate = selected.candidate;
    const planKey = `${group.dispatch_date}|${candidate.driver.driver_id}|${candidate.vehicle.vehicle_id}`;
    let plan = plansByKey.get(planKey);
    if (!plan) {
      plan = {
        plan_id: `PLAN-${String(plansByKey.size + 1).padStart(4, "0")}`,
        dispatch_date: group.dispatch_date,
        driver_id: candidate.driver.driver_id,
        vehicle_id: candidate.vehicle.vehicle_id,
        order_ids: [],
        total_orders: 0,
        load_summary: {
          kg: 0,
          pallets: 0,
          tubs: 0,
          loose_units: 0,
          trolleys: 0,
          stillages: 0
        },
        zone_code: group.zone_code,
        time_window_start: minutesToHHMM(group.window_start),
        time_window_end: minutesToHHMM(group.window_end),
        urgent_order_count: 0,
        objective_score: 0,
        explanation: [],
        stop_sequence: [],
        etas: {},
        planned_start: null,
        planned_finish: null
      };
      plansByKey.set(planKey, plan);
      plans.push(plan);
    }

    plan.order_ids.push(...safeArray(group.orders).map((order) => order.order_id));
    plan.total_orders += safeArray(group.orders).length;
    plan.load_summary.kg = Number((plan.load_summary.kg + Number(group.load.kg || 0)).toFixed(2));
    plan.load_summary.pallets += Number(group.load.pallets || 0);
    plan.load_summary.tubs += Number(group.load.tubs || 0);
    plan.load_summary.loose_units += Number(group.load.loose_units || 0);
    plan.load_summary.trolleys += Number(group.load.trolleys || 0);
    plan.load_summary.stillages += Number(group.load.stillages || 0);
    plan.urgent_order_count += Number(group.urgent_count || 0);
    plan.objective_score += Number(candidate.objective_score || 0);
    plan.time_window_start = minutesToHHMM(Math.min(parseTimeToMinutes(plan.time_window_start) || group.window_start, group.window_start));
    plan.time_window_end = minutesToHHMM(Math.max(parseTimeToMinutes(plan.time_window_end) || group.window_end, group.window_end));
    if (plan.zone_code !== group.zone_code) {
      plan.zone_code = "MULTI_ZONE";
    }
    for (const line of safeArray(selected.explanation)) {
      if (!plan.explanation.includes(line)) {
        plan.explanation.push(line);
      }
    }

    for (const order of safeArray(group.orders)) {
      assignments.push({
        order_id: order.order_id,
        plan_id: plan.plan_id,
        dispatch_date: group.dispatch_date,
        driver_id: candidate.driver.driver_id,
        vehicle_id: candidate.vehicle.vehicle_id,
        status: "ASSIGNED",
        postcode: order.postcode || null,
        zone_code: order.zone_code || null,
        objective_score: candidate.objective_score,
        explanation: selected.explanation,
        stop_sequence: null,
        eta: null,
        departure: null,
        planned_start: null,
        planned_finish: null
      });
    }
  }

  for (const plan of plans) {
    plan.order_ids = Array.from(new Set(plan.order_ids)).sort((left, right) =>
      asText(left).localeCompare(asText(right), undefined, { numeric: true, sensitivity: "base" })
    );
    plan.total_orders = plan.order_ids.length;
  }

  assignments.sort((left, right) => {
    const driverDiff = asText(left.driver_id).localeCompare(asText(right.driver_id), undefined, { numeric: true, sensitivity: "base" });
    if (driverDiff !== 0) return driverDiff;
    const vehicleDiff = asText(left.vehicle_id).localeCompare(asText(right.vehicle_id), undefined, { numeric: true, sensitivity: "base" });
    if (vehicleDiff !== 0) return vehicleDiff;
    const dateDiff = asText(left.dispatch_date).localeCompare(asText(right.dispatch_date));
    if (dateDiff !== 0) return dateDiff;
    return asText(left.order_id).localeCompare(asText(right.order_id), undefined, { numeric: true, sensitivity: "base" });
  });

  exceptions.push(...buildUnusedDriverHints(prepared.drivers, groups, plans.length, candidateStats));

  return { plans, order_assignments: assignments, exceptions };
}

function renderResult(result) {
  const plans = Array.isArray(result?.plans) ? result.plans : [];
  const assignments = Array.isArray(result?.order_assignments) ? result.order_assignments : [];
  const exceptions = Array.isArray(result?.exceptions) ? result.exceptions : [];
  const assignedDrivers = new Set(assignments.map((item) => asText(item.driver_id).trim()).filter((item) => item !== ""));
  if (get("plansCount")) get("plansCount").textContent = String(plans.length);
  if (get("assignmentsCount")) get("assignmentsCount").textContent = String(assignments.length);
  if (get("exceptionsCount")) get("exceptionsCount").textContent = String(exceptions.length);
  if (get("assignedDrivers")) get("assignedDrivers").textContent = String(assignedDrivers.size);
  renderAssignments(assignments, plans);
  renderExceptions(exceptions, plans);
  renderPlans(plans);
  if (get("resultJson")) get("resultJson").textContent = prettyJson(result);
}

function getRenderUtilsModule() {
  return typeof window !== "undefined" &&
    window.DeliveryRenderUtils &&
    typeof window.DeliveryRenderUtils.buildResultDisplayLookups === "function"
    ? window.DeliveryRenderUtils
    : null;
}

function buildResultDisplayLookups() {
  const renderUtils = getRenderUtilsModule();
  if (renderUtils) {
    return renderUtils.buildResultDisplayLookups(appState?.view || null);
  }
  const driverById = {};
  const vehicleById = {};
  const view = appState?.view || null;
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
  const renderUtils = getRenderUtilsModule();
  if (renderUtils && typeof renderUtils.resolveDriverDisplay === "function") {
    return renderUtils.resolveDriverDisplay(driverId, lookups);
  }
  const key = asText(driverId).trim();
  if (!key) return "-";
  return asText(lookups?.driverById?.[key]).trim() || key;
}

function resolveVehicleDisplay(vehicleId, lookups) {
  const renderUtils = getRenderUtilsModule();
  if (renderUtils && typeof renderUtils.resolveVehicleDisplay === "function") {
    return renderUtils.resolveVehicleDisplay(vehicleId, lookups);
  }
  const key = asText(vehicleId).trim();
  if (!key) return "-";
  return asText(lookups?.vehicleById?.[key]).trim() || key;
}

function toBusinessExplanation(value) {
  const renderUtils = getRenderUtilsModule();
  if (renderUtils && typeof renderUtils.toBusinessExplanation === "function") {
    return renderUtils.toBusinessExplanation(value);
  }
  const raw = Array.isArray(value) ? value.join(" / ") : asText(value);
  return raw.replace(/\bTrip\s+RUN-\d+\b/gi, "Assignment group").replace(/\bRUN-\d+\b/gi, "").trim();
}

function buildDriverAssignmentSummary(assignments, plans) {
  const summaryModule =
    typeof window !== "undefined" &&
    window.DeliveryDriverAssignmentSummary &&
    typeof window.DeliveryDriverAssignmentSummary.buildDriverAssignmentSummary === "function"
      ? window.DeliveryDriverAssignmentSummary
      : null;
  const lookups = buildResultDisplayLookups();
  if (summaryModule) {
    return summaryModule.buildDriverAssignmentSummary(assignments, plans, lookups);
  }

  const grouped = new Map();
  for (const item of safeArray(assignments)) {
    const driverId = asText(item.driver_id).trim() || "UNASSIGNED";
    const vehicleId = asText(item.vehicle_id).trim() || "-";
    const driverDisplay = resolveDriverDisplay(driverId, lookups);
    const vehicleDisplay = resolveVehicleDisplay(vehicleId, lookups);
    if (!grouped.has(driverId)) grouped.set(driverId, { driver_id: driverId, driver_display: driverDisplay, total_orders: 0, vehicles: new Map() });
    const driverBucket = grouped.get(driverId);
    driverBucket.total_orders += 1;
    if (!driverBucket.vehicles.has(vehicleId)) {
      driverBucket.vehicles.set(vehicleId, { vehicle_id: vehicleId, vehicle_display: vehicleDisplay, total_orders: 0, orders: [] });
    }
    const vehicleBucket = driverBucket.vehicles.get(vehicleId);
    vehicleBucket.total_orders += 1;
    vehicleBucket.orders.push({ ...item, driver_display: driverDisplay, vehicle_display: vehicleDisplay });
  }

  return Array.from(grouped.values())
    .map((driverBucket) => ({
      driver_id: driverBucket.driver_id,
      driver_display: driverBucket.driver_display,
      total_orders: driverBucket.total_orders,
      vehicle_count: driverBucket.vehicles.size,
      vehicles: Array.from(driverBucket.vehicles.values())
    }))
    .sort((left, right) => left.driver_display.localeCompare(right.driver_display, undefined, { numeric: true, sensitivity: "base" }));
}

function renderAssignments(assignments, plans) {
  const node = get("orderAssignmentsContainer");
  if (!node) return;
  if (!Array.isArray(assignments) || assignments.length === 0) {
    node.className = "empty-state";
    if (Array.isArray(plans) && plans.length > 0) {
      node.innerHTML = `
        <div class="empty-state-copy">
          <strong>计划已生成，但暂无订单分配记录。</strong>
          <p>请查看 Exceptions 或开发者模式中的 Result JSON 继续排查。</p>
        </div>
      `;
      return;
    }
    node.innerHTML = `
      <div class="empty-state-copy">
        <strong>暂无分配结果</strong>
        <p>生成计划后，这里会按 司机 -> 车辆 -> 订单 展示最终分配。</p>
      </div>
    `;
    return;
  }

  const summaries = buildDriverAssignmentSummary(assignments, plans);
  node.className = "driver-summary-list";
  node.innerHTML = summaries
    .map((driverSummary) => {
      const vehiclesHtml = safeArray(driverSummary.vehicles)
        .map((vehicleSummary) => {
          const rowsHtml = safeArray(vehicleSummary.orders)
            .map((item) => {
              const areaText = [asText(item.postcode).trim(), asText(item.zone_code).trim()].filter(Boolean).join(" / ");
              return `
                <tr>
                  <td>${escapeHtml(asText(item.order_id))}</td>
                  <td>${escapeHtml(asText(item.driver_display || driverSummary.driver_display || driverSummary.driver_id))}</td>
                  <td>${escapeHtml(asText(item.vehicle_display || vehicleSummary.vehicle_display || vehicleSummary.vehicle_id))}</td>
                  <td>${escapeHtml(asText(item.status || "ASSIGNED"))}</td>
                  <td>${escapeHtml(areaText || "-")}</td>
                  <td>${escapeHtml(toBusinessExplanation(item.explanation) || "-")}</td>
                </tr>
              `;
            })
            .join("");
          return `
            <section class="driver-vehicle-group">
              <div class="driver-vehicle-header">
                <div>
                  <h5>Vehicle ${escapeHtml(asText(vehicleSummary.vehicle_display || vehicleSummary.vehicle_id))}</h5>
                  <p class="driver-vehicle-meta">Orders ${escapeHtml(asText(vehicleSummary.total_orders) || "0")}</p>
                </div>
              </div>
              <div class="assignment-wrap">
                <table class="assignment-table">
                  <thead>
                    <tr>
                      <th>Order</th>
                      <th>Driver</th>
                      <th>Vehicle</th>
                      <th>Status</th>
                      <th>Postcode / Zone</th>
                      <th>Explanation</th>
                    </tr>
                  </thead>
                  <tbody>${rowsHtml}</tbody>
                </table>
              </div>
            </section>
          `;
        })
        .join("");
      return `
        <article class="driver-summary-card">
          <header class="driver-summary-header">
            <div>
              <h4>${escapeHtml(asText(driverSummary.driver_display || driverSummary.driver_id))}</h4>
              <p class="driver-summary-time">Driver ID ${escapeHtml(asText(driverSummary.driver_id))}</p>
            </div>
            <div class="driver-summary-badges">
              <span class="pill">Orders ${escapeHtml(asText(driverSummary.total_orders) || "0")}</span>
              <span class="pill">Vehicles ${escapeHtml(asText(driverSummary.vehicle_count) || "0")}</span>
            </div>
          </header>
          ${vehiclesHtml}
        </article>
      `;
    })
    .join("");
}

function buildExceptionPlanContext(plans, lookups) {
  const context = {};
  for (const plan of safeArray(plans)) {
    const planId = asText(plan.plan_id || plan.run_id).trim();
    if (!planId) continue;
    const driverId = asText(plan.driver_id).trim();
    const vehicleId = asText(plan.vehicle_id).trim();
    const orderIds = safeArray(plan.order_ids).map((item) => asText(item).trim()).filter((item) => item !== "");
    const payload = {
      plan_id: planId,
      order_ids: orderIds,
      dispatch_date: asText(plan.dispatch_date).trim(),
      zone_code: asText(plan.zone_code).trim(),
      driver_id: driverId,
      driver_display: resolveDriverDisplay(driverId, lookups),
      vehicle_id: vehicleId,
      vehicle_display: resolveVehicleDisplay(vehicleId, lookups)
    };
    context[planId] = payload;
    if (orderIds.length > 0) {
      context[`orders:${orderIds.join(",")}`] = payload;
    }
  }
  return context;
}

function buildExceptionBusinessDetails(item, plans, lookups) {
  const details = [];
  const contextByRun = buildExceptionPlanContext(plans, lookups);
  const entityId = asText(item.entity_id).trim();
  const context = entityId ? contextByRun[entityId] : null;
  const orderIds =
    safeArray(item.order_ids).length > 0
      ? safeArray(item.order_ids).map((orderId) => asText(orderId).trim()).filter((orderId) => orderId !== "")
      : (context?.order_ids || []);
  if (orderIds.length === 0 && entityId.toLowerCase().startsWith("orders:")) {
    const inlineOrderIds = entityId
      .slice("orders:".length)
      .split(",")
      .map((orderId) => asText(orderId).trim())
      .filter((orderId) => orderId !== "");
    orderIds.push(...inlineOrderIds);
  }
  if (orderIds.length > 0) details.push(`Orders: ${orderIds.join(", ")}`);

  const driverId = asText(item.driver_id ?? item.designated_driver_id ?? context?.driver_id).trim();
  if (driverId) details.push(`Driver: ${resolveDriverDisplay(driverId, lookups)}`);
  else if (context?.driver_display) details.push(`Driver: ${context.driver_display}`);

  const vehicleId = asText(item.vehicle_id ?? context?.vehicle_id).trim();
  if (vehicleId) details.push(`Vehicle: ${resolveVehicleDisplay(vehicleId, lookups)}`);
  else if (context?.vehicle_display) details.push(`Vehicle: ${context.vehicle_display}`);

  const dispatchDate = asText(item.dispatch_date ?? context?.dispatch_date).trim();
  if (dispatchDate) details.push(`Date: ${dispatchDate}`);
  const zoneCode = asText(item.zone_code ?? context?.zone_code).trim();
  if (zoneCode) details.push(`Zone: ${zoneCode}`);
  if (details.length === 0 && entityId) details.push(`Entity: ${entityId}`);
  return details;
}

function renderExceptions(exceptions, plans) {
  const node = get("exceptionsContainer");
  if (!node) return;
  if (!Array.isArray(exceptions) || exceptions.length === 0) {
    node.className = "exceptions-list empty-state";
    node.textContent = "当前没有异常。";
    return;
  }
  const lookups = buildResultDisplayLookups();
  node.className = "exceptions-list";
  node.innerHTML = exceptions
    .map((item) => {
      const details = buildExceptionBusinessDetails(item, plans, lookups);
      return `
        <article class="exception-item">
          <h4>${escapeHtml(asText(item.reason_code))}</h4>
          <p>${escapeHtml(asText(item.reason_text))}</p>
          <p><strong>影响对象：</strong>${escapeHtml(details.join(" | "))}</p>
          <p><strong>建议：</strong>${escapeHtml(asText(item.suggested_action || "-"))}</p>
        </article>
      `;
    })
    .join("");
}

function renderPlans(plans) {
  const node = get("plansContainer");
  if (!node) return;
  if (!Array.isArray(plans) || plans.length === 0) {
    node.className = "plans-list empty-state";
    node.innerHTML = "生成计划后，这里会显示分组分配摘要。";
    return;
  }
  const lookups = buildResultDisplayLookups();
  node.className = "plans-list";
  node.innerHTML = plans
    .map((plan, index) => {
      const orderIds = safeArray(plan.order_ids).map((item) => escapeHtml(asText(item))).join(", ");
      const explanation = Array.isArray(plan.explanation)
        ? plan.explanation.map((line) => toBusinessExplanation(line)).filter((line) => asText(line).trim() !== "")
        : [];
      return `
        <article class="plan-card">
          <h3>Assignment Group ${index + 1}</h3>
          <div class="plan-meta">
            <span class="metric-chip">Date ${escapeHtml(asText(plan.dispatch_date) || "-")}</span>
            <span class="metric-chip">Driver ${escapeHtml(resolveDriverDisplay(plan.driver_id, lookups))}</span>
            <span class="metric-chip">Vehicle ${escapeHtml(resolveVehicleDisplay(plan.vehicle_id, lookups))}</span>
            <span class="metric-chip">Zone ${escapeHtml(asText(plan.zone_code) || "-")}</span>
            <span class="metric-chip">Orders ${escapeHtml(asText(plan.total_orders) || "0")}</span>
            <span class="metric-chip">Urgent ${escapeHtml(asText(plan.urgent_order_count) || "0")}</span>
            <span class="metric-chip">Window ${escapeHtml(asText(plan.time_window_start) || "-")} - ${escapeHtml(asText(plan.time_window_end) || "-")}</span>
          </div>
          <p class="trip-meta">Order IDs: ${orderIds || "-"}</p>
          <p class="trip-meta">Load: ${escapeHtml(formatLoadSummaryText(plan.load_summary))}</p>
          ${explanation.length > 0 ? `<ul class="explanation-list">${explanation.map((line) => `<li>${escapeHtml(line)}</li>`).join("")}</ul>` : ""}
        </article>
      `;
    })
    .join("");
}

function renderSnapshotEditor() {
  const editor = get("snapshotEditor");
  if (!editor) return;
  editor.value = prettyJson(appState.snapshot);
}

function renderValidationPanel(report) {
  const panel = get("validationPanel");
  if (!panel) return;
  const errors = safeArray(report?.errors);
  const warnings = safeArray(report?.warnings);
  if (errors.length === 0 && warnings.length === 0) {
    panel.classList.add("hidden");
    panel.innerHTML = "";
    return;
  }
  panel.classList.remove("hidden");
  panel.innerHTML = `
    ${errors.length > 0 ? `<div class="validation-block"><strong>阻断错误 (${errors.length})</strong><ul>${errors.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>` : ""}
    ${warnings.length > 0 ? `<div class="validation-block"><strong>警告 (${warnings.length})</strong><ul>${warnings.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>` : ""}
  `;
}

function handleOrderFileImport(event) {
  const input = event.target;
  const file = input?.files?.[0];
  if (!file) return;
  const name = asText(file.name).toLowerCase();
  if (name.endsWith(".xlsx")) {
    setImportReport("当前仅支持 CSV。请先将 Excel 另存为 CSV 再导入。", true);
    banner("Excel 导入暂不支持，请转为 CSV。", "error");
    input.value = "";
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    try {
      const text = asText(reader.result);
      const report = importOrdersFromCsv(text);
      const summary = `CSV 导入：成功 ${report.succeeded} 行，失败 ${report.failedRows.length} 行，警告 ${report.warnings.length} 条。`;
      const details = report.failedRows.map((item) => `第 ${item.line} 行：${item.reason}`).join("\n");
      const warningText = report.warnings.length > 0 ? `\n${report.warnings.join("\n")}` : "";
      setImportReport(details ? `${summary}\n${details}${warningText}` : `${summary}${warningText}`, report.failedRows.length > 0);
      if (report.succeeded > 0) renderOrdersTable();
      banner(summary, report.failedRows.length > 0 ? "error" : "success");
    } catch (error) {
      setImportReport(`CSV 导入失败：${error.message}`, true);
      banner(`CSV 导入失败：${error.message}`, "error");
    } finally {
      input.value = "";
    }
  };
  reader.onerror = () => {
    setImportReport("文件读取失败。", true);
    banner("文件读取失败。", "error");
    input.value = "";
  };
  reader.readAsText(file, "utf-8");
}

function importOrdersFromCsv(csvText) {
  const rows = parseCsv(csvText);
  if (rows.length === 0) return { succeeded: 0, failedRows: [], warnings: [] };
  const [header, ...dataRows] = rows;
  const indexMap = buildHeaderIndexMap(header);
  if (indexMap.order_id < 0 || indexMap.delivery_address < 0 || indexMap.postcode < 0) {
    throw new Error("CSV 缺少必要列：order_id / delivery_address / postcode。");
  }
  const report = { succeeded: 0, failedRows: [], warnings: [] };
  for (let i = 0; i < dataRows.length; i += 1) {
    const lineNo = i + 2;
    const cells = dataRows[i];
    const candidate = {
      order_id: readCsvValue(cells, indexMap.order_id),
      dispatch_date: readCsvValue(cells, indexMap.dispatch_date) || todayISO(),
      delivery_address: readCsvValue(cells, indexMap.delivery_address),
      postcode: readCsvValue(cells, indexMap.postcode),
      zone_code: readCsvValue(cells, indexMap.zone_code),
      urgency: readCsvValue(cells, indexMap.urgency) || "NORMAL",
      preferred_driver_id: readCsvValue(cells, indexMap.preferred_driver_id),
      pallet_qty: readCsvValue(cells, indexMap.pallet_qty) || "0",
      loose_bags: readCsvValue(cells, indexMap.loose_bags) || "0",
      window_start: readCsvValue(cells, indexMap.window_start) || "08:00",
      window_end: readCsvValue(cells, indexMap.window_end) || "10:00"
    };
    if (isBlank(candidate.order_id) || isBlank(candidate.delivery_address) || isBlank(candidate.postcode)) {
      report.failedRows.push({ line: lineNo, reason: "order_id / delivery_address / postcode 不能为空。" });
      continue;
    }
    const mappedZone = resolveZoneCodeByPostcode(candidate.postcode, appState.view.config._extra?.zone_by_postcode || {});
    if (!mappedZone) {
      report.failedRows.push({ line: lineNo, reason: "postcode 未命中 zone 映射。" });
      continue;
    }
    if (candidate.zone_code && asText(candidate.zone_code).trim() !== mappedZone) {
      report.warnings.push(`第 ${lineNo} 行：zone_code 与 postcode 映射冲突，已采用 ${mappedZone}。`);
    }
    candidate.zone_code = mappedZone;
    appState.view.orders.push(createOrderRow(candidate));
    report.succeeded += 1;
  }
  return report;
}

function buildHeaderIndexMap(headerRow) {
  const normalizedHeader = safeArray(headerRow).map((item) => normalizeHeader(item));
  const resolveIndex = (aliases) => {
    for (const alias of aliases) {
      const normalizedAlias = normalizeHeader(alias);
      const index = normalizedHeader.findIndex((item) => item === normalizedAlias);
      if (index >= 0) return index;
    }
    return -1;
  };
  return {
    order_id: resolveIndex(ORDER_HEADER_ALIAS.order_id),
    dispatch_date: resolveIndex(ORDER_HEADER_ALIAS.dispatch_date),
    delivery_address: resolveIndex(ORDER_HEADER_ALIAS.delivery_address),
    postcode: resolveIndex(ORDER_HEADER_ALIAS.postcode),
    zone_code: resolveIndex(ORDER_HEADER_ALIAS.zone_code),
    urgency: resolveIndex(ORDER_HEADER_ALIAS.urgency),
    preferred_driver_id: resolveIndex(ORDER_HEADER_ALIAS.preferred_driver_id),
    pallet_qty: resolveIndex(ORDER_HEADER_ALIAS.pallet_qty),
    loose_bags: resolveIndex(ORDER_HEADER_ALIAS.loose_bags),
    window_start: resolveIndex(ORDER_HEADER_ALIAS.window_start),
    window_end: resolveIndex(ORDER_HEADER_ALIAS.window_end)
  };
}

function parseCsv(text) {
  const rows = [];
  let currentRow = [];
  let currentValue = "";
  let inQuotes = false;
  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    const next = text[i + 1];
    if (char === "\"") {
      if (inQuotes && next === "\"") {
        currentValue += "\"";
        i += 1;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }
    if (char === "," && !inQuotes) {
      currentRow.push(currentValue);
      currentValue = "";
      continue;
    }
    if ((char === "\n" || char === "\r") && !inQuotes) {
      if (char === "\r" && next === "\n") i += 1;
      currentRow.push(currentValue);
      const isEmptyRow = currentRow.every((item) => asText(item).trim() === "");
      if (!isEmptyRow) rows.push(currentRow);
      currentRow = [];
      currentValue = "";
      continue;
    }
    currentValue += char;
  }
  if (currentValue !== "" || currentRow.length > 0) {
    currentRow.push(currentValue);
    if (!currentRow.every((item) => asText(item).trim() === "")) rows.push(currentRow);
  }
  return rows;
}

function readCsvValue(cells, index) {
  if (!Number.isInteger(index) || index < 0 || index >= cells.length) return "";
  return asText(cells[index]).trim();
}

function computeRunPriorityScore(run) {
  const urgentBonus = run.urgent_count > 0 ? 300 : 0;
  const designatedBonus = run.designated_driver_id !== null ? 180 : 0;
  const span = Math.max(run.window_end - run.window_start, 1);
  const pressure = Math.max(180 - span, 0) * 2;
  return urgentBonus + designatedBonus + pressure;
}

function estimateTripWindow(run, driver, config) {
  const centroid = estimateRunCentroid(run.orders);
  const startRef = centroid || driver.start_ref;
  const endRef = centroid || driver.end_ref;
  const deadheadStart = estimateTravelMinutes(driver.start_ref, startRef, config);
  const deadheadEnd = estimateTravelMinutes(endRef, driver.end_ref, config);
  const intraTrip = Math.max(run.orders.length - 1, 0) * 12;
  const travelMinutes = deadheadStart + intraTrip + deadheadEnd;
  const workMinutes = run.estimated_service_minutes + travelMinutes;
  const estimatedStart = Math.max(driver.shift_start, run.window_start);
  const estimatedFinish = estimatedStart + workMinutes;
  const latestWindowFinish = run.window_end + Math.min(90, Math.max(20, run.orders.length * 8));
  return {
    feasible: estimatedFinish <= driver.shift_end && estimatedFinish <= latestWindowFinish,
    estimated_start: estimatedStart,
    estimated_finish: estimatedFinish,
    travel_minutes: travelMinutes,
    deadhead_minutes: deadheadStart,
    work_minutes: workMinutes
  };
}

function hasTripOverlap(intervals, estimate) {
  return safeArray(intervals).some((interval) => interval[0] < estimate.estimated_finish && estimate.estimated_start < interval[1]);
}

function countVehicleSwitches(items) {
  const ordered = safeArray(items).slice().sort((left, right) => {
    if (left.estimate.estimated_start !== right.estimate.estimated_start) {
      return left.estimate.estimated_start - right.estimate.estimated_start;
    }
    if (left.estimate.estimated_finish !== right.estimate.estimated_finish) {
      return left.estimate.estimated_finish - right.estimate.estimated_finish;
    }
    return asText(left.group?.plan_group_id).localeCompare(asText(right.group?.plan_group_id), undefined, { numeric: true, sensitivity: "base" });
  });
  let switches = 0;
  for (let index = 1; index < ordered.length; index += 1) {
    if (asText(ordered[index - 1].vehicle?.vehicle_id) !== asText(ordered[index].vehicle?.vehicle_id)) {
      switches += 1;
    }
  }
  return switches;
}

function switchDeltaForCandidate(candidate, selectedByDriverDay) {
  const driverDayKey = `${candidate.driver.driver_id}|${candidate.group.dispatch_date}`;
  const existing = selectedByDriverDay.get(driverDayKey) || [];
  const before = countVehicleSwitches(existing);
  const after = countVehicleSwitches([...existing, candidate]);
  return Math.max(after - before, 0);
}

function sameZoneContinuityHit(candidate, selectedByDriverDay) {
  const driverDayKey = `${candidate.driver.driver_id}|${candidate.group.dispatch_date}`;
  const existing = selectedByDriverDay.get(driverDayKey) || [];
  if (existing.length === 0) return false;
  return existing.some((item) => asText(item.group?.zone_code).trim() === asText(candidate.group?.zone_code).trim());
}

function zoneMismatchRank(candidate) {
  const preferred = safeArray(candidate?.driver?.preferred_zone_codes);
  if (preferred.length === 0) return 0;
  return candidate.preferred_zone_match ? 0 : 1;
}

function buildUnusedDriverHints(drivers, runs, assignedPlanCount, candidateStats) {
  const result = [];
  const totalRuns = safeArray(runs).length;
  for (const driver of safeArray(drivers)) {
    const driverDisplay = asText(driver.display_name).trim() || asText(driver.driver_id).trim();
    const stats = candidateStats.get(driver.driver_id) || { candidateCount: 0, selectedCount: 0 };
    if ((stats.selectedCount || 0) > 0) continue;
    if ((stats.candidateCount || 0) <= 0) {
      if (totalRuns > 0 && assignedPlanCount >= totalRuns) {
        result.push(
          makeException(
            "DRIVER",
            driver.driver_id,
            "DRIVER_UNUSED_NO_REMAINING_RUN",
            `司机 ${driverDisplay} 本轮未被激活：没有剩余可分配任务。`,
            "如需提升司机利用率，可增加订单量或开启更细粒度拆分。",
            false
          )
        );
      } else {
        result.push(
          makeException(
            "DRIVER",
            driver.driver_id,
            "DRIVER_UNUSED_NO_FEASIBLE_CANDIDATE",
            `司机 ${driverDisplay} 在当前硬约束下没有可行候选任务。`,
            "请检查班次、容量、指定司机与时间窗约束。",
            false
          )
        );
      }
    } else {
      result.push(
          makeException(
            "DRIVER",
            driver.driver_id,
            "DRIVER_UNUSED_OUTSCORED",
            `司机 ${driverDisplay} 有可行候选，但在全局优先级下未被选中。`,
            "可调整负载均衡与利用率权重以提高覆盖。",
            false
          )
        );
    }
  }
  return result;
}

function estimateRunCentroid(orders) {
  const points = safeArray(orders).filter((order) => Number.isFinite(order.lat) && Number.isFinite(order.lng));
  if (points.length === 0) return null;
  return {
    lat: points.reduce((sum, item) => sum + Number(item.lat), 0) / points.length,
    lng: points.reduce((sum, item) => sum + Number(item.lng), 0) / points.length
  };
}

function estimateTravelMinutes(fromRef, toRef, config) {
  if (!fromRef || !toRef) return 12;
  const latDelta = (Number(fromRef.lat) - Number(toRef.lat)) * 111.0;
  const lngDelta = (Number(fromRef.lng) - Number(toRef.lng)) * 111.0;
  const km = Math.sqrt(latDelta * latDelta + lngDelta * lngDelta);
  const speed = positiveInt(config.average_speed_kph, 35);
  const minimum = positiveInt(config.minimum_travel_minutes, 3);
  const minutes = Math.round((km / speed) * 60);
  return Math.max(minutes, minimum);
}

function orderToLoad(order, config) {
  const loadType = asText(order.load_type).toUpperCase();
  const tubs = loadType === "MIXED" ? Math.ceil(nonNegativeInt(order.bag_count, 0) / positiveInt(config.loose_units_per_tub, 4)) : 0;
  const looseUnits = loadType === "LOOSE" ? nonNegativeInt(order.bag_count, 0) : 0;
  return {
    kg: nonNegativeNumber(order.kg_count, 0),
    pallets: nonNegativeInt(order.pallet_count, 0),
    tubs,
    loose_units: looseUnits,
    trolleys: 0,
    stillages: 0
  };
}

function sumLoad(left, right) {
  return {
    kg: left.kg + right.kg,
    pallets: left.pallets + right.pallets,
    tubs: left.tubs + right.tubs,
    loose_units: left.loose_units + right.loose_units,
    trolleys: left.trolleys + right.trolleys,
    stillages: left.stillages + right.stillages
  };
}

function loadFits(load, capacity) {
  return (
    (capacity.kg <= 0 || load.kg <= capacity.kg) &&
    load.pallets <= capacity.pallets &&
    load.tubs <= capacity.tubs &&
    load.loose_units <= capacity.loose_units &&
    load.trolleys <= capacity.trolleys &&
    load.stillages <= capacity.stillages
  );
}

function capacityWaste(load, capacity) {
  return (
    (capacity.kg > 0 ? Math.max(capacity.kg - load.kg, 0) : 0) +
    Math.max(capacity.pallets - load.pallets, 0) +
    Math.max(capacity.tubs - load.tubs, 0) +
    Math.max(capacity.loose_units - load.loose_units, 0) +
    Math.max(capacity.trolleys - load.trolleys, 0) +
    Math.max(capacity.stillages - load.stillages, 0)
  );
}

function makeException(scope, entityId, reasonCode, reasonText, suggestedAction, isUrgent = false, extra = {}) {
  return Object.assign(
    {
      scope,
      entity_id: entityId,
      reason_code: reasonCode,
      reason_text: reasonText,
      suggested_action: suggestedAction,
      is_urgent: !!isUrgent
    },
    deepClone(extra || {})
  );
}

function resolveLocation(address, lat, lng, geocoder) {
  if (Number.isFinite(toNumber(lat)) && Number.isFinite(toNumber(lng))) {
    return { lat: Number(lat), lng: Number(lng), address: asText(address) };
  }
  const key = asText(address).trim();
  const point = isObject(geocoder) ? geocoder[key] : null;
  if (Array.isArray(point) && point.length >= 2) {
    return { lat: Number(point[0]), lng: Number(point[1]), address: key };
  }
  return null;
}

function resolveDriverRef(address, lat, lng, branchNo, config) {
  const explicit = resolveLocation(address, lat, lng, config.geocoder);
  if (explicit) return explicit;
  const branch = asText(branchNo).trim();
  const depot = config.branch_locations?.[branch];
  if (Array.isArray(depot) && depot.length >= 2) {
    return {
      lat: Number(depot[0]),
      lng: Number(depot[1]),
      address: asText(address).trim() || asText(depot[2]).trim() || "Depot"
    };
  }
  return null;
}

function resolveZoneCodeByPostcode(postcode, zoneByPostcode) {
  const zoneUtils =
    typeof window !== "undefined" &&
    window.DeliveryZoneUtils &&
    typeof window.DeliveryZoneUtils.resolveZoneCodeByPostcode === "function"
      ? window.DeliveryZoneUtils
      : null;
  if (zoneUtils) return zoneUtils.resolveZoneCodeByPostcode(postcode, zoneByPostcode);
  const normalizedPostcode = asText(postcode).trim();
  if (normalizedPostcode === "" || !isObject(zoneByPostcode)) return "";
  return asText(zoneByPostcode[normalizedPostcode]).trim();
}

function resolveZoneLabelByCode(zoneCode, zoneLabelByCode) {
  const zoneUtils =
    typeof window !== "undefined" &&
    window.DeliveryZoneUtils &&
    typeof window.DeliveryZoneUtils.resolveZoneLabelByCode === "function"
      ? window.DeliveryZoneUtils
      : null;
  if (zoneUtils) return zoneUtils.resolveZoneLabelByCode(zoneCode, zoneLabelByCode);
  const normalizedCode = asText(zoneCode).trim();
  if (normalizedCode === "") return "-";
  if (isObject(zoneLabelByCode) && normalizedCode in zoneLabelByCode) {
    const label = asText(zoneLabelByCode[normalizedCode]).trim();
    return label || normalizedCode;
  }
  return normalizedCode;
}

function parseZoneList(value) {
  const text = asText(value).trim();
  if (text === "") return { values: [], invalid: false };
  const parts = text
    .split(/[,，\s]+/)
    .map((item) => item.trim())
    .filter((item) => item !== "");
  const values = [];
  const seen = new Set();
  for (const part of parts) {
    if (!/^[A-Za-z0-9_-]+$/.test(part)) return { values: [], invalid: true };
    const code = part.toUpperCase();
    if (!seen.has(code)) {
      seen.add(code);
      values.push(code);
    }
  }
  return { values, invalid: false };
}

function createOrderRow(seed) {
  return {
    _key: nextKey("order"),
    order_id: asText(seed.order_id),
    dispatch_date: asText(seed.dispatch_date) || todayISO(),
    delivery_address: asText(seed.delivery_address),
    postcode: asText(seed.postcode),
    zone_code: asText(seed.zone_code),
    urgency: normalizeUrgency(seed.urgency),
    preferred_driver_id: asText(seed.preferred_driver_id),
    pallet_qty: asText(seed.pallet_qty || 0),
    loose_bags: asText(seed.loose_bags || 0),
    window_start: asText(seed.window_start) || "08:00",
    window_end: asText(seed.window_end) || "10:00",
    _extra: deepClone(seed._extra || {})
  };
}

function createDriverRow(seed) {
  return {
    _key: nextKey("driver"),
    driver_id: asText(seed.driver_id),
    name: asText(seed.name),
    shift_start: asText(seed.shift_start) || "08:00",
    shift_end: asText(seed.shift_end) || "17:00",
    is_available: seed.is_available !== false,
    preferred_zone_codes: asText(seed.preferred_zone_codes),
    start_location: asText(seed.start_location),
    end_location: asText(seed.end_location),
    _extra: deepClone(seed._extra || {})
  };
}

function createVehicleRow(seed) {
  return {
    _key: nextKey("vehicle"),
    vehicle_id: asText(seed.vehicle_id),
    rego: asText(seed.rego),
    vehicle_type: asText(seed.vehicle_type) || "van",
    is_available: seed.is_available !== false,
    kg_capacity: asText(seed.kg_capacity || 0),
    pallet_capacity: asText(seed.pallet_capacity || 0),
    tub_capacity: asText(seed.tub_capacity || 0),
    trolley_capacity: asText(seed.trolley_capacity || 0),
    stillage_capacity: asText(seed.stillage_capacity || 0),
    source: asText(seed.source || "vehicle master export"),
    _extra: deepClone(seed._extra || {}),
    _metadataExtra: deepClone(seed._metadataExtra || {})
  };
}

function formatLoadSummaryText(summary) {
  if (!isObject(summary)) return "-";
  const ordered = ["kg", "pallets", "tubs", "loose_units", "trolleys", "stillages"];
  return ordered
    .filter((key) => key in summary)
    .map((key) => `${key}:${summary[key]}`)
    .join(" | ");
}

function parseTimeToMinutes(value) {
  if (typeof value === "number" && Number.isFinite(value)) return Math.trunc(value);
  const text = asText(value).trim();
  const match = text.match(/^(\d{1,2}):(\d{2})$/);
  if (!match) return null;
  const hours = Number(match[1]);
  const minutes = Number(match[2]);
  if (hours < 0 || hours > 23 || minutes < 0 || minutes > 59) return null;
  return hours * 60 + minutes;
}

function minutesToHHMM(value) {
  const total = Math.max(0, Math.trunc(Number(value) || 0));
  const hours = Math.floor(total / 60);
  const minutes = total % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

function normalizeTimeString(value, fallback) {
  const minutes = parseTimeToMinutes(value);
  return minutes === null ? fallback : minutesToHHMM(minutes);
}

function urgencyRank(value) {
  return normalizeUrgency(value) === "URGENT" ? 1 : 0;
}

function normalizeUrgency(value) {
  return asText(value).toUpperCase() === "URGENT" ? "URGENT" : "NORMAL";
}

function normalizeIdentifier(value) {
  const text = asText(value).trim();
  if (text === "") return "";
  return /^-?\d+$/.test(text) ? Number(text) : text;
}

function parseOptionalInt(value) {
  const text = asText(value).trim();
  if (text === "") return null;
  if (!/^-?\d+$/.test(text)) return null;
  return Number(text);
}

function positiveInt(value, fallback) {
  const numeric = Math.trunc(toNumber(value));
  if (!Number.isFinite(numeric) || numeric <= 0) return fallback;
  return numeric;
}

function nonNegativeInt(value, fallback) {
  const numeric = Math.trunc(toNumber(value));
  if (!Number.isFinite(numeric) || numeric < 0) return fallback;
  return numeric;
}

function nonNegativeNumber(value, fallback) {
  const numeric = toNumber(value);
  if (!Number.isFinite(numeric) || numeric < 0) return fallback;
  return numeric;
}

function normalizeHeader(value) {
  return asText(value)
    .trim()
    .toLowerCase()
    .replace(/[^\w\u4e00-\u9fa5]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

function setImportReport(message, isError = false) {
  const node = get("orderImportReport");
  if (!node) return;
  node.textContent = message;
  node.classList.toggle("hint-error", !!isError);
}

function banner(message, tone = "info") {
  const node = get("messageBanner");
  if (!node) return;
  node.textContent = message;
  node.classList.remove("hidden", "is-info", "is-success", "is-error");
  if (tone === "success") node.classList.add("is-success");
  else if (tone === "error") node.classList.add("is-error");
  else node.classList.add("is-info");
}

function omitKeys(objectValue, keys) {
  const result = {};
  if (!isObject(objectValue)) return result;
  const deny = new Set(keys);
  for (const [key, value] of Object.entries(objectValue)) {
    if (!deny.has(key)) result[key] = deepClone(value);
  }
  return result;
}

function safeArray(value) {
  return Array.isArray(value) ? value : [];
}

function deepClone(value) {
  if (value === undefined) return undefined;
  return JSON.parse(JSON.stringify(value));
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isBlank(value) {
  return asText(value).trim() === "";
}

function toNumber(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : NaN;
}

function asText(value) {
  if (value === undefined || value === null) return "";
  return String(value);
}

function prettyJson(value) {
  return JSON.stringify(value, null, 2);
}

function nextKey(prefix) {
  rowSequence += 1;
  return `${prefix}-${rowSequence}`;
}

function escapeHtml(value) {
  return asText(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;")
    .replaceAll("'", "&#39;");
}

function get(id) {
  return document.getElementById(id);
}

function setIf(id, value) {
  const node = get(id);
  if (node) node.value = value;
}

function onIf(id, eventName, handler) {
  const node = get(id);
  if (node) node.addEventListener(eventName, handler);
}

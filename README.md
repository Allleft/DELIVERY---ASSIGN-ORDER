# Delivery Dispatch Optimizer

面向配送调度场景的订单分配系统。当前核心口径为 **trip grouping + assignment**：先组单成 trip（兼容字段仍叫 `run_id`），再分配司机与车辆。  
系统保留顶层输出结构不变：`plans / order_assignments / exceptions`。

---

## 1. 项目概览

- 解决问题：给定订单、司机、车辆后，自动产出“每个司机每趟带哪些订单、用哪辆车”的可行分配。
- 当前核心能力：订单标准化、trip grouping、司机/车辆全局分配、异常输出、前端业务工作台展示。
- 顶层输入/输出：
  - 输入：`config + orders + drivers + vehicles`
  - 输出：`plans / order_assignments / exceptions`
- 当前前端默认主视图：`Driver Assignment Summary`
- 当前 travel time 策略：`cache first -> Google Routes -> Haversine fallback`
- 当前主数据来源：
  - zone：`data/raw/zone-postcode-raw-data.csv`
  - driver：`data/raw/driver-raw-data.csv`
  - vehicle：`data/raw/vehicle-raw-data.csv`

### 权威结果来源

- 后端 `dispatch_optimizer.DispatchEngine` 是结果口径权威。
- 前端负责输入编辑与结果可视化，包含本地预览求解逻辑，但生产口径以后端输出为准。

---

## 2. 项目主流程

1. 读取输入（支持输入形状兼容：扁平 config 顶层键 + `config` 包裹）。
2. 预处理订单/司机/车辆：  
   - postcode 映射 zone；  
   - 坐标补全；  
   - `service_minutes` 已从输入模型移除，系统统一使用固定每站停留时间（`FIXED_STOP_MINUTES = 10`）。
3. trip grouping（run 语义升级）：
   - 继续按 `dispatch_date + zone_code + bucket` 初步分组。
4. 候选枚举与分配：
   - 枚举 `(trip, driver, vehicle)` 可行组合；
   - 用粗粒度时间可行性估算（不依赖详细 stop 路由）。
5. 全局求解：
   - 满足硬约束并优化 urgency、偏好命中、容量浪费、连续性等软目标。
6. 输出：
   - `plans`：trip summaries
   - `order_assignments`：订单级分配结果
   - `exceptions`：无法自动分配的原因
7. 前端展示：  
   - 主视图 `Driver Assignment Summary`（`Driver -> Vehicle -> Orders`）  
   - 次级视图 `Assignment Groups (Secondary)`（仅做排查/对账）

> 当前 detailed routing 不再是主输出。`routing_core.py` 保留为兼容层，不是主链路必经步骤。

---

## 3. 目录结构说明

```text
Delivery/
├─ data/
│  └─ raw/
├─ dispatch_optimizer/
├─ frontend/
│  └─ modules/
├─ sql/
├─ tests/
├─ tools/
├─ examples/
├─ docs/
├─ AGENTS.md
└─ README.md
```

- `dispatch_optimizer/`：后端调度核心实现（预处理、组单、分配、provider、CLI）。
- `frontend/`：业务工作台前端（输入编辑 + 结果展示）。
- `sql/`：dispatch 层 schema 与主数据导入导出脚本。
- `tests/`：后端、前端 parity、治理守护测试。
- `tools/`：样例刷新与回收站删除等辅助脚本。
- `data/raw/`：raw source of truth。
- `examples/`：可直接运行的样例输入。

---

## 4. 关键文件/模块说明

### 前端

- `frontend/index.html`
  - 输入：无（页面结构）
  - 输出：DOM 容器与脚本加载顺序
  - 角色：工作台布局、结果区标题与空态文案
  - 调用关系：加载 `zone-utils -> driver-assignment-summary -> render-utils -> app.js -> overrides.js`

- `frontend/app.js`
  - 输入：表格数据、开发者模式 JSON
  - 输出：前端本地求解结果与渲染
  - 角色：页面主控制器（状态管理、表格映射、校验、渲染）
  - 调用关系：调用 `DeliveryZoneUtils` 与 `DeliveryDriverAssignmentSummary`

- `frontend/modules/driver-assignment-summary.js`
  - 输入：`order_assignments` + `plans`
  - 输出：`driver -> vehicle -> orders` 聚合结构
  - 角色：主视图聚合模块（业务展示不暴露 run/trip 技术层）
- `frontend/modules/render-utils.js`
  - 输入：当前 `view`（drivers/vehicles）与 result 展示字段
  - 输出：driver/vehicle 展示名映射、业务 explanation 文本转换
  - 角色：纯展示辅助模块，`app.js` 优先调用该模块并保留回退逻辑

- `frontend/overrides.js`
  - 输入：全局 `window`
  - 输出：shim 标记
  - 角色：兼容 shim，不承载核心业务逻辑（`frontend/overrides.js` 仅兼容 shim）

### 后端（façade + core）

- `dispatch_optimizer/engine.py` / `dispatch_optimizer/engine_core.py`
  - façade + 核心实现；
  - 输入：标准化实体与 providers；
  - 输出：`DispatchEngineResult(plans/order_assignments/exceptions)`；
  - 角色：主流程编排。

- `dispatch_optimizer/models.py` / `dispatch_optimizer/models_core.py`
  - façade + 核心数据模型；
  - 定义订单、司机、车辆、trip plan、assignment、exception 契约。

- `dispatch_optimizer/preprocess.py` / `dispatch_optimizer/preprocess_core.py`
  - façade + 核心预处理；
  - 输入：原始 orders/drivers/vehicles；
  - 输出：标准化 snapshot 与预处理异常。

- `dispatch_optimizer/run_generation.py` / `dispatch_optimizer/run_generation_core.py`
  - façade + 组单核心；
  - 输入：标准化订单；
  - 输出：`DispatchRun`（trip grouping）。

- `dispatch_optimizer/assignment.py` / `dispatch_optimizer/assignment_core.py`
  - façade + 分配核心；
  - 输入：runs、drivers、vehicles；
  - 输出：候选与最终分配；
  - 采用粗粒度时间估算，不以 detailed route 为前置。

- `dispatch_optimizer/routing.py` / `dispatch_optimizer/routing_core.py`
  - façade + 兼容路由模块；
  - 当前不是主输出链路，但保留以兼容历史逻辑和后续扩展。

- `dispatch_optimizer/providers.py` / `dispatch_optimizer/providers_core.py`
  - façade + provider 核心；
  - 提供 geocoder、travel time、缓存、Google Routes fallback。

- `dispatch_optimizer/cli.py`
  - 输入：snapshot JSON 文件；
  - 输出：标准 JSON 结果（`plans / order_assignments / exceptions`）；
  - 负责序列化与 provider 装配。

### 工具与 SQL

- `tools/refresh_sample_master_data.py`
  - 从 raw driver/vehicle 刷新 sample；
  - **规则：`tools/refresh_sample_master_data.py` 只覆盖 `drivers` 与 `vehicles`**。

- `tools/recycle.ps1`
  - 回收站删除脚本（禁止直接物理删除文件）。

- `sql/dispatch-input-snapshot-schema.sql`
  - dispatch 层 snapshot/output schema（含 postcode + zone_code 链路字段）。

- `sql/vehicle-raw-import.sql`
  - vehicle raw CSV -> staging -> upsert 主表。

---

## 5. 数据来源与主数据流

### Source of Truth 与产物边界

- Raw Source of Truth
  - `data/raw/zone-postcode-raw-data.csv`
  - `data/raw/driver-raw-data.csv`
  - `data/raw/vehicle-raw-data.csv`
- Generated Artifact
  - `examples/sample-dispatch-input.json` 中自动刷新段（drivers/vehicles）
- Frontend Default State
  - Front page 首屏默认 `orders` 为空，drivers/vehicles 直接展示

### 区域模型

- 订单输入：`postcode`
- 系统映射：`zone_code`
- 算法分组与偏好匹配：统一使用 `zone_code`
- 异常码：`POSTCODE_NOT_MAPPED`

---

## 6. 前端说明

- 默认输入方式：表格编辑（orders/drivers/vehicles），支持 CSV 导入订单。
- 默认主结果视图：`Driver Assignment Summary`
  - 层级：Driver -> Vehicle -> Orders
  - 聚合层保留 `related_run_ids` 便于排查
- 次级结果视图：`Assignment Groups (Secondary)`（显示分组明细）
- 开发者模式：整包 JSON 查看与回填，便于排查兼容数据。
- 输入结构不变：继续使用 `config / orders / drivers / vehicles`。

---

## 7. 调度算法说明

- run 保留但语义升级为 trip grouping；
- 分配目标是“每趟分给谁、用哪辆车”，不是 stop 路线排序。
- 硬约束：
  - 指定司机、司机可用、车辆可用、容量、资源时间冲突
- 软目标：
  - urgency、preferred zone、历史连续性、容量浪费、同日尽量少换车（vehicle_switch_penalty）
- 结果输出：
  - plans：trip summary
  - order_assignments：订单级分配
  - exceptions：失败原因

---

## 8. 配置与运行方式

### 常用命令

```powershell
node --check frontend/app.js
node --check frontend/overrides.js
python -m unittest discover -s tests -v
```

### CLI 示例

```powershell
python -m dispatch_optimizer.cli examples/sample-dispatch-input.json
```

### Google Routes 与 fallback

- 当前外部主路由时间源：**Google Routes API**
- Travel time 链路：`cache first -> Google Routes -> Haversine fallback`
- 关键配置：
  - `google_routes_api_key`
  - `google_routes_base_url`
  - `routing_preference`
  - `departure_time_strategy`
  - `request_timeout_seconds`
  - `max_retries`
  - `backoff_seconds`

---

## 9. 当前重要规则与约束

- 顶层输出结构固定：`plans / order_assignments / exceptions`
- 区域模型固定：`postcode + zone_code`
- 驱动偏好字段：`preferred_zone_codes`
- 兼容策略：允许读旧字段，不再新写出 `zone_id` / `preferred_zone_ids`
- `service_minutes` 不再作为输入字段；内部统一固定每站停留时间为 10 分钟（`FIXED_STOP_MINUTES = 10`）
- `run_id` 继续保留，语义承载 trip 标识
- 不直接物理删除文件，统一走 `tools/recycle.ps1`

---

## 10. 已知边界 / 注意事项

### 兼容层

- `dispatch_optimizer/*.py` 多数是 façade，真实实现在 `*_core.py`
- `routing_core.py` 仍保留，但当前不是主输出链路
- 前端保留历史兼容定义，最终生效逻辑由文件后段覆盖

### 技术债

- `frontend/app.js` 体量较大、历史重复定义较多，维护成本高
- 前端本地求解器与后端权威逻辑并存，联调时需明确口径
- 治理测试对 README 关键语句有守护，改文档需同步更新测试

---

## 本次口径更新摘要

- 主输出语义从“route/ETA 驱动”收敛为“trip grouping + assignment”。
- `plans` 表示 trip summaries；`order_assignments` 表示订单级分配结果。
- detailed routing 不再是主输出；兼容字段保留占位但不再业务依赖。
## UI Display Convergence (2026-04-23)

- Default primary result view is now **Driver Assignment Summary**.
- Primary hierarchy is **Driver -> Vehicle -> Orders**.
- Driver display name priority: `name` -> `metadata.name` -> `driver_id`.
- Vehicle display priority: `rego` -> `vehicle_id`.
- The UI no longer shows `run_id`, stop sequence, ETA, or departure in the main result area.
- Secondary result view label is **Assignment Groups (Secondary)** and also does not surface `run_id`.
- Top-level output contract remains unchanged: `plans / order_assignments / exceptions`.
## Same-Day Vehicle Continuity Priority (2026-04-23)

- Priority is now governed by the newer Zone-First policy (see section below), where same-day vehicle continuity is enforced before normal coverage.
- Same-day vehicle minimization means minimizing distinct vehicles per `(driver_id, dispatch_date)`.
- Greedy path uses explicit ordering:
  1) preferred-zone match, 2) same-zone continuity, 3) zone mismatch rank, 4) `switch_delta`, 5) business/balance score, 6) `estimated_finish`.
- CP-SAT path keeps lexicographic stages and does **not** collapse to a single weighted sum.
- This preference remains a soft rule and never overrides hard constraints.

## Driver Utilization Explainability (2026-04-23)

- The engine now emits driver-level idle reasons via `exceptions` (`scope="DRIVER"`), without changing top-level output keys.
- Reason codes:
  - `DRIVER_UNUSED_NO_FEASIBLE_CANDIDATE`
  - `DRIVER_UNUSED_OUTSCORED`
  - `DRIVER_UNUSED_NO_REMAINING_RUN`
- The frontend local planner follows the same direction and surfaces matching idle-driver hints.

## Plan ID Migration (2026-04-23)

- External output no longer uses `run_id` as a public contract field.
- `plans[*]` is linked by `plan_id`.
- `order_assignments[*]` is linked by the same `plan_id`.

## Zone-First Assignment Policy (2026-04-24)

- Zone preference is now treated as a **strong soft constraint**.
- Objective priority is:
  `hard constraints -> urgent coverage -> preferred-zone match -> minimize driver-day zone spread -> same-day vehicle minimization -> assignment coverage -> used drivers / balance / normal objective`.
- Driver preferred zone logic:
  - matched preferred zone gets a strong bonus (`preferred_zone_bonus=3000`);
  - mismatch against configured preferred zones gets a strong penalty (`zone_mismatch_penalty=2500`);
  - drivers without preferred zones are not penalized for mismatch.
- Normal orders are **not** pre-filtered away; feasible candidates are still generated. The lower coverage priority only affects final selection order.
- Same-day zone continuity is favored: if a driver already handles a zone on a dispatch date, subsequent groups from that zone are preferred for that driver.
- Zone is still **not** a hard constraint. When resources are limited, cross-zone assignment remains allowed to avoid unnecessary unassigned orders.
- `plans` are aggregated by `(dispatch_date, driver_id, vehicle_id)` for business readability.
- Internal engine may still use run/group objects during solving, but run identifiers are no longer surfaced in result payloads.

## VIC Zone Split Update (2026-04-24)

- `zone-postcode` mapping has been split from `MAJOR_EAST_SOUTH_EAST` into:
  - `MAJOR_EAST` for postcodes `3120-3139`
  - `SOUTH_EAST` for postcodes `3140-3209` and `3800-3979`
- `WEST` has been expanded to full range `3011-3077`.
- Source of truth updated: `data/raw/zone-postcode-raw-data.csv`.
- Frontend built-in mapping and labels updated in `frontend/app.js`.
- Sample config/orders updated in `examples/sample-dispatch-input.json` to use new zone codes.
- Historical SQL seed script synchronized: `sql/driver-vehicle-orders-schema.sql`.

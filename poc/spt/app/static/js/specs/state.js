/* Specs — shared state */

let specsList = [];
let selectedSpecService = null;
let specsEnv = "dev";
let specsView = "overview"; // overview | swagger | raw | config | versions | trace
let specsOpenOp = null; // "METHOD path" key currently expanded in overview
let specsSwaggerFilter = "";
let specsSwaggerUi = null;
let specsTryToken = null;
let specsTryTokenAt = 0;
let specsCache = {}; // key service|env -> openapi payload
let specsVersionsCache = {}; // service -> versions payload
let specsPayloadIndex = []; // list from /api/payloads?service=
let specsPayloadCatalog = []; // [{key,label,apiId,method,path,body,query,pathParams}]
let specsPayloadCursor = 0;
let specsPayloadService = null;
let specsEnrichedDoc = null;
/** Active working payload per api_id: { name, version, body, query, path, method } */
let specsActivePayloads = {};
/** Service-level payload set (one version covers all APIs) */
let specsPayloadSets = []; // summaries
let specsPayloadSetVersion = null;
let specsPayloadSetDetail = null; // full set with apis{}
let specsPayloadSetService = null;
/** APIs checked for load test from OpenAPI overview (catalog api ids) */
let specsLoadApiIds = [];
/** Pinned OpenAPI info.version for load (from contract dropdown) */
let specsContractVersion = null;

function specsCacheKey(service, env){ return service + "|" + env; }

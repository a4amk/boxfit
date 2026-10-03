import http from "k6/http";
import { check } from "k6";
import { Trend, Rate } from "k6/metrics";

// boxfit load driver: tenant + corpus IN-list filtered search over REST.
// Env: QDRANT_URL, QDRANT_API_KEY, COLLECTION, RATE, DUR, EF, TOPK, DIM,
// TENANTS (default 500), CORP (corpora per tenant, default 5),
// CORP_PICK (corpora per query, default 2),
// FILTER_JSON (rendered from the boxfit spec filter section, e.g.
// {"tenant": {"field": "tenant_id", "match": "value"},
//  "corpus": {"field": "corpus_id", "match": "any"}}; either may be null).
const p50t = new Trend("search_p50");
const errRate = new Rate("errors");

export const options = {
  scenarios: {
    load: {
      executor: "constant-arrival-rate",
      rate: parseInt(__ENV.RATE || "250", 10),
      timeUnit: "1s",
      duration: __ENV.DUR || "60s",
      preAllocatedVUs: parseInt(__ENV.VUS || "200", 10),
      maxVUs: parseInt(__ENV.VUS || "200", 10) * 4,
    },
  },
  thresholds: { errors: ["rate<0.02"] },
};

const BASE = __ENV.QDRANT_URL || "http://127.0.0.1:6333";
const COLLECTION = __ENV.COLLECTION || "boxfit";
const EF = parseInt(__ENV.EF || "100", 10);
const TOPK = parseInt(__ENV.TOPK || "10", 10);
const DIM = parseInt(__ENV.DIM || "512", 10);
const TENANTS = parseInt(__ENV.TENANTS || "500", 10);
const CORP = parseInt(__ENV.CORP || "5", 10);
const PICK = parseInt(__ENV.CORP_PICK || "2", 10);
const FILTER = JSON.parse(__ENV.FILTER_JSON || "{}");

function gauss() {
  const u = Math.max(Math.random(), 1e-9);
  const w = Math.max(Math.random(), 1e-9);
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * w) * 0.3;
}

function randomVector() {
  const v = new Array(DIM);
  for (let i = 0; i < DIM; i++) {
    const x = gauss();
    const c = x < -1 ? -1 : x > 1 ? 1 : x;
    v[i] = Math.round(((c + 1) / 2) * 255);
  }
  return v;
}

const HDRS = {
  headers: {
    "Content-Type": "application/json",
    "api-key": __ENV.QDRANT_API_KEY,
  },
};

export default function () {
  const t = Math.floor(Math.random() * TENANTS);
  const tt = `t-${String(t).padStart(3, "0")}`;
  const must = [];
  if (FILTER.tenant) {
    must.push({ key: FILTER.tenant.field, match: { value: tt } });
  }
  if (FILTER.corpus) {
    const picked = new Set();
    while (picked.size < Math.min(PICK, CORP))
      picked.add(Math.floor(Math.random() * CORP));
    const corps = [...picked].map((k) => `${tt}-c${k}`);
    must.push({ key: FILTER.corpus.field, match: { any: corps } });
  }
  const body = JSON.stringify({
    vector: randomVector(),
    limit: TOPK,
    with_vector: false,
    with_payload: false,
    filter: {
      must,
    },
    params: { hnsw_ef: EF, indexed_only: false },
  });
  const res = http.post(
    `${BASE}/collections/${COLLECTION}/points/search`,
    body,
    HDRS,
  );
  check(res, { "search 200": (r) => r.status === 200 });
  errRate.add(res.status !== 200);
  p50t.add(res.timings.duration);
}

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ||
  "http://localhost:5000/api";

async function get(path) {
  const response = await fetch(`${API_BASE_URL}${path}`);

  let payload;

  try {
    payload = await response.json();
  } catch {
    throw new Error(`Invalid response received from ${path}`);
  }

  if (!response.ok || payload.success === false) {
    throw new Error(
      payload.message || payload.error || `Request failed: ${response.status}`,
    );
  }

  return payload;
}

export async function getDashboardData() {
  const [healthPayload, summaryPayload] = await Promise.all([
    get("/health"),
    get("/summary"),
  ]);

  return {
    health: healthPayload.data ?? healthPayload,
    summary: summaryPayload.data ?? summaryPayload,
  };
}
export async function getRiskMap() {
  const payload = await get("/map");
  const result = payload.data ?? payload;

  if (result.type === "FeatureCollection") {
    return result;
  }

  if (result.geojson?.type === "FeatureCollection") {
    return result.geojson;
  }

  if (result.map?.type === "FeatureCollection") {
    return result.map;
  }

  throw new Error("The API did not return valid GeoJSON data");
}
export async function getWardForecast(wardId) {
  const payload = await get(`/wards/${encodeURIComponent(wardId)}`);
  const result = payload.data ?? payload;

  if (!Array.isArray(result.forecast)) {
    throw new Error("Ward forecast data is missing");
  }

  return result;
}
export async function getDailyForecast(date = "") {
  const query = date
    ? `?date=${encodeURIComponent(date)}`
    : "";

  const payload = await get(`/forecast/daily${query}`);

  return {
    metadata: payload.metadata ?? {},
    rows: Array.isArray(payload.data) ? payload.data : [],
  };
}
export async function getAlertPreview(wardId, date) {
  const payload = await get(
    `/alerts/preview?ward_id=${encodeURIComponent(
      wardId,
    )}&date=${encodeURIComponent(date)}`,
  );

  return payload.data ?? payload;
}

export async function simulateAlertDispatch(wardId, date) {
  const response = await fetch(
    `${API_BASE_URL}/alerts/dispatch`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        ward_id: String(wardId),
        date,
        channels: [
          "sms",
          "whatsapp",
          "administration",
        ],
      }),
    },
  );

  const payload = await response.json();

  if (!response.ok || payload.success === false) {
    throw new Error(
      payload.error?.message ||
        payload.message ||
        "Alert simulation failed",
    );
  }

  return payload.data;
}
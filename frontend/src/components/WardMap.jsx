import { useEffect, useMemo, useState } from "react";
import L from "leaflet";
import {
  GeoJSON,
  MapContainer,
  TileLayer,
  ZoomControl,
  useMap,
} from "react-leaflet";
import { AlertTriangle, MapPin, ThermometerSun } from "lucide-react";
import "leaflet/dist/leaflet.css";
import AlertActionPanel from "./AlertActionPanel";
import { getDailyForecast, getRiskMap } from "../api";
import WardForecastChart from "./WardForecastChart";

const DELHI_CENTRE = [28.6139, 77.209];

function FitDelhiBoundaries({ geoJson }) {
  const map = useMap();

  useEffect(() => {
    const timer = window.setTimeout(() => {
      map.invalidateSize();

      const boundaryLayer = L.geoJSON(geoJson);
      const bounds = boundaryLayer.getBounds();

      if (bounds.isValid()) {
        map.fitBounds(bounds, {
          padding: [20, 20],
          maxZoom: 11,
        });
      }
    }, 250);

    return () => window.clearTimeout(timer);
  }, [map, geoJson]);

  return null;
}

function getRisk(properties = {}) {
  return Number(
    properties.calibrated_mortality_risk_index ??
      properties.mortality_risk_index ??
      0,
  );
}

function getRiskLevel(properties = {}) {
  return (
    properties.calibrated_risk_level ??
    properties.risk_level ??
    "Unknown"
  );
}

/*
 * Continuous intensity colours make differences visible while preserving
 * the official High/Extreme risk level shown in the ward information.
 */
function getRiskColor(properties = {}) {
  const risk = getRisk(properties);

  if (risk >= 90) return "#7F0000";
  if (risk >= 85) return "#A50F15";
  if (risk >= 80) return "#CB181D";
  if (risk >= 75) return "#EF3B2C";
  if (risk >= 70) return "#F16913";
  if (risk >= 60) return "#FD8D3C";
  if (risk >= 50) return "#FDBB84";
  if (risk >= 25) return "#FDD49E";

  return "#2E9D70";
}

function getFeatureStyle(feature) {
  return {
    color: "#ffffff",
    weight: 1,
    opacity: 0.9,
    fillColor: getRiskColor(feature.properties),
    fillOpacity: 0.8,
  };
}

function formatNumber(value, digits = 1) {
  const number = Number(value);

  if (!Number.isFinite(number)) {
    return "--";
  }

  return number.toFixed(digits);
}

function WardMap() {
  const [peakGeoJson, setPeakGeoJson] = useState(null);
  const [dailyRows, setDailyRows] = useState([]);
  const [availableDates, setAvailableDates] = useState([]);
  const [selectedDate, setSelectedDate] = useState("");
  const [mapMode, setMapMode] = useState("daily");
  const [selectedWardId, setSelectedWardId] = useState(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const [dailyLoading, setDailyLoading] = useState(false);
  const [mapError, setMapError] = useState("");

  useEffect(() => {
    let active = true;

    async function loadInitialData() {
      try {
        setInitialLoading(true);
        setMapError("");

        const [mapData, dailyData] = await Promise.all([
          getRiskMap(),
          getDailyForecast(),
        ]);

        if (!active) return;

        setPeakGeoJson(mapData);
        setDailyRows(dailyData.rows);
        setAvailableDates(dailyData.metadata.available_dates ?? []);
        setSelectedDate(dailyData.metadata.selected_date ?? "");
      } catch (error) {
        if (active) {
          setMapError(error.message);
        }
      } finally {
        if (active) {
          setInitialLoading(false);
        }
      }
    }

    loadInitialData();

    return () => {
      active = false;
    };
  }, []);

  const displayGeoJson = useMemo(() => {
    if (!peakGeoJson) {
      return null;
    }

    if (mapMode === "peak") {
      return peakGeoJson;
    }

    const dailyDataByWard = new Map(
      dailyRows.map((row) => [String(row.ward_id), row]),
    );

    return {
      ...peakGeoJson,
      features: peakGeoJson.features.map((feature) => {
        const wardId = String(feature.properties?.ward_id ?? "");
        const dailyData = dailyDataByWard.get(wardId);

        return {
          ...feature,
          properties: {
            ...feature.properties,
            ...(dailyData ?? {}),
          },
        };
      }),
    };
  }, [peakGeoJson, dailyRows, mapMode]);

  const selectedWard = useMemo(() => {
      if (!selectedWardId || !displayGeoJson) {
        return null;
      }

      const selectedFeature = displayGeoJson.features.find(
        (feature) =>
          String(feature.properties?.ward_id) === String(selectedWardId),
      );

      return selectedFeature?.properties ?? null;
    }, [displayGeoJson, selectedWardId]);
  async function handleDateChange(event) {
    const newDate = event.target.value;

    try {
      setSelectedDate(newDate);
      setDailyLoading(true);
      setMapError("");

      const dailyData = await getDailyForecast(newDate);

      setDailyRows(dailyData.rows);
      setAvailableDates(dailyData.metadata.available_dates ?? []);
    } catch (error) {
      setMapError(error.message);
    } finally {
      setDailyLoading(false);
    }
  }

  function handleEachWard(feature, layer) {
    const properties = feature.properties ?? {};
    const wardName = properties.ward_name ?? "Unnamed ward";
    const wardId = properties.ward_id ?? "--";
    const risk = formatNumber(getRisk(properties), 2);

    layer.bindTooltip(
      `${wardName} · Ward ${wardId} · Risk ${risk}`,
      {
        sticky: true,
        direction: "top",
      },
    );

    layer.on({
      mouseover(event) {
        event.target.setStyle({
          weight: 3,
          color: "#17212b",
          fillOpacity: 0.95,
        });

        event.target.bringToFront();
      },

      mouseout(event) {
        event.target.setStyle(getFeatureStyle(feature));
      },

      click() {
        setSelectedWardId(String(properties.ward_id));
      },
    });
  }

  return (
    <section className="panel map-panel">
      <div className="panel-heading map-heading">
        <div>
          <span className="eyebrow">Interactive GIS intelligence</span>
          <h2>
            {mapMode === "daily"
              ? `Delhi heat-health risk: ${selectedDate}`
              : "Delhi five-day peak heat-health risk"}
          </h2>
        </div>

        <div className="map-heading-actions">
          <div className="map-mode-switch">
            <button
              type="button"
              className={mapMode === "daily" ? "active" : ""}
              onClick={() => setMapMode("daily")}
            >
              Daily
            </button>

            <button
              type="button"
              className={mapMode === "peak" ? "active" : ""}
              onClick={() => setMapMode("peak")}
            >
              5-day peak
            </button>
          </div>

          {mapMode === "daily" && (
            <select
              className="map-date-select"
              value={selectedDate}
              onChange={handleDateChange}
              disabled={dailyLoading}
              aria-label="Select forecast date"
            >
              {availableDates.map((date) => (
                <option key={date} value={date}>
                  {date}
                </option>
              ))}
            </select>
          )}

          <MapPin size={22} />
        </div>
      </div>

      {initialLoading && (
        <div className="map-message">
          <div className="loader" />
          <p>Loading 290 ward boundaries...</p>
        </div>
      )}

      {mapError && (
        <div className="warning-banner map-warning">
          <AlertTriangle size={18} />
          {mapError}
        </div>
      )}

      {!initialLoading && displayGeoJson && (
        <div className="map-content-grid">
          <div className="map-wrapper">
            <MapContainer
              center={DELHI_CENTRE}
              zoom={10}
              minZoom={9}
              maxZoom={16}
              scrollWheelZoom
              zoomControl={false}
              className="delhi-map"
            >
              <TileLayer
                attribution="&copy; OpenStreetMap contributors"
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />

              <FitDelhiBoundaries geoJson={displayGeoJson} />

              <GeoJSON
                key={`${mapMode}-${selectedDate}`}
                data={displayGeoJson}
                style={getFeatureStyle}
                onEachFeature={handleEachWard}
              />

              <ZoomControl position="topright" />
            </MapContainer>

            {dailyLoading && (
              <div className="map-updating">Updating daily risks...</div>
            )}

            <div className="map-legend">
              <strong>Risk intensity (MRI)</strong>

              <div className="risk-gradient" />

              <div className="risk-scale">
                <span>0</span>
                <span>50</span>
                <span>75</span>
                <span>100</span>
              </div>

              <small>
                {mapMode === "daily"
                  ? `Daily view: ${selectedDate}`
                  : "Worst value during five days"}
              </small>
            </div>
          </div>

          <aside className="ward-details">
            {!selectedWard ? (
              <div className="ward-placeholder">
                <MapPin size={38} />
                <h3>Select a ward</h3>
                <p>Click a Delhi ward to inspect its forecast.</p>
              </div>
            ) : (
              <>
                <div className="ward-title">
                  <div>
                    <span>Ward {selectedWard.ward_id}</span>
                    <h3>{selectedWard.ward_name}</h3>
                  </div>

                  <span
                    className="selected-risk-badge"
                    style={{
                      backgroundColor: getRiskColor(selectedWard),
                    }}
                  >
                    {getRiskLevel(selectedWard)}
                  </span>
                </div>

                <div className="risk-score-box">
                  <span>Calibrated Mortality Risk Index</span>
                  <strong>{formatNumber(getRisk(selectedWard), 2)}</strong>
                  <small>Relative impact ranking out of 100</small>
                </div>

                <div className="ward-metric-grid">
                  <div>
                    <span>Forecast date</span>
                    <strong>{selectedWard.forecast_date ?? "--"}</strong>
                  </div>

                  <div>
                    <span>Maximum temperature</span>
                    <strong>
                      {formatNumber(selectedWard.temperature_max_c)}°C
                    </strong>
                  </div>

                  <div>
                    <span>Maximum WBGT</span>
                    <strong>
                      {formatNumber(selectedWard.wbgt_max_c)}°C
                    </strong>
                  </div>

                  <div>
                    <span>Maximum UTCI</span>
                    <strong>
                      {formatNumber(selectedWard.utci_max_c)}°C
                    </strong>
                  </div>

                  <div>
                    <span>Danger hours</span>
                    <strong>{selectedWard.danger_hours ?? "--"}</strong>
                  </div>

                  <div>
                    <span>Evidence increase</span>
                    <strong>
                      {formatNumber(
                        selectedWard.evidence_relative_increase_pct,
                      )}
                      %
                    </strong>
                  </div>
                </div>

                <div className="ward-advisory">
                  <ThermometerSun size={20} />

                  <div>
                    <strong>Recommended intervention</strong>
                    <p>
                      {selectedWard.calibrated_recommended_action ??
                        selectedWard.recommended_action ??
                        "Activate the local heat action plan."}
                    </p>
                  </div>
                </div>
              </>
            )}
          </aside>
        </div>
      )}

      {!initialLoading && selectedWard && (
        <WardForecastChart wardId={selectedWard.ward_id} />
      )}
      {!initialLoading &&
        selectedWard &&
        selectedWard.forecast_date && (
          <AlertActionPanel
            key={`${selectedWard.ward_id}-${selectedWard.forecast_date}`}
            wardId={selectedWard.ward_id}
            date={selectedWard.forecast_date}
          />
        )}
    </section>
  );
}

export default WardMap;
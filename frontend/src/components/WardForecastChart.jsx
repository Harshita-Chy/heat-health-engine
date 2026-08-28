import { useEffect, useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { AlertTriangle, CalendarDays } from "lucide-react";
import { getWardForecast } from "../api";

function formatDate(date) {
  return new Date(`${date}T00:00:00`).toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
  });
}

function WardForecastChart({ wardId }) {
  const [wardData, setWardData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!wardId) return undefined;

    let active = true;

    async function loadForecast() {
      try {
        setLoading(true);
        setError("");

        const result = await getWardForecast(wardId);

        if (active) {
          setWardData(result);
        }
      } catch (requestError) {
        if (active) {
          setError(requestError.message);
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    loadForecast();

    return () => {
      active = false;
    };
  }, [wardId]);

  if (!wardId) {
    return null;
  }

  if (loading) {
    return (
      <div className="forecast-chart-message">
        Loading ward forecast...
      </div>
    );
  }

  if (error) {
    return (
      <div className="forecast-chart-message chart-error">
        <AlertTriangle size={19} />
        {error}
      </div>
    );
  }

  if (!wardData) {
    return null;
  }

  const chartData = wardData.forecast.map((day) => ({
    date: formatDate(day.forecast_date),
    fullDate: day.forecast_date,
    risk: day.calibrated_mortality_risk_index,
    temperature: day.temperature_max_c,
    wbgt: day.wbgt_max_c,
    utci: day.utci_max_c,
  }));

  const highestRiskDay = wardData.forecast.reduce((highest, day) => {
    if (
      day.calibrated_mortality_risk_index >
      highest.calibrated_mortality_risk_index
    ) {
      return day;
    }

    return highest;
  }, wardData.forecast[0]);

  return (
    <div className="forecast-chart-panel">
      <div className="forecast-chart-heading">
        <div>
          <span className="eyebrow">Selected ward forecast</span>
          <h2>{wardData.ward_name}: five-day risk progression</h2>
        </div>

        <div className="peak-day">
          <CalendarDays size={18} />
          <div>
            <span>Peak risk day</span>
            <strong>{highestRiskDay.forecast_date}</strong>
          </div>
        </div>
      </div>

      <div className="chart-and-summary">
        <div className="chart-container">
          <ResponsiveContainer width="100%" height={340}>
            <ComposedChart
              data={chartData}
              margin={{ top: 15, right: 15, left: 0, bottom: 5 }}
            >
              <defs>
                <linearGradient id="riskGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#d64545" stopOpacity={0.35} />
                  <stop offset="95%" stopColor="#d64545" stopOpacity={0.03} />
                </linearGradient>
              </defs>

              <CartesianGrid strokeDasharray="4 4" stroke="#e4e9ed" />

              <XAxis
                dataKey="date"
                tick={{ fontSize: 11, fill: "#6b7785" }}
              />

              <YAxis
                yAxisId="risk"
                domain={[0, 100]}
                tick={{ fontSize: 11, fill: "#6b7785" }}
              />

              <YAxis
                yAxisId="thermal"
                orientation="right"
                domain={[20, 60]}
                tick={{ fontSize: 11, fill: "#6b7785" }}
                unit="°"
              />

              <Tooltip
                formatter={(value, name) => [
                  `${Number(value).toFixed(1)}${
                    name === "Risk Index" ? "" : "°C"
                  }`,
                  name,
                ]}
              />

              <Legend />

              <Area
                yAxisId="risk"
                type="monotone"
                dataKey="risk"
                name="Risk Index"
                stroke="#c62828"
                strokeWidth={3}
                fill="url(#riskGradient)"
              />

              <Line
                yAxisId="thermal"
                type="monotone"
                dataKey="temperature"
                name="Temperature"
                stroke="#e8792e"
                strokeWidth={2}
                dot={{ r: 4 }}
              />

              <Line
                yAxisId="thermal"
                type="monotone"
                dataKey="wbgt"
                name="WBGT"
                stroke="#2878b5"
                strokeWidth={2}
                dot={{ r: 4 }}
              />

              <Line
                yAxisId="thermal"
                type="monotone"
                dataKey="utci"
                name="UTCI"
                stroke="#8d56b3"
                strokeWidth={2}
                dot={{ r: 4 }}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        <aside className="peak-summary">
          <span
            className="peak-risk-level"
            style={{
              backgroundColor:
                highestRiskDay.calibrated_map_color ?? "#c62828",
            }}
          >
            {highestRiskDay.calibrated_risk_level}
          </span>

          <span>Peak calibrated risk</span>

          <strong>
            {Number(
              highestRiskDay.calibrated_mortality_risk_index,
            ).toFixed(2)}
          </strong>

          <dl>
            <div>
              <dt>Temperature</dt>
              <dd>{highestRiskDay.temperature_max_c}°C</dd>
            </div>

            <div>
              <dt>WBGT</dt>
              <dd>{highestRiskDay.wbgt_max_c}°C</dd>
            </div>

            <div>
              <dt>UTCI</dt>
              <dd>{highestRiskDay.utci_max_c}°C</dd>
            </div>

            <div>
              <dt>Danger hours</dt>
              <dd>{highestRiskDay.danger_hours}</dd>
            </div>
          </dl>

          <p>{highestRiskDay.calibrated_recommended_action}</p>
        </aside>
      </div>
    </div>
  );
}

export default WardForecastChart;
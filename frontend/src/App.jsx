import { useEffect, useState } from "react";
import WardMap from "./components/WardMap";

import {
  Activity,
  AlertTriangle,
  CalendarDays,
  HeartPulse,
  MapPinned,
  RefreshCw,
  ShieldCheck,
  ThermometerSun,
} from "lucide-react";
import { getDashboardData } from "./api";
import "./App.css";

function formatNumber(value, digits = 0) {
  const number = Number(value);

  if (!Number.isFinite(number)) {
    return "--";
  }

  return number.toLocaleString("en-IN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function formatTime(value) {
  if (!value) return "--";

  return new Date(value).toLocaleString("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Kolkata",
  });
}

function App() {
  const [health, setHealth] = useState(null);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function handleRefresh() {
  try {
      setLoading(true);
      setError("");
    
      const result = await getDashboardData();
    
      setHealth(result.health);
      setSummary(result.summary);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }
  
  useEffect(() => {
    let active = true;
  
    getDashboardData()
      .then((result) => {
        if (!active) return;
      
        setHealth(result.health);
        setSummary(result.summary);
        setError("");
      })
      .catch((requestError) => {
        if (active) {
          setError(requestError.message);
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    
    return () => {
      active = false;
    };
  }, []);
  if (error && !summary) {
    return (
      <main className="center-screen">
        <AlertTriangle size={42} />
        <h1>Unable to load the dashboard</h1>
        <p>{error}</p>
        <button className="primary-button" onClick={handleRefresh}>
          Try again
        </button>
      </main>
    );
  }

  const forecast = summary?.current_forecast ?? {};
  const geography = summary?.geographic_summary ?? {};
  const validation = summary?.historical_validation ?? {};

  const topWards = geography.top_10_risk_wards ?? [];
  const riskCounts = geography.risk_level_counts ?? {};
  const totalWards = geography.forecast_wards ?? 0;
  const extremeWards = riskCounts.Extreme ?? 0;
  const highWards = riskCounts.High ?? 0;

  const extremePercent =
    totalWards > 0 ? (extremeWards / totalWards) * 100 : 0;

  const highPercent = totalWards > 0 ? (highWards / totalWards) * 100 : 0;

  const availableFiles = Object.values(health?.files ?? {}).filter(
    (file) => file.available,
  ).length;

  const totalFiles = Object.keys(health?.files ?? {}).length;

  return (
    <div className="app-shell">
      <header className="dashboard-header">
        <div>
          <div className="brand-line">
            <ThermometerSun size={30} />
            <h1>Delhi Heat-Health Command Centre</h1>
          </div>

          <p>
            Ward-level human thermal stress and mortality-risk early warning
          </p>
        </div>

        <div className="header-actions">
          <span className="system-status">
            <span className="status-dot" />
            API {health?.status ?? "unknown"}
          </span>

          <button
            className="refresh-button"
            onClick={handleRefresh}
            disabled={loading}
          >
            <RefreshCw className={loading ? "spin" : ""} size={17} />
            Refresh
          </button>
        </div>
      </header>

      {error && <div className="warning-banner">{error}</div>}

      <main className="dashboard-content">
        <section className="stat-grid">
          <article className="stat-card danger">
            <div className="stat-icon">
              <HeartPulse />
            </div>
            <div>
              <span>Maximum mortality risk</span>
              <strong>
                {formatNumber(geography.maximum_calibrated_risk, 2)}
              </strong>
              <small>Relative risk index out of 100</small>
            </div>
          </article>

          <article className="stat-card orange">
            <div className="stat-icon">
              <MapPinned />
            </div>
            <div>
              <span>Delhi wards monitored</span>
              <strong>{formatNumber(totalWards)}</strong>
              <small>Hyper-local GIS coverage</small>
            </div>
          </article>

          <article className="stat-card yellow">
            <div className="stat-icon">
              <CalendarDays />
            </div>
            <div>
              <span>Forecast horizon</span>
              <strong>{formatNumber(forecast.forecast_days)} days</strong>
              <small>{formatNumber(forecast.rows)} ward-day predictions</small>
            </div>
          </article>

          <article className="stat-card green">
            <div className="stat-icon">
              <ShieldCheck />
            </div>
            <div>
              <span>Model files ready</span>
              <strong>
                {availableFiles}/{totalFiles}
              </strong>
              <small>Forecast, GIS and validation files</small>
            </div>
          </article>
        </section>
        <WardMap />
        <section className="dashboard-grid">
          <article className="panel risk-panel">
            <div className="panel-heading">
              <div>
                <span className="eyebrow">Five-day peak</span>
                <h2>Ward risk distribution</h2>
              </div>
              <Activity size={22} />
            </div>

            <div className="distribution-item">
              <div className="distribution-label">
                <span>Extreme risk</span>
                <strong>{extremeWards} wards</strong>
              </div>
              <div className="progress-track">
                <div
                  className="progress-fill extreme"
                  style={{ width: `${extremePercent}%` }}
                />
              </div>
            </div>

            <div className="distribution-item">
              <div className="distribution-label">
                <span>High risk</span>
                <strong>{highWards} wards</strong>
              </div>
              <div className="progress-track">
                <div
                  className="progress-fill high"
                  style={{ width: `${highPercent}%` }}
                />
              </div>
            </div>

            <div className="model-note">
              <AlertTriangle size={19} />
              <p>
                This is a relative heat-health impact ranking, not a predicted
                death count.
              </p>
            </div>
          </article>

          <article className="panel validation-panel">
            <div className="panel-heading">
              <div>
                <span className="eyebrow">Historical validation</span>
                <h2>May 2024 Delhi heatwave</h2>
              </div>
              <ShieldCheck size={22} />
            </div>

            <div className="validation-values">
              <div>
                <span>Days tested</span>
                <strong>{validation.period?.days ?? "--"}</strong>
              </div>

              <div>
                <span>Comprehensive warnings</span>
                <strong>
                  {validation.event_detection?.comprehensive_warning_days ??
                    "--"}
                </strong>
              </div>

              <div>
                <span>Temperature threshold missed</span>
                <strong>
                  {validation.event_detection
                    ?.dangerous_days_missed_by_40c_threshold ?? "--"}
                </strong>
              </div>

              <div>
                <span>Maximum historical risk</span>
                <strong>
                  {formatNumber(
                    validation.maximum_values?.calibrated_risk_index,
                  )}
                </strong>
              </div>
            </div>
          </article>
        </section>

        <section className="dashboard-grid lower-grid">
          <article className="panel hotspot-panel">
            <div className="panel-heading">
              <div>
                <span className="eyebrow">Priority intervention</span>
                <h2>Highest-risk wards</h2>
              </div>
              <MapPinned size={22} />
            </div>

            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>Rank</th>
                    <th>Ward</th>
                    <th>Peak date</th>
                    <th>Risk index</th>
                    <th>Level</th>
                  </tr>
                </thead>

                <tbody>
                  {topWards.map((ward, index) => (
                    <tr key={ward.ward_id}>
                      <td>{index + 1}</td>
                      <td>
                        <strong>{ward.ward_name}</strong>
                        <small>Ward {ward.ward_id}</small>
                      </td>
                      <td>{ward.forecast_date}</td>
                      <td>
                        {formatNumber(
                          ward.calibrated_mortality_risk_index,
                          2,
                        )}
                      </td>
                      <td>
                        <span className="risk-badge">
                          {ward.calibrated_risk_level}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>

          <article className="panel actions-panel">
            <div className="panel-heading">
              <div>
                <span className="eyebrow">Automated response</span>
                <h2>Recommended actions</h2>
              </div>
              <AlertTriangle size={22} />
            </div>

            <ul className="action-list">
              <li>
                <span>1</span>
                Open cooling centres in extreme-risk wards.
              </li>
              <li>
                <span>2</span>
                Shift outdoor work away from afternoon peak hours.
              </li>
              <li>
                <span>3</span>
                Alert hospitals about a possible heat-illness surge.
              </li>
              <li>
                <span>4</span>
                Push localized SMS and WhatsApp heat advisories.
              </li>
            </ul>

            <div className="update-time">
              Forecast generated: {formatTime(forecast.generated_at_utc)}
            </div>
          </article>
        </section>
        
      </main>
    </div>
  );
}

export default App;
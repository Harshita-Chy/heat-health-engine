import { useEffect, useState } from "react";
import {
  BellRing,
  Building2,
  CheckCircle2,
  Clock,
  Hospital,
  MessageCircle,
  Send,
  Users,
  Zap,
} from "lucide-react";
import {
  getAlertPreview,
  simulateAlertDispatch,
} from "../api";

function Trigger({ active, icon, children }) {
  return (
    <div className={`admin-trigger ${active ? "active" : ""}`}>
      {icon}
      <span>{children}</span>
      <strong>{active ? "Triggered" : "Standby"}</strong>
    </div>
  );
}

function AlertActionPanel({ wardId, date }) {
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [dispatching, setDispatching] = useState(false);
  const [dispatchResult, setDispatchResult] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;

    getAlertPreview(wardId, date)
      .then((result) => {
        if (active) {
          setPreview(result);
          setError("");
        }
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
  }, [wardId, date]);

  async function handleDispatch() {
    try {
      setDispatching(true);
      setDispatchResult(null);
      setError("");

      const result = await simulateAlertDispatch(
        wardId,
        date,
      );

      setDispatchResult(result);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setDispatching(false);
    }
  }

  if (loading) {
    return (
      <div className="alert-panel-message">
        Loading alert preview...
      </div>
    );
  }

  if (!preview) {
    return (
      <div className="alert-panel-message alert-panel-error">
        {error || "Alert preview unavailable"}
      </div>
    );
  }

  const triggers = preview.administrative_triggers;

  return (
    <section className="alert-action-panel">
      <div className="alert-panel-heading">
        <div>
          <span className="eyebrow">Automated response API</span>
          <h2>Regional alert and administration console</h2>
          <p>
            {preview.ward.ward_name} · Ward{" "}
            {preview.ward.ward_id} · {preview.forecast.date}
          </p>
        </div>

        <div className="simulation-badge">
          <BellRing size={16} />
          Simulation mode
        </div>
      </div>

      <div className="alert-message-grid">
        <article className="alert-message-card">
          <div className="alert-message-title">
            <MessageCircle size={19} />
            <strong>SMS preview</strong>
          </div>

          <p>{preview.messages.sms}</p>
        </article>

        <article className="alert-message-card">
          <div className="alert-message-title">
            <Users size={19} />
            <strong>WhatsApp preview</strong>
          </div>

          <p className="whatsapp-preview">
            {preview.messages.whatsapp}
          </p>
        </article>
      </div>

      <div className="trigger-grid">
        <Trigger
          active={triggers.open_cooling_centres}
          icon={<Building2 size={18} />}
        >
          Cooling centres
        </Trigger>

        <Trigger
          active={triggers.shift_outdoor_work_hours}
          icon={<Clock size={18} />}
        >
          Work-hour shift
        </Trigger>

        <Trigger
          active={triggers.hospital_surge_alert}
          icon={<Hospital size={18} />}
        >
          Hospital surge
        </Trigger>

        <Trigger
          active={triggers.power_grid_readiness}
          icon={<Zap size={18} />}
        >
          Grid readiness
        </Trigger>
      </div>

      {error && (
        <div className="alert-panel-error">{error}</div>
      )}

      {dispatchResult && (
        <div className="dispatch-success">
          <CheckCircle2 size={19} />

          <div>
            <strong>Alert simulation completed</strong>
            <span>
              Dispatch ID: {dispatchResult.dispatch_id}
            </span>
          </div>
        </div>
      )}

      <div className="alert-panel-footer">
        <p>
          No real messages are sent. The simulation is saved in the
          dispatch audit log.
        </p>

        <button
          type="button"
          className="dispatch-button"
          onClick={handleDispatch}
          disabled={
            dispatching || !preview.should_dispatch
          }
        >
          <Send size={17} />
          {dispatching
            ? "Simulating..."
            : "Simulate alert dispatch"}
        </button>
      </div>
    </section>
  );
}

export default AlertActionPanel;
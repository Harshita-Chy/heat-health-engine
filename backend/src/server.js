const path = require("path");
const fs = require("fs/promises");

const express = require("express");
const cors = require("cors");
const helmet = require("helmet");
const morgan = require("morgan");
const { rateLimit } = require("express-rate-limit");
const { parse } = require("csv-parse/sync");

require("dotenv").config();


const app = express();

const PORT = Number(process.env.PORT) || 5000;

// server.js is backend/src/server.js.
// Moving two levels upward reaches heat-health-engine.
const PROJECT_ROOT = path.resolve(__dirname, "..", "..");


const FILES = {
    model: path.join(
        PROJECT_ROOT,
        "models",
        "mortality_model_v1.json"
    ),

    forecast: path.join(
        PROJECT_ROOT,
        "output",
        "delhi_ward_daily_calibrated_risk.csv"
    ),

    map: path.join(
        PROJECT_ROOT,
        "output",
        "delhi_5day_peak_calibrated_risk_map.geojson"
    ),

    hotspots: path.join(
        PROJECT_ROOT,
        "output",
        "delhi_calibrated_hotspots.csv"
    ),

    mortalitySummary: path.join(
        PROJECT_ROOT,
        "output",
        "delhi_mortality_calibration_summary.json"
    ),

    mapSummary: path.join(
        PROJECT_ROOT,
        "output",
        "delhi_calibrated_map_summary.json"
    ),

    backtestSummary: path.join(
        PROJECT_ROOT,
        "output",
        "delhi_may_2024_backtest_summary.json"
    ),
};
const ALERT_LOG_FILE = path.join(
    PROJECT_ROOT,
    "output",
    "alert_dispatch_log.jsonl"
);

const limiter = rateLimit({
    windowMs: 60 * 1000,
    limit: 120,
    standardHeaders: "draft-8",
    legacyHeaders: false,
});


app.disable("x-powered-by");

app.use(helmet());

app.use(
    cors({
        origin: process.env.CORS_ORIGIN || "http://localhost:5173",
    })
);

app.use(morgan("dev"));

app.use(
    express.json({
        limit: "100kb",
    })
);

app.use("/api", limiter);


function asyncHandler(handler) {
    return function wrappedHandler(request, response, next) {
        Promise.resolve(
            handler(request, response, next)
        ).catch(next);
    };
}


function normalizeWardId(value) {
    if (value === null || value === undefined) {
        return "";
    }

    const text = String(value).trim();

    if (/^-?\d+\.0$/.test(text)) {
        return text.slice(0, -2);
    }

    return text;
}


function convertCsvValue(value) {
    if (value === "") {
        return null;
    }

    const lowerValue = String(value).toLowerCase();

    if (lowerValue === "true") {
        return true;
    }

    if (lowerValue === "false") {
        return false;
    }

    if (/^-?\d+(\.\d+)?$/.test(value)) {
        return Number(value);
    }

    return value;
}


async function readJson(filePath) {
    const content = await fs.readFile(
        filePath,
        "utf-8"
    );

    return JSON.parse(content);
}


async function readCsv(filePath) {
    const content = await fs.readFile(
        filePath,
        "utf-8"
    );

    const rows = parse(content, {
        columns: true,
        skip_empty_lines: true,
        trim: true,
    });

    return rows.map((row) => {
        const convertedRow = {};

        for (const [key, value] of Object.entries(row)) {
            convertedRow[key] = convertCsvValue(value);
        }

        return convertedRow;
    });
}


async function getFileStatus(filePath) {
    try {
        const details = await fs.stat(filePath);

        return {
            available: true,
            size_bytes: details.size,
            last_modified: details.mtime.toISOString(),
        };
    } catch (error) {
        if (error.code === "ENOENT") {
            return {
                available: false,
                size_bytes: 0,
                last_modified: null,
            };
        }

        throw error;
    }
}


function parseLimit(value, defaultValue, maximum) {
    if (value === undefined) {
        return defaultValue;
    }

    const parsedValue = Number.parseInt(value, 10);

    if (
        Number.isNaN(parsedValue)
        || parsedValue < 1
    ) {
        return defaultValue;
    }

    return Math.min(parsedValue, maximum);
}
function buildHeatAlert(row) {
    const wardId = normalizeWardId(row.ward_id);
    const wardName = String(row.ward_name);
    const forecastDate = String(row.forecast_date);

    const riskIndex = Number(
        row.calibrated_mortality_risk_index
        ?? row.mortality_risk_index
        ?? 0
    );

    const riskLevel = String(
        row.calibrated_risk_level
        ?? row.risk_level
        ?? "Unknown"
    );

    const alertCode = String(
        row.calibrated_alert_code
        ?? row.alert_code
        ?? "ADVISORY"
    );

    const temperature = Number(
        row.temperature_max_c ?? 0
    );

    const wbgt = Number(
        row.wbgt_max_c ?? 0
    );

    const peakTime = String(
        row.peak_risk_time_ist ?? ""
    ).slice(11, 16);

    const recommendedAction = String(
        row.calibrated_recommended_action
        ?? row.recommended_action
        ?? "Follow the local heat action plan."
    );

    const shouldDispatch = Boolean(
        row.calibrated_sms_alert_required
        ?? row.sms_alert_required
        ?? false
    );

    const shortAdvice = riskLevel.toLowerCase() === "extreme"
        ? (
            "Avoid afternoon outdoor work, use cooling centres, "
            + "and check elderly residents."
        )
        : (
            "Stay hydrated and avoid strenuous afternoon activity."
        );

    return {
        ward: {
            ward_id: wardId,
            ward_name: wardName,
        },

        forecast: {
            date: forecastDate,
            peak_time_ist: peakTime || null,
            temperature_max_c: temperature,
            wbgt_max_c: wbgt,
        },

        risk: {
            index: riskIndex,
            level: riskLevel,
            alert_code: alertCode,
            evidence_relative_increase_pct: Number(
                row.evidence_relative_increase_pct ?? 0
            ),
        },

        should_dispatch: shouldDispatch,

        messages: {
            sms: (
                `DELHI HEAT ${alertCode}: ${wardName} `
                + `(Ward ${wardId}), ${forecastDate}. `
                + `Risk ${riskIndex.toFixed(1)}/100, `
                + `WBGT ${wbgt.toFixed(1)}C. `
                + shortAdvice
            ),

            whatsapp: (
                `Delhi Heat-Health Alert\n\n`
                + `Ward: ${wardName} (${wardId})\n`
                + `Date: ${forecastDate}\n`
                + `Alert: ${alertCode} - ${riskLevel}\n`
                + `Mortality Risk Index: ${riskIndex.toFixed(1)}/100\n`
                + `Maximum temperature: ${temperature.toFixed(1)}C\n`
                + `Maximum WBGT: ${wbgt.toFixed(1)}C\n`
                + `Peak risk time: ${peakTime || "Not available"} IST\n\n`
                + `Recommended action: ${recommendedAction}`
            ),
        },

        administrative_triggers: {
            open_cooling_centres: Boolean(
                row.calibrated_open_cooling_centres
                ?? row.open_cooling_centres
                ?? false
            ),

            shift_outdoor_work_hours: Boolean(
                row.calibrated_shift_outdoor_work_hours
                ?? row.shift_outdoor_work_hours
                ?? false
            ),

            hospital_surge_alert: Boolean(
                row.calibrated_hospital_surge_alert
                ?? row.hospital_surge_alert
                ?? false
            ),

            power_grid_readiness: riskIndex >= 75,
        },

        interpretation: (
            "Relative ward-level heat-health impact ranking; "
            + "not a predicted death count."
        ),
    };
}


async function findForecastRow(wardId, forecastDate) {
    const rows = await readCsv(FILES.forecast);

    return rows.find(
        (row) => (
            normalizeWardId(row.ward_id)
                === normalizeWardId(wardId)
            && String(row.forecast_date)
                === String(forecastDate)
        )
    );
}

// ---------------------------------------------------------
// API health and output status
// ---------------------------------------------------------

app.get(
    "/api/health",
    asyncHandler(async (request, response) => {
        const entries = await Promise.all(
            Object.entries(FILES).map(
                async ([name, filePath]) => {
                    const status = await getFileStatus(filePath);

                    return [
                        name,
                        {
                            ...status,
                            file: path.basename(filePath),
                        },
                    ];
                }
            )
        );

        const files = Object.fromEntries(entries);

        const ready = Object.values(files).every(
            (file) => file.available
        );

        response.status(ready ? 200 : 503).json({
            success: ready,
            service: "Delhi Heat-Health API",
            api_version: "1.0.0",
            status: ready ? "ready" : "incomplete",
            timestamp: new Date().toISOString(),
            files,
        });
    })
);


// ---------------------------------------------------------
// Mortality model information
// ---------------------------------------------------------

app.get(
    "/api/model",
    asyncHandler(async (request, response) => {
        const model = await readJson(FILES.model);

        response.json({
            success: true,
            data: model,
        });
    })
);


// ---------------------------------------------------------
// Combined summary
// ---------------------------------------------------------

app.get(
    "/api/summary",
    asyncHandler(async (request, response) => {
        const [
            mortalitySummary,
            mapSummary,
            backtestSummary,
        ] = await Promise.all([
            readJson(FILES.mortalitySummary),
            readJson(FILES.mapSummary),
            readJson(FILES.backtestSummary),
        ]);

        response.json({
            success: true,
            data: {
                current_forecast: mortalitySummary,
                geographic_summary: mapSummary,
                historical_validation: backtestSummary,
            },
        });
    })
);


// ---------------------------------------------------------
// Historical validation
// ---------------------------------------------------------

app.get(
    "/api/backtest",
    asyncHandler(async (request, response) => {
        const backtest = await readJson(
            FILES.backtestSummary
        );

        response.json({
            success: true,
            data: backtest,
        });
    })
);


// ---------------------------------------------------------
// Complete GIS map
// ---------------------------------------------------------

app.get(
    "/api/map",
    asyncHandler(async (request, response) => {
        const map = await readJson(FILES.map);

        response.set(
            "Cache-Control",
            "public, max-age=300"
        );

        response.json(map);
    })
);


// ---------------------------------------------------------
// Daily forecast for all Delhi wards
// ---------------------------------------------------------

app.get(
    "/api/forecast/daily",
    asyncHandler(async (request, response) => {
        const rows = await readCsv(FILES.forecast);

        const availableDates = [
            ...new Set(
                rows
                    .map((row) => String(row.forecast_date))
                    .filter(Boolean)
            ),
        ].sort();

        const requestedDate = request.query.date
            ? String(request.query.date).trim()
            : availableDates[0];

        if (!availableDates.includes(requestedDate)) {
            return response.status(400).json({
                success: false,
                error: {
                    code: "INVALID_FORECAST_DATE",
                    message: (
                        `No forecast is available for `
                        + `${requestedDate}.`
                    ),
                    available_dates: availableDates,
                },
            });
        }

        const riskLevel = request.query.risk_level
            ? String(request.query.risk_level).toLowerCase()
            : null;

        const search = request.query.search
            ? String(request.query.search).toLowerCase()
            : null;

        const limit = parseLimit(
            request.query.limit,
            500,
            500
        );

        let dailyForecast = rows.filter(
            (row) => (
                String(row.forecast_date) === requestedDate
            )
        );

        const wardsForDate = dailyForecast.length;

        if (riskLevel) {
            dailyForecast = dailyForecast.filter(
                (row) => (
                    String(
                        row.calibrated_risk_level
                        ?? row.risk_level
                        ?? ""
                    ).toLowerCase() === riskLevel
                )
            );
        }

        if (search) {
            dailyForecast = dailyForecast.filter((row) => {
                const wardName = String(
                    row.ward_name ?? ""
                ).toLowerCase();

                const wardId = normalizeWardId(
                    row.ward_id
                ).toLowerCase();

                return (
                    wardName.includes(search)
                    || wardId.includes(search)
                );
            });
        }

        dailyForecast.sort(
            (first, second) => (
                Number(
                    second.calibrated_mortality_risk_index
                    ?? second.mortality_risk_index
                    ?? 0
                )
                - Number(
                    first.calibrated_mortality_risk_index
                    ?? first.mortality_risk_index
                    ?? 0
                )
            )
        );

        const filteredTotal = dailyForecast.length;

        dailyForecast = dailyForecast.slice(0, limit);

        response.set(
            "Cache-Control",
            "public, max-age=60"
        );

        return response.json({
            success: true,
            metadata: {
                selected_date: requestedDate,
                available_dates: availableDates,
                wards_for_date: wardsForDate,
                filtered_total: filteredTotal,
                returned: dailyForecast.length,
                risk_level_filter: riskLevel,
                search,
            },
            data: dailyForecast,
        });
    })
);

// ---------------------------------------------------------
// Peak-risk ward list
// ---------------------------------------------------------

app.get(
    "/api/wards",
    asyncHandler(async (request, response) => {
        const map = await readJson(FILES.map);

        const riskLevel = request.query.risk_level
            ? String(request.query.risk_level).toLowerCase()
            : null;

        const search = request.query.search
            ? String(request.query.search).toLowerCase()
            : null;

        const limit = parseLimit(
            request.query.limit,
            290,
            500
        );

        let wards = map.features.map(
            (feature) => feature.properties
        );

        if (riskLevel) {
            wards = wards.filter(
                (ward) => (
                    String(ward.risk_level).toLowerCase()
                    === riskLevel
                )
            );
        }

        if (search) {
            wards = wards.filter((ward) => {
                const wardName = String(
                    ward.ward_name || ""
                ).toLowerCase();

                const wardId = normalizeWardId(
                    ward.ward_id
                ).toLowerCase();

                return (
                    wardName.includes(search)
                    || wardId.includes(search)
                );
            });
        }

        wards.sort(
            (first, second) => (
                Number(second.mortality_risk_index)
                - Number(first.mortality_risk_index)
            )
        );

        const total = wards.length;

        wards = wards.slice(0, limit);

        response.json({
            success: true,
            metadata: {
                total,
                returned: wards.length,
                risk_level_filter: riskLevel,
                search,
            },
            data: wards,
        });
    })
);


// ---------------------------------------------------------
// Five-day forecast for one ward
// ---------------------------------------------------------

app.get(
    "/api/wards/:wardId",
    asyncHandler(async (request, response) => {
        const requestedWardId = normalizeWardId(
            request.params.wardId
        );

        const rows = await readCsv(FILES.forecast);

        const forecast = rows
            .filter(
                (row) => (
                    normalizeWardId(row.ward_id)
                    === requestedWardId
                )
            )
            .sort(
                (first, second) => (
                    String(first.forecast_date).localeCompare(
                        String(second.forecast_date)
                    )
                )
            );

        if (forecast.length === 0) {
            return response.status(404).json({
                success: false,
                error: {
                    code: "WARD_NOT_FOUND",
                    message: (
                        `No forecast found for ward `
                        + `${requestedWardId}.`
                    ),
                },
            });
        }

        return response.json({
            success: true,
            data: {
                ward_id: requestedWardId,
                ward_name: forecast[0].ward_name,
                forecast_days: forecast.length,
                forecast,
            },
        });
    })
);


// ---------------------------------------------------------
// Highest-risk wards
// ---------------------------------------------------------

app.get(
    "/api/hotspots",
    asyncHandler(async (request, response) => {
        const limit = parseLimit(
            request.query.limit,
            10,
            100
        );

        const riskLevel = request.query.risk_level
            ? String(request.query.risk_level).toLowerCase()
            : null;

        let hotspots = await readCsv(FILES.hotspots);

        if (riskLevel) {
            hotspots = hotspots.filter(
                (ward) => (
                    String(
                        ward.calibrated_risk_level
                    ).toLowerCase() === riskLevel
                )
            );
        }

        hotspots.sort(
            (first, second) => (
                Number(
                    second.calibrated_mortality_risk_index
                )
                - Number(
                    first.calibrated_mortality_risk_index
                )
            )
        );

        const total = hotspots.length;

        hotspots = hotspots.slice(0, limit);

        response.json({
            success: true,
            metadata: {
                total,
                returned: hotspots.length,
                risk_level_filter: riskLevel,
            },
            data: hotspots,
        });
    })
);


// ---------------------------------------------------------
// Alert preview
// ---------------------------------------------------------

app.get(
    "/api/alerts/preview",
    asyncHandler(async (request, response) => {
        const wardId = request.query.ward_id;
        const forecastDate = request.query.date;

        if (!wardId || !forecastDate) {
            return response.status(400).json({
                success: false,
                error: {
                    code: "MISSING_ALERT_PARAMETERS",
                    message: (
                        "ward_id and date query parameters are required."
                    ),
                },
            });
        }

        const row = await findForecastRow(
            wardId,
            forecastDate
        );

        if (!row) {
            return response.status(404).json({
                success: false,
                error: {
                    code: "FORECAST_NOT_FOUND",
                    message: (
                        `No forecast exists for ward ${wardId} `
                        + `on ${forecastDate}.`
                    ),
                },
            });
        }

        return response.json({
            success: true,
            dispatch_mode: "simulation",
            data: buildHeatAlert(row),
        });
    })
);


// ---------------------------------------------------------
// Simulated alert dispatch
// ---------------------------------------------------------

app.post(
    "/api/alerts/dispatch",
    asyncHandler(async (request, response) => {
        const {
            ward_id: wardId,
            date: forecastDate,
            channels,
        } = request.body ?? {};

        if (!wardId || !forecastDate) {
            return response.status(400).json({
                success: false,
                error: {
                    code: "MISSING_ALERT_PARAMETERS",
                    message: "ward_id and date are required.",
                },
            });
        }

        const allowedChannels = new Set([
            "sms",
            "whatsapp",
            "administration",
        ]);

        const requestedChannels = Array.isArray(channels)
            && channels.length > 0
            ? channels.map(
                (channel) => String(channel).toLowerCase()
            )
            : [
                "sms",
                "whatsapp",
                "administration",
            ];

        const invalidChannel = requestedChannels.find(
            (channel) => !allowedChannels.has(channel)
        );

        if (invalidChannel) {
            return response.status(400).json({
                success: false,
                error: {
                    code: "INVALID_ALERT_CHANNEL",
                    message: (
                        `Unsupported alert channel: `
                        + `${invalidChannel}.`
                    ),
                },
            });
        }

        const row = await findForecastRow(
            wardId,
            forecastDate
        );

        if (!row) {
            return response.status(404).json({
                success: false,
                error: {
                    code: "FORECAST_NOT_FOUND",
                    message: (
                        `No forecast exists for ward ${wardId} `
                        + `on ${forecastDate}.`
                    ),
                },
            });
        }

        const alert = buildHeatAlert(row);
        const createdAt = new Date().toISOString();

        const dispatchRecord = {
            dispatch_id: (
                `SIM-${Date.now()}-`
                + `${normalizeWardId(wardId)}`
            ),

            mode: "simulation",

            status: alert.should_dispatch
                ? "simulated"
                : "not_required",

            created_at_utc: createdAt,

            requested_channels: requestedChannels,

            delivery_results: requestedChannels.map(
                (channel) => ({
                    channel,
                    status: alert.should_dispatch
                        ? "simulated_success"
                        : "not_required",
                })
            ),

            alert,
        };

        await fs.appendFile(
            ALERT_LOG_FILE,
            `${JSON.stringify(dispatchRecord)}\n`,
            "utf-8"
        );

        return response.status(202).json({
            success: true,
            message: (
                "Alert simulation completed. "
                + "No real messages were sent."
            ),
            data: dispatchRecord,
        });
    })
);

// ---------------------------------------------------------
// Root endpoint
// ---------------------------------------------------------

app.get("/", (request, response) => {
    response.json({
        service: "Delhi Heat-Health Early Warning API",
        api_version: "1.0.0",
        documentation: {
            health: "/api/health",
            model: "/api/model",
            summary: "/api/summary",
            backtest: "/api/backtest",
            map: "/api/map",
            daily_forecast: "/api/forecast/daily?date=YYYY-MM-DD",
            wards: "/api/wards",
            ward_forecast: "/api/wards/:wardId",
            hotspots: "/api/hotspots?limit=10",
            alert_preview: "/api/alerts/preview?ward_id=236&date=2026-08-28",
            alert_dispatch: "POST /api/alerts/dispatch",
        },
    });
});


app.use((request, response) => {
    response.status(404).json({
        success: false,
        error: {
            code: "ENDPOINT_NOT_FOUND",
            message: (
                `No API endpoint exists at `
                + `${request.method} ${request.originalUrl}.`
            ),
        },
    });
});


app.use((error, request, response, next) => {
    console.error(error);

    const isMissingFile = error.code === "ENOENT";

    response
        .status(isMissingFile ? 503 : 500)
        .json({
            success: false,
            error: {
                code: isMissingFile
                    ? "MODEL_OUTPUT_NOT_READY"
                    : "INTERNAL_SERVER_ERROR",
                message: isMissingFile
                    ? "A required model output file is unavailable."
                    : "The server could not complete the request.",
                details:
                    process.env.NODE_ENV === "development"
                        ? error.message
                        : undefined,
            },
        });
});


app.listen(PORT, () => {
    console.log(
        `Delhi Heat-Health API running at `
        + `http://localhost:${PORT}`
    );

    console.log(
        `Project root: ${PROJECT_ROOT}`
    );
});
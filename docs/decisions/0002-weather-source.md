# 2. Weather source

Date: 2026-08-22

## Status

Accepted.

## Context

The Pi needs current conditions, hourly forecast, and today's high/low for
the right-half pane. Constraints on the data source:

- No per-month fee and no signup wall (project is fully open source;
  secrets must stay out of the repo).
- Hourly granularity.
- Permissive display/redistribution terms.
- Perth (Australia/Perth) is the default location; the config must allow
  other lat/lon + timezone pairs.

## Decision

Use the **Open-Meteo HTTPS JSON API** at
`https://api.open-meteo.com/v1/forecast`:

- `current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m`
  → refreshed once per hour.
- `daily=weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset`
  → refreshed once per day at first boot and once at ~06:00 local.
- Latitude/longitude/timezone stored in
  `/etc/kitchen-clock/config.toml`; default Perth.

No API key, no account, no client library. A short attribution line
("Weather by Open-Meteo.com, CC BY 4.0") is shown in an about / details
pane on the UI.

## Consequences

- Zero secrets in the repo and on the SD card image.
- Open-Meteo's free tier is unmetered for personal use.
- AGPL on the server side is not triggered since we only consume the JSON
  over HTTPS in our own client.
- An outage of `api.open-meteo.com` does not crash the clock; the last
  fetched values are shown until the next successful fetch.
- Single weather provider modelled. A fallback provider, if needed later,
  will be its own ADR.

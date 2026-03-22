# ServiceM8 Business Dashboard for Home Assistant

A friendly custom Home Assistant integration that connects to the ServiceM8 REST API in **read-only** mode using a private API key and creates a wide set of business dashboard sensors.

## What it gives you

- Revenue sensors
- Job flow and workload sensors
- Quote conversion sensors
- Payment and receivables sensors
- Time-logging and productivity sensors
- Customer growth and repeat-customer sensors
- Scheduling and capacity sensors
- Per-staff performance sensors
- Long-term monthly trend sensors
- Alert-style binary sensors

## Highlights

- Uses your **ServiceM8 private API key** via the `X-API-Key` header.
- Talks to the ServiceM8 REST API resources directly.
- Treats ServiceM8 UI naming properly: customer/client is `Company`, and scheduled bookings / recorded time are represented via `JobActivity`.
- Handles cursor-based pagination.
- Produces dashboard-friendly sensors rather than mirroring raw objects.

## Installation

### Manual install

1. Copy `custom_components/servicem8_business_dashboard` into your Home Assistant `custom_components` folder.
2. Restart Home Assistant.
3. Go to **Settings → Devices & Services → Add Integration**.
4. Search for **ServiceM8 Business Dashboard**.
5. Enter your API key.

### Folder structure after install

```text
config/
  custom_components/
    servicem8_business_dashboard/
      __init__.py
      api.py
      binary_sensor.py
      config_flow.py
      const.py
      coordinator.py
      manifest.json
      sensor.py
      strings.json
```

## Recommended ServiceM8 setup

Create a private API key in ServiceM8 and keep this integration read-only. Polling every 10 to 30 minutes is sensible for dashboard use.

## Main sensor groups

### Revenue
- `sensor.servicem8_dashboard_revenue_today`
- `sensor.servicem8_dashboard_revenue_this_week`
- `sensor.servicem8_dashboard_revenue_this_month`
- `sensor.servicem8_dashboard_revenue_rolling_30d`
- `sensor.servicem8_dashboard_revenue_3m_moving_average`
- `sensor.servicem8_dashboard_revenue_12m_moving_average`

### Jobs
- `sensor.servicem8_dashboard_jobs_created_today`
- `sensor.servicem8_dashboard_jobs_completed_today`
- `sensor.servicem8_dashboard_jobs_open_now`
- `sensor.servicem8_dashboard_jobs_overdue_now`
- `sensor.servicem8_dashboard_jobs_unscheduled_now`
- `sensor.servicem8_dashboard_job_completion_rate_30d`

### Sales
- `sensor.servicem8_dashboard_quotes_open_now`
- `sensor.servicem8_dashboard_quotes_open_value_now`
- `sensor.servicem8_dashboard_quotes_created_last_30d`
- `sensor.servicem8_dashboard_quotes_accepted_last_30d`
- `sensor.servicem8_dashboard_quote_conversion_rate_30d`

### Time and productivity
- `sensor.servicem8_dashboard_time_logged_today_hours`
- `sensor.servicem8_dashboard_time_logged_this_week_hours`
- `sensor.servicem8_dashboard_time_logged_rolling_30d_hours`
- `sensor.servicem8_dashboard_average_hours_per_job_30d`
- `sensor.servicem8_dashboard_revenue_per_logged_hour_30d`

### Customers
- `sensor.servicem8_dashboard_customers_total`
- `sensor.servicem8_dashboard_customers_new_rolling_30d`
- `sensor.servicem8_dashboard_customers_active_90d`
- `sensor.servicem8_dashboard_repeat_customer_rate_365d`

### Alerts
- `binary_sensor.servicem8_dashboard_jobs_overdue_present`
- `binary_sensor.servicem8_dashboard_invoices_overdue_present`
- `binary_sensor.servicem8_dashboard_schedule_over_capacity_today`
- `binary_sensor.servicem8_dashboard_backlog_above_threshold`

## Notes on data quality

This integration uses sensible fall-backs because ServiceM8 tenants can differ in how they populate fields. A few sensors therefore depend on the account’s actual data quality:

- payment-derived revenue is strongest when job payments are recorded consistently
- customer and staff analytics improve when jobs are linked cleanly
- some invoice-style sensors are inferred from job totals, balances and due dates

## Options

You can turn these groups on or off in the integration options:

- Per-staff sensors
- Monthly history sensors
- Alert binary sensors
- Customer sensors
- Scheduling sensors
- Refresh interval
- Number of monthly history sensors

## Lovelace example

See `examples/lovelace_dashboard.yaml`.

## Caveats

This repo is designed to be practical and friendly, not to claim perfect knowledge of every possible ServiceM8 field variant. The coordinator is intentionally defensive and tolerant of missing fields.

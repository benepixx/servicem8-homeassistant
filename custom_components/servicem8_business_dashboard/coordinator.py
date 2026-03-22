"""Data coordinator and analytics engine for ServiceM8."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
import logging
from statistics import mean, median
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import slugify

from .api import ServiceM8ApiClient, ServiceM8ApiError, ServiceM8AuthError
from .const import (
    ATTR_AVAILABLE_DATA,
    ATTR_CURRENCY,
    ATTR_FORMULA,
    ATTR_GENERATED_FROM,
    ATTR_LAST_SUCCESSFUL_UPDATE,
    ATTR_NOTE,
    ATTR_PERIOD_END,
    ATTR_PERIOD_START,
    ATTR_SOURCE_RECORD_COUNTS,
    CONF_INCLUDE_ALERTS,
    CONF_INCLUDE_CUSTOMERS,
    CONF_INCLUDE_HISTORY,
    CONF_INCLUDE_SCHEDULE,
    CONF_INCLUDE_STAFF,
    CONF_TREND_MONTHS,
    KNOWN_JOB_STATUSES,
    STATUS_COMPLETED,
    STATUS_QUOTE,
    STATUS_UNSUCCESSFUL,
    STATUS_WORK_ORDER,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class SensorDef:
    key: str
    name: str
    value: Any
    unit: str | None = None
    icon: str | None = None
    device_class: str | None = None
    state_class: str | None = None
    suggested_display_precision: int | None = None
    attributes: dict[str, Any] | None = None
    entity_category: str | None = None


@dataclass(slots=True)
class BinarySensorDef:
    key: str
    name: str
    value: bool
    icon: str | None = None
    attributes: dict[str, Any] | None = None


class ServiceM8DashboardCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch and aggregate ServiceM8 data for sensors."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: ServiceM8ApiClient,
        entry: ConfigEntry,
        *,
        update_interval: timedelta,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="ServiceM8 Business Dashboard",
            update_interval=update_interval,
        )
        self.api = api
        self.entry = entry

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            jobs = await self.api.async_get_resource("job")
            companies = await self.api.async_get_resource("company")
            job_activities = await self.api.async_get_resource("jobactivity")
            job_payments = await self.api.async_get_resource("jobpayment")
            try:
                staff = await self.api.async_get_resource("staff")
            except ServiceM8ApiError:
                staff = []
        except ServiceM8AuthError as err:
            raise UpdateFailed(f"Authentication failed: {err}") from err
        except ServiceM8ApiError as err:
            raise UpdateFailed(str(err)) from err

        return build_dashboard_dataset(
            jobs=jobs,
            companies=companies,
            job_activities=job_activities,
            job_payments=job_payments,
            staff=staff,
            options={**self.entry.data, **self.entry.options},
        )


def build_dashboard_dataset(
    *,
    jobs: list[dict[str, Any]],
    companies: list[dict[str, Any]],
    job_activities: list[dict[str, Any]],
    job_payments: list[dict[str, Any]],
    staff: list[dict[str, Any]],
    options: dict[str, Any],
) -> dict[str, Any]:
    now = datetime.now(UTC)
    today = now.date()
    current_month_start = today.replace(day=1)
    current_week_start = today - timedelta(days=today.weekday())
    last_month_end = current_month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    trend_months = int(options.get(CONF_TREND_MONTHS, 12))

    jobs_n = [_normalise_job(job) for job in jobs]
    companies_n = [_normalise_company(company) for company in companies]
    activities_n = [_normalise_activity(activity) for activity in job_activities]
    payments_n = [_normalise_payment(payment) for payment in job_payments]
    staff_n = [_normalise_staff(member) for member in staff]

    currency = _guess_currency(jobs_n, payments_n)

    sensors: list[SensorDef] = []
    binary_sensors: list[BinarySensorDef] = []

    def add_sensor(sensor: SensorDef) -> None:
        base_attr = {
            ATTR_LAST_SUCCESSFUL_UPDATE: now.isoformat(),
            ATTR_SOURCE_RECORD_COUNTS: {
                "jobs": len(jobs_n),
                "companies": len(companies_n),
                "job_activities": len(activities_n),
                "job_payments": len(payments_n),
                "staff": len(staff_n),
            },
            ATTR_AVAILABLE_DATA: {
                "job_statuses": sorted({j["status"] for j in jobs_n if j["status"]}),
            },
            ATTR_CURRENCY: currency,
        }
        if sensor.attributes:
            base_attr.update(sensor.attributes)
        sensor.attributes = base_attr
        sensors.append(sensor)

    def add_binary(sensor: BinarySensorDef) -> None:
        base_attr = {
            ATTR_LAST_SUCCESSFUL_UPDATE: now.isoformat(),
            ATTR_SOURCE_RECORD_COUNTS: {
                "jobs": len(jobs_n),
                "companies": len(companies_n),
                "job_activities": len(activities_n),
                "job_payments": len(payments_n),
                "staff": len(staff_n),
            },
        }
        if sensor.attributes:
            base_attr.update(sensor.attributes)
        sensor.attributes = base_attr
        binary_sensors.append(sensor)

    def money_sensor(key: str, name: str, value: float | int, **kwargs: Any) -> None:
        add_sensor(
            SensorDef(
                key=key,
                name=name,
                value=round(float(value), 2),
                unit=currency,
                device_class="monetary",
                state_class="measurement",
                suggested_display_precision=2,
                **kwargs,
            )
        )

    def count_sensor(key: str, name: str, value: int, **kwargs: Any) -> None:
        add_sensor(
            SensorDef(
                key=key,
                name=name,
                value=int(value),
                state_class="measurement",
                **kwargs,
            )
        )

    def percent_sensor(key: str, name: str, value: float, **kwargs: Any) -> None:
        add_sensor(
            SensorDef(
                key=key,
                name=name,
                value=round(value, 2),
                unit="%",
                state_class="measurement",
                suggested_display_precision=2,
                **kwargs,
            )
        )

    def hour_sensor(key: str, name: str, value: float, **kwargs: Any) -> None:
        add_sensor(
            SensorDef(
                key=key,
                name=name,
                value=round(value, 2),
                unit="h",
                state_class="measurement",
                suggested_display_precision=2,
                **kwargs,
            )
        )

    def day_sensor(key: str, name: str, value: float, **kwargs: Any) -> None:
        add_sensor(
            SensorDef(
                key=key,
                name=name,
                value=round(value, 2),
                unit="d",
                state_class="measurement",
                suggested_display_precision=2,
                **kwargs,
            )
        )

    def generic_sensor(key: str, name: str, value: Any, **kwargs: Any) -> None:
        add_sensor(SensorDef(key=key, name=name, value=value, **kwargs))

    def jobs_created_between(start: date, end: date) -> list[dict[str, Any]]:
        return [j for j in jobs_n if j["created_date"] and start <= j["created_date"] <= end]

    def jobs_completed_between(start: date, end: date) -> list[dict[str, Any]]:
        return [j for j in jobs_n if j["completed_date"] and start <= j["completed_date"] <= end]

    def jobs_with_status(status: str) -> list[dict[str, Any]]:
        return [j for j in jobs_n if j["status"] == status and j["active"]]

    def sum_job_value(items: list[dict[str, Any]]) -> float:
        return round(sum(j["value"] for j in items), 2)

    def payments_between(start: date, end: date) -> list[dict[str, Any]]:
        return [p for p in payments_n if p["payment_date"] and start <= p["payment_date"] <= end]

    def payment_value(items: list[dict[str, Any]]) -> float:
        return round(sum(p["amount"] for p in items), 2)

    def date_range(days: int) -> tuple[date, date]:
        return today - timedelta(days=days - 1), today

    revenue_today = payment_value(payments_between(today, today))
    revenue_week = payment_value(payments_between(current_week_start, today))
    revenue_month = payment_value(payments_between(current_month_start, today))
    revenue_last_month = payment_value(payments_between(last_month_start, last_month_end))

    money_sensor("revenue_today", "Revenue Today", revenue_today)
    money_sensor("revenue_this_week", "Revenue This Week", revenue_week)
    money_sensor("revenue_this_month", "Revenue This Month", revenue_month)
    money_sensor("revenue_last_month", "Revenue Last Month", revenue_last_month)

    for days in (7, 14, 30, 60, 90, 180, 365):
        start, end = date_range(days)
        money_sensor(
            f"revenue_rolling_{days}d",
            f"Revenue Rolling {days}d",
            payment_value(payments_between(start, end)),
            attributes={ATTR_PERIOD_START: start.isoformat(), ATTR_PERIOD_END: end.isoformat()},
        )

    created_today = jobs_created_between(today, today)
    completed_today = jobs_completed_between(today, today)
    count_sensor("jobs_created_today", "Jobs Created Today", len(created_today))
    count_sensor("jobs_completed_today", "Jobs Completed Today", len(completed_today))
    count_sensor("jobs_open_now", "Jobs Open Now", len([j for j in jobs_n if j["active"] and j["status"] != STATUS_COMPLETED]))
    count_sensor("jobs_overdue_now", "Jobs Overdue Now", len([j for j in jobs_n if j["is_overdue"]]))
    count_sensor("jobs_unscheduled_now", "Jobs Unscheduled Now", len([j for j in jobs_n if j["active"] and not j["scheduled_date"] and j["status"] == STATUS_WORK_ORDER]))
    count_sensor("jobs_unassigned_now", "Jobs Unassigned Now", len([j for j in jobs_n if j["active"] and not j["assigned_staff_uuids"]]))
    count_sensor("quotes_open_now", "Quotes Open Now", len(jobs_with_status(STATUS_QUOTE)))
    money_sensor("quotes_open_value_now", "Quotes Open Value Now", sum_job_value(jobs_with_status(STATUS_QUOTE)))
    count_sensor("jobs_completed_not_invoiced_now", "Jobs Completed Not Invoiced Now", len([j for j in jobs_n if j["status"] == STATUS_COMPLETED and not j["is_paid"]]))

    for days in (7, 14, 30, 60, 90, 365):
        start, end = date_range(days)
        created = jobs_created_between(start, end)
        completed = jobs_completed_between(start, end)
        count_sensor(f"jobs_created_last_{days}d", f"Jobs Created Last {days}d", len(created))
        count_sensor(f"jobs_completed_last_{days}d", f"Jobs Completed Last {days}d", len(completed))
        money_sensor(f"job_value_completed_last_{days}d", f"Job Value Completed Last {days}d", sum_job_value(completed))
        if created:
            percent_sensor(
                f"job_completion_rate_{days}d",
                f"Job Completion Rate {days}d",
                (len(completed) / len(created)) * 100,
                attributes={ATTR_FORMULA: "completed_jobs / created_jobs * 100"},
            )
        else:
            percent_sensor(f"job_completion_rate_{days}d", f"Job Completion Rate {days}d", 0.0)

    status_counts = Counter(j["status"] for j in jobs_n if j["active"])
    for status in KNOWN_JOB_STATUSES:
        count_sensor(
            f"jobs_status_{slugify(status)}_now",
            f"Jobs Status {status} Now",
            status_counts.get(status, 0),
        )

    for days in (7, 30, 90):
        start, end = date_range(days)
        created = jobs_created_between(start, end)
        by_status = Counter(j["status"] for j in created)
        for status in KNOWN_JOB_STATUSES:
            count_sensor(
                f"jobs_status_{slugify(status)}_created_{days}d",
                f"Jobs Status {status} Created {days}d",
                by_status.get(status, 0),
            )

    quote_created_30 = [j for j in jobs_created_between(*date_range(30)) if j["status"] == STATUS_QUOTE]
    accepted_30 = [j for j in jobs_n if j["quote_to_work_order_date"] and date_range(30)[0] <= j["quote_to_work_order_date"] <= today]
    count_sensor("quotes_created_last_30d", "Quotes Created Last 30d", len(quote_created_30))
    count_sensor("quotes_accepted_last_30d", "Quotes Accepted Last 30d", len(accepted_30))
    money_sensor("quotes_created_value_last_30d", "Quotes Created Value Last 30d", sum_job_value(quote_created_30))
    money_sensor("quotes_accepted_value_last_30d", "Quotes Accepted Value Last 30d", sum_job_value(accepted_30))
    percent_sensor(
        "quote_conversion_rate_30d",
        "Quote Conversion Rate 30d",
        (len(accepted_30) / len(quote_created_30) * 100) if quote_created_30 else 0.0,
        attributes={ATTR_FORMULA: "accepted_quotes / created_quotes * 100"},
    )

    outstanding = [j for j in jobs_n if j["value"] > 0 and not j["is_paid"] and j["active"]]
    overdue_unpaid = [j for j in outstanding if j["is_overdue"]]
    count_sensor("outstanding_invoices_count", "Outstanding Invoices Count", len(outstanding))
    money_sensor("outstanding_invoices_value", "Outstanding Invoices Value", sum_job_value(outstanding))
    count_sensor("overdue_invoices_count", "Overdue Invoices Count", len(overdue_unpaid))
    money_sensor("overdue_invoices_value", "Overdue Invoices Value", sum_job_value(overdue_unpaid))

    if payments_n:
        days_to_payment = [p["days_from_job_to_payment"] for p in payments_n if p["days_from_job_to_payment"] is not None]
        if days_to_payment:
            day_sensor("average_days_to_payment_90d", "Average Days to Payment 90d", mean(days_to_payment))
            day_sensor("median_days_to_payment_90d", "Median Days to Payment 90d", median(days_to_payment))

    hours_logged_today = sum(a["hours"] for a in activities_n if a["activity_date"] == today and not a["was_scheduled"])
    hours_logged_week = sum(a["hours"] for a in activities_n if a["activity_date"] and current_week_start <= a["activity_date"] <= today and not a["was_scheduled"])
    hours_logged_month = sum(a["hours"] for a in activities_n if a["activity_date"] and current_month_start <= a["activity_date"] <= today and not a["was_scheduled"])
    hour_sensor("time_logged_today_hours", "Time Logged Today Hours", hours_logged_today)
    hour_sensor("time_logged_this_week_hours", "Time Logged This Week Hours", hours_logged_week)
    hour_sensor("time_logged_this_month_hours", "Time Logged This Month Hours", hours_logged_month)

    for days in (30, 90, 365):
        start, end = date_range(days)
        logged_hours = sum(a["hours"] for a in activities_n if a["activity_date"] and start <= a["activity_date"] <= end and not a["was_scheduled"])
        hour_sensor(f"time_logged_rolling_{days}d_hours", f"Time Logged Rolling {days}d Hours", logged_hours)
        completed = jobs_completed_between(start, end)
        hour_sensor(
            f"average_hours_per_job_{days}d",
            f"Average Hours per Job {days}d",
            logged_hours / len(completed) if completed else 0.0,
            attributes={ATTR_FORMULA: "logged_hours / completed_jobs"},
        )
        revenue = payment_value(payments_between(start, end))
        money_sensor(
            f"revenue_per_logged_hour_{days}d",
            f"Revenue per Logged Hour {days}d",
            revenue / logged_hours if logged_hours else 0.0,
            attributes={ATTR_FORMULA: "payments_received / logged_hours"},
        )

    if options.get(CONF_INCLUDE_CUSTOMERS, True):
        count_sensor("customers_total", "Customers Total", len(companies_n))
        for days in (30, 90, 365):
            start, end = date_range(days)
            new_customers = [c for c in companies_n if c["created_date"] and start <= c["created_date"] <= end]
            count_sensor(f"customers_new_rolling_{days}d", f"Customers New Rolling {days}d", len(new_customers))
            active_customers = {
                j["company_uuid"]
                for j in jobs_n
                if j["company_uuid"] and ((j["created_date"] and start <= j["created_date"] <= end) or (j["completed_date"] and start <= j["completed_date"] <= end))
            }
            count_sensor(f"customers_active_{days}d", f"Customers Active {days}d", len(active_customers))
            repeat_customers = sum(1 for company_uuid in active_customers if sum(1 for j in jobs_n if j["company_uuid"] == company_uuid and ((j["created_date"] and start <= j["created_date"] <= end) or (j["completed_date"] and start <= j["completed_date"] <= end))) > 1)
            count_sensor(f"customers_repeat_{days}d", f"Customers Repeat {days}d", repeat_customers)
            percent_sensor(
                f"repeat_customer_rate_{days}d",
                f"Repeat Customer Rate {days}d",
                (repeat_customers / len(active_customers) * 100) if active_customers else 0.0,
            )

    if options.get(CONF_INCLUDE_SCHEDULE, True):
        bookings_today = [a for a in activities_n if a["was_scheduled"] and a["activity_date"] == today]
        bookings_next_7d = [a for a in activities_n if a["was_scheduled"] and a["activity_date"] and today <= a["activity_date"] <= today + timedelta(days=6)]
        count_sensor("bookings_today", "Bookings Today", len(bookings_today))
        count_sensor("bookings_next_7d", "Bookings Next 7d", len(bookings_next_7d))
        count_sensor("jobs_scheduled_today", "Jobs Scheduled Today", len({a['job_uuid'] for a in bookings_today if a['job_uuid']}))
        count_sensor("jobs_scheduled_next_7d", "Jobs Scheduled Next 7d", len({a['job_uuid'] for a in bookings_next_7d if a['job_uuid']}))
        staff_count = max(len([s for s in staff_n if s["active"]]), 1)
        percent_sensor("schedule_utilisation_today", "Schedule Utilisation Today", min(100.0, len(bookings_today) / staff_count * 100))
        percent_sensor("schedule_utilisation_next_7d", "Schedule Utilisation Next 7d", min(100.0, len(bookings_next_7d) / (staff_count * 7) * 100))
        future_dates = sorted({a["activity_date"] for a in activities_n if a["was_scheduled"] and a["activity_date"] and a["activity_date"] >= today})
        generic_sensor("days_of_work_scheduled_ahead", "Days of Work Scheduled Ahead", (future_dates[-1] - today).days if future_dates else 0)

    completed_with_cycle = [j for j in jobs_n if j["created_datetime"] and j["completed_datetime"]]
    if completed_with_cycle:
        cycle_hours = [(j["completed_datetime"] - j["created_datetime"]).total_seconds() / 3600 for j in completed_with_cycle]
        hour_sensor("average_time_job_created_to_completed_hours_30d", "Average Time Job Created to Completed Hours 30d", mean(cycle_hours[-min(len(cycle_hours), 30):]))
        hour_sensor("median_time_job_created_to_completed_hours_90d", "Median Time Job Created to Completed Hours 90d", median(cycle_hours[-min(len(cycle_hours), 90):]))

    if options.get(CONF_INCLUDE_STAFF, True):
        staff_by_uuid = {s["uuid"]: s for s in staff_n if s["uuid"]}
        if not staff_by_uuid:
            all_staff_ids = sorted({sid for j in jobs_n for sid in j["assigned_staff_uuids"] if sid})
            staff_by_uuid = {sid: {"uuid": sid, "name": sid[:8], "active": True} for sid in all_staff_ids}
        staff_performance: list[tuple[str, float, int]] = []
        for staff_uuid, member in staff_by_uuid.items():
            name_slug = slugify(member["name"] or staff_uuid)
            assigned_now = [j for j in jobs_n if staff_uuid in j["assigned_staff_uuids"] and j["active"]]
            completed_30 = [j for j in jobs_n if staff_uuid in j["assigned_staff_uuids"] and j["completed_date"] and date_range(30)[0] <= j["completed_date"] <= today]
            logged_30 = sum(a["hours"] for a in activities_n if a["staff_uuid"] == staff_uuid and a["activity_date"] and date_range(30)[0] <= a["activity_date"] <= today and not a["was_scheduled"])
            revenue_30 = sum_job_value(completed_30)
            count_sensor(f"staff_{name_slug}_jobs_assigned_now", f"Staff {member['name']} Jobs Assigned Now", len(assigned_now))
            count_sensor(f"staff_{name_slug}_jobs_completed_30d", f"Staff {member['name']} Jobs Completed 30d", len(completed_30))
            hour_sensor(f"staff_{name_slug}_hours_logged_30d", f"Staff {member['name']} Hours Logged 30d", logged_30)
            money_sensor(f"staff_{name_slug}_revenue_completed_30d", f"Staff {member['name']} Revenue Completed 30d", revenue_30)
            money_sensor(f"staff_{name_slug}_revenue_per_hour_30d", f"Staff {member['name']} Revenue per Hour 30d", revenue_30 / logged_30 if logged_30 else 0.0)
            staff_performance.append((member["name"], revenue_30, len(completed_30)))
        if staff_performance:
            top_revenue = max(staff_performance, key=lambda item: item[1])
            top_jobs = max(staff_performance, key=lambda item: item[2])
            generic_sensor("top_staff_by_revenue_30d", "Top Staff by Revenue 30d", top_revenue[0])
            generic_sensor("top_staff_by_jobs_completed_30d", "Top Staff by Jobs Completed 30d", top_jobs[0])

    if options.get(CONF_INCLUDE_HISTORY, True):
        monthly_revenue: list[tuple[str, float]] = []
        monthly_jobs: list[tuple[str, int]] = []
        monthly_quotes: list[tuple[str, int]] = []
        for index in range(1, trend_months + 1):
            month_end = current_month_start - timedelta(days=1)
            for _ in range(index - 1):
                month_end = month_end.replace(day=1) - timedelta(days=1)
            month_start = month_end.replace(day=1)
            label = month_start.strftime("%Y-%m")
            revenue = payment_value(payments_between(month_start, month_end))
            jobs_completed = len(jobs_completed_between(month_start, month_end))
            quotes_created = len([j for j in jobs_created_between(month_start, month_end) if j["status"] == STATUS_QUOTE])
            monthly_revenue.append((label, revenue))
            monthly_jobs.append((label, jobs_completed))
            monthly_quotes.append((label, quotes_created))
            money_sensor(f"revenue_{index}m_ago", f"Revenue {index}m Ago", revenue, attributes={ATTR_NOTE: label})
            count_sensor(f"jobs_completed_{index}m_ago", f"Jobs Completed {index}m Ago", jobs_completed, attributes={ATTR_NOTE: label})
            count_sensor(f"quotes_created_{index}m_ago", f"Quotes Created {index}m Ago", quotes_created, attributes={ATTR_NOTE: label})

        if monthly_revenue:
            revenue_values = [item[1] for item in monthly_revenue]
            count_values = [item[1] for item in monthly_jobs]
            money_sensor("revenue_3m_moving_average", "Revenue 3m Moving Average", mean(revenue_values[: min(3, len(revenue_values))]))
            money_sensor("revenue_12m_moving_average", "Revenue 12m Moving Average", mean(revenue_values[: min(12, len(revenue_values))]))
            add_sensor(
                SensorDef(
                    key="revenue_history_json",
                    name="Revenue History JSON",
                    value=str({k: v for k, v in monthly_revenue}),
                    icon="mdi:chart-line",
                    attributes={ATTR_GENERATED_FROM: "payments by calendar month"},
                )
            )
            add_sensor(
                SensorDef(
                    key="jobs_completed_history_json",
                    name="Jobs Completed History JSON",
                    value=str({k: v for k, v in monthly_jobs}),
                    icon="mdi:briefcase-check",
                    attributes={ATTR_GENERATED_FROM: "completed jobs by calendar month"},
                )
            )
            add_sensor(
                SensorDef(
                    key="quotes_created_history_json",
                    name="Quotes Created History JSON",
                    value=str({k: v for k, v in monthly_quotes}),
                    icon="mdi:tag-multiple",
                    attributes={ATTR_GENERATED_FROM: "quote jobs created by calendar month"},
                )
            )
            if len(count_values) >= 3:
                add_sensor(
                    SensorDef(
                        key="jobs_completed_3m_moving_average",
                        name="Jobs Completed 3m Moving Average",
                        value=round(mean(count_values[:3]), 2),
                        state_class="measurement",
                    )
                )

    if options.get(CONF_INCLUDE_ALERTS, True):
        add_binary(BinarySensorDef("jobs_overdue_present", "Jobs Overdue Present", any(j["is_overdue"] for j in jobs_n), icon="mdi:alert"))
        add_binary(BinarySensorDef("invoices_overdue_present", "Invoices Overdue Present", any(j["is_overdue"] and not j["is_paid"] for j in jobs_n), icon="mdi:cash-alert"))
        add_binary(BinarySensorDef("schedule_over_capacity_today", "Schedule Over Capacity Today", len([a for a in activities_n if a['was_scheduled'] and a['activity_date'] == today]) > max(len(staff_n), 1), icon="mdi:calendar-alert"))
        add_binary(BinarySensorDef("backlog_above_threshold", "Backlog Above Threshold", len([j for j in jobs_n if j['active'] and j['status'] == STATUS_WORK_ORDER]) > 50, icon="mdi:clipboard-alert"))

    return {
        "sensors": sensors,
        "binary_sensors": binary_sensors,
        "meta": {
            "currency": currency,
            "record_counts": {
                "jobs": len(jobs_n),
                "companies": len(companies_n),
                "job_activities": len(activities_n),
                "job_payments": len(payments_n),
                "staff": len(staff_n),
            },
        },
    }


def _normalise_job(raw: dict[str, Any]) -> dict[str, Any]:
    status = _first_present(raw, ["status", "job_status"], default="")
    created_dt = _parse_datetime(_first_present(raw, ["create_date", "created_at", "date_created", "timestamp"]))
    completed_dt = _parse_datetime(_first_present(raw, ["completion_date", "completed_at", "date_completed", "done_date"]))
    scheduled_dt = _parse_datetime(_first_present(raw, ["scheduled_date", "start_date", "booking_start", "job_date"]))
    quote_to_work_order_dt = _parse_datetime(_first_present(raw, ["quote_converted_date", "quote_accepted_date", "work_order_date"]))
    value = _to_float(_first_present(raw, ["total_job_price", "total", "invoice_total", "job_total", "quote_total", "amount", "value"], default=0.0))
    balance = _to_float(_first_present(raw, ["balance_due", "outstanding_balance", "amount_due"], default=value))
    due_dt = _parse_datetime(_first_present(raw, ["payment_due_date", "invoice_due_date", "due_date"]))
    paid_total = _to_float(_first_present(raw, ["total_paid", "amount_paid", "paid_total"], default=0.0))
    assigned = _extract_staff_uuids(raw)
    return {
        "uuid": raw.get("uuid"),
        "company_uuid": _first_present(raw, ["company_uuid", "client_uuid", "customer_uuid"]),
        "status": status,
        "active": bool(raw.get("active", True)),
        "created_datetime": created_dt,
        "created_date": created_dt.date() if created_dt else None,
        "completed_datetime": completed_dt,
        "completed_date": completed_dt.date() if completed_dt else None,
        "scheduled_date": scheduled_dt.date() if scheduled_dt else None,
        "quote_to_work_order_date": quote_to_work_order_dt.date() if quote_to_work_order_dt else None,
        "value": value,
        "balance": max(balance, 0.0),
        "paid_total": paid_total,
        "is_paid": paid_total >= value > 0 or balance <= 0,
        "due_date": due_dt.date() if due_dt else None,
        "is_overdue": bool(due_dt and due_dt.date() < datetime.now(UTC).date() and balance > 0),
        "assigned_staff_uuids": assigned,
        "raw": raw,
    }


def _normalise_company(raw: dict[str, Any]) -> dict[str, Any]:
    created_dt = _parse_datetime(_first_present(raw, ["create_date", "created_at", "date_created", "timestamp"]))
    return {
        "uuid": raw.get("uuid"),
        "name": _first_present(raw, ["name", "company_name", "display_name"], default=raw.get("uuid", "Customer")),
        "created_date": created_dt.date() if created_dt else None,
        "raw": raw,
    }


def _normalise_activity(raw: dict[str, Any]) -> dict[str, Any]:
    start_dt = _parse_datetime(_first_present(raw, ["start_date", "start_time", "timestamp", "date"]))
    end_dt = _parse_datetime(_first_present(raw, ["end_date", "end_time", "finish_date"]))
    hours = _to_float(_first_present(raw, ["duration_hours", "hours", "duration", "hours_decimal"], default=0.0))
    if hours == 0.0 and start_dt and end_dt and end_dt >= start_dt:
        hours = (end_dt - start_dt).total_seconds() / 3600
    was_scheduled = _to_bool(_first_present(raw, ["activity_was_scheduled", "was_scheduled"], default=False))
    return {
        "uuid": raw.get("uuid"),
        "job_uuid": _first_present(raw, ["job_uuid"]),
        "staff_uuid": _first_present(raw, ["staff_uuid", "created_by_staff_uuid", "assigned_staff_uuid"]),
        "activity_date": start_dt.date() if start_dt else None,
        "hours": max(hours, 0.0),
        "was_scheduled": was_scheduled,
        "raw": raw,
    }


def _normalise_payment(raw: dict[str, Any]) -> dict[str, Any]:
    payment_dt = _parse_datetime(_first_present(raw, ["payment_date", "timestamp", "create_date", "date_paid"]))
    amount = _to_float(_first_present(raw, ["amount", "payment_amount", "total"], default=0.0))
    linked_job_date = _parse_datetime(_first_present(raw, ["job_create_date", "job_date", "regarding_job_date"]))
    days_from_job_to_payment = None
    if payment_dt and linked_job_date:
        days_from_job_to_payment = max((payment_dt.date() - linked_job_date.date()).days, 0)
    return {
        "uuid": raw.get("uuid"),
        "job_uuid": _first_present(raw, ["job_uuid", "regarding_job_uuid"]),
        "payment_date": payment_dt.date() if payment_dt else None,
        "amount": amount,
        "days_from_job_to_payment": days_from_job_to_payment,
        "raw": raw,
    }


def _normalise_staff(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "uuid": raw.get("uuid"),
        "name": _first_present(raw, ["full_name", "name", "display_name"], default=raw.get("uuid", "Staff")),
        "active": bool(raw.get("active", True)),
        "raw": raw,
    }


def _extract_staff_uuids(raw: dict[str, Any]) -> list[str]:
    candidates = []
    for key in ("staff_uuid", "assigned_staff_uuid", "created_by_staff_uuid"):
        value = raw.get(key)
        if isinstance(value, str) and value:
            candidates.append(value)
    for key in ("staff_uuids", "assigned_staff_uuids"):
        value = raw.get(key)
        if isinstance(value, list):
            candidates.extend(str(item) for item in value if item)
        elif isinstance(value, str) and value:
            candidates.extend(part.strip() for part in value.split(",") if part.strip())
    return list(dict.fromkeys(candidates))


def _first_present(raw: dict[str, Any], keys: list[str], default: Any = None) -> Any:
    for key in keys:
        if key in raw and raw[key] not in (None, ""):
            return raw[key]
    return default


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=UTC)
    if isinstance(value, str):
        candidate = value.strip().replace("Z", "+00:00")
        for parser in (datetime.fromisoformat,):
            try:
                parsed = parser(candidate)
                return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
            except ValueError:
                continue
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S"):
            try:
                parsed = datetime.strptime(value, fmt)
                return parsed.replace(tzinfo=UTC)
            except ValueError:
                continue
    return None


def _to_float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.replace(",", "").replace("£", "").replace("$", "").strip()
        try:
            return float(Decimal(cleaned))
        except (InvalidOperation, ValueError):
            return 0.0
    return 0.0


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return False


def _guess_currency(jobs: list[dict[str, Any]], payments: list[dict[str, Any]]) -> str:
    raw_values = []
    for collection in (jobs, payments):
        for item in collection:
            raw = item.get("raw", {})
            for key in ("currency_symbol", "currency"):
                if raw.get(key):
                    raw_values.append(str(raw[key]))
    if any(value == "GBP" or "£" in value for value in raw_values):
        return "GBP"
    if any(value == "AUD" or "$" in value for value in raw_values):
        return "AUD"
    return "GBP"

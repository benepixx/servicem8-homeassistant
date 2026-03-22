"""Constants for the ServiceM8 Business Dashboard integration."""
from __future__ import annotations

DOMAIN = "servicem8_business_dashboard"
DEFAULT_NAME = "ServiceM8"
DEFAULT_BASE_URL = "https://api.servicem8.com/api_1.0"
DEFAULT_SCAN_INTERVAL_MINUTES = 15
DEFAULT_TREND_MONTHS = 12
DEFAULT_INCLUDE_STAFF = True
DEFAULT_INCLUDE_HISTORY = True
DEFAULT_INCLUDE_ALERTS = True
DEFAULT_INCLUDE_CUSTOMERS = True
DEFAULT_INCLUDE_SCHEDULE = True

CONF_API_KEY = "api_key"
CONF_BASE_URL = "base_url"
CONF_SCAN_INTERVAL_MINUTES = "scan_interval_minutes"
CONF_INCLUDE_STAFF = "include_staff"
CONF_INCLUDE_HISTORY = "include_history"
CONF_INCLUDE_ALERTS = "include_alerts"
CONF_INCLUDE_CUSTOMERS = "include_customers"
CONF_INCLUDE_SCHEDULE = "include_schedule"
CONF_TREND_MONTHS = "trend_months"

PLATFORMS = ["sensor", "binary_sensor"]

ATTR_LAST_SUCCESSFUL_UPDATE = "last_successful_update"
ATTR_SOURCE_RECORD_COUNTS = "source_record_counts"
ATTR_NOTE = "note"
ATTR_PERIOD_START = "period_start"
ATTR_PERIOD_END = "period_end"
ATTR_FORMULA = "formula"
ATTR_AVAILABLE_DATA = "available_data"
ATTR_CURRENCY = "currency"
ATTR_GENERATED_FROM = "generated_from"

STATUS_QUOTE = "Quote"
STATUS_WORK_ORDER = "Work Order"
STATUS_COMPLETED = "Completed"
STATUS_UNSUCCESSFUL = "Unsuccessful"
KNOWN_JOB_STATUSES = [STATUS_QUOTE, STATUS_WORK_ORDER, STATUS_COMPLETED, STATUS_UNSUCCESSFUL]

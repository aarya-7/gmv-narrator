from datetime import date

WINDOW_START = date(2017, 1, 1)
WINDOW_END   = date(2018, 8, 31)

ROLLING_WINDOW_DAYS = 28
ANOMALY_THRESHOLD   = 3.5   # robust z-score cutoff
SEVERITY_HIGH       = 5.0   # |z| > 5 → high

MODEL_NAME = "claude-sonnet-4-6"

DATA_DIR = "/Users/reflex/Desktop/llm o_list"

VALID_STATUSES = ("delivered", "shipped", "invoiced")

TOP_CATEGORIES_KEEP = 20   # bucket long tail beyond this into "Other"

SEGMENT_DIMS = ("category", "region")

STATE_TO_REGION = {
    "AC": "North", "AM": "North", "AP": "North", "PA": "North",
    "RO": "North", "RR": "North", "TO": "North",
    "AL": "Northeast", "BA": "Northeast", "CE": "Northeast",
    "MA": "Northeast", "PB": "Northeast", "PE": "Northeast",
    "PI": "Northeast", "RN": "Northeast", "SE": "Northeast",
    "DF": "Center-West", "GO": "Center-West", "MS": "Center-West", "MT": "Center-West",
    "ES": "Southeast", "MG": "Southeast", "RJ": "Southeast", "SP": "Southeast",
    "PR": "South", "RS": "South", "SC": "South",
}

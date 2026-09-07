"""Runtime configuration for the demand-profile integration."""
import os

SRID = int(os.getenv("SRID", "4326"))
THERMAGRID_API_URL = os.getenv("THERMAGRID_API_URL", "")
THERMAGRID_API_KEY = os.getenv("THERMAGRID_API_KEY", "")

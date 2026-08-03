# app/services/schedule.py
# Controls poller operating hours.
#
# Default behaviour:
#   - Auto-runs 09:00–18:00 MST (UTC-7)
#   - Outside hours: paused unless manually resumed
#   - Manual resume outside hours: auto-pauses after INACTIVITY_TIMEOUT seconds
#     of no connected clients
#
# Called from start_poller() loop in poller.py.

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from nicegui import app as nicegui_app

log = logging.getLogger(__name__)

MST = timezone(timedelta(hours=-7))
HOUR_START = 9    # 9am MST
HOUR_END   = 18   # 6pm MST
INACTIVITY_TIMEOUT = 600  # 10 minutes in seconds

# state
_manual_override  = False   # True = user manually resumed outside hours
_last_activity    = {'t': None}  # last time a client was connected


def is_operating_hours() -> bool:
    now = datetime.now(MST)
    return HOUR_START <= now.hour < HOUR_END


def record_activity():
    """Call this whenever a client connects to the transit page."""
    _last_activity['t'] = datetime.now(timezone.utc)


def manual_resume():
    """User pressed Resume outside operating hours."""
    global _manual_override
    _manual_override = True
    record_activity()
    log.info("Poller manually resumed outside operating hours.")


def manual_pause():
    """User pressed Pause."""
    global _manual_override
    _manual_override = False
    log.info("Poller manually paused.")


def _inactivity_expired() -> bool:
    if _last_activity['t'] is None:
        return True
    elapsed = (datetime.now(timezone.utc) - _last_activity['t']).total_seconds()
    return elapsed > INACTIVITY_TIMEOUT


def _count_clients() -> int:
    """Count currently connected NiceGUI clients on the transit page."""
    try:
        return sum(
            1 for client in nicegui_app.clients.values()
            if '/transit' in str(getattr(client, 'page_path', ''))
        )
    except Exception:
        return 0


def should_poll() -> bool:
    """
    Returns True if the poller should fetch this cycle.
    Logic:
      - Within operating hours → always poll
      - Outside hours + manual override → poll unless inactivity expired
      - Outside hours + no override → don't poll
    """
    global _manual_override

    if is_operating_hours():
        _manual_override = False  # reset override when back in hours
        return True

    if _manual_override:
        # update activity if clients are connected
        if _count_clients() > 0:
            record_activity()

        if _inactivity_expired():
            log.info(
                "No activity for %d minutes outside operating hours — pausing poller.",
                INACTIVITY_TIMEOUT // 60,
            )
            _manual_override = False
            return False
        return True

    return False


async def schedule_monitor():
    """
    Background task that logs operating hours transitions.
    Runs every minute, purely informational.
    """
    last_state = None
    while True:
        current = should_poll()
        if current != last_state:
            now = datetime.now(MST)
            if current:
                log.info("Poller active — operating hours or manual override. MST: %s", now.strftime('%H:%M'))
            else:
                log.info("Poller inactive — outside operating hours (09:00-18:00 MST). MST: %s", now.strftime('%H:%M'))
            last_state = current
        await asyncio.sleep(60)
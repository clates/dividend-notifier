import time
import os
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from daily_runner import run_daily
from weekly_runner import run_weekly
import pytz
import traceback
from log_config import get_logger

log = get_logger("scheduler")


def job_wrapper(func):
    job_name = func.__name__
    log.info("=" * 60)
    log.info("JOB STARTING: %s", job_name)
    log.info("=" * 60)
    try:
        func()
        log.info("JOB COMPLETE: %s", job_name)
    except Exception as e:
        log.error("JOB FAILED: %s — %s", job_name, e)
        log.error("Traceback:\n%s", traceback.format_exc())


if __name__ == "__main__":
    tz = os.environ.get("TZ", "America/New_York")
    log.info("Starting scheduler with timezone: %s", tz)

    scheduler = BlockingScheduler(timezone=pytz.timezone(tz))

    # Daily run at 8:00 AM ET on weekdays
    scheduler.add_job(
        job_wrapper,
        CronTrigger(day_of_week="mon-fri", hour=8, minute=0),
        args=[run_daily],
        name="daily_signal",
    )
    log.info("Scheduled: daily_signal — Mon-Fri 08:00 %s", tz)

    # Weekly recap at 8:00 AM ET on Saturdays
    scheduler.add_job(
        job_wrapper,
        CronTrigger(day_of_week="sat", hour=8, minute=0),
        args=[run_weekly],
        name="weekly_recap",
    )
    log.info("Scheduled: weekly_recap — Sat 08:00 %s", tz)

    log.info("All jobs scheduled. Waiting for next trigger...")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped.")

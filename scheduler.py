import time
import os
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from daily_runner import run_daily
from weekly_runner import run_weekly
import pytz


def job_wrapper(func):
    try:
        func()
    except Exception as e:
        print(f"Error executing job: {e}")


if __name__ == "__main__":
    tz = os.environ.get("TZ", "America/New_York")
    print(f"Starting scheduler with timezone: {tz}")

    scheduler = BlockingScheduler(timezone=pytz.timezone(tz))

    # Daily run at 8:00 AM ET on weekdays
    scheduler.add_job(
        job_wrapper,
        CronTrigger(day_of_week="mon-fri", hour=8, minute=0),
        args=[run_daily],
        name="daily_signal",
    )

    # Weekly recap at 8:00 AM ET on Saturdays
    scheduler.add_job(
        job_wrapper,
        CronTrigger(day_of_week="sat", hour=8, minute=0),
        args=[run_weekly],
        name="weekly_recap",
    )

    print("Jobs scheduled. Waiting for first run...")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass

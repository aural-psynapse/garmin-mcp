"""Garmin delta/full sync, flag evaluation — only module that calls Garmin API."""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta, timezone
from typing import Any

from dateutil import parser as dateparser
from garminconnect import GarminConnectAuthenticationError

import database as db
from auth import GarminAuthManager
from config import FlagRules, UserConfig
from metrics import SYNC_CALLS

logger = logging.getLogger(__name__)


def _parse_activity(a: dict[str, Any]) -> dict[str, Any]:
    start = a.get("startTimeGMT") or a.get("startTimeLocal")
    dist = a.get("distance") or a.get("distanceInMeters")
    dur = a.get("duration") or a.get("elapsedDuration") or a.get("movingDuration")
    hr = a.get("averageHR") or a.get("avgHr")
    pace = None
    try:
        if dist and dur and float(dist) > 0:
            pace = float(dur) / (float(dist) / 1000.0)
    except (TypeError, ValueError, ZeroDivisionError):
        pass
    st = None
    if start:
        try:
            st = dateparser.parse(str(start)).astimezone(timezone.utc).isoformat()
        except Exception:
            st = str(start)
    return {
        "type": a.get("activityType", {}).get("typeKey") if isinstance(a.get("activityType"), dict) else a.get("activityType"),
        "start_time_utc": st,
        "distance_m": float(dist) / 1000.0 if dist else None,
        "duration_s": float(dur) if dur else None,
        "avg_hr": float(hr) if hr else None,
        "pace_s_per_km": pace,
    }


def evaluate_flags(
    conn,
    user: UserConfig,
    rules: FlagRules,
) -> list[str]:
    """Insert flags based on DB state; return flag types created."""
    uid = user.name
    created: list[str] = []
    # Poor sleep streak
    cur = conn.execute(
        """SELECT calendar_date, raw_json FROM sleep
           WHERE user_id=? AND status='active'
           ORDER BY calendar_date DESC LIMIT 14""",
        (uid,),
    )
    rows = list(cur)
    poor = 0
    streak = 0
    for r in sorted(rows, key=lambda x: x["calendar_date"]):
        try:
            j = __import__("json").loads(r["raw_json"])
            score = j.get("dailySleepDTO", {}).get("sleepScores", {}).get("overall", {}).get("value")
            if score is not None and float(score) < 60:
                streak += 1
            else:
                streak = 0
            poor = max(poor, streak)
        except Exception:
            continue
    if poor >= rules.poor_sleep_streak_days:
        db.insert_flag(conn, uid, "recovery_risk", {"reason": "poor_sleep_streak", "days": poor})
        created.append("recovery_risk")

    # Overtraining: compare last 7d activity volume vs prior 7d (simplified)
    # Stub: use activity count
    c1 = conn.execute(
        """SELECT COUNT(*) as c FROM activities WHERE user_id=? AND status='active'
           AND start_time_utc >= datetime('now', '-7 days')""",
        (uid,),
    ).fetchone()["c"]
    c2 = conn.execute(
        """SELECT COUNT(*) as c FROM activities WHERE user_id=? AND status='active'
           AND start_time_utc >= datetime('now', '-14 days')
           AND start_time_utc < datetime('now', '-7 days')""",
        (uid,),
    ).fetchone()["c"]
    if c2 and c1:
        try:
            wow = (c1 - c2) / max(c2, 1) * 100.0
            if wow >= rules.load_week_over_week_pct:
                db.insert_flag(conn, uid, "overtraining_risk", {"wow_pct": wow})
                created.append("overtraining_risk")
        except Exception:
            pass

    # Goal at risk: active goal with deadline soon and no recent activity
    goals = db.list_active_goals(conn, uid)
    last_act = conn.execute(
        "SELECT MAX(start_time_utc) as m FROM activities WHERE user_id=? AND status='active'",
        (uid,),
    ).fetchone()["m"]
    for g in goals:
        td = g["target_date"]
        if not td:
            continue
        try:
            dl = date.fromisoformat(td[:10])
            days_to = (dl - date.today()).days
            idle = 999
            if last_act:
                try:
                    dlast = dateparser.parse(str(last_act)).date()
                    idle = (date.today() - dlast).days
                except Exception:
                    pass
            if 0 <= days_to <= rules.goal_idle_days_before_deadline and idle >= rules.goal_idle_days_before_deadline:
                db.insert_flag(conn, uid, "goal_at_risk", {"goal_id": g["id"], "days_to_deadline": days_to})
                created.append("goal_at_risk")
        except Exception:
            continue

    if rules.pr_detection_enabled:
        # Placeholder: would compare PR endpoint; skip without API
        pass

    return created


def run_sync(
    user: UserConfig,
    auth: GarminAuthManager,
    full_historical_days: int | None = None,
) -> dict[str, Any]:
    """Run Garmin sync for one user; return record counts and timing."""
    uid = user.name
    conn = db.connect(user.db_path)
    db.init_schema(conn)
    SYNC_CALLS.labels(user=uid).inc()
    t0 = time.perf_counter()
    sync_id = db.insert_sync_log_start(conn, uid)
    counts = {"activities": 0, "sleep": 0, "training_status": 0, "training_readiness": 0}
    err: str | None = None
    try:

        def api_call(fn):
            return auth.call_with_retry(fn)

        client = auth.get_client()

        last = db.get_last_sync_at(conn, uid)
        end_d = date.today()
        if last and not full_historical_days:
            try:
                start_d = max(
                    date.fromisoformat(last[:10]),
                    end_d - timedelta(days=30),
                )
            except Exception:
                start_d = end_d - timedelta(days=user.initial_sync_days)
        else:
            days = full_historical_days or user.initial_sync_days
            start_d = end_d - timedelta(days=days)

        # Activities
        acts = client.get_activities_by_date(start_d.isoformat(), end_d.isoformat())
        seen: set[str] = set()
        for a in acts or []:
            aid = str(a.get("activityId") or "")
            if not aid:
                continue
            detail = client.get_activity(aid)
            norm = _parse_activity(detail)
            db.upsert_activity(conn, uid, aid, detail, norm)
            seen.add(aid)
            counts["activities"] += 1
        db.archive_missing_activities(conn, uid, seen)

        # Sleep (daily in range, cap 45 days per sync)
        d = start_d
        n = 0
        while d <= end_d and n < 45:
            try:
                sd = client.get_sleep_data(d.isoformat())
                sid = str(sd.get("dailySleepDTO", {}).get("sleepStartTimestampGMT") or d.isoformat())
                db.upsert_sleep_row(
                    conn,
                    uid,
                    sid,
                    d.isoformat(),
                    sd,
                    float(sd.get("dailySleepDTO", {}).get("sleepTimeSeconds") or 0) or None,
                    float(sd["dailySleepDTO"]["sleepScores"]["overall"]["value"])
                    if sd.get("dailySleepDTO", {})
                    .get("sleepScores", {})
                    .get("overall", {})
                    .get("value")
                    else None,
                    sd.get("dailySleepDTO", {}).get("sleepLevels"),
                )
                counts["sleep"] += 1
            except Exception as e:
                logger.debug("sleep fetch %s: %s", d, e)
            d += timedelta(days=1)
            n += 1

        # Training
        try:
            ts = client.get_training_status()
            db.upsert_training_status(conn, uid, ts)
            counts["training_status"] = 1
        except Exception as e:
            logger.warning("training_status: %s", e)
        try:
            tr = client.get_training_readiness()
            score = None
            if isinstance(tr, dict):
                score = tr.get("score") or tr.get("readinessScore")
            db.upsert_training_readiness(conn, uid, tr, float(score) if score is not None else None)
            counts["training_readiness"] = 1
        except Exception as e:
            logger.warning("training_readiness: %s", e)

        evaluate_flags(conn, user, user.flag_rules)
        dur_ms = int((time.perf_counter() - t0) * 1000)
        db.complete_sync_log(conn, sync_id, dur_ms, counts, "ok", None)
        return {"ok": True, "counts": counts, "duration_ms": dur_ms}
    except GarminConnectAuthenticationError as e:
        err = str(e)
        db.complete_sync_log(conn, sync_id, int((time.perf_counter() - t0) * 1000), counts, "error", err)
        raise
    except Exception as e:
        err = str(e)
        logger.exception("sync failed user=%s", uid)
        db.complete_sync_log(conn, sync_id, int((time.perf_counter() - t0) * 1000), counts, "error", err)
        raise
    finally:
        conn.close()

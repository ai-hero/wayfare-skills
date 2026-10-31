"""Q16.xx / RQ-h2-023 -- Can an OEE-style score (availability x
performance x quality) be computed for the factory? Availability = working
share of session time (D6); performance = change sets per hour worked;
quality = 1 - D5 followup rate. Multiplied together as the OEE proxy --
a first attempt, not a validated manufacturing-equivalent metric.
"""
RQ_ID = "RQ-h2-023"
QUESTION = "Can an OEE-style score (availability x performance x quality) be computed for the factory?"


def answer(con):
    seg = {r["kind"]: r["minutes"] for r in con.execute(
        "SELECT kind, SUM(minutes) AS minutes FROM detectors.session_time_segments GROUP BY kind"
    ).fetchall()}
    total_minutes = sum(seg.values())
    working_minutes = seg.get("working", 0)
    availability = working_minutes / total_minutes if total_minutes else None

    total_sets = con.execute(
        "SELECT SUM(n_sets) FROM detectors.cs_units"
    ).fetchone()[0] or 0
    performance = total_sets / (working_minutes / 60) if working_minutes else None

    followups = con.execute(
        "SELECT COUNT(*) AS total, SUM(CASE WHEN followup_within_14d_days IS NOT NULL THEN 1 ELSE 0 END) AS followed "
        "FROM detectors.followups"
    ).fetchone()
    quality = 1 - (followups["followed"] / followups["total"]) if followups["total"] else None

    oee = None
    if availability is not None and quality is not None:
        oee = round(availability * min(performance or 1, 1) * quality, 4)

    return [{"availability": round(availability, 3) if availability else None,
             "performance_change_sets_per_working_hour": round(performance, 2) if performance else None,
             "quality_1_minus_followup_rate": round(quality, 3) if quality else None,
             "oee_style_score_capping_performance_at_1": oee,
             "note": "a first attempt at the analogy, not a validated manufacturing-equivalent metric"}]


if __name__ == "__main__":
    from cube.db import connect
    for row in answer(connect()):
        print(row)

import csv
from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg, Sum
from django.http import HttpResponse
from django.utils import timezone

from .models import DailyActivity, MealEntry, MealTemplate, UserProfile, WaterEntry, WeightEntry


def get_or_create_profile(user) -> UserProfile:
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


def build_sparkline_paths(values: list[float], width: int = 200, height: int = 42) -> tuple[str, str]:
    """Erzeugt SVG-Pfad-Strings (Linie, Fläche) für KPI-Sparklines."""
    if len(values) < 2:
        return "", ""
    min_v = min(values)
    max_v = max(values)
    span = max_v - min_v or 1.0
    pad_y = 4.0
    usable_h = height - 2 * pad_y
    step_x = width / (len(values) - 1)
    points = []
    for idx, val in enumerate(values):
        x = round(idx * step_x, 1)
        norm = (val - min_v) / span
        y = round(height - pad_y - norm * usable_h, 1)
        points.append((x, y))
    line_path = "M " + " L ".join(f"{x},{y}" for x, y in points)
    area_path = f"{line_path} L {points[-1][0]},{height} L {points[0][0]},{height} Z"
    return line_path, area_path


def build_progress_segments(ratio: float, total_segments: int = 12) -> list[bool]:
    """Erzeugt eine Liste aktiver Segmente für die KPI-Fortschrittsanzeige."""
    clamped = max(0.0, min(1.0, ratio))
    active_count = round(clamped * total_segments)
    return [i < active_count for i in range(total_segments)]


def export_queryset_csv(filename: str, headers: list[str], rows: list[list]) -> HttpResponse:
    """Gibt eine UTF-8-CSV-Datei (mit BOM für Excel) als HttpResponse zurück."""
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(headers)
    writer.writerows(rows)
    return response


def get_daily_calorie_map(user) -> dict[str, int]:
    """Gibt eine Map {YYYY-MM-DD: Gesamtkalorien} für alle Tage des Benutzers zurück."""
    rows = MealEntry.objects.filter(user=user).values("date").annotate(total=Sum("calories"))
    return {row["date"].isoformat(): int(row["total"] or 0) for row in rows}


def get_daily_activity_map(user) -> dict[str, int]:
    """Gibt eine Map {YYYY-MM-DD: Bewegungskalorien} zurück."""
    return {
        row["date"].isoformat(): int(row["calories_burned"] or 0)
        for row in DailyActivity.objects.filter(user=user).values("date", "calories_burned")
    }


def get_weight_modal_context(user) -> dict:
    """Liefert Kalorienziel, Bewegungskalorien, heutige Kalorien und Tages-Maps für das Gewichts-Modal."""
    today = timezone.localdate()
    profile = get_or_create_profile(user)
    base_goal = profile.daily_calorie_goal or 2000
    daily_map = get_daily_calorie_map(user)
    activity_map = get_daily_activity_map(user)
    today_iso = today.isoformat()
    today_calories = daily_map.get(today_iso, 0)
    today_goal = base_goal + activity_map.get(today_iso, 0)
    return {
        "weight_modal_goal": today_goal,
        "weight_modal_base_goal": base_goal,
        "weight_modal_today_calories": today_calories,
        "weight_modal_remaining": today_goal - today_calories,
        "weight_modal_daily_map": daily_map,
        "weight_modal_activity_map": activity_map,
    }


def build_macro_calorie_chart_series(user, start_date, end_date, calorie_goal: int) -> dict:
    """Erzeugt tägliche kcal-Serien (Eiweiß, KH, Fett, Ballaststoffe, Rest) + Zielkalorien."""
    num_days = (end_date - start_date).days + 1
    days = [start_date + timedelta(days=i) for i in range(num_days)]

    rows = (
        MealEntry.objects.filter(user=user, date__gte=start_date, date__lte=end_date)
        .values("date")
        .annotate(
            total_cal=Sum("calories"),
            total_protein=Sum("protein_g"),
            total_carbs=Sum("carbs_g"),
            total_fat=Sum("fat_g"),
            total_fiber=Sum("fiber_g"),
        )
    )
    by_day = {r["date"]: r for r in rows}
    activity_map = get_daily_activity_map(user)

    labels, p_kcal, c_kcal, f_kcal, fib_kcal, o_kcal = [], [], [], [], [], []
    p_g, c_g, f_g, fib_g, goal_series, act_kcal = [], [], [], [], [], []
    max_day_cal = 0

    for d in days:
        labels.append(d.strftime("%d.%m."))
        day_act = activity_map.get(d.isoformat(), 0)
        act_kcal.append(day_act)
        day_goal = calorie_goal + day_act
        goal_series.append(day_goal)
        r = by_day.get(d)
        if not r:
            p_kcal.append(0)
            c_kcal.append(0)
            f_kcal.append(0)
            fib_kcal.append(0)
            o_kcal.append(0)
            p_g.append(0.0)
            c_g.append(0.0)
            f_g.append(0.0)
            fib_g.append(0.0)
            continue

        pg = float(r["total_protein"] or 0)
        cg = float(r["total_carbs"] or 0)
        fg = float(r["total_fat"] or 0)
        fibg = float(r["total_fiber"] or 0)
        tot = int(r["total_cal"] or 0)

        pk = round(pg * 4)
        fib_in_carbs = min(cg, fibg)
        net_cg = max(0.0, cg - fib_in_carbs)
        ck = round(net_cg * 4)
        fibk = round(fib_in_carbs * 4)
        fk = round(fg * 9)
        ok = max(0, tot - (pk + ck + fk + fibk))
        day_sum = pk + ck + fk + fibk + ok
        if day_sum > max_day_cal:
            max_day_cal = day_sum

        p_kcal.append(pk)
        c_kcal.append(ck)
        f_kcal.append(fk)
        fib_kcal.append(fibk)
        o_kcal.append(ok)
        p_g.append(round(pg, 1))
        c_g.append(round(cg, 1))
        f_g.append(round(fg, 1))
        fib_g.append(round(fibg, 1))

    top_ref = max(max(goal_series, default=calorie_goal), max_day_cal)
    suggested_max = max(500, ((int(top_ref * 1.1) + 99) // 100) * 100)

    return {
        "labels": labels,
        "protein_kcal": p_kcal,
        "carbs_kcal": c_kcal,
        "fat_kcal": f_kcal,
        "fiber_kcal": fib_kcal,
        "other_kcal": o_kcal,
        "protein_g": p_g,
        "carbs_g": c_g,
        "fat_g": f_g,
        "fiber_g": fib_g,
        "goal": calorie_goal,
        "goal_series": goal_series,
        "activity_kcal": act_kcal,
        "suggested_max": suggested_max,
    }


def build_weight_chart_series(user, start_date, end_date, target_weight_kg: Decimal | None = None) -> dict:
    """Erzeugt tägliche Gewichtsserie inkl. Carry-Forward-Startwert und Y-Achsen-Grenzen."""
    num_days = (end_date - start_date).days + 1
    days = [start_date + timedelta(days=i) for i in range(num_days)]

    entries = list(
        WeightEntry.objects.filter(user=user, date__gte=start_date, date__lte=end_date)
        .order_by("date", "created_at")
    )
    weight_by_day = {e.date: float(e.weight_kg) for e in entries}

    if start_date not in weight_by_day:
        baseline = (
            WeightEntry.objects.filter(user=user, date__lt=start_date)
            .order_by("-date", "-created_at")
            .first()
        )
        if baseline:
            weight_by_day[start_date] = float(baseline.weight_kg)

    values = [weight_by_day.get(d) for d in days]
    numeric_vals = [v for v in values if v is not None]
    target_val = float(target_weight_kg) if target_weight_kg is not None else None
    if target_val is not None:
        numeric_vals.append(target_val)

    suggested_min = round(min(numeric_vals) - 1.0, 1) if numeric_vals else None
    suggested_max = round(max(numeric_vals) + 1.0, 1) if numeric_vals else None

    return {
        "labels": [d.strftime("%d.%m.") for d in days],
        "values": values,
        "target": target_val,
        "suggested_min": suggested_min,
        "suggested_max": suggested_max,
    }


def build_activity_chart_series(user, start_date, end_date) -> dict:
    """Erzeugt tägliche Bewegungskalorien-Serie (kcal) inkl. Datum & Level für Charts."""
    num_days = (end_date - start_date).days + 1
    days = [start_date + timedelta(days=i) for i in range(num_days)]
    rows = DailyActivity.objects.filter(user=user, date__gte=start_date, date__lte=end_date).values(
        "date", "level", "calories_burned"
    )
    by_day = {r["date"]: r for r in rows}
    values = [int(by_day[d]["calories_burned"]) if d in by_day else 0 for d in days]
    levels = [by_day[d]["level"] if d in by_day else "none" for d in days]
    max_val = max([500] + values)
    suggested_max = max(500, ((int(max_val * 1.15) + 99) // 100) * 100)
    return {
        "labels": [d.strftime("%d.%m.") for d in days],
        "dates": [d.isoformat() for d in days],
        "values": values,
        "levels": levels,
        "suggested_max": suggested_max,
    }


def build_water_chart_series(user, start_date, end_date, water_goal_ml: int) -> dict:
    """Erzeugt tägliche Wasser-Serien (ml) und Zielwert für Charts."""
    num_days = (end_date - start_date).days + 1
    days = [start_date + timedelta(days=i) for i in range(num_days)]
    rows = (
        WaterEntry.objects.filter(user=user, date__gte=start_date, date__lte=end_date)
        .values("date")
        .annotate(total_ml=Sum("amount_ml"))
    )
    by_day = {r["date"]: int(r["total_ml"] or 0) for r in rows}
    values = [by_day.get(d, 0) for d in days]
    max_val = max([water_goal_ml] + values)
    suggested_max = max(1000, ((int(max_val * 1.1) + 249) // 250) * 250)
    return {
        "labels": [d.strftime("%d.%m.") for d in days],
        "values": values,
        "goal": water_goal_ml,
        "suggested_max": suggested_max,
    }


def get_dashboard_context(user) -> dict:
    """Berechnet alle KPIs, Trenddaten und Tabellen für das Dashboard."""
    today = timezone.localdate()
    profile = get_or_create_profile(user)

    latest_weight_entry = WeightEntry.objects.filter(user=user).first()
    previous_weight_entry = WeightEntry.objects.filter(user=user)[1:2].first()
    current_weight = latest_weight_entry.weight_kg if latest_weight_entry else None

    weight_delta = None
    if latest_weight_entry and previous_weight_entry:
        weight_delta = latest_weight_entry.weight_kg - previous_weight_entry.weight_kg

    today_meals = MealEntry.objects.filter(user=user, date=today)
    today_agg = today_meals.aggregate(
        total_calories=Sum("calories"),
        total_protein=Sum("protein_g"),
        total_carbs=Sum("carbs_g"),
        total_fat=Sum("fat_g"),
        total_fiber=Sum("fiber_g"),
    )
    today_calories = int(today_agg["total_calories"] or 0)
    today_fiber = today_agg["total_fiber"] or Decimal("0.0")
    base_calorie_goal = profile.daily_calorie_goal or 2000
    today_activity = DailyActivity.objects.filter(user=user, date=today).first()
    today_activity_level = today_activity.level if today_activity else "none"
    today_activity_kcal = today_activity.calories_burned if today_activity else 0
    calorie_goal = base_calorie_goal + today_activity_kcal
    recommended_tdee = profile.calculate_tdee(current_weight)
    remaining_calories = calorie_goal - today_calories
    calorie_ratio = today_calories / calorie_goal if calorie_goal > 0 else 0.0

    fiber_goal_g = profile.daily_fiber_goal_g or 30
    fiber_ratio = float(today_fiber) / fiber_goal_g if fiber_goal_g > 0 else 0.0

    # Fortschritt zum Zielgewicht
    goal_progress_pct = None
    goal_diff_kg = None
    if current_weight is not None and profile.target_weight_kg is not None:
        goal_diff_kg = current_weight - profile.target_weight_kg
        start_w = profile.start_weight_kg or current_weight
        total_span = abs(start_w - profile.target_weight_kg)
        if total_span > Decimal("0"):
            achieved = abs(start_w - current_weight)
            # Wenn sich das Gewicht in die falsche Richtung bewegt hat, 0% anzeigen
            moving_towards_goal = (
                (start_w > profile.target_weight_kg and current_weight <= start_w)
                or (start_w < profile.target_weight_kg and current_weight >= start_w)
            )
            ratio = float(achieved / total_span) if moving_towards_goal else 0.0
            goal_progress_pct = min(100, max(0, round(ratio * 100)))
        elif current_weight == profile.target_weight_kg:
            goal_progress_pct = 100

    # 14-Tage-Trend für Sparklines & Charts
    start_date = today - timedelta(days=13)
    days = [start_date + timedelta(days=i) for i in range(14)]
    day_labels = [d.strftime("%d.%m.") for d in days]

    meal_by_day = {
        row["date"]: int(row["total"] or 0)
        for row in MealEntry.objects.filter(user=user, date__gte=start_date, date__lte=today)
        .values("date")
        .annotate(total=Sum("calories"))
    }
    calorie_series = [meal_by_day.get(d, 0) for d in days]
    cal_spark_line, cal_spark_area = build_sparkline_paths([float(v) for v in calorie_series])

    weight_chart = build_weight_chart_series(user, start_date, today, profile.target_weight_kg)
    weight_values_for_spark = [v for v in weight_chart["values"] if v is not None]
    if len(weight_values_for_spark) < 2:
        all_recent = list(WeightEntry.objects.filter(user=user).order_by("-date", "-created_at")[:14])
        weight_values_for_spark = [float(e.weight_kg) for e in reversed(all_recent)]
    weight_spark_line, weight_spark_area = build_sparkline_paths(weight_values_for_spark)

    # 7-Tage-Durchschnitt Kalorien
    week_start = today - timedelta(days=6)
    week_day_totals = list(
        MealEntry.objects.filter(user=user, date__gte=week_start, date__lte=today)
        .values("date")
        .annotate(total=Sum("calories"))
    )
    avg_7d_calories = (
        round(sum(r["total"] for r in week_day_totals) / len(week_day_totals))
        if week_day_totals
        else 0
    )

    macro_chart = build_macro_calorie_chart_series(user, start_date, today, base_calorie_goal)
    activity_chart = build_activity_chart_series(user, start_date, today)
    fiber_spark_line, fiber_spark_area = build_sparkline_paths([float(v) for v in macro_chart["fiber_g"]])

    water_goal_ml = profile.daily_water_goal_ml or 2500
    recommended_water_ml = profile.calculate_water_need_ml(current_weight)
    today_water_ml = int(
        WaterEntry.objects.filter(user=user, date=today).aggregate(total=Sum("amount_ml"))["total"] or 0
    )
    remaining_water_ml = max(0, water_goal_ml - today_water_ml)
    water_ratio = today_water_ml / water_goal_ml if water_goal_ml > 0 else 0.0
    water_chart = build_water_chart_series(user, start_date, today, water_goal_ml)
    water_spark_line, water_spark_area = build_sparkline_paths([float(v) for v in water_chart["values"]])

    remaining_ratio = max(0.0, remaining_calories / calorie_goal) if calorie_goal > 0 else 0.0
    avg7d_ratio = (avg_7d_calories / calorie_goal) if calorie_goal > 0 else 0.0

    return {
        "today": today,
        "profile": profile,
        "current_weight": current_weight,
        "latest_weight_entry": latest_weight_entry,
        "weight_delta": weight_delta,
        "today_calories": today_calories,
        "today_protein": today_agg["total_protein"] or Decimal("0.0"),
        "today_carbs": today_agg["total_carbs"] or Decimal("0.0"),
        "today_fat": today_agg["total_fat"] or Decimal("0.0"),
        "today_fiber": today_fiber,
        "fiber_goal_g": fiber_goal_g,
        "fiber_ratio_pct": min(100, round(fiber_ratio * 100)),
        "fiber_segments": build_progress_segments(fiber_ratio),
        "fiber_spark_line": fiber_spark_line,
        "fiber_spark_area": fiber_spark_area,
        "base_calorie_goal": base_calorie_goal,
        "today_activity_level": today_activity_level,
        "today_activity_kcal": today_activity_kcal,
        "calorie_goal": calorie_goal,
        "recommended_tdee": recommended_tdee,
        "remaining_calories": remaining_calories,
        "calorie_ratio_pct": min(100, round(calorie_ratio * 100)),
        "calorie_segments": build_progress_segments(calorie_ratio),
        "remaining_segments": build_progress_segments(remaining_ratio),
        "avg7d_segments": build_progress_segments(avg7d_ratio),
        "avg7d_pct": min(100, round(avg7d_ratio * 100)),
        "goal_progress_pct": goal_progress_pct,
        "goal_segments": build_progress_segments((goal_progress_pct or 0) / 100.0) if goal_progress_pct is not None else None,
        "goal_diff_kg": goal_diff_kg,
        "avg_7d_calories": avg_7d_calories,
        "cal_spark_line": cal_spark_line,
        "cal_spark_area": cal_spark_area,
        "weight_spark_line": weight_spark_line,
        "weight_spark_area": weight_spark_area,
        "chart_labels": day_labels,
        "chart_calories": calorie_series,
        "weight_chart_data": weight_chart,
        "macro_chart_data": macro_chart,
        "activity_chart_data": activity_chart,
        "today_water_ml": today_water_ml,
        "water_goal_ml": water_goal_ml,
        "recommended_water_ml": recommended_water_ml,
        "remaining_water_ml": remaining_water_ml,
        "water_ratio_pct": min(100, round(water_ratio * 100)),
        "water_segments": build_progress_segments(water_ratio),
        "water_spark_line": water_spark_line,
        "water_spark_area": water_spark_area,
        "recent_meals": MealEntry.objects.filter(user=user)[:8],
        "recent_weights": WeightEntry.objects.filter(user=user)[:8],
        "meal_templates": MealTemplate.objects.filter(user=user),
        **get_weight_modal_context(user),
    }

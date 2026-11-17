from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db.models import Avg, Max, Min, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import (
    MealEntryForm,
    MealTemplateForm,
    RegistrationForm,
    StyledAuthenticationForm,
    UserProfileForm,
    WaterEntryForm,
    WeightEntryForm,
)
from .models import DailyActivity, MealEntry, MealTemplate, WaterEntry, WeightEntry
from .services import (
    build_macro_calorie_chart_series,
    build_progress_segments,
    build_sparkline_paths,
    build_water_chart_series,
    build_weight_chart_series,
    export_queryset_csv,
    get_dashboard_context,
    get_or_create_profile,
    get_weight_modal_context,
)


class TrackerLoginView(LoginView):
    template_name = "tracker/login.html"
    authentication_form = StyledAuthenticationForm
    redirect_authenticated_user = True


def register_view(request):
    if request.user.is_authenticated:
        return redirect("tracker:dashboard")
    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Willkommen! Dein Konto wurde erstellt.")
            return redirect("tracker:dashboard")
    else:
        form = RegistrationForm()
    return render(request, "tracker/register.html", {"form": form})


def logout_view(request):
    logout(request)
    messages.info(request, "Du wurdest abgemeldet.")
    return redirect("tracker:login")


@login_required
def dashboard_view(request):
    context = get_dashboard_context(request.user)
    context["meal_form"] = MealEntryForm(initial={"date": timezone.localdate()})
    context["weight_form"] = WeightEntryForm(initial={"date": timezone.localdate()})
    context["water_form"] = WaterEntryForm(initial={"date": timezone.localdate(), "amount_ml": 250})
    return render(request, "tracker/dashboard.html", context)


@login_required
@require_POST
def set_daily_activity_view(request):
    """Setzt die heutigen Bewegungskalorien (Preset oder Apple Watch / Manuell)."""
    profile = get_or_create_profile(request.user)
    today = timezone.localdate()
    level = request.POST.get("level", "none").strip()

    preset_map = {
        "none": 0,
        "low": profile.activity_kcal_low,
        "medium": profile.activity_kcal_medium,
        "high": profile.activity_kcal_high,
    }

    if level == "custom":
        try:
            burned = max(0, int(request.POST.get("custom_kcal", 0)))
        except (TypeError, ValueError):
            messages.error(request, "Bitte gültige Bewegungskalorien (kcal) eingeben.")
            return redirect(request.POST.get("next") or "tracker:dashboard")
        if burned == 0:
            level = "none"
    elif level in preset_map:
        burned = preset_map[level]
    else:
        messages.error(request, "Ungültiges Bewegungslevel.")
        return redirect(request.POST.get("next") or "tracker:dashboard")

    DailyActivity.objects.update_or_create(
        user=request.user,
        date=today,
        defaults={"level": level, "calories_burned": burned},
    )
    messages.success(request, f"Bewegung heute gespeichert (+{burned} kcal).")
    return redirect(request.POST.get("next") or "tracker:dashboard")


def _apply_date_filters(queryset, date_from: str, date_to: str):
    if date_from:
        queryset = queryset.filter(date__gte=date_from)
    if date_to:
        queryset = queryset.filter(date__lte=date_to)
    return queryset


@login_required
def meals_list_view(request):
    if request.method == "POST":
        action = request.POST.get("action", "create")
        if action == "delete":
            entry = get_object_or_404(MealEntry, pk=request.POST.get("entry_id"), user=request.user)
            entry.delete()
            messages.success(request, "Mahlzeit wurde gelöscht.")
            return redirect("tracker:meals_list")

        instance = None
        if action == "update" and request.POST.get("entry_id"):
            instance = get_object_or_404(MealEntry, pk=request.POST.get("entry_id"), user=request.user)
        form = MealEntryForm(request.POST, instance=instance)
        if form.is_valid():
            meal = form.save(commit=False)
            meal.user = request.user
            meal.save()
            if request.POST.get("save_as_template") == "on":
                MealTemplate.objects.update_or_create(
                    user=request.user,
                    category=meal.category,
                    name=meal.name,
                    defaults={
                        "calories": meal.calories,
                        "protein_g": meal.protein_g,
                        "carbs_g": meal.carbs_g,
                        "fat_g": meal.fat_g,
                        "fiber_g": meal.fiber_g,
                        "notes": meal.notes,
                    },
                )
            messages.success(
                request,
                "Mahlzeit aktualisiert." if instance else "Mahlzeit gespeichert.",
            )
            return redirect(request.POST.get("next") or "tracker:meals_list")
        err_msg = next(iter(form.non_field_errors()), "Bitte überprüfe die Eingaben für die Mahlzeit.")
        messages.error(request, err_msg)

    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    category = request.GET.get("category", "").strip()
    query = request.GET.get("q", "").strip()

    meals = _apply_date_filters(MealEntry.objects.filter(user=request.user), date_from, date_to)
    if category:
        meals = meals.filter(category=category)
    if query:
        meals = meals.filter(Q(name__icontains=query) | Q(notes__icontains=query))

    if request.GET.get("export") == "csv":
        rows = [
            [
                m.date.isoformat(),
                m.get_category_display(),
                m.name,
                m.calories,
                m.protein_g,
                m.carbs_g,
                m.fat_g,
                m.fiber_g,
                m.notes,
            ]
            for m in meals
        ]
        return export_queryset_csv(
            "mahlzeiten_export.csv",
            ["Datum", "Kategorie", "Mahlzeit", "Kalorien (kcal)", "Eiweiß (g)", "Kohlenhydrate (g)", "Fett (g)", "Ballaststoffe (g)", "Notizen"],
            rows,
        )

    totals = meals.aggregate(
        total_calories=Sum("calories"),
        total_protein=Sum("protein_g"),
        total_carbs=Sum("carbs_g"),
        total_fat=Sum("fat_g"),
        total_fiber=Sum("fiber_g"),
    )

    return render(
        request,
        "tracker/meals_list.html",
        {
            "meals": meals,
            "meal_form": MealEntryForm(initial={"date": timezone.localdate()}),
            "meal_templates": MealTemplate.objects.filter(user=request.user),
            "categories": MealEntry.CATEGORY_CHOICES,
            "filter_date_from": date_from,
            "filter_date_to": date_to,
            "filter_category": category,
            "filter_q": query,
            "totals": totals,
        },
    )


@login_required
def weights_list_view(request):
    if request.method == "POST":
        action = request.POST.get("action", "create")
        if action == "delete":
            entry = get_object_or_404(WeightEntry, pk=request.POST.get("entry_id"), user=request.user)
            entry.delete()
            messages.success(request, "Gewichtseintrag wurde gelöscht.")
            return redirect("tracker:weights_list")

        instance = None
        if action == "update" and request.POST.get("entry_id"):
            instance = get_object_or_404(WeightEntry, pk=request.POST.get("entry_id"), user=request.user)
        form = WeightEntryForm(request.POST, instance=instance)
        if form.is_valid():
            weight = form.save(commit=False)
            weight.user = request.user
            weight.save()
            messages.success(
                request,
                "Gewichtseintrag aktualisiert." if instance else "Gewichtseintrag gespeichert.",
            )
            return redirect(request.POST.get("next") or "tracker:weights_list")
        messages.error(request, "Bitte überprüfe die Eingaben für den Gewichtseintrag.")

    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    query = request.GET.get("q", "").strip()

    weights = _apply_date_filters(WeightEntry.objects.filter(user=request.user), date_from, date_to)
    if query:
        weights = weights.filter(notes__icontains=query)

    if request.GET.get("export") == "csv":
        rows = [
            [
                w.date.isoformat(),
                w.weight_kg,
                w.body_fat_pct if w.body_fat_pct is not None else "",
                w.notes,
            ]
            for w in weights
        ]
        return export_queryset_csv(
            "gewicht_export.csv",
            ["Datum", "Gewicht (kg)", "Körperfett (%)", "Notizen"],
            rows,
        )

    stats = weights.aggregate(
        avg_weight=Avg("weight_kg"),
        min_weight=Min("weight_kg"),
        max_weight=Max("weight_kg"),
    )
    weight_ctx = get_weight_modal_context(request.user)
    daily_map = weight_ctx["weight_modal_daily_map"]
    activity_map = weight_ctx["weight_modal_activity_map"]
    base_goal = weight_ctx["weight_modal_base_goal"]
    weight_rows = []
    for w in weights:
        d_iso = w.date.isoformat()
        day_cal = daily_map.get(d_iso, 0)
        day_goal = base_goal + activity_map.get(d_iso, 0)
        w.day_calories = day_cal
        w.day_remaining = day_goal - day_cal
        weight_rows.append(w)

    return render(
        request,
        "tracker/weights_list.html",
        {
            "weights": weight_rows,
            "weight_form": WeightEntryForm(initial={"date": timezone.localdate()}),
            "filter_date_from": date_from,
            "filter_date_to": date_to,
            "filter_q": query,
            "stats": stats,
            **weight_ctx,
        },
    )


@login_required
def meal_templates_view(request):
    if request.method == "POST":
        action = request.POST.get("action", "create")
        if action == "delete":
            tpl = get_object_or_404(MealTemplate, pk=request.POST.get("entry_id"), user=request.user)
            tpl.delete()
            messages.success(request, "Vorlage wurde gelöscht.")
            return redirect("tracker:meal_templates_list")

        instance = None
        if action == "update" and request.POST.get("entry_id"):
            instance = get_object_or_404(MealTemplate, pk=request.POST.get("entry_id"), user=request.user)
        form = MealTemplateForm(request.POST, instance=instance)
        if form.is_valid():
            tpl = form.save(commit=False)
            tpl.user = request.user
            tpl.save()
            messages.success(request, "Vorlage aktualisiert." if instance else "Vorlage gespeichert.")
            return redirect("tracker:meal_templates_list")
        err_msg = next(iter(form.non_field_errors()), "Bitte überprüfe die Eingaben für die Vorlage.")
        messages.error(request, err_msg)

    category = request.GET.get("category", "").strip()
    query = request.GET.get("q", "").strip()
    templates = MealTemplate.objects.filter(user=request.user)
    if category:
        templates = templates.filter(category=category)
    if query:
        templates = templates.filter(Q(name__icontains=query) | Q(notes__icontains=query))

    return render(
        request,
        "tracker/meal_templates_list.html",
        {
            "templates": templates,
            "template_form": MealTemplateForm(),
            "categories": MealEntry.CATEGORY_CHOICES,
            "filter_category": category,
            "filter_q": query,
        },
    )


@login_required
def water_list_view(request):
    if request.method == "POST":
        action = request.POST.get("action", "create")
        if action == "delete":
            entry = get_object_or_404(WaterEntry, pk=request.POST.get("entry_id"), user=request.user)
            entry.delete()
            messages.success(request, "Wassereintrag wurde gelöscht.")
            return redirect("tracker:water_list")

        instance = None
        if action == "update" and request.POST.get("entry_id"):
            instance = get_object_or_404(WaterEntry, pk=request.POST.get("entry_id"), user=request.user)
        form = WaterEntryForm(request.POST, instance=instance)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.user = request.user
            entry.save()
            messages.success(
                request,
                "Wassereintrag aktualisiert." if instance else "Wassereintrag gespeichert.",
            )
            return redirect(request.POST.get("next") or "tracker:water_list")
        messages.error(request, "Bitte überprüfe die Eingaben für Wasser.")

    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    drink_type = request.GET.get("drink_type", "").strip()
    query = request.GET.get("q", "").strip()

    entries = _apply_date_filters(WaterEntry.objects.filter(user=request.user), date_from, date_to)
    if drink_type:
        entries = entries.filter(drink_type=drink_type)
    if query:
        entries = entries.filter(notes__icontains=query)

    if request.GET.get("export") == "csv":
        rows = [
            [w.date.isoformat(), w.get_drink_type_display(), w.amount_ml, w.notes]
            for w in entries
        ]
        return export_queryset_csv(
            "wasser_export.csv",
            ["Datum", "Getränk", "Menge (ml)", "Notizen"],
            rows,
        )

    today = timezone.localdate()
    profile = get_or_create_profile(request.user)
    latest_weight = WeightEntry.objects.filter(user=request.user).first()
    recommended_water_ml = profile.calculate_water_need_ml(latest_weight.weight_kg if latest_weight else None)
    today_water_ml = int(
        WaterEntry.objects.filter(user=request.user, date=today).aggregate(total=Sum("amount_ml"))["total"] or 0
    )
    total_filtered_ml = int(entries.aggregate(total=Sum("amount_ml"))["total"] or 0)

    return render(
        request,
        "tracker/water_list.html",
        {
            "water_entries": entries,
            "water_form": WaterEntryForm(initial={"date": today, "amount_ml": 250}),
            "drink_choices": WaterEntry.DRINK_CHOICES,
            "filter_date_from": date_from,
            "filter_date_to": date_to,
            "filter_drink_type": drink_type,
            "filter_q": query,
            "total_filtered_ml": total_filtered_ml,
            "today_water_ml": today_water_ml,
            "water_goal_ml": profile.daily_water_goal_ml or 2500,
            "recommended_water_ml": recommended_water_ml,
        },
    )


@login_required
def analytics_view(request):
    try:
        days_count = int(request.GET.get("days", 30))
    except (TypeError, ValueError):
        days_count = 30
    if days_count not in (7, 30, 90, 365):
        days_count = 30

    today = timezone.localdate()
    start_date = today - timedelta(days=days_count - 1)
    profile = get_or_create_profile(request.user)

    meals_qs = MealEntry.objects.filter(user=request.user, date__gte=start_date, date__lte=today)
    weights_qs = WeightEntry.objects.filter(user=request.user, date__gte=start_date, date__lte=today).order_by("date", "created_at")

    meal_stats = meals_qs.aggregate(
        total_calories=Sum("calories"),
        total_protein=Sum("protein_g"),
        total_carbs=Sum("carbs_g"),
        total_fat=Sum("fat_g"),
        total_fiber=Sum("fiber_g"),
    )
    daily_cal_rows = list(
        meals_qs.values("date").annotate(total=Sum("calories")).order_by("date")
    )
    avg_daily_calories = (
        round(sum(r["total"] for r in daily_cal_rows) / len(daily_cal_rows))
        if daily_cal_rows
        else 0
    )

    weight_list = list(weights_qs)
    baseline_weight = (
        WeightEntry.objects.filter(user=request.user, date__lt=start_date)
        .order_by("-date", "-created_at")
        .first()
    )
    weight_delta = None
    if len(weight_list) >= 2:
        first_w = baseline_weight.weight_kg if baseline_weight and weight_list[0].date > start_date else weight_list[0].weight_kg
        weight_delta = weight_list[-1].weight_kg - first_w
    elif len(weight_list) == 1 and baseline_weight:
        weight_delta = weight_list[0].weight_kg - baseline_weight.weight_kg

    weight_chart = build_weight_chart_series(request.user, start_date, today, profile.target_weight_kg)

    category_breakdown = list(
        meals_qs.values("category")
        .annotate(total_calories=Sum("calories"))
        .order_by("-total_calories")
    )
    cat_labels_map = dict(MealEntry.CATEGORY_CHOICES)
    for row in category_breakdown:
        row["label"] = cat_labels_map.get(row["category"], row["category"])

    macro_chart = build_macro_calorie_chart_series(
        request.user, start_date, today, profile.daily_calorie_goal or 2000
    )
    water_goal_ml = profile.daily_water_goal_ml or 2500
    water_qs = WaterEntry.objects.filter(user=request.user, date__gte=start_date, date__lte=today)
    total_water_ml = int(water_qs.aggregate(total=Sum("amount_ml"))["total"] or 0)
    daily_water_rows = list(water_qs.values("date").annotate(total=Sum("amount_ml")))
    avg_daily_water_ml = (
        round(sum(r["total"] for r in daily_water_rows) / len(daily_water_rows))
        if daily_water_rows
        else 0
    )
    water_chart = build_water_chart_series(request.user, start_date, today, water_goal_ml)

    cal_goal = profile.daily_calorie_goal or 2000
    daily_cal_totals = [
        p + c + f + fib + o
        for p, c, f, fib, o in zip(
            macro_chart["protein_kcal"],
            macro_chart["carbs_kcal"],
            macro_chart["fat_kcal"],
            macro_chart["fiber_kcal"],
            macro_chart["other_kcal"],
        )
    ]
    cal_spark_line, cal_spark_area = build_sparkline_paths([float(v) for v in daily_cal_totals])
    prot_spark_line, prot_spark_area = build_sparkline_paths([float(v) for v in macro_chart["protein_g"]])
    fiber_spark_line, fiber_spark_area = build_sparkline_paths([float(v) for v in macro_chart["fiber_g"]])
    weight_spark_line, weight_spark_area = build_sparkline_paths(
        [float(v) for v in weight_chart["values"] if v is not None]
    )
    water_spark_line, water_spark_area = build_sparkline_paths([float(v) for v in water_chart["values"]])

    fiber_goal_g = profile.daily_fiber_goal_g or 30
    active_meal_days = len(daily_cal_rows) or 1
    avg_daily_fiber = round(float(meal_stats["total_fiber"] or 0) / active_meal_days, 1) if daily_cal_rows else 0.0
    avg_fiber_ratio = avg_daily_fiber / fiber_goal_g if fiber_goal_g > 0 else 0.0

    avg_cal_ratio = avg_daily_calories / cal_goal if cal_goal > 0 else 0.0
    avg_water_ratio = avg_daily_water_ml / water_goal_ml if water_goal_ml > 0 else 0.0

    return render(
        request,
        "tracker/analytics.html",
        {
            "days_count": days_count,
            "start_date": start_date,
            "today": today,
            "profile": profile,
            "meal_count": meals_qs.count(),
            "weight_count": weights_qs.count(),
            "meal_stats": meal_stats,
            "avg_daily_calories": avg_daily_calories,
            "avg_cal_pct": min(100, round(avg_cal_ratio * 100)),
            "avg_cal_segments": build_progress_segments(avg_cal_ratio),
            "weight_delta": weight_delta,
            "latest_weight": weight_list[-1] if weight_list else None,
            "category_breakdown": category_breakdown,
            "macro_chart_data": macro_chart,
            "total_water_ml": total_water_ml,
            "avg_daily_water_ml": avg_daily_water_ml,
            "water_goal_ml": water_goal_ml,
            "avg_water_pct": min(100, round(avg_water_ratio * 100)),
            "avg_water_segments": build_progress_segments(avg_water_ratio),
            "water_chart_data": water_chart,
            "weight_chart_data": weight_chart,
            "cal_spark_line": cal_spark_line,
            "cal_spark_area": cal_spark_area,
            "prot_spark_line": prot_spark_line,
            "prot_spark_area": prot_spark_area,
            "fiber_goal_g": fiber_goal_g,
            "avg_daily_fiber": avg_daily_fiber,
            "avg_fiber_pct": min(100, round(avg_fiber_ratio * 100)),
            "avg_fiber_segments": build_progress_segments(avg_fiber_ratio),
            "fiber_spark_line": fiber_spark_line,
            "fiber_spark_area": fiber_spark_area,
            "weight_spark_line": weight_spark_line,
            "weight_spark_area": weight_spark_area,
            "water_spark_line": water_spark_line,
            "water_spark_area": water_spark_area,
        },
    )


@login_required
def profile_view(request):
    profile = get_or_create_profile(request.user)
    latest_weight = WeightEntry.objects.filter(user=request.user).first()
    ref_weight = latest_weight.weight_kg if latest_weight else None
    recommended_tdee = profile.calculate_tdee(ref_weight)
    recommended_water_ml = profile.calculate_water_need_ml(ref_weight)
    recommended_fiber_g = profile.calculate_fiber_need_g()

    if request.method == "POST":
        if request.POST.get("apply_tdee") == "1" and recommended_tdee:
            profile.daily_calorie_goal = recommended_tdee
            profile.save(update_fields=["daily_calorie_goal", "updated_at"])
            messages.success(request, f"Kalorienziel auf {recommended_tdee} kcal übernommen.")
            return redirect("tracker:profile")

        if request.POST.get("apply_water_need") == "1" and recommended_water_ml:
            profile.daily_water_goal_ml = recommended_water_ml
            profile.save(update_fields=["daily_water_goal_ml", "updated_at"])
            messages.success(request, f"Wasserziel auf {recommended_water_ml} ml übernommen.")
            return redirect("tracker:profile")

        if request.POST.get("apply_fiber_need") == "1":
            profile.daily_fiber_goal_g = recommended_fiber_g
            profile.save(update_fields=["daily_fiber_goal_g", "updated_at"])
            messages.success(request, f"Ballaststoffziel auf {recommended_fiber_g} g übernommen.")
            return redirect("tracker:profile")

        form = UserProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Profil & Stammdaten gespeichert.")
            return redirect("tracker:profile")
    else:
        form = UserProfileForm(instance=profile)

    return render(
        request,
        "tracker/profile.html",
        {
            "form": form,
            "profile": profile,
            "latest_weight": latest_weight,
            "recommended_tdee": recommended_tdee,
            "recommended_water_ml": recommended_water_ml,
            "recommended_fiber_g": recommended_fiber_g,
        },
    )

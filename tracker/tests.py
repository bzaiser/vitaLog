import json
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from design_studio.storage import get_storage_adapter

from .models import DailyActivity, MealEntry, MealTemplate, UserProfile, WaterEntry, WeightEntry
from .services import build_macro_calorie_chart_series, build_weight_chart_series


class TrackerModelsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="secret123")

    def test_profile_created_automatically_and_tdee(self):
        profile = self.user.profile
        self.assertIsInstance(profile, UserProfile)
        profile.height_cm = 175
        profile.age = 30
        profile.gender = "M"
        profile.activity_level = Decimal("1.55")
        profile.save()
        tdee = profile.calculate_tdee(Decimal("80.00"))
        self.assertIsNotNone(tdee)
        self.assertGreater(tdee, 2000)

    def test_meal_and_weight_str_and_ordering(self):
        today = timezone.localdate()
        yesterday = today - timedelta(days=1)
        m1 = MealEntry.objects.create(user=self.user, date=yesterday, name="Haferflocken", calories=350)
        m2 = MealEntry.objects.create(user=self.user, date=today, name="Salat", calories=450)
        self.assertEqual(list(MealEntry.objects.filter(user=self.user)), [m2, m1])
        self.assertIn("Salat", str(m2))

        w1 = WeightEntry.objects.create(user=self.user, date=yesterday, weight_kg=Decimal("82.50"))
        w2 = WeightEntry.objects.create(user=self.user, date=today, weight_kg=Decimal("81.90"))
        self.assertEqual(list(WeightEntry.objects.filter(user=self.user)), [w2, w1])
        self.assertIn("81.90 kg", str(w2))


class TrackerViewsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="bob", password="password123")
        self.other = User.objects.create_user(username="eve", password="password123")
        self.client.force_login(self.user)

    def test_anonymous_redirects_to_login(self):
        self.client.logout()
        for url_name in ("tracker:dashboard", "tracker:meals_list", "tracker:weights_list", "tracker:analytics", "tracker:profile"):
            resp = self.client.get(reverse(url_name))
            self.assertEqual(resp.status_code, 302)
            self.assertIn("/accounts/login/", resp.url)

    def test_registration_flow(self):
        self.client.logout()
        # Erster Benutzer ohne vorhandenen Superuser wird automatisch Admin
        resp = self.client.post(
            reverse("tracker:register"),
            {
                "username": "firstadmin",
                "email": "admin@example.com",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )
        self.assertRedirects(resp, reverse("tracker:dashboard"))
        first_user = User.objects.get(username="firstadmin")
        self.assertTrue(first_user.is_staff)
        self.assertTrue(first_user.is_superuser)

        # Zweiter Benutzer bleibt normaler Benutzer
        self.client.logout()
        resp2 = self.client.post(
            reverse("tracker:register"),
            {
                "username": "newuser",
                "email": "new@example.com",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )
        self.assertRedirects(resp2, reverse("tracker:dashboard"))
        second_user = User.objects.get(username="newuser")
        self.assertFalse(second_user.is_staff)
        self.assertFalse(second_user.is_superuser)

    def test_dashboard_renders_kpis(self):
        today = timezone.localdate()
        MealEntry.objects.create(user=self.user, date=today, name="Frühstück", calories=600)
        WeightEntry.objects.create(user=self.user, date=today, weight_kg=Decimal("78.40"))
        resp = self.client.get(reverse("tracker:dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "78,4")
        self.assertContains(resp, "600")
        self.assertContains(resp, "vitaLog")

        resp_30 = self.client.get(reverse("tracker:dashboard"), {"days": 30})
        self.assertEqual(resp_30.status_code, 200)
        self.assertContains(resp_30, "Gewichtsverlauf (30 Tage)")

    def test_meals_crud_filter_and_csv_export(self):
        today = timezone.localdate().isoformat()
        # Create
        resp = self.client.post(
            reverse("tracker:meals_list"),
            {
                "action": "create",
                "date": today,
                "category": "breakfast",
                "name": "Müsli",
                "calories": 420,
                "protein_g": "15.0",
                "carbs_g": "60.0",
                "fat_g": "10.0",
                "fiber_g": "8.5",
                "notes": "mit Beeren",
                "save_as_template": "on",
            },
        )
        self.assertRedirects(resp, reverse("tracker:meals_list"))
        meal = MealEntry.objects.get(user=self.user, name="Müsli")
        self.assertEqual(meal.fiber_g, Decimal("8.5"))
        # 15*4 + 60*4 + 10*9 = 60 + 240 + 90 = 390 (Ballaststoffe nicht doppelt)
        self.assertEqual(meal.calories, 390)
        self.assertTrue(MealTemplate.objects.filter(user=self.user, name="Müsli", category="breakfast").exists())

        # Validation: all macros 0 must be rejected
        bad_resp = self.client.post(
            reverse("tracker:meals_list"),
            {
                "action": "create",
                "date": today,
                "category": "snack",
                "name": "Ungültig",
                "protein_g": "0",
                "carbs_g": "0",
                "fat_g": "0",
                "fiber_g": "0",
            },
        )
        self.assertEqual(bad_resp.status_code, 200)
        self.assertFalse(MealEntry.objects.filter(user=self.user, name="Ungültig").exists())

        # Validation: fiber_g > carbs_g must be rejected
        bad_fiber = self.client.post(
            reverse("tracker:meals_list"),
            {
                "action": "create",
                "date": today,
                "category": "snack",
                "name": "ZuVielBallast",
                "protein_g": "10",
                "carbs_g": "5",
                "fat_g": "2",
                "fiber_g": "8",
            },
        )
        self.assertEqual(bad_fiber.status_code, 200)
        self.assertFalse(MealEntry.objects.filter(user=self.user, name="ZuVielBallast").exists())

        # Update
        resp = self.client.post(
            reverse("tracker:meals_list"),
            {
                "action": "update",
                "entry_id": meal.id,
                "date": today,
                "category": "breakfast",
                "name": "Protein-Müsli",
                "calories": 9999,
                "protein_g": "25.0",
                "carbs_g": "55.0",
                "fat_g": "12.0",
                "fiber_g": "9.0",
                "notes": "",
            },
        )
        self.assertRedirects(resp, reverse("tracker:meals_list"))
        meal.refresh_from_db()
        self.assertEqual(meal.name, "Protein-Müsli")
        # 25*4 + 55*4 + 12*9 = 100 + 220 + 108 = 428
        self.assertEqual(meal.calories, 428)

        # Filter
        resp = self.client.get(reverse("tracker:meals_list"), {"q": "Protein", "category": "breakfast"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Protein-Müsli")

        # CSV Export
        csv_resp = self.client.get(reverse("tracker:meals_list"), {"export": "csv"})
        self.assertEqual(csv_resp.status_code, 200)
        self.assertIn("text/csv", csv_resp["Content-Type"])
        self.assertIn("Protein-Müsli", csv_resp.content.decode("utf-8"))

        # Isolation: other user cannot delete
        self.client.force_login(self.other)
        resp_other = self.client.post(reverse("tracker:meals_list"), {"action": "delete", "entry_id": meal.id})
        self.assertEqual(resp_other.status_code, 404)

        # Delete as owner
        self.client.force_login(self.user)
        self.client.post(reverse("tracker:meals_list"), {"action": "delete", "entry_id": meal.id})
        self.assertFalse(MealEntry.objects.filter(pk=meal.id).exists())

    def test_weights_crud_filter_and_csv_export(self):
        today = timezone.localdate().isoformat()
        resp = self.client.post(
            reverse("tracker:weights_list"),
            {
                "action": "create",
                "date": today,
                "weight_kg": "80.50",
                "body_fat_pct": "18.2",
                "notes": "morgens",
            },
        )
        self.assertRedirects(resp, reverse("tracker:weights_list"))
        entry = WeightEntry.objects.get(user=self.user)

        self.client.post(
            reverse("tracker:weights_list"),
            {
                "action": "update",
                "entry_id": entry.id,
                "date": today,
                "weight_kg": "80.10",
                "body_fat_pct": "18.0",
                "notes": "aktualisiert",
            },
        )
        entry.refresh_from_db()
        self.assertEqual(entry.weight_kg, Decimal("80.10"))

        csv_resp = self.client.get(reverse("tracker:weights_list"), {"export": "csv"})
        self.assertEqual(csv_resp.status_code, 200)
        self.assertIn("80.10", csv_resp.content.decode("utf-8"))

        self.client.post(reverse("tracker:weights_list"), {"action": "delete", "entry_id": entry.id})
        self.assertFalse(WeightEntry.objects.filter(pk=entry.id).exists())

    def test_weights_list_shows_day_calories_and_remaining(self):
        today = timezone.localdate()
        self.user.profile.daily_calorie_goal = 2200
        self.user.profile.save()
        MealEntry.objects.create(user=self.user, date=today, name="Mittag", calories=800)
        WeightEntry.objects.create(user=self.user, date=today, weight_kg=Decimal("79.50"))

        resp = self.client.get(reverse("tracker:weights_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "800 kcal")
        self.assertContains(resp, "1400 kcal")

    def test_meal_templates_crud_and_modal_integration(self):
        resp = self.client.post(
            reverse("tracker:meal_templates_list"),
            {
                "action": "create",
                "category": "snack",
                "name": "Apfel & Nüsse",
                "calories": 220,
                "protein_g": "5.0",
                "carbs_g": "20.0",
                "fat_g": "12.0",
                "fiber_g": "4.5",
                "notes": "Nachmittags",
            },
        )
        self.assertRedirects(resp, reverse("tracker:meal_templates_list"))
        tpl = MealTemplate.objects.get(user=self.user, name="Apfel & Nüsse")

        meals_resp = self.client.get(reverse("tracker:meals_list"))
        self.assertContains(meals_resp, "Apfel &amp; Nüsse")
        self.assertContains(meals_resp, 'data-fiber="4,5"')

        self.client.post(
            reverse("tracker:meal_templates_list"),
            {"action": "delete", "entry_id": tpl.id},
        )
        self.assertFalse(MealTemplate.objects.filter(pk=tpl.id).exists())

    def test_macro_calorie_stacked_chart_series_and_views(self):
        today = timezone.localdate()
        self.user.profile.daily_calorie_goal = 2000
        self.user.profile.save()
        MealEntry.objects.create(
            user=self.user,
            date=today,
            name="Lachs Bowl",
            calories=600,
            protein_g=Decimal("40.0"),  # 160 kcal
            carbs_g=Decimal("50.0"),    # 200 kcal
            fat_g=Decimal("20.0"),      # 180 kcal
            fiber_g=Decimal("10.0"),    # 20 kcal -> sum 560, other = 40
        )
        series = build_macro_calorie_chart_series(self.user, today, today, 2000)
        self.assertEqual(series["protein_kcal"], [160])
        self.assertEqual(series["carbs_kcal"], [160])  # (50 - 10) * 4
        self.assertEqual(series["fiber_kcal"], [40])   # 10 * 4
        self.assertEqual(series["fat_kcal"], [180])
        self.assertNotIn("other_kcal", series)
        self.assertEqual(series["goal"], 2000)
        self.assertEqual(series["suggested_max"], 2200)

        dash_resp = self.client.get(reverse("tracker:dashboard"))
        self.assertContains(dash_resp, "ds-macro-chart-data")
        an_resp = self.client.get(reverse("tracker:analytics"), {"days": 7})
        self.assertContains(an_resp, "an-macro-chart-data")

    def test_water_tracking_crud_need_and_analytics(self):
        today = timezone.localdate()
        WeightEntry.objects.create(user=self.user, date=today, weight_kg=Decimal("80.00"))
        self.assertEqual(self.user.profile.calculate_water_need_ml(Decimal("80.00")), 2800)

        resp = self.client.post(
            reverse("tracker:water_list"),
            {
                "action": "create",
                "date": today.isoformat(),
                "drink_type": "water",
                "amount_ml": 500,
                "notes": "Morgens",
            },
        )
        self.assertRedirects(resp, reverse("tracker:water_list"))
        w_entry = WaterEntry.objects.get(user=self.user)
        self.assertEqual(w_entry.amount_ml, 500)

        dash_resp = self.client.get(reverse("tracker:dashboard"))
        self.assertContains(dash_resp, "500")

        an_resp = self.client.get(reverse("tracker:analytics"), {"days": 7})
        self.assertContains(an_resp, "an-water-chart-data")

        csv_resp = self.client.get(reverse("tracker:water_list"), {"export": "csv"})
        self.assertEqual(csv_resp.status_code, 200)
        self.assertIn("500", csv_resp.content.decode("utf-8"))

        self.client.post(
            reverse("tracker:water_list"),
            {"action": "delete", "entry_id": w_entry.id},
        )
        self.assertFalse(WaterEntry.objects.filter(pk=w_entry.id).exists())

    def test_weight_trend_carries_forward_past_baseline_and_nonzero_scale(self):
        today = timezone.localdate()
        # Gewicht vor 20 Tagen (außerhalb des 7-Tage-Fensters) und heute
        WeightEntry.objects.create(user=self.user, date=today - timedelta(days=20), weight_kg=Decimal("84.00"))
        WeightEntry.objects.create(user=self.user, date=today, weight_kg=Decimal("82.50"))

        start_7d = today - timedelta(days=6)
        series = build_weight_chart_series(self.user, start_7d, today, Decimal("78.00"))
        self.assertEqual(len(series["values"]), 7)
        self.assertEqual(series["values"][0], 84.0)
        self.assertEqual(series["values"][-1], 82.5)
        self.assertEqual(series["suggested_min"], 77.0)
        self.assertEqual(series["suggested_max"], 85.0)

        an_resp = self.client.get(reverse("tracker:analytics"), {"days": 7})
        self.assertContains(an_resp, "an-weight-chart-data")
        self.assertContains(an_resp, "-1,5")

    def test_kpi_cards_support_design_studio_features(self):
        today = timezone.localdate()
        yesterday = today - timedelta(days=1)
        MealEntry.objects.create(user=self.user, date=yesterday, name="Abend", calories=500, protein_g=Decimal("30.0"))
        MealEntry.objects.create(user=self.user, date=today, name="Mittag", calories=700, protein_g=Decimal("40.0"))
        WeightEntry.objects.create(user=self.user, date=yesterday, weight_kg=Decimal("81.00"))
        WeightEntry.objects.create(user=self.user, date=today, weight_kg=Decimal("80.50"))

        for url in (reverse("tracker:dashboard"), reverse("tracker:analytics") + "?days=7"):
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200)
            self.assertContains(resp, "kpi-spotlight")
            self.assertContains(resp, "kpi-watermark-icon")
            self.assertContains(resp, "kpi-sparkline-svg")
            self.assertContains(resp, "kpi-segmented-wrap")
            self.assertContains(resp, "data-target-url=")
        dash = self.client.get(reverse("tracker:dashboard"))
        self.assertContains(dash, "Basis 2000 + Beweg. 0 kcal")
        self.assertEqual(len(dash.context["calorie_segments"]), 10)

    def test_daily_activity_presets_and_apple_watch_custom(self):
        today = timezone.localdate()
        self.user.profile.daily_calorie_goal = 2000
        self.user.profile.activity_kcal_medium = 550
        self.user.profile.save()
        MealEntry.objects.create(user=self.user, date=today, name="Mittag", calories=1000)
        WeightEntry.objects.create(user=self.user, date=today, weight_kg=Decimal("80.00"))

        # Preset-Auswahl ("medium" -> +550 kcal aus Profil)
        resp = self.client.post(reverse("tracker:set_daily_activity"), {"level": "medium"})
        self.assertRedirects(resp, reverse("tracker:dashboard"))
        act = DailyActivity.objects.get(user=self.user, date=today)
        self.assertEqual(act.level, "medium")
        self.assertEqual(act.calories_burned, 550)

        # Verbleibende Kalorien = 2000 + 550 - 1000 = 1550
        dash = self.client.get(reverse("tracker:dashboard"))
        self.assertContains(dash, "1550")
        w_resp = self.client.get(reverse("tracker:weights_list"))
        self.assertContains(w_resp, "1550 kcal")

        # Apple Watch / Manuelle Eingabe (+745 kcal)
        self.client.post(reverse("tracker:set_daily_activity"), {"level": "custom", "custom_kcal": 745})
        act.refresh_from_db()
        self.assertEqual(act.level, "custom")
        self.assertEqual(act.calories_burned, 745)
        dash2 = self.client.get(reverse("tracker:dashboard"))
        self.assertContains(dash2, "1745")
        self.assertContains(dash2, "ds-activity-chart-data")

        # Vergangenes Datum ändern (z. B. vor 3 Tagen)
        past_date = (today - timedelta(days=3)).isoformat()
        self.client.post(
            reverse("tracker:set_daily_activity"),
            {"date": past_date, "level": "custom", "custom_kcal": 620},
        )
        past_act = DailyActivity.objects.get(user=self.user, date=today - timedelta(days=3))
        self.assertEqual(past_act.calories_burned, 620)

        an_resp = self.client.get(reverse("tracker:analytics"), {"days": 7})
        self.assertContains(an_resp, "an-activity-chart-data")
        self.assertContains(an_resp, "745")

    def test_body_fat_estimation_and_trend_views(self):
        today = timezone.localdate()
        self.user.profile.height_cm = 180
        self.user.profile.age = 35
        self.user.profile.gender = "M"
        self.user.profile.activity_level = Decimal("1.55")
        self.user.profile.target_body_fat_pct = Decimal("15.0")
        self.user.profile.save()

        est = self.user.profile.estimate_body_fat_pct(Decimal("80.00"))
        self.assertIsNotNone(est)
        self.assertGreater(est, Decimal("10.0"))
        self.assertLess(est, Decimal("30.0"))

        WeightEntry.objects.create(user=self.user, date=today - timedelta(days=5), weight_kg=Decimal("82.00"), body_fat_pct=Decimal("20.5"))
        WeightEntry.objects.create(user=self.user, date=today, weight_kg=Decimal("80.00"), body_fat_pct=Decimal("19.0"))

        dash = self.client.get(reverse("tracker:dashboard"))
        self.assertContains(dash, "19,0")
        self.assertContains(dash, "ds-weight-bf-profile")

        an = self.client.get(reverse("tracker:analytics"), {"days": 30})
        self.assertContains(an, "Körperfett-Trend")
        self.assertContains(an, "-1,5")

    def test_analytics_and_profile_views(self):
        today = timezone.localdate()
        MealEntry.objects.create(user=self.user, date=today, name="Mittag", calories=750)
        WeightEntry.objects.create(user=self.user, date=today, weight_kg=Decimal("79.00"))

        resp_an = self.client.get(reverse("tracker:analytics"), {"days": 7})
        self.assertEqual(resp_an.status_code, 200)
        self.assertContains(resp_an, "750")

        resp_prof = self.client.post(
            reverse("tracker:profile"),
            {
                "first_name": "Bob",
                "last_name": "Tester",
                "email": "bob@example.com",
                "height_cm": 180,
                "age": 32,
                "gender": "M",
                "activity_level": "1.55",
                "start_weight_kg": "85.00",
                "target_weight_kg": "75.00",
                "daily_calorie_goal": 2100,
                "daily_water_goal_ml": 2800,
                "daily_fiber_goal_g": 32,
                "activity_kcal_low": 250,
                "activity_kcal_medium": 550,
                "activity_kcal_high": 1100,
            },
        )
        self.assertRedirects(resp_prof, reverse("tracker:profile"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Bob")
        self.assertEqual(self.user.profile.daily_calorie_goal, 2100)
        self.assertEqual(self.user.profile.daily_water_goal_ml, 2800)
        self.assertEqual(self.user.profile.daily_fiber_goal_g, 32)
        self.assertEqual(self.user.profile.activity_kcal_medium, 550)

        # Design Studio link integrated in profile
        prof_get = self.client.get(reverse("tracker:profile"))
        self.assertContains(prof_get, reverse("design_studio:studio"))

    def test_admin_menu_item_visibility_for_staff(self):
        resp_user = self.client.get(reverse("tracker:dashboard"))
        self.assertNotContains(resp_user, 'href="/admin/"')

        self.user.is_staff = True
        self.user.save()
        resp_staff = self.client.get(reverse("tracker:dashboard"))
        self.assertContains(resp_staff, 'href="/admin/"')


class DesignStudioIntegrationTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="designer", password="password123")
        self.client.force_login(self.user)

    def test_studio_page_and_cancel_back_url(self):
        resp = self.client.get(reverse("design_studio:studio"), {"next": reverse("tracker:profile")})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, reverse("tracker:profile"))
        self.assertContains(resp, "Abbrechen")

    def test_save_studio_settings(self):
        resp = self.client.post(
            reverse("design_studio:save"),
            {
                "gradient_start": "#112233",
                "gradient_end": "#445566",
                "theme_mood": "modern",
                "theme_bg_mode": "light",
                "theme_bg_custom": "#ffffff",
                "theme_card_surface": "auto",
                "theme_bg_svg_mode": "auto",
                "theme_menu_layout": "top",
                "theme_menu_style": "auto",
                "next": reverse("tracker:dashboard"),
            },
        )
        self.assertRedirects(resp, reverse("tracker:dashboard"))
        ts = get_storage_adapter().get_settings(self.user)
        self.assertEqual(ts["c1"], "#112233")
        self.assertEqual(ts["c2"], "#445566")

    def test_toggle_night_mode(self):
        adapter = get_storage_adapter()
        initial = adapter.get_settings(self.user)
        self.assertNotEqual(initial["bg_mode"], "dark")

        resp = self.client.get(reverse("design_studio:toggle_night"), HTTP_REFERER="/")
        self.assertEqual(resp.status_code, 302)
        after_night = adapter.get_settings(self.user)
        self.assertEqual(after_night["bg_mode"], "dark")

        self.client.get(reverse("design_studio:toggle_night"), HTTP_REFERER="/")
        after_day = adapter.get_settings(self.user)
        self.assertNotEqual(after_day["bg_mode"], "dark")

    def test_menu_studio_customize_and_reset(self):
        custom_menu = [
            {
                "id": "meals",
                "label": "Essen",
                "icon": "bi-egg-fried",
                "display": "icon_text",
                "zone": "main",
                "visible": True,
                "order": 1,
            },
            {
                "id": "design_studio",
                "label": "Studio",
                "icon": "bi-palette",
                "display": "icon_only",
                "zone": "utility",
                "visible": False,  # locked item must remain visible in resolved menu
                "order": 2,
            },
        ]
        self.client.post(
            reverse("design_studio:save"),
            {"menu_config_json": json.dumps(custom_menu)},
        )
        dash = self.client.get(reverse("tracker:dashboard"))
        self.assertContains(dash, "Essen")
        self.assertContains(dash, reverse("design_studio:studio"))

        # Reset menu config
        self.client.post(
            reverse("design_studio:save"),
            {"menu_config_json": "RESET"},
        )
        ts = get_storage_adapter().get_settings(self.user)
        self.assertEqual(ts["menu_config"], [])

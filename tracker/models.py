from decimal import Decimal

from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone


class UserProfile(models.Model):
    """Persönliche Stammdaten und Zielwerte eines Benutzers."""

    GENDER_CHOICES = [
        ("M", "Männlich"),
        ("W", "Weiblich"),
        ("D", "Divers"),
    ]

    ACTIVITY_CHOICES = [
        (Decimal("1.20"), "Sitzend (kaum Bewegung)"),
        (Decimal("1.37"), "Leicht aktiv (1-3x Sport/Woche)"),
        (Decimal("1.55"), "Mäßig aktiv (3-5x Sport/Woche)"),
        (Decimal("1.72"), "Sehr aktiv (6-7x Sport/Woche)"),
        (Decimal("1.90"), "Extrem aktiv (körperliche Arbeit / 2x Training)"),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name="Benutzer",
    )
    height_cm = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Größe (cm)",
    )
    age = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Alter",
    )
    gender = models.CharField(
        max_length=1,
        choices=GENDER_CHOICES,
        default="M",
        verbose_name="Geschlecht",
    )
    activity_level = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        choices=ACTIVITY_CHOICES,
        default=Decimal("1.37"),
        verbose_name="Aktivitätslevel",
    )
    start_weight_kg = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Startgewicht (kg)",
    )
    target_weight_kg = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Zielgewicht (kg)",
    )
    target_body_fat_pct = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
        verbose_name="Ziel-Körperfett (%)",
    )
    daily_calorie_goal = models.PositiveIntegerField(
        default=2000,
        verbose_name="Tägliches Kalorienziel (kcal)",
    )
    daily_water_goal_ml = models.PositiveIntegerField(
        default=2500,
        verbose_name="Tägliches Wasserziel (ml)",
    )
    daily_fiber_goal_g = models.PositiveIntegerField(
        default=30,
        verbose_name="Tägliches Ballaststoffziel (g)",
    )
    activity_kcal_low = models.PositiveIntegerField(
        default=200,
        verbose_name="Bewegung Wenig (kcal)",
    )
    activity_kcal_medium = models.PositiveIntegerField(
        default=500,
        verbose_name="Bewegung Mittel (kcal)",
    )
    activity_kcal_high = models.PositiveIntegerField(
        default=1000,
        verbose_name="Bewegung Hoch (kcal)",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Benutzerprofil"
        verbose_name_plural = "Benutzerprofile"

    def __str__(self) -> str:
        return f"Profil ({self.user.username})"

    def calculate_tdee(self, weight_kg: Decimal | None = None) -> int | None:
        """Berechnet den geschätzten Tagesbedarf (Mifflin-St Jeor) in kcal."""
        ref_weight = weight_kg or self.start_weight_kg
        if not (ref_weight and self.height_cm and self.age):
            return None
        base = (
            Decimal("10") * Decimal(ref_weight)
            + Decimal("6.25") * Decimal(self.height_cm)
            - Decimal("5") * Decimal(self.age)
        )
        if self.gender == "M":
            bmr = base + Decimal("5")
        elif self.gender == "W":
            bmr = base - Decimal("161")
        else:
            bmr = base - Decimal("78")
        return max(1000, int(bmr * self.activity_level))

    def calculate_water_need_ml(self, weight_kg: Decimal | None = None) -> int | None:
        """Berechnet den geschätzten täglichen Wasserbedarf (~35 ml pro kg Körpergewicht)."""
        ref_weight = weight_kg or self.start_weight_kg
        if not ref_weight:
            return None
        return max(1500, round(float(ref_weight) * 35 / 50) * 50)

    def calculate_fiber_need_g(self) -> int:
        """Berechnet die tägliche Ballaststoff-Empfehlung (DGE: ~14 g pro 1.000 kcal)."""
        cal_goal = self.daily_calorie_goal or 2000
        return max(25, round(cal_goal / 1000 * 14))

    def estimate_body_fat_pct(self, weight_kg: Decimal | None = None) -> Decimal | None:
        """Schätzt den Körperfettanteil (%) aus Größe, Alter, Gewicht, Geschlecht & Bewegungsmuster."""
        ref_weight = weight_kg or self.start_weight_kg
        if not (ref_weight and self.height_cm and self.age):
            return None
        height_m = float(self.height_cm) / 100.0
        if height_m <= 0:
            return None
        bmi = float(ref_weight) / (height_m * height_m)
        sex_factor = 1.0 if self.gender == "M" else (0.0 if self.gender == "W" else 0.5)
        raw_bf = 1.20 * bmi + 0.23 * float(self.age) - 10.8 * sex_factor - 5.4

        act = float(self.activity_level or Decimal("1.37"))
        if act >= 1.90:
            raw_bf -= 3.0
        elif act >= 1.72:
            raw_bf -= 2.0
        elif act >= 1.55:
            raw_bf -= 1.0

        clamped = max(4.0, min(60.0, raw_bf))
        return Decimal(str(round(clamped, 1)))


@receiver(post_save, sender=User)
def ensure_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)


class MealEntry(models.Model):
    """Täglicher Mahlzeiteneintrag mit Kalorien und Makronährstoffen."""

    CATEGORY_CHOICES = [
        ("breakfast", "Frühstück"),
        ("lunch", "Mittagessen"),
        ("dinner", "Abendessen"),
        ("snack", "Snack"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="meals",
        verbose_name="Benutzer",
    )
    date = models.DateField(
        default=timezone.localdate,
        db_index=True,
        verbose_name="Datum",
    )
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default="lunch",
        verbose_name="Kategorie",
    )
    name = models.CharField(max_length=120, verbose_name="Mahlzeit")
    calories = models.PositiveIntegerField(verbose_name="Kalorien (kcal)")
    protein_g = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        default=Decimal("0.0"),
        verbose_name="Eiweiß (g)",
    )
    carbs_g = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        default=Decimal("0.0"),
        verbose_name="Kohlenhydrate (g)",
    )
    fat_g = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        default=Decimal("0.0"),
        verbose_name="Fett (g)",
    )
    fiber_g = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        default=Decimal("0.0"),
        verbose_name="davon Ballaststoffe (g)",
    )
    notes = models.TextField(blank=True, verbose_name="Notizen")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "Mahlzeit"
        verbose_name_plural = "Mahlzeiten"

    def __str__(self) -> str:
        return f"{self.date} - {self.name} ({self.calories} kcal)"


class MealTemplate(models.Model):
    """Wiederkehrende Mahlzeitenvorlage nach Kategorie."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="meal_templates",
        verbose_name="Benutzer",
    )
    category = models.CharField(
        max_length=20,
        choices=MealEntry.CATEGORY_CHOICES,
        default="breakfast",
        verbose_name="Kategorie",
    )
    name = models.CharField(max_length=120, verbose_name="Vorlagenname")
    calories = models.PositiveIntegerField(verbose_name="Kalorien (kcal)")
    protein_g = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        default=Decimal("0.0"),
        verbose_name="Eiweiß (g)",
    )
    carbs_g = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        default=Decimal("0.0"),
        verbose_name="Kohlenhydrate (g)",
    )
    fat_g = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        default=Decimal("0.0"),
        verbose_name="Fett (g)",
    )
    fiber_g = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        default=Decimal("0.0"),
        verbose_name="davon Ballaststoffe (g)",
    )
    notes = models.TextField(blank=True, verbose_name="Notizen")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["category", "name"]
        verbose_name = "Mahlzeitenvorlage"
        verbose_name_plural = "Mahlzeitenvorlagen"

    def __str__(self) -> str:
        return f"{self.get_category_display()}: {self.name} ({self.calories} kcal)"


class WaterEntry(models.Model):
    """Tägliche Flüssigkeitsaufnahme in Millilitern."""

    DRINK_CHOICES = [
        ("water", "Wasser"),
        ("tea", "Tee (ungesüßt)"),
        ("coffee", "Kaffee"),
        ("other", "Sonstiges"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="water_entries",
        verbose_name="Benutzer",
    )
    date = models.DateField(
        default=timezone.localdate,
        db_index=True,
        verbose_name="Datum",
    )
    drink_type = models.CharField(
        max_length=20,
        choices=DRINK_CHOICES,
        default="water",
        verbose_name="Getränk",
    )
    amount_ml = models.PositiveIntegerField(verbose_name="Menge (ml)")
    notes = models.TextField(blank=True, verbose_name="Notizen")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "Wassereintrag"
        verbose_name_plural = "Wassereinträge"

    def __str__(self) -> str:
        return f"{self.date} - {self.get_drink_type_display()} ({self.amount_ml} ml)"


class DailyActivity(models.Model):
    """Tägliche Bewegungs- bzw. Aktivitätskalorien (Apple Watch oder Preset)."""

    LEVEL_CHOICES = [
        ("none", "Keine"),
        ("low", "Wenig"),
        ("medium", "Mittel"),
        ("high", "Hoch"),
        ("custom", "Apple Watch / Manuell"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="daily_activities",
        verbose_name="Benutzer",
    )
    date = models.DateField(
        default=timezone.localdate,
        db_index=True,
        verbose_name="Datum",
    )
    level = models.CharField(
        max_length=10,
        choices=LEVEL_CHOICES,
        default="none",
        verbose_name="Bewegungslevel",
    )
    calories_burned = models.PositiveIntegerField(
        default=0,
        verbose_name="Bewegungskalorien (kcal)",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "date")
        ordering = ["-date"]
        verbose_name = "Tägliche Bewegung"
        verbose_name_plural = "Tägliche Bewegungen"

    def __str__(self) -> str:
        return f"{self.date} - {self.get_level_display()} (+{self.calories_burned} kcal)"


class WeightEntry(models.Model):
    """Gewichtsmessung eines Benutzers."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="weights",
        verbose_name="Benutzer",
    )
    date = models.DateField(
        default=timezone.localdate,
        db_index=True,
        verbose_name="Datum",
    )
    weight_kg = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name="Gewicht (kg)",
    )
    body_fat_pct = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
        verbose_name="Körperfett (%)",
    )
    notes = models.TextField(blank=True, verbose_name="Notizen")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "Gewichtseintrag"
        verbose_name_plural = "Gewichtseinträge"

    def __str__(self) -> str:
        return f"{self.date} - {self.weight_kg} kg"

from decimal import Decimal

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

from .models import MealEntry, MealTemplate, UserProfile, WaterEntry, WeightEntry


class BootstrapFormMixin:
    """Fügt allen Formularfeldern einheitliche Bootstrap-5-Klassen hinzu."""

    def _apply_bootstrap_classes(self):
        for field in self.fields.values():
            widget = field.widget
            css_class = "form-select" if isinstance(widget, forms.Select) else "form-control"
            existing = widget.attrs.get("class", "")
            widget.attrs["class"] = f"{existing} {css_class}".strip()


class StyledAuthenticationForm(BootstrapFormMixin, AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap_classes()


class RegistrationForm(BootstrapFormMixin, UserCreationForm):
    email = forms.EmailField(required=False, label="E-Mail-Adresse (optional)")

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap_classes()


class UserProfileForm(BootstrapFormMixin, forms.ModelForm):
    first_name = forms.CharField(max_length=150, required=False, label="Vorname")
    last_name = forms.CharField(max_length=150, required=False, label="Nachname")
    email = forms.EmailField(required=False, label="E-Mail-Adresse")

    class Meta:
        model = UserProfile
        fields = (
            "height_cm",
            "age",
            "gender",
            "activity_level",
            "start_weight_kg",
            "target_weight_kg",
            "daily_calorie_goal",
            "daily_water_goal_ml",
            "daily_fiber_goal_g",
            "activity_kcal_low",
            "activity_kcal_medium",
            "activity_kcal_high",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.user_id:
            self.fields["first_name"].initial = self.instance.user.first_name
            self.fields["last_name"].initial = self.instance.user.last_name
            self.fields["email"].initial = self.instance.user.email
        self._apply_bootstrap_classes()

    def save(self, commit=True):
        profile = super().save(commit=commit)
        user = profile.user
        user.first_name = self.cleaned_data.get("first_name", "")
        user.last_name = self.cleaned_data.get("last_name", "")
        user.email = self.cleaned_data.get("email", "")
        if commit:
            user.save(update_fields=["first_name", "last_name", "email"])
        return profile


class MacroCalorieCalculationMixin:
    """Validiert Makronährstoffe und berechnet daraus die Kalorien automatisch."""

    def _configure_calorie_field(self):
        self.fields["calories"].required = False
        self.fields["calories"].widget.attrs["readonly"] = True

    def clean(self):
        cleaned = super().clean()
        p = cleaned.get("protein_g") or Decimal("0")
        c = cleaned.get("carbs_g") or Decimal("0")
        f = cleaned.get("fat_g") or Decimal("0")
        fib = cleaned.get("fiber_g") or Decimal("0")

        if any(val < 0 for val in (p, c, f, fib)):
            raise forms.ValidationError("Makronährstoffe und Ballaststoffe dürfen nicht negativ sein.")
        if fib > c:
            raise forms.ValidationError(
                "Ballaststoffe können nicht größer sein als die gesamten Kohlenhydrate."
            )
        if (p + c + f) <= Decimal("0"):
            raise forms.ValidationError(
                "Bitte zuerst mindestens einen Makronährstoff (> 0 g) eintragen."
            )

        cleaned["calories"] = round(float(p) * 4 + float(c) * 4 + float(f) * 9)
        return cleaned


class MealEntryForm(BootstrapFormMixin, MacroCalorieCalculationMixin, forms.ModelForm):
    class Meta:
        model = MealEntry
        fields = ("date", "category", "name", "protein_g", "carbs_g", "fiber_g", "fat_g", "calories", "notes")
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap_classes()
        self._configure_calorie_field()


class MealTemplateForm(BootstrapFormMixin, MacroCalorieCalculationMixin, forms.ModelForm):
    class Meta:
        model = MealTemplate
        fields = ("category", "name", "protein_g", "carbs_g", "fiber_g", "fat_g", "calories", "notes")
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap_classes()
        self._configure_calorie_field()


class WaterEntryForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = WaterEntry
        fields = ("date", "drink_type", "amount_ml", "notes")
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap_classes()


class WeightEntryForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = WeightEntry
        fields = ("date", "weight_kg", "body_fat_pct", "notes")
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap_classes()

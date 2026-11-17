from django.contrib import admin

from .models import DailyActivity, MealEntry, MealTemplate, UserProfile, WaterEntry, WeightEntry


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "daily_calorie_goal", "start_weight_kg", "target_weight_kg", "updated_at")
    search_fields = ("user__username", "user__email")


@admin.register(MealEntry)
class MealEntryAdmin(admin.ModelAdmin):
    list_display = ("date", "user", "category", "name", "calories", "protein_g", "carbs_g", "fat_g", "fiber_g")
    list_filter = ("category", "date")
    search_fields = ("name", "notes", "user__username")
    date_hierarchy = "date"


@admin.register(MealTemplate)
class MealTemplateAdmin(admin.ModelAdmin):
    list_display = ("user", "category", "name", "calories", "protein_g", "carbs_g", "fat_g", "fiber_g")
    list_filter = ("category",)
    search_fields = ("name", "notes", "user__username")


@admin.register(WeightEntry)
class WeightEntryAdmin(admin.ModelAdmin):
    list_display = ("date", "user", "weight_kg", "body_fat_pct")
    list_filter = ("date",)
    search_fields = ("notes", "user__username")
    date_hierarchy = "date"


@admin.register(WaterEntry)
class WaterEntryAdmin(admin.ModelAdmin):
    list_display = ("date", "user", "drink_type", "amount_ml")
    list_filter = ("drink_type", "date")
    search_fields = ("notes", "user__username")
    date_hierarchy = "date"


@admin.register(DailyActivity)
class DailyActivityAdmin(admin.ModelAdmin):
    list_display = ("date", "user", "level", "calories_burned", "updated_at")
    list_filter = ("level", "date")
    search_fields = ("user__username",)
    date_hierarchy = "date"

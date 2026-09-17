from django.db import models
from django.conf import settings

import uuid

class TravelPlan(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE,
        related_name="travel_plans",
        null=True,
        blank=True
    )
    start_location = models.CharField(max_length=255)
    destination = models.CharField(max_length=255)

    
    # Social Features
    share_token = models.UUIDField(default=uuid.uuid4, editable=False, null=True)
    is_public = models.BooleanField(default=False)
    collaborators = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="collaborated_trips",
        blank=True
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.start_location} → {self.destination}"

    class Meta:
        ordering = ['-created_at']


class Itinerary(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField()
    latitude = models.FloatField()
    longitude = models.FloatField()
    image_url = models.URLField(max_length=500, blank=True)
    city = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']
        verbose_name_plural = "Itineraries"



# NEW MODEL: Store places for each travel plan
class PlanItinerary(models.Model):
    """Links places to specific travel plans with day organization"""
    travel_plan = models.ForeignKey(
        TravelPlan,
        on_delete=models.CASCADE,
        related_name='plan_itineraries'
    )
    name = models.CharField(max_length=255)
    description = models.TextField()
    latitude = models.FloatField()
    longitude = models.FloatField()
    image_url = models.URLField(max_length=500, blank=True)
    city = models.CharField(max_length=100, blank=True)
    location = models.CharField(max_length=255, blank=True)
    distance = models.FloatField(default=0)  # Distance from start
    category = models.CharField(max_length=100, blank=True)
    day_number = models.IntegerField(default=1)  # Which day of the trip
    order_in_day = models.IntegerField(default=0)  # Order within that day
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    activity_type = models.CharField(max_length=50, default='sightseeing') # sightseeing, transport, food, accommodation
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - Day {self.day_number} ({self.travel_plan})"

    class Meta:
        ordering = ['travel_plan', 'day_number', 'order_in_day']
        verbose_name_plural = "Plan Itineraries"


class PackingChecklist(models.Model):
    """Stores a smart packing checklist for a travel plan"""
    travel_plan = models.OneToOneField(
        TravelPlan,
        on_delete=models.CASCADE,
        related_name='packing_checklist'
    )
    items = models.JSONField(default=list)  # [{name, category, emoji, reason, checked, is_weather_based}]
    weather_summary = models.JSONField(default=dict)  # Cached weather forecast summary
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        checked = sum(1 for i in self.items if i.get('checked'))
        return f"Packing list for {self.travel_plan} ({checked}/{len(self.items)} packed)"

    class Meta:
        verbose_name_plural = "Packing Checklists"
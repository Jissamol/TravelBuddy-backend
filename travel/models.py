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
    cover_image = models.ImageField(upload_to='trip_covers/', null=True, blank=True)

    
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
    custom_image = models.ImageField(upload_to='itinerary_images/', null=True, blank=True)
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
    custom_image = models.ImageField(upload_to='itinerary_images/', null=True, blank=True)
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


class PlaceImageOverride(models.Model):
    """Stores global user-uploaded image overrides for Google Places/OSM places."""
    place_id = models.CharField(max_length=255, unique=True, db_index=True)
    image = models.ImageField(upload_to='place_overrides/')
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Override for {self.place_id}"

class Accommodation(models.Model):
    travel_plan = models.ForeignKey(
        TravelPlan,
        on_delete=models.CASCADE,
        related_name='accommodations'
    )
    hotel_name = models.CharField(max_length=255)
    address = models.TextField(blank=True)
    check_in = models.DateTimeField()
    check_out = models.DateTimeField()
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    booking_reference = models.CharField(max_length=100, blank=True)
    contact_number = models.CharField(max_length=50, blank=True)
    notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.hotel_name} for {self.travel_plan}"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        # Automatically insert into itinerary if it's new
        if is_new:
            # We can calculate day_number based on check_in compared to travel_plan created_at or just put it on Day 1
            # Assuming travel plan starts around check_in date or just insert it and let user reorder
            PlanItinerary.objects.create(
                travel_plan=self.travel_plan,
                name=self.hotel_name,
                description=f"Check-in at {self.hotel_name}. Ref: {self.booking_reference}. Notes: {self.notes}",
                location=self.address,
                latitude=0.0, # Could be updated via geocoding
                longitude=0.0,
                day_number=1, # Default to day 1, users can change
                order_in_day=99, # Put at the end of the day by default
                start_time=self.check_in.time(),
                end_time=self.check_out.time(),
                activity_type='accommodation'
            )
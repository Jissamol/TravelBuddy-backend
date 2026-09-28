from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import TravelPlan, Itinerary, PlanItinerary, Accommodation, MemoryFolder, MemoryImage

User = get_user_model()

class MemoryImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = MemoryImage
        fields = '__all__'
        read_only_fields = ['id', 'uploaded_at', 'folder']

class MemoryFolderSerializer(serializers.ModelSerializer):
    preview_image = serializers.SerializerMethodField()
    images_count = serializers.SerializerMethodField()

    class Meta:
        model = MemoryFolder
        fields = ['id', 'user', 'name', 'description', 'created_at', 'preview_image', 'images_count']
        read_only_fields = ['id', 'created_at', 'user']

    def get_preview_image(self, obj):
        first_image = obj.images.order_by('uploaded_at').first()
        if first_image and first_image.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(first_image.image.url)
            return first_image.image.url
        return None

    def get_images_count(self, obj):
        return obj.images.count()

class AccommodationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Accommodation
        fields = '__all__'
        read_only_fields = ['id', 'created_at']

class PlanItinerarySerializer(serializers.ModelSerializer):
    class Meta:
        model = PlanItinerary
        fields = '__all__'
        read_only_fields = ['id', 'created_at']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        # Ensure lat/lon mapping for frontend compatibility
        representation['lat'] = representation.get('latitude')
        representation['lon'] = representation.get('longitude')
        representation['image'] = representation.get('custom_image') or representation.get('image_url')
        return representation

class TripMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email']

class TravelPlanSerializer(serializers.ModelSerializer):
    collaborators_details = TripMemberSerializer(source='collaborators', many=True, read_only=True)
    is_owner = serializers.SerializerMethodField()
    
    class Meta:
        model = TravelPlan
        fields = [
            'id', 'user', 'start_location', 'destination', 'cover_image',
            'created_at', 'updated_at', 'share_token', 'is_public', 
            'collaborators', 'collaborators_details', 'is_owner'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'share_token']

    def get_is_owner(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.user == request.user
        return False

class ItinerarySerializer(serializers.ModelSerializer):
    """Serializer for Itinerary model with optional distance field"""
    distance = serializers.FloatField(read_only=True, required=False)
    
    class Meta:
        model = Itinerary
        fields = [
            'id',
            'name',
            'description',
            'latitude',
            'longitude',
            'image_url',
            'custom_image',
            'city',
            'distance',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def to_representation(self, instance):
        """Customize the output representation"""
        representation = super().to_representation(instance)
        
        # Add distance if it exists as an attribute (calculated in view)
        if hasattr(instance, 'distance'):
            representation['distance'] = round(instance.distance, 2)
        
        # Ensure custom_image overrides image_url, then return as 'image' for frontend compatibility
        custom_img = representation.pop('custom_image', None)
        img_url = representation.pop('image_url', None)
        representation['image'] = custom_img or img_url
        
        # Map latitude/longitude to lat/lon for frontend
        representation['lat'] = representation.pop('latitude')
        representation['lon'] = representation.pop('longitude')
        
        return representation


class RouteItinerarySerializer(serializers.Serializer):
    """Serializer for route itinerary responses from external APIs"""
    id = serializers.IntegerField()
    name = serializers.CharField(max_length=255)
    description = serializers.CharField()
    lat = serializers.FloatField()
    lon = serializers.FloatField()
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    district = serializers.CharField(max_length=100, required=False, allow_blank=True)
    location = serializers.CharField(max_length=255, required=False, allow_blank=True)
    image = serializers.URLField(required=False, allow_blank=True)
    distance = serializers.FloatField()
    category = serializers.CharField(max_length=100, required=False, allow_blank=True)


class UserTravelPlanListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing user's travel plans"""
    duration_days = serializers.SerializerMethodField()
    
    class Meta:
        model = TravelPlan
        fields = [
            'id',
            'start_location',
            'destination',
            'cover_image',
            'duration_days',
            'is_public',
            'share_token',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_at']
    
    def get_duration_days(self, obj):
        """Calculate trip duration in days (defaulting to 3 since dates are removed)"""
        return 3
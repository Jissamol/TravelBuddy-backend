from django.urls import path
from .views import PersonalizePlanView,top_itineraries,all_itineraries_daywise
from . import views

urlpatterns = [
    path("personalize-plan/", PersonalizePlanView.as_view(), name="personalize-plan"),
    path("plans/", views.TravelPlanListView.as_view(), name="plan-list"),
    path("plans/<int:pk>/", views.TravelPlanDetailView.as_view(), name="plan-detail"),
    # path("generate-itinerary/", generate_itinerary, name="generate-itinerary"),
    path('top-itineraries/', top_itineraries, name='top-itineraries'),
    path("nearby-itineraries/", views.nearby_itineraries, name="itineraries-nearby"),
    path("nearby-places/", views.nearby_places, name="nearby-places"),
    path("nearby-place-photo/", views.nearby_place_photo, name="nearby-place-photo"),
    path('route-itineraries/', views.route_itineraries, name='route-itineraries'),  

    path('save-plan-itineraries/', views.save_plan_itineraries, name='save_plan_itineraries'),
    path('allitineraries/', views.all_itineraries_daywise, name='all_itineraries'),
    path('plans/<int:plan_id>/itineraries/add/', views.add_plan_itinerary, name='add_plan_itinerary'),

    # Trip Collaboration & Sharing
    path('trips/token/<uuid:token>/', views.get_trip_by_token, name='get_trip_by_token'),
    path('trips/join/<uuid:token>/', views.join_trip, name='join_trip'),
    path('trips/visibility/<int:plan_id>/', views.update_trip_visibility, name='update_trip_visibility'),
    
    # Image Overrides
    path('places/override-image/', views.upload_place_image_override, name='upload_place_image_override'),
    path('itineraries/<int:item_id>/image/', views.update_plan_itinerary_image, name='update_plan_itinerary_image'),
    path('plans/<int:plan_id>/accommodations/', views.AccommodationListCreateView.as_view(), name='accommodation_list_create'),
    path('accommodations/<int:pk>/', views.AccommodationDetailView.as_view(), name='accommodation_detail'),
]


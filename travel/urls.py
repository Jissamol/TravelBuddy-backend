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
    path('route-itineraries/', views.route_itineraries, name='route-itineraries'),  

    path('save-plan-itineraries/', views.save_plan_itineraries, name='save_plan_itineraries'),
    path('allitineraries/', views.all_itineraries_daywise, name='all_itineraries'),
    path('plans/<int:plan_id>/itineraries/add/', views.add_plan_itinerary, name='add_plan_itinerary'),

    # Trip Collaboration & Sharing
    path('trips/token/<uuid:token>/', views.get_trip_by_token, name='get_trip_by_token'),
    path('trips/join/<uuid:token>/', views.join_trip, name='join_trip'),
    path('trips/visibility/<int:plan_id>/', views.update_trip_visibility, name='update_trip_visibility'),

    # Smart Packing Checklist
    path('packing-checklist/', views.generate_packing_checklist, name='generate_packing_checklist'),
    path('packing-checklist/<int:plan_id>/', views.update_packing_checklist, name='update_packing_checklist'),
]

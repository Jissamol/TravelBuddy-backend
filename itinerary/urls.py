from django.urls import path
from .views import SignupView, UserProfileView

urlpatterns = [
    path('signup/', SignupView.as_view(), name='signup'),
    path('user/', UserProfileView.as_view(), name='user-profile'),
]

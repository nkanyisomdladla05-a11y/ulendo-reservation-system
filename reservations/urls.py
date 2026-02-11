from django.urls import path
from . import views

app_name = 'reservations'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('new/', views.new_reservation, name='new_reservation'),
    path('confirm/', views.confirm_reservation, name='confirm_reservation'),
    path('availability/', views.room_availability, name='room_availability'),
    path('list/', views.reservation_list, name='reservation_list'),
    path('<int:pk>/edit/', views.edit_reservation, name='edit_reservation'),
    path('<int:pk>/cancel/', views.cancel_reservation, name='cancel_reservation'),
]

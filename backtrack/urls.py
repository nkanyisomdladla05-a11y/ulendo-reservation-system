from django.urls import path
from . import views

app_name = 'backtrack'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('new/', views.new_backtrack, name='new_backtrack'),
    path('upload/', views.upload_backtrack_voucher, name='upload_backtrack_voucher'),
    path('<int:voucher_id>/review/', views.review_backtrack_voucher, name='review_backtrack_voucher'),
    path('list/', views.backtrack_list, name='backtrack_list'),
    path('reports/', views.backtrack_report, name='backtrack_report'),
    path('calendar/', views.backtrack_calendar, name='backtrack_calendar'),
    path('api/available-rooms/', views.api_available_backtrack_rooms, name='api_available_backtrack_rooms'),
    path('<int:pk>/edit/', views.edit_backtrack_reservation, name='edit_reservation'),
    path('<int:pk>/delete/', views.delete_backtrack_reservation, name='delete_reservation'),
    path('<int:pk>/delete-dashboard/', views.delete_backtrack_from_dashboard, name='delete_from_dashboard'),
    path('<int:pk>/vouchers/', views.backtrack_vouchers_json, name='backtrack_vouchers'),
    path('<int:pk>/vouchers/upload/', views.upload_backtrack_reservation_voucher, name='upload_backtrack_voucher'),
    path('<int:pk>/vouchers/<int:voucher_id>/delete/', views.delete_backtrack_reservation_voucher, name='delete_backtrack_voucher'),
    path('<int:pk>/uploads/', views.backtrack_uploads_page, name='backtrack_uploads'),
]

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
    path('<int:pk>/delete/', views.delete_backtrack_reservation, name='delete_reservation'),
    path('<int:pk>/delete-dashboard/', views.delete_backtrack_from_dashboard, name='delete_from_dashboard'),
]

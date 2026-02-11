from django.urls import path
from . import views

app_name = 'vouchers'

urlpatterns = [
    path('upload/', views.upload_voucher, name='upload_voucher'),
    path('<int:voucher_id>/review/', views.review_voucher, name='review_voucher'),
]

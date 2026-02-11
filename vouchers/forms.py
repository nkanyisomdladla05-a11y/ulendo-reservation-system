from django import forms
from .models import Voucher


class VoucherUploadForm(forms.ModelForm):
    """Form for uploading voucher images."""
    
    class Meta:
        model = Voucher
        fields = ['voucher_file']
        widgets = {
            'voucher_file': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*,application/pdf,.pdf'
            })
        }


class VoucherReviewForm(forms.ModelForm):
    """Form for reviewing and editing OCR extracted data."""
    
    class Meta:
        model = Voucher
        fields = ['customer_name', 'voucher_number', 'check_in_date', 'check_out_date']
        widgets = {
            'customer_name': forms.TextInput(attrs={'class': 'form-control'}),
            'voucher_number': forms.TextInput(attrs={'class': 'form-control'}),
            'check_in_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'check_out_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

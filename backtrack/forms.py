from django import forms
from .models import BacktrackReservation, BacktrackVoucher

ROOM_CHOICES = [(str(i), f'Room {i}') for i in range(1, 31)]


class BacktrackReservationForm(forms.ModelForm):
    """Form for backtrack reservations - accepts past dates, no room availability checks."""

    check_in_date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control date-picker', 'type': 'text', 'placeholder': 'yyyy/mm/dd'}),
        input_formats=['%Y/%m/%d', '%Y/%-m/%d', '%y/%m/%d', '%Y-%m-%d'],
    )
    check_out_date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control date-picker', 'type': 'text', 'placeholder': 'yyyy/mm/dd'}),
        input_formats=['%Y/%m/%d', '%Y/%-m/%d', '%y/%m/%d', '%Y-%m-%d'],
    )

    class Meta:
        model = BacktrackReservation
        fields = ['customer_name', 'voucher_number', 'room_number', 'check_in_date', 'check_out_date', 'notes']
        widgets = {
            'customer_name': forms.TextInput(attrs={'class': 'form-control'}),
            'voucher_number': forms.TextInput(attrs={'class': 'form-control'}),
            'room_number': forms.Select(attrs={'class': 'form-control'}, choices=ROOM_CHOICES),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def clean(self):
        cleaned_data = super().clean()
        check_in = cleaned_data.get('check_in_date')
        check_out = cleaned_data.get('check_out_date')

        if check_in and check_out:
            if check_out <= check_in:
                raise forms.ValidationError('Check-out date must be after check-in date.')

        return cleaned_data


class BacktrackVoucherUploadForm(forms.ModelForm):
    class Meta:
        model = BacktrackVoucher
        fields = ['voucher_file']
        widgets = {
            'voucher_file': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*,application/pdf,.pdf'
            })
        }

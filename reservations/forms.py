from django import forms
from .models import Reservation
from .services import get_rooms_available_for_booking
from rooms.models import Room
from datetime import date


class ReservationForm(forms.ModelForm):
    """Form for creating/editing reservations."""
    
    class Meta:
        model = Reservation
        fields = ['customer_name', 'voucher_number', 'room', 'check_in_date', 'check_out_date', 'notes']
        widgets = {
            'customer_name': forms.TextInput(attrs={'class': 'form-control'}),
            'voucher_number': forms.TextInput(attrs={'class': 'form-control'}),
            'room': forms.Select(attrs={'class': 'form-control'}),
            'check_in_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'check_out_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        check_in = kwargs.pop('check_in_date', None)
        check_out = kwargs.pop('check_out_date', None)
        super().__init__(*args, **kwargs)
        
        # Same room list as upload voucher: get_rooms_available_for_booking() so dropdown is literally the same.
        qs = get_rooms_available_for_booking()
        self.fields['room'].queryset = qs
        self.fields['room'].empty_label = "-- Select a room --"
        self.fields['room'].required = qs.exists()
        
        # Set initial dates if provided (for display purposes)
        if not self.instance.pk:
            if check_in:
                self.fields['check_in_date'].initial = check_in
            if check_out:
                self.fields['check_out_date'].initial = check_out
    
    def clean(self):
        cleaned_data = super().clean()
        check_in = cleaned_data.get('check_in_date')
        check_out = cleaned_data.get('check_out_date')
        room = cleaned_data.get('room')
        
        if check_in and check_out:
            if check_out <= check_in:
                raise forms.ValidationError('Check-out date must be after check-in date.')
            
            # Validate room availability
            if room:
                from .services import check_room_availability
                exclude_reservation = self.instance if self.instance.pk else None
                if not check_room_availability(room, check_in, check_out, exclude_reservation):
                    raise forms.ValidationError(f'Room {room.room_number} is not available for the selected dates.')
        
        return cleaned_data

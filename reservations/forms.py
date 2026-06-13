import sys
from django import forms
from django.db.models import Exists, OuterRef, IntegerField
from django.db.models.functions import Cast
from .models import Reservation
from .services import get_available_rooms
from rooms.models import Room
from datetime import date


class ReservationForm(forms.ModelForm):
    """Form for creating/editing reservations."""

    check_in_date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control date-picker', 'type': 'text', 'placeholder': 'yyyy/mm/dd'}),
        input_formats=['%Y/%m/%d', '%Y/%-m/%d', '%y/%m/%d', '%Y-%m-%d'],
    )
    check_out_date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control date-picker', 'type': 'text', 'placeholder': 'yyyy/mm/dd'}),
        input_formats=['%Y/%m/%d', '%Y/%-m/%d', '%y/%m/%d', '%Y-%m-%d'],
    )

    class Meta:
        model = Reservation
        fields = ['customer_name', 'voucher_number', 'confirmation_code', 'room', 'check_in_date', 'check_out_date', 'notes']
        widgets = {
            'customer_name': forms.TextInput(attrs={'class': 'form-control'}),
            'voucher_number': forms.TextInput(attrs={'class': 'form-control'}),
            'confirmation_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional confirmation code/number'}),
            'room': forms.Select(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        check_in = kwargs.pop('check_in_date', None)
        check_out = kwargs.pop('check_out_date', None)
        super().__init__(*args, **kwargs)

        if self.instance.pk:
            if not check_in and self.instance.check_in_date:
                check_in = self.instance.check_in_date
            if not check_out and self.instance.check_out_date:
                check_out = self.instance.check_out_date

        if check_in:
            self.fields['check_in_date'].initial = check_in.strftime('%Y/%m/%d')
        if check_out:
            self.fields['check_out_date'].initial = check_out.strftime('%Y/%m/%d')

        print(f"[ReservationForm.__init__] check_in={check_in} check_out={check_out} instance.pk={self.instance.pk}", file=sys.stderr)

        if check_in and check_out and check_out > check_in:
            qs = get_available_rooms(check_in, check_out, exclude_reservation=self.instance if self.instance.pk else None)
            self.fields['room'].queryset = qs
            self.fields['room'].empty_label = "-- Select a room --"
            self.fields['room'].required = qs.exists()
            print(f"[ReservationForm.__init__] FILTERED queryset count: {qs.count()}", file=sys.stderr)
        else:
            today = date.today()
            qs = Room.objects.filter(is_active=True).annotate(
                has_booking=Exists(
                    Reservation.objects.filter(
                        room=OuterRef('pk'),
                        status='confirmed',
                        check_out_date__gt=today,
                    )
                ),
                room_num_int=Cast('room_number', IntegerField())
            ).order_by('room_num_int')
            self.fields['room'].queryset = qs
            self.fields['room'].empty_label = "-- Select a room --"
            self.fields['room'].required = False
            print(f"[ReservationForm.__init__] UNFILTERED queryset (all rooms): {[(r.id, r.room_number) for r in qs]}", file=sys.stderr)

            def label_from_instance(room):
                label = f"Room {room.room_number}"
                if room.room_type:
                    label += f" ({room.room_type})"
                if getattr(room, 'has_booking', False):
                    label += " — Booked"
                if room.status == 'booked':
                    label += " ●"
                return label

            self.fields['room'].label_from_instance = label_from_instance


    def clean(self):
        cleaned_data = super().clean()
        check_in = cleaned_data.get('check_in_date')
        check_out = cleaned_data.get('check_out_date')
        room = cleaned_data.get('room')

        if check_in and check_out:
            if check_out <= check_in:
                raise forms.ValidationError('Check-out date must be after check-in date.')

            if room:
                from .services import check_room_availability
                exclude_reservation = self.instance if self.instance.pk else None
                if not check_room_availability(room, check_in, check_out, exclude_reservation):
                    raise forms.ValidationError(f'Room {room.room_number} is not available for the selected dates.')

        return cleaned_data

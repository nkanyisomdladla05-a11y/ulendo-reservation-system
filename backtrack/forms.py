from django import forms
from django.db.models import Q, IntegerField, Exists, OuterRef
from django.db.models.functions import Cast
from .models import BacktrackReservation, BacktrackVoucher
from rooms.models import Room
from reservations.models import Reservation


def get_available_backtrack_rooms(check_in_date, check_out_date, exclude_reservation=None):
    """
    Get available rooms for backtrack: exclude rooms with overlapping
    confirmed reservations in BOTH the main system and backtrack system.
    """
    if not check_in_date or not check_out_date or check_out_date <= check_in_date:
        return Room.objects.none()

    all_rooms = Room.objects.filter(is_active=True)

    booked_main = Reservation.objects.filter(
        status='confirmed',
        room_id=OuterRef('pk'),
        check_in_date__lt=check_out_date,
        check_out_date__gt=check_in_date,
    )

    backtrack_qs = BacktrackReservation.objects.filter(
        status='confirmed',
        room_number=OuterRef('room_number'),
        check_in_date__lt=check_out_date,
        check_out_date__gt=check_in_date,
    )
    if exclude_reservation:
        backtrack_qs = backtrack_qs.exclude(pk=exclude_reservation.pk)

    booked_backtrack = backtrack_qs

    booked_room_ids = all_rooms.filter(
        Q(Exists(booked_main)) |
        Q(Exists(booked_backtrack))
    ).values_list('id', flat=True).distinct()

    return (
        all_rooms
        .exclude(id__in=booked_room_ids)
        .annotate(room_num_int=Cast('room_number', IntegerField()))
        .order_by('room_num_int')
    )


class BacktrackReservationForm(forms.ModelForm):
    """Form for backtrack reservations using the same Room dropdown as the main system."""

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
            'room_number': forms.Select(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        check_in = kwargs.pop('check_in_date', None)
        check_out = kwargs.pop('check_out_date', None)
        super().__init__(*args, **kwargs)

        # Use instance values if editing and no explicit dates provided
        if self.instance.pk:
            if not check_in and self.instance.check_in_date:
                check_in = self.instance.check_in_date
            if not check_out and self.instance.check_out_date:
                check_out = self.instance.check_out_date

        # Set date initial values in Y/m/d format for Flatpickr
        if check_in:
            self.fields['check_in_date'].initial = check_in.strftime('%Y/%m/%d')
        if check_out:
            self.fields['check_out_date'].initial = check_out.strftime('%Y/%m/%d')

        if check_in and check_out and check_out > check_in:
            exclude = self.instance if self.instance.pk else None
            available = get_available_backtrack_rooms(check_in, check_out, exclude_reservation=exclude)
            choices = [(r.room_number, str(r)) for r in available]
            self.fields['room_number'].widget = forms.Select(
                attrs={'class': 'form-control'},
                choices=choices,
            )
            self.fields['room_number'].required = bool(choices)
            self._available_rooms = available
        else:
            booked_main = Reservation.objects.filter(
                room_id=OuterRef('pk'),
                status='confirmed',
            )
            qs = Room.objects.filter(is_active=True).annotate(
                has_booking=Exists(booked_main),
                room_num_int=Cast('room_number', IntegerField())
            ).order_by('room_num_int')
            choices = []
            for room in qs:
                label = str(room)
                if getattr(room, 'has_booking', False):
                    label += " - Booked"
                choices.append((room.room_number, label))
            self.fields['room_number'].widget = forms.Select(
                attrs={'class': 'form-control'},
                choices=choices,
            )
            self.fields['room_number'].required = False
            self._available_rooms = qs

    def clean(self):
        cleaned_data = super().clean()
        check_in = cleaned_data.get('check_in_date')
        check_out = cleaned_data.get('check_out_date')
        room_number = cleaned_data.get('room_number')

        if check_in and check_out:
            if check_out <= check_in:
                raise forms.ValidationError('Check-out date must be after check-in date.')

        if room_number and check_in and check_out:
            try:
                room = Room.objects.get(room_number=room_number, is_active=True)
            except Room.DoesNotExist:
                raise forms.ValidationError(f'Room {room_number} does not exist or is inactive.')

            exclude = self.instance if self.instance.pk else None
            available = get_available_backtrack_rooms(check_in, check_out, exclude_reservation=exclude)
            if not available.filter(room_number=room_number).exists():
                raise forms.ValidationError(f'Room {room_number} is not available for the selected dates.')

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

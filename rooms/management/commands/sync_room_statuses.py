from django.core.management.base import BaseCommand
from rooms.models import Room


class Command(BaseCommand):
    help = 'Update room statuses based on current reservations'

    def handle(self, *args, **options):
        count = 0
        for room in Room.objects.filter(is_active=True):
            room.update_status(save=True)
            count += 1
        self.stdout.write(self.style.SUCCESS(f'Updated {count} room statuses'))

"""Appointment and Review Services."""
from decimal import Decimal
from django.db import transaction
from django.db.models import Avg, Count
from apps.doctors.models import Doctor
from apps.appointments.models import DoctorReview

def recalculate_doctor_rating(doctor_id):
    """
    Lock the doctor row with select_for_update and recalculate
    rating and review_count strictly from the database review rows.
    Uses pure arithmetic average rounded to 2 decimal places.
    """
    doctor = Doctor.objects.select_for_update().get(id=doctor_id)
    stats = DoctorReview.objects.filter(doctor=doctor).aggregate(
        avg_rating=Avg('rating'),
        count=Count('id')
    )
    count = stats['count'] or 0
    if count > 0:
        avg_rating = stats['avg_rating'] or 0.0
        doctor.rating = Decimal(str(round(avg_rating, 2)))
        doctor.review_count = count
    else:
        doctor.review_count = 0

    doctor.save(update_fields=['rating', 'review_count', 'updated_at'])
    return doctor

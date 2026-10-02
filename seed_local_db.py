"""
MeetAdr Local SQLite Seed Script
===================================
Run: python seed_local_db.py  (from the backend/ directory)

Creates:
  - Demo users (patient, doctor, hospital admin, admin)
  - 6 Hospitals (Dubai & Abu Dhabi)
  - 4 Clinics
  - 12+ Doctors with schedules
  - Patient profile for demo patient
"""

import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from django.db import transaction
from apps.accounts.models import User, UserRole, PatientProfile
from apps.facilities.models import Hospital, Clinic, FacilityDepartment, FacilityStatus
from apps.doctors.models import Doctor, DoctorSchedule

# ──────────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def get_or_create_user(email, name, role, password, phone='', is_staff=False, is_superuser=False):
    user, created = User.objects.get_or_create(
        email=email,
        defaults={'name': name, 'role': role, 'phone': phone, 'is_staff': is_staff}
    )
    if created or not user.has_usable_password():
        user.set_password(password)
        user.is_staff = is_staff
        user.is_superuser = is_superuser
        user.save()
        print(f"  + Created user: {email} ({role})")
    else:
        # Always reset password to ensure demo creds work
        user.set_password(password)
        user.save(update_fields=['password'])
        print(f"  ~ Updated password: {email} ({role})")
    return user

# ──────────────────────────────────────────────────────────────────────────────
# SEED
# ──────────────────────────────────────────────────────────────────────────────

with transaction.atomic():

    print("\n=== 1. Demo User Accounts ===")

    admin_user = get_or_create_user(
        email='admin@meetadr.demo',
        name='Platform Admin',
        role=UserRole.ADMIN,
        password='Admin@123',
        phone='+97142000001',
        is_staff=True,
        is_superuser=True
    )

    patient_user = get_or_create_user(
        email='patient@meetadr.demo',
        name='Ahmed Al Mansouri',
        role=UserRole.PATIENT,
        password='Patient@123',
        phone='+971501234567'
    )

    # Ensure PatientProfile exists for demo patient
    profile, _ = PatientProfile.objects.get_or_create(
        user=patient_user,
        defaults={
            'gender': 'Male',
            'blood_group': 'O+',
            'insurance_provider': 'Daman',
            'insurance_number': 'DAM-2026-00123',
            'emergency_contact': '+971509876543',
        }
    )
    print(f"  + Patient profile ready")

    hospital_admin_user = get_or_create_user(
        email='hospital@meetadr.demo',
        name='American Hospital Administration',
        role=UserRole.HOSPITAL,
        password='Hospital@123',
        phone='+97142000002'
    )

    doctor_user = get_or_create_user(
        email='doctor@meetadr.demo',
        name='Dr. Omar Khalid Al Hassan',
        role=UserRole.DOCTOR,
        password='Doctor@123',
        phone='+97142000003'
    )

    print("\n=== 2. Hospitals ===")

    h1, _ = Hospital.objects.get_or_create(
        name='American Hospital Dubai',
        defaults=dict(
            name_ar='المستشفى الأمريكي دبي',
            admin_user=hospital_admin_user,
            photo='https://images.unsplash.com/photo-1519494026892-80bbd2d6fd0d?auto=format&fit=crop&q=80&w=800',
            location='Dubai',
            address='Oud Metha Road, Dubai, UAE',
            address_ar='طريق عود ميثاء، دبي، الإمارات',
            phone='+97143368888',
            operating_hours='Open 24/7',
            operating_hours_ar='مفتوح 24/7',
            about='American Hospital Dubai is a Joint Commission International (JCI)-accredited hospital delivering world-class multi-specialty healthcare to residents and visitors since 1996.',
            about_ar='المستشفى الأمريكي دبي مستشفى حاصل على اعتماد الجمعية الدولية للجودة في الرعاية الصحية.',
            emergency_available=True,
            status=FacilityStatus.ACTIVE
        )
    )
    print(f"  + Hospital: {h1.name}")

    h2, _ = Hospital.objects.get_or_create(
        name='Mediclinic City Hospital',
        defaults=dict(
            name_ar='مستشفى ميديكلينيك سيتي',
            photo='https://images.unsplash.com/photo-1586773860418-d37222d8fce3?auto=format&fit=crop&q=80&w=800',
            location='Dubai',
            address='Dubai Healthcare City, Block B, Dubai, UAE',
            address_ar='مدينة دبي الطبية، المبنى B، دبي',
            phone='+97143359999',
            operating_hours='Open 24/7',
            operating_hours_ar='مفتوح 24/7',
            about='Mediclinic City Hospital is located in Dubai Healthcare City and offers 280+ beds with specialist care across over 50 medical disciplines.',
            about_ar='مستشفى ميديكلينيك سيتي يقع في مدينة دبي الطبية ويقدم خدمات متخصصة في أكثر من 50 تخصصاً طبياً.',
            emergency_available=True,
            status=FacilityStatus.ACTIVE
        )
    )
    print(f"  + Hospital: {h2.name}")

    h3, _ = Hospital.objects.get_or_create(
        name='Cleveland Clinic Abu Dhabi',
        defaults=dict(
            name_ar='كليفلاند كلينيك أبوظبي',
            photo='https://images.unsplash.com/photo-1538108149393-fbbd81895907?auto=format&fit=crop&q=80&w=800',
            location='Abu Dhabi',
            address='Al Maryah Island, Abu Dhabi, UAE',
            address_ar='جزيرة المارية، أبوظبي، الإمارات',
            phone='+97126596000',
            operating_hours='Open 24/7',
            operating_hours_ar='مفتوح 24/7',
            about='Cleveland Clinic Abu Dhabi delivers world-class quaternary and tertiary care with 364 beds. The hospital is a branch of the globally renowned Cleveland Clinic.',
            about_ar='كليفلاند كلينيك أبوظبي يقدم رعاية طبية متميزة تضم 364 سريراً.',
            emergency_available=True,
            status=FacilityStatus.ACTIVE
        )
    )
    print(f"  + Hospital: {h3.name}")

    h4, _ = Hospital.objects.get_or_create(
        name='Dubai Hospital',
        defaults=dict(
            name_ar='مستشفى دبي',
            photo='https://images.unsplash.com/photo-1516549655169-df83a0774514?auto=format&fit=crop&q=80&w=800',
            location='Dubai',
            address='Al Baraha, Deira, Dubai, UAE',
            address_ar='البراحة، ديرة، دبي، الإمارات',
            phone='+97142197000',
            operating_hours='Open 24/7',
            operating_hours_ar='مفتوح 24/7',
            about='Dubai Hospital is one of the largest government hospitals in the UAE, providing comprehensive healthcare services across all medical specialties.',
            about_ar='مستشفى دبي من أكبر المستشفيات الحكومية في الإمارات.',
            emergency_available=True,
            status=FacilityStatus.ACTIVE
        )
    )
    print(f"  + Hospital: {h4.name}")

    h5, _ = Hospital.objects.get_or_create(
        name='Burjeel Hospital Abu Dhabi',
        defaults=dict(
            name_ar='مستشفى برجيل أبوظبي',
            photo='https://images.unsplash.com/photo-1631217868264-e5b90bb7e133?auto=format&fit=crop&q=80&w=800',
            location='Abu Dhabi',
            address='35th Street, Tourist Club Area, Abu Dhabi, UAE',
            address_ar='شارع 35، منطقة النادي السياحي، أبوظبي',
            phone='+97125065065',
            operating_hours='Open 24/7',
            operating_hours_ar='مفتوح 24/7',
            about='Burjeel Hospital is a leading multi-specialty hospital in Abu Dhabi offering advanced medical care with a team of over 500 highly skilled specialists.',
            about_ar='مستشفى برجيل هو مستشفى متعدد التخصصات رائد في أبوظبي.',
            emergency_available=True,
            status=FacilityStatus.ACTIVE
        )
    )
    print(f"  + Hospital: {h5.name}")

    h6, _ = Hospital.objects.get_or_create(
        name='Aster Hospital Mankhool',
        defaults=dict(
            name_ar='مستشفى أستر المنخول',
            photo='https://images.unsplash.com/photo-1581595220892-b0739db3ba8c?auto=format&fit=crop&q=80&w=800',
            location='Dubai',
            address='Mankhool Road, Bur Dubai, Dubai, UAE',
            address_ar='طريق المنخول، بر دبي، دبي',
            phone='+97143638800',
            operating_hours='Open 24/7',
            operating_hours_ar='مفتوح 24/7',
            about='Aster Hospital Mankhool is an affordable multi-specialty hospital in Bur Dubai committed to delivering quality healthcare to diverse communities.',
            about_ar='مستشفى أستر المنخول مستشفى متعدد التخصصات في بر دبي.',
            emergency_available=True,
            status=FacilityStatus.ACTIVE
        )
    )
    print(f"  + Hospital: {h6.name}")

    print("\n=== 3. Clinics ===")

    c1, _ = Clinic.objects.get_or_create(
        name='Emirates Skin & Dermatology Clinic',
        defaults=dict(
            name_ar='عيادة الإمارات للجلدية',
            photo='https://images.unsplash.com/photo-1576671081837-49000212a370?auto=format&fit=crop&q=80&w=800',
            location='Dubai',
            address='Jumeirah Beach Road, Dubai, UAE',
            address_ar='شارع جميرا بيتش رود، دبي',
            primary_specialty='Dermatology',
            phone='+97143445566',
            operating_hours='Sun-Thu: 9am-9pm',
            operating_hours_ar='الأحد-الخميس: 9ص-9م',
            about='Specialized dermatology and aesthetics clinic offering laser treatments, skin care, and cosmetic procedures.',
            about_ar='عيادة متخصصة في الأمراض الجلدية والتجميل.',
            status=FacilityStatus.ACTIVE
        )
    )
    print(f"  + Clinic: {c1.name}")

    c2, _ = Clinic.objects.get_or_create(
        name='Dubai Orthopedic & Sports Medicine Clinic',
        defaults=dict(
            name_ar='عيادة دبي لجراحة العظام',
            photo='https://images.unsplash.com/photo-1588776814546-1ffedbe0f38b?auto=format&fit=crop&q=80&w=800',
            location='Dubai',
            address='Al Wasl Road, Jumeirah, Dubai, UAE',
            address_ar='شارع الوصل، جميرا، دبي',
            primary_specialty='Orthopedics',
            phone='+97143669900',
            operating_hours='Sun-Thu: 8am-8pm',
            operating_hours_ar='الأحد-الخميس: 8ص-8م',
            about='Premier orthopedic and sports medicine clinic offering physiotherapy, joint replacements, and sports injury treatment.',
            about_ar='عيادة متميزة لجراحة العظام والطب الرياضي.',
            status=FacilityStatus.ACTIVE
        )
    )
    print(f"  + Clinic: {c2.name}")

    c3, _ = Clinic.objects.get_or_create(
        name='Abu Dhabi Cardiology & Heart Center',
        defaults=dict(
            name_ar='مركز أبوظبي لأمراض القلب',
            photo='https://images.unsplash.com/photo-1559757148-5c350d0d3c56?auto=format&fit=crop&q=80&w=800',
            location='Abu Dhabi',
            address='Khalidiyah Street, Abu Dhabi, UAE',
            address_ar='شارع الخالدية، أبوظبي',
            primary_specialty='Cardiology',
            phone='+97124422233',
            operating_hours='Daily: 8am-10pm',
            operating_hours_ar='يومياً: 8ص-10م',
            about='Leading cardiology center with advanced cardiac imaging, catheterization labs, and cardiac rehabilitation.',
            about_ar='مركز رائد لأمراض القلب يوفر تصوير قلبي متقدم.',
            status=FacilityStatus.ACTIVE
        )
    )
    print(f"  + Clinic: {c3.name}")

    c4, _ = Clinic.objects.get_or_create(
        name='NMC Royal Eye Hospital Sharjah',
        defaults=dict(
            name_ar='مستشفى NMC رويال للعيون',
            photo='https://images.unsplash.com/photo-1530497610245-94d3c16cda28?auto=format&fit=crop&q=80&w=800',
            location='Sharjah',
            address='Al Nahda, Sharjah, UAE',
            address_ar='النهدة، الشارقة',
            primary_specialty='Ophthalmology',
            phone='+97165745545',
            operating_hours='Sun-Thu: 8am-8pm',
            operating_hours_ar='الأحد-الخميس: 8ص-8م',
            about='Specialized eye hospital offering LASIK, cataract surgery, retinal care, and comprehensive ophthalmology services.',
            about_ar='مستشفى متخصص للعيون يقدم عمليات الليزر وإزالة المياه البيضاء.',
            status=FacilityStatus.ACTIVE
        )
    )
    print(f"  + Clinic: {c4.name}")

    print("\n=== 4. Hospital Departments ===")

    dept_data = [
        (h1, [('Cardiology', 'Dr. Sami Al Fardan', 40), ('Oncology', 'Dr. Lisa Chang', 30), ('Neurology', 'Dr. Ahmed Nassif', 25)]),
        (h2, [('Internal Medicine', 'Dr. Paul Muller', 50), ('Pediatrics', 'Dr. Sara El Haddad', 35)]),
        (h3, [('Cardiac Surgery', 'Dr. James OBrien', 20), ('Transplant Medicine', 'Dr. Amira Youssef', 15)]),
        (h4, [('Emergency Medicine', 'Dr. Khalil Ibrahim', 80), ('Orthopedics', 'Dr. Tariq Al Qasim', 30)]),
        (h5, [('Obstetrics & Gynecology', 'Dr. Hana Al Rashidi', 45), ('Neonatology', 'Dr. Mohamed Al Amin', 20)]),
        (h6, [('General Surgery', 'Dr. Priya Nair', 25), ('Gastroenterology', 'Dr. Faisal Al Habsi', 20)]),
    ]

    for hospital, depts in dept_data:
        for dept_name, hod, beds in depts:
            FacilityDepartment.objects.get_or_create(
                hospital=hospital,
                name=dept_name,
                defaults={'head_of_department': hod, 'bed_capacity': beds}
            )
    print("  + Departments created")

    print("\n=== 5. Doctors ===")

    WEEK_DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday']
    SLOTS_MORNING = ['09:00 - 09:30', '09:30 - 10:00', '10:00 - 10:30', '10:30 - 11:00', '11:00 - 11:30', '11:30 - 12:00']
    SLOTS_AFTERNOON = ['14:00 - 14:30', '14:30 - 15:00', '15:00 - 15:30', '15:30 - 16:00', '16:00 - 16:30', '16:30 - 17:00']
    SLOTS_ALL = SLOTS_MORNING + SLOTS_AFTERNOON

    doctors_data = [
        # (name, name_ar, specialty, hospital, clinic, user, location, exp_years, fee, about, photo, days, slots)
        (
            'Dr. Omar Khalid Al Hassan', 'د. عمر خالد الحسن', 'Cardiology', h1, None, doctor_user,
            'Dubai', 18, 600,
            'Board-certified interventional cardiologist with 18 years of experience in advanced cardiac procedures including TAVR, complex PCI, and structural heart disease management.',
            'https://images.unsplash.com/photo-1612349317150-e413f6a5b16d?auto=format&fit=crop&q=80&w=400',
            WEEK_DAYS, SLOTS_ALL
        ),
        (
            'Dr. Sarah Mitchell', '', 'Neurology', h1, None, None,
            'Dubai', 14, 550,
            'Experienced neurologist specializing in epilepsy, movement disorders, and stroke management. Fellow of the American Academy of Neurology.',
            'https://images.unsplash.com/photo-1594824476967-48c8b964273f?auto=format&fit=crop&q=80&w=400',
            ['Sunday', 'Monday', 'Wednesday', 'Thursday'], SLOTS_MORNING
        ),
        (
            'Dr. Fatima Al Zaabi', 'د. فاطمة الزعابي', 'Oncology', h1, None, None,
            'Dubai', 16, 650,
            'Senior consultant clinical oncologist specializing in precision cancer therapies, targeted treatments, immunotherapy, and multi-disciplinary breast cancer management.',
            'https://images.unsplash.com/photo-1559839734-2b71ea197ec2?auto=format&fit=crop&q=80&w=400',
            WEEK_DAYS, SLOTS_MORNING
        ),
        (
            'Dr. Rajesh Patel', '', 'Orthopedics', h2, None, None,
            'Dubai', 20, 700,
            'Renowned orthopedic surgeon specializing in minimally invasive joint replacement, sports injuries, and spine surgery with over 3000 successful surgeries.',
            'https://images.unsplash.com/photo-1622253692010-333f2da6031d?auto=format&fit=crop&q=80&w=400',
            ['Monday', 'Tuesday', 'Thursday'], SLOTS_MORNING
        ),
        (
            'Dr. Hana Al Rashidi', 'د. هناء الراشدي', 'Obstetrics & Gynecology', h2, None, None,
            'Dubai', 12, 500,
            'Specialist in high-risk pregnancies, laparoscopic gynecological surgery, and maternal-fetal medicine. Arabic and English speaking.',
            'https://images.unsplash.com/photo-1559839734-2b71ea197ec2?auto=format&fit=crop&q=80&w=400',
            ['Sunday', 'Tuesday', 'Wednesday', 'Saturday'], SLOTS_ALL
        ),
        (
            'Dr. James OBrien', '', 'Cardiac Surgery', h3, None, None,
            'Abu Dhabi', 25, 1200,
            'Internationally acclaimed cardiac surgeon with expertise in CABG, valve repair/replacement, and heart transplantation at Cleveland Clinic Abu Dhabi.',
            'https://images.unsplash.com/photo-1537368910025-700350fe46c7?auto=format&fit=crop&q=80&w=400',
            ['Sunday', 'Monday', 'Tuesday'], SLOTS_MORNING
        ),
        (
            'Dr. Amira Youssef', 'د. أميرة يوسف', 'Internal Medicine', h3, None, None,
            'Abu Dhabi', 10, 450,
            'Internal medicine physician specializing in complex multi-system diseases, autoimmune conditions, and preventive medicine.',
            'https://images.unsplash.com/photo-1643297654416-05795d62e39c?auto=format&fit=crop&q=80&w=400',
            WEEK_DAYS, SLOTS_ALL
        ),
        (
            'Dr. Khalil Ibrahim', 'د. خليل إبراهيم', 'Emergency Medicine', h4, None, None,
            'Dubai', 15, 350,
            'Emergency medicine consultant with extensive experience in trauma, critical care, and disaster medicine at Dubai Hospital.',
            'https://images.unsplash.com/photo-1612349317150-e413f6a5b16d?auto=format&fit=crop&q=80&w=400',
            ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Saturday'], SLOTS_ALL
        ),
        (
            'Dr. Priya Nair', '', 'Gastroenterology', h6, None, None,
            'Dubai', 11, 480,
            'Gastroenterologist specializing in advanced endoscopy, inflammatory bowel disease, and hepatology at Aster Hospital.',
            'https://images.unsplash.com/photo-1584516150909-c43483ee7932?auto=format&fit=crop&q=80&w=400',
            ['Monday', 'Wednesday', 'Thursday', 'Saturday'], SLOTS_AFTERNOON
        ),
        (
            'Dr. Ahmed Nassif', 'د. أحمد ناصيف', 'Dermatology', None, c1, None,
            'Dubai', 9, 420,
            'Dermatologist with expertise in medical and cosmetic dermatology including laser treatments, acne management, and skin cancer screening.',
            'https://images.unsplash.com/photo-1582750433449-648ed127bb54?auto=format&fit=crop&q=80&w=400',
            ['Sunday', 'Monday', 'Tuesday', 'Thursday'], SLOTS_MORNING
        ),
        (
            'Dr. Tariq Al Qasim', 'د. طارق القاسم', 'Orthopedics', None, c2, None,
            'Dubai', 16, 600,
            'Orthopedic surgeon and sports medicine specialist with expertise in arthroscopic surgery, ACL reconstruction, and platelet-rich plasma therapy.',
            'https://images.unsplash.com/photo-1622253692010-333f2da6031d?auto=format&fit=crop&q=80&w=400',
            ['Sunday', 'Tuesday', 'Wednesday', 'Thursday'], SLOTS_ALL
        ),
        (
            'Dr. Layla Al Mansouri', 'د. ليلى المنصوري', 'Cardiology', None, c3, None,
            'Abu Dhabi', 13, 550,
            'Cardiologist specializing in heart failure management, cardiac imaging, and preventive cardiology.',
            'https://images.unsplash.com/photo-1494790108377-be9c29b29330?auto=format&fit=crop&q=80&w=400',
            ['Sunday', 'Monday', 'Wednesday', 'Thursday'], SLOTS_MORNING
        ),
        (
            'Dr. Faisal Al Habsi', 'د. فيصل الحبسي', 'Ophthalmology', None, c4, None,
            'Sharjah', 8, 380,
            'Ophthalmologist specializing in LASIK refractive surgery, cataract surgery, glaucoma management, and diabetic retinopathy.',
            'https://images.unsplash.com/photo-1559839734-2b71ea197ec2?auto=format&fit=crop&q=80&w=400',
            ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Saturday'], SLOTS_ALL
        ),
        (
            'Dr. Sara El Haddad', 'د. سارة الحداد', 'Pediatrics', h2, None, None,
            'Dubai', 14, 450,
            'Consultant pediatrician specializing in general pediatrics, childhood allergies, developmental milestones, and neonatal follow-up at Mediclinic City Hospital.',
            'https://images.unsplash.com/photo-1594824476967-48c8b964273f?auto=format&fit=crop&q=80&w=400',
            ['Sunday', 'Monday', 'Wednesday', 'Thursday'], SLOTS_MORNING
        ),
        (
            'Dr. Marcus Vance', '', 'Physiotherapy', None, c2, None,
            'Dubai', 12, 400,
            'Specialist physical therapist focusing on musculoskeletal rehabilitation, sports injury recovery, post-operative mobility, and spinal biomechanics.',
            'https://images.unsplash.com/photo-1537368910025-700350fe46c7?auto=format&fit=crop&q=80&w=400',
            WEEK_DAYS, SLOTS_ALL
        ),
        (
            'Dr. Elena Rostova', '', 'Radiology', h4, None, None,
            'Dubai', 15, 550,
            'Consultant diagnostic radiologist specializing in neuroimaging, 3T MRI interpretation, multi-slice CT, and abdominal ultrasound diagnostics.',
            'https://images.unsplash.com/photo-1559839734-2b71ea197ec2?auto=format&fit=crop&q=80&w=400',
            ['Sunday', 'Tuesday', 'Thursday'], SLOTS_MORNING
        ),
        (
            'Dr. Tariq Mansoor', 'د. طارق منصور', 'ENT', h4, None, None,
            'Dubai', 16, 520,
            'Senior consultant ENT and head & neck surgeon specializing in endoscopic sinus surgery, pediatric otolaryngology, and hearing disorder treatments.',
            'https://images.unsplash.com/photo-1622253692010-333f2da6031d?auto=format&fit=crop&q=80&w=400',
            ['Monday', 'Wednesday', 'Thursday', 'Saturday'], SLOTS_AFTERNOON
        ),
    ]

    for (name, name_ar, specialty, hospital, clinic, user, location, exp_years, fee, about, photo, days, slots) in doctors_data:
        doc, created = Doctor.objects.get_or_create(
            name=name,
            defaults=dict(
                name_ar=name_ar,
                specialty=specialty,
                hospital=hospital,
                clinic=clinic,
                user=user,
                location=location,
                experience_years=exp_years,
                experience_text=f'{exp_years}+ Years Experience',
                experience_text_ar=f'{exp_years}+ سنة خبرة',
                consultation_fee=fee,
                about=about,
                photo=photo,
                rating=0.00,
                review_count=0,
                status=FacilityStatus.ACTIVE
            )
        )
        if created:
            DoctorSchedule.objects.get_or_create(
                doctor=doc,
                defaults={
                    'available_days': days,
                    'standard_slots': slots,
                    'slot_duration_minutes': 30
                }
            )
            print(f"  + Doctor: {name} ({specialty})")
        else:
            print(f"  ~ Skipped existing: {name}")

    print("\n=== 6. Verified Patient Reviews & Rating Calculation ===")
    from datetime import date, timedelta
    from apps.appointments.models import Appointment, AppointmentStatus, DoctorReview
    from apps.appointments.services import recalculate_doctor_rating

    patient_user = User.objects.filter(role=UserRole.PATIENT).first()
    patient_profile = getattr(patient_user, 'patient_profile', None)

    reviews_data = [
        ('Dr. Omar Khalid Al Hassan', [
            (5, 'Excellent interventional cardiologist. He took the time to explain my cardiac catheterization procedure with utter clarity.'),
            (5, 'Very knowledgeable and compassionate. The clinic staff at American Hospital were top notch.'),
            (5, 'Outstanding care and diagnosis. Highly recommended for complex heart consultations.'),
            (4, 'Great specialist, very thorough assessment and prompt treatment follow-up.')
        ]),
        ('Dr. Sarah Mitchell', [
            (5, 'Dr. Mitchell was incredible with my neurological treatment plan. My symptoms have improved dramatically.'),
            (5, 'Very attentive and professional neurologist. She addressed all my concerns patiently.'),
            (5, 'Compassionate and sharp physician. Five stars!')
        ]),
        ('Dr. Fatima Al Zaabi', [
            (5, 'World class oncology care. Dr. Fatima provided the reassurance and precise oncology roadmap our family needed.'),
            (4, 'Very supportive, empathetic, and exceptionally thorough doctor.')
        ]),
        ('Dr. Rajesh Patel', [
            (5, 'Top orthopedic specialist! Knee replacement surgery was smooth and the recovery was very fast.'),
            (5, 'Very attentive and professional surgeon. Fully restored my mobility.')
        ]),
        ('Dr. Sara El Haddad', [
            (5, 'Wonderful pediatrician. She was very gentle and caring with my daughter.'),
            (5, 'Extremely knowledgeable and puts both kids and parents at complete ease.')
        ]),
    ]

    today = date.today()
    for doc_name, revs in reviews_data:
        doc = Doctor.objects.filter(name=doc_name).first()
        if not doc:
            continue
        for idx, (star, comm) in enumerate(revs):
            appt_date = today - timedelta(days=(idx + 1) * 7)
            appt, _ = Appointment.objects.get_or_create(
                doctor=doc,
                date=appt_date,
                time_slot='10:00 - 10:30',
                defaults=dict(
                    booked_by=patient_user,
                    hospital=doc.hospital,
                    clinic=doc.clinic,
                    patient_profile=patient_profile,
                    patient_name_snapshot=patient_user.name if patient_user else 'Patient',
                    patient_phone_snapshot=patient_user.phone if patient_user else '+971501234567',
                    patient_email_snapshot=patient_user.email if patient_user else 'patient@meetadr.demo',
                    specialty_snapshot=doc.specialty,
                    status=AppointmentStatus.COMPLETED,
                    notes='Follow-up completed'
                )
            )
            DoctorReview.objects.get_or_create(
                appointment=appt,
                defaults=dict(
                    doctor=doc,
                    patient=patient_user,
                    rating=star,
                    comment=comm
                )
            )
        recalculate_doctor_rating(doc.id)
        doc.refresh_from_db()
        print(f"  + Review synced for {doc.name}: {doc.rating} stars ({doc.review_count} reviews)")

    for d in Doctor.objects.exclude(name__in=[r[0] for r in reviews_data]):
        recalculate_doctor_rating(d.id)

    print("\n=== DONE ===")
    print("Database seeded successfully!")
    print("\nDemo credentials:")
    print("  Patient  -> patient@meetadr.demo  / Patient@123")
    print("  Doctor   -> doctor@meetadr.demo   / Doctor@123")
    print("  Hospital -> hospital@meetadr.demo / Hospital@123")
    print("  Admin    -> admin@meetadr.demo    / Admin@123")
    from apps.accounts.models import User
    from apps.facilities.models import Hospital, Clinic
    from apps.doctors.models import Doctor
    print(f"\nData: {User.objects.count()} users | {Hospital.objects.count()} hospitals | {Clinic.objects.count()} clinics | {Doctor.objects.count()} doctors")

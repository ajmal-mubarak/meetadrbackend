from django.db import migrations
from django.contrib.auth.hashers import make_password

def create_subadmin_user(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    if not User.objects.filter(email='subadmin@meetadr.demo').exists():
        User.objects.create(
            email='subadmin@meetadr.demo',
            name='Operations Sub-Admin',
            role='subadmin',
            phone='+971501234567',
            password=make_password('Subadmin@123'),
            is_active=True,
            is_staff=True,
        )

def remove_subadmin_user(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    User.objects.filter(email='subadmin@meetadr.demo').delete()

class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_alter_user_role'),
    ]

    operations = [
        migrations.RunPython(create_subadmin_user, remove_subadmin_user),
    ]

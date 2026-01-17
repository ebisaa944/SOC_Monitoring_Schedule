# create_initial_data.py
import os
import django
from datetime import date, datetime, time, timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'soc_schedule.settings')
django.setup()

from schedule_app.models import (
    Analyst, MonitoringType, SchedulePattern, 
    ScheduleGenerator, MonitoringAssignment
)
from django.utils import timezone

def create_initial_data():
    print("Creating initial data for SOC Monitoring Schedule...")
    
    # 1. Create Analysts in pattern order
    analysts_data = [
        {'username': 'ebisa', 'name': 'Ebisa', 'email': 'ebisa@soc.com', 'phone': '+251911111111', 'pattern_position': 0},
        {'username': 'gezagn', 'name': 'Gezagn', 'email': 'gezagn@soc.com', 'phone': '+251922222222', 'pattern_position': 1},
        {'username': 'natnael', 'name': 'Natnael', 'email': 'natnael@soc.com', 'phone': '+251933333333', 'pattern_position': 2},
        {'username': 'nurahmed', 'name': 'Nurahmed', 'email': 'nurahmed@soc.com', 'phone': '+251944444444', 'pattern_position': 3},
    ]
    
    for data in analysts_data:
        analyst, created = Analyst.objects.update_or_create(
            username=data['username'],
            defaults=data
        )
        if created:
            print(f"✓ Created analyst: {analyst.name} (Username: {analyst.username})")
            
            # Create corresponding Django User
            user = analyst.get_user()
            print(f"  Created Django user: {user.username} with password: {analyst.username}@soc2024")
    
    # 2. Create Admin user if not exists
    if not User.objects.filter(username='admin').exists():
        User.objects.create_superuser(
            username='admin',
            email='admin@soc.com',
            password='admin123',
            first_name='System',
            last_name='Administrator'
        )
        print("✓ Created admin user: admin (password: admin123)")
    
    # 2. Create Monitoring Types with Monday exceptions
    monitoring_types = [
        {
            'code': 'EM',
            'name': 'Early Morning Monitoring',
            'description': 'Server Status Report (5:00 PM previous day to 7:00 AM current day)',
            'default_start_hour': 17,  # 5:00 PM
            'default_start_minute': 0,
            'default_end_hour': 7,     # 7:00 AM
            'default_end_minute': 0,
            'monday_start_offset_hours': 58,  # Saturday 5:00 PM (38h window)
            'monday_end_offset_hours': 0,
        },
        {
            'code': 'DM',
            'name': 'Daily Monitoring',
            'description': 'Daily Events/Incidents Report (5:00 PM previous day to 5:00 PM current day)',
            'default_start_hour': 17,  # 5:00 PM
            'default_start_minute': 0,
            'default_end_hour': 17,    # 5:00 PM
            'default_end_minute': 0,
            'monday_start_offset_hours': 48,  # Friday 5:00 PM (72h window)
            'monday_end_offset_hours': 0,
        }
    ]
    
    for mt_data in monitoring_types:
        mt, created = MonitoringType.objects.update_or_create(
            code=mt_data['code'],
            defaults=mt_data
        )
        if created:
            print(f"✓ Created monitoring type: {mt.name}")
    
    # 3. Create Schedule Pattern based on your exact pattern
    # Calculate pattern for 150 days (5 months)
    em_pattern = []
    dm_pattern = []
    
    # Reference start date (today's Monday or next Monday)
    today = date.today()
    # Find the most recent Monday
    days_since_monday = today.weekday()  # Monday=0, Sunday=6
    last_monday = today - timedelta(days=days_since_monday)
    
    # Generate pattern for 150 days starting from last Monday
    for day in range(150):
        em_index = day % 4  # 0=Ebisa, 1=Gezagn, 2=Natnael, 3=Nurahmed
        dm_index = (em_index + 3) % 4  # DM is 3 positions ahead
        
        em_pattern.append(em_index)
        dm_pattern.append(dm_index)
    
    pattern, created = SchedulePattern.objects.update_or_create(
        name="SOC Monitoring Pattern",
        defaults={
            'description': 'Exact pattern: EM: Ebisa→Gezagn→Natnael→Nurahmed, DM: Nurahmed→Ebisa→Gezagn→Natnael',
            'reference_start_date': last_monday,
            'em_pattern': em_pattern,
            'dm_pattern': dm_pattern,
        }
    )
    
    if created:
        print(f"✓ Created schedule pattern with {len(em_pattern)} days")
    
    # 4. Create Schedule Generator
    generator, created = ScheduleGenerator.objects.update_or_create(
        name="SOC Schedule Generator",
        defaults={
            'pattern': pattern,
            'auto_generate': True,
            'generate_days_ahead': 150,
        }
    )
    
    if created:
        print("✓ Created schedule generator")
    
    # 5. Generate schedule for next 5 months
    print("\nGenerating schedule for next 5 months...")
    today = date.today()
    end_date = today + timedelta(days=150)
    
    assignments_created = generator.generate_schedule(today, end_date)
    print(f"✓ Generated {assignments_created} assignments from {today} to {end_date}")
    
    # 6. Show sample schedule for next 7 days
    print("\n--- Sample Schedule (Next 7 Days) ---")
    assignments = MonitoringAssignment.objects.filter(
        date__range=[today, today + timedelta(days=6)]
    ).order_by('date', 'monitoring_type__code')
    
    current_date = None
    for assignment in assignments:
        if assignment.date != current_date:
            current_date = assignment.date
            day_name = assignment.date.strftime('%A')
            print(f"\n{day_name}, {assignment.date}:")
        
        hours = assignment.duration_hours
        window_info = f"({hours:.0f}h)" if hours.is_integer() else f"({hours:.1f}h)"
        
        print(f"  • {assignment.monitoring_type}: {assignment.analyst.name} {window_info}")
        if assignment.is_extended_window:
            print(f"    ⚠ Extended window: {assignment.window_start.strftime('%Y-%m-%d %H:%M')} to {assignment.window_end.strftime('%Y-%m-%d %H:%M')}")
    
    # 7. Show Monday duties for next 4 weeks
    print("\n--- Monday Duties (Next 4 Weeks) ---")
    mondays = []
    for i in range(4):
        monday_date = last_monday + timedelta(weeks=i)
        if monday_date >= today:
            mondays.append(monday_date)
    
    for monday in mondays:
        em_assignment = MonitoringAssignment.objects.filter(
            date=monday, 
            monitoring_type__code='EM'
        ).first()
        dm_assignment = MonitoringAssignment.objects.filter(
            date=monday, 
            monitoring_type__code='DM'
        ).first()
        
        if em_assignment and dm_assignment:
            print(f"\n{monday.strftime('%Y-%m-%d')} (Week {(monday - last_monday).days // 7 + 1}):")
            print(f"  EM: {em_assignment.analyst.name} ({em_assignment.duration_hours:.0f}h)")
            print(f"  DM: {dm_assignment.analyst.name} ({dm_assignment.duration_hours:.0f}h)")
    
    print("\n✅ Initial data setup complete!")
    print(f"\nTotal analysts: {Analyst.objects.count()}")
    print(f"Total assignments: {MonitoringAssignment.objects.count()}")
    print(f"Schedule covers: {today} to {end_date}")

if __name__ == '__main__':
    create_initial_data()
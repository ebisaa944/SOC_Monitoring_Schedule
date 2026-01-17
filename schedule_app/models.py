# schedule_app/models.py
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from datetime import date, datetime, time, timedelta
import uuid

class Analyst(models.Model):
    """SOC Analyst Model for the 4 team members"""
    # One-to-one relationship with Django User model (better integration)
    user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE,
        related_name='analyst_profile',
        null=True,  # Allow null initially
        blank=True
    )
    
    # Analyst's display name (separate from username)
    display_name = models.CharField(max_length=100, unique=True)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    is_active = models.BooleanField(default=True)
    join_date = models.DateField(auto_now_add=True)
    
    # Pattern position (0=Ebisa, 1=Gezagn, 2=Natnael, 3=Nurahmed)
    pattern_position = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(3)],
        help_text="Position in rotation pattern (0-3)"
    )
    
    class Meta:
        ordering = ['pattern_position', 'display_name']
        verbose_name = 'SOC Analyst'
        verbose_name_plural = 'SOC Analysts'
    
    def __str__(self):
        return self.display_name
    
    @property
    def username(self):
        """Get username from associated User object"""
        return self.user.username if self.user else None
    
    @property
    def name(self):
        """Compatibility property for older code expecting .name"""
        return self.display_name
    
    def ensure_user_account(self):
        """Create or update Django User account for this analyst"""
        if not self.user:
            # Generate username from display name (lowercase, no spaces)
            username_base = self.display_name.lower().replace(' ', '_')
            username = username_base
            
            # Ensure username is unique
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{username_base}_{counter}"
                counter += 1
            
            # Create user account
            user = User.objects.create_user(
                username=username,
                email=self.email,
                password=f"{username}@soc2024",  # Default password
                first_name=self.display_name.split()[0] if ' ' in self.display_name else self.display_name,
                is_active=self.is_active
            )
            self.user = user
            self.save()
        
        return self.user
    
    def save(self, *args, **kwargs):
        # Auto-generate email if not provided
        if not self.email and self.display_name:
            self.email = f"{self.display_name.lower().replace(' ', '.')}@soc.example.com"
        
        # Make sure email is lowercase
        if self.email:
            self.email = self.email.lower()
        
        super().save(*args, **kwargs)

class MonitoringType(models.Model):
    """Types of monitoring: Early Morning (EM) or Daily (DM)"""
    MONITORING_TYPES = [
        ('EM', 'Early Morning Monitoring (Server Status)'),
        ('DM', 'Daily Monitoring (Events/Incidents)'),
    ]
    
    code = models.CharField(max_length=2, choices=MONITORING_TYPES, unique=True)
    name = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    
    # Default time windows
    default_start_hour = models.IntegerField(
        default=17, 
        help_text="5 PM = 17 (24-hour format)"
    )
    default_start_minute = models.IntegerField(default=0)
    default_end_hour = models.IntegerField(
        default=7, 
        help_text="7 AM = 7 (24-hour format)"
    )
    default_end_minute = models.IntegerField(default=0)
    
    # Monday exceptions (in hours)
    monday_start_offset_hours = models.IntegerField(
        default=0,
        help_text="Hours to extend start time back for Monday"
    )
    monday_end_offset_hours = models.IntegerField(
        default=0,
        help_text="Hours to extend end time forward for Monday"
    )
    
    class Meta:
        verbose_name = 'Monitoring Type'
        verbose_name_plural = 'Monitoring Types'
    
    def __str__(self):
        return f"{self.get_code_display()} ({self.name})"
    
    def get_time_window_for_date(self, target_date):
        """Calculate time window for a specific date"""
        from datetime import datetime, time
        
        is_monday = target_date.weekday() == 0
        
        # Calculate start time
        if is_monday and self.monday_start_offset_hours > 0:
            start_date = target_date - timedelta(days=self.monday_start_offset_hours // 24)
            start_hour = self.default_start_hour - (self.monday_start_offset_hours % 24)
            if start_hour < 0:
                start_hour += 24
                start_date -= timedelta(days=1)
        else:
            start_date = target_date - timedelta(days=1)
            start_hour = self.default_start_hour
        
        start_time = datetime.combine(start_date, time(start_hour, self.default_start_minute))
        
        # Calculate end time
        if is_monday and self.monday_end_offset_hours > 0:
            end_hour = self.default_end_hour + self.monday_end_offset_hours
            end_date = target_date
            if end_hour >= 24:
                end_hour -= 24
                end_date += timedelta(days=1)
        else:
            end_date = target_date
            end_hour = self.default_end_hour
        
        end_time = datetime.combine(end_date, time(end_hour, self.default_end_minute))
        
        return start_time, end_time
    
    def save(self, *args, **kwargs):
        # Set appropriate end hour based on monitoring type
        if self.code == 'EM' and self.default_end_hour == 17:  # Wrong for EM
            self.default_end_hour = 7
        elif self.code == 'DM' and self.default_end_hour == 7:  # Wrong for DM
            self.default_end_hour = 17
        
        super().save(*args, **kwargs)

class SchedulePattern(models.Model):
    """Stores the exact pattern you provided"""
    name = models.CharField(max_length=100, default="SOC Monitoring Pattern")
    description = models.TextField(blank=True)
    
    # Reference start date (Week 1 Monday from your pattern)
    reference_start_date = models.DateField(default=date.today)
    
    # Pattern definition
    em_pattern = models.JSONField(
        default=list, 
        help_text="EM rotation pattern [0,1,2,3,0,1,2,...]"
    )
    dm_pattern = models.JSONField(
        default=list, 
        help_text="DM rotation pattern [3,0,1,2,3,0,1,...]"
    )
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Schedule Pattern'
        verbose_name_plural = 'Schedule Patterns'
    
    def __str__(self):
        return self.name
    
    def get_assignments_for_date(self, target_date):
        """Get EM and DM assignments for a specific date using the pattern"""
        days_diff = (target_date - self.reference_start_date).days
        
        if days_diff < 0:
            # If date is before reference, go backwards in pattern
            days_diff = abs(days_diff)
            pattern_length = len(self.em_pattern) if self.em_pattern else 4
            
            em_index = self.em_pattern[-days_diff % pattern_length] if self.em_pattern else days_diff % 4
            dm_index = self.dm_pattern[-days_diff % pattern_length] if self.dm_pattern else (em_index + 3) % 4
        else:
            # Normal forward calculation
            if self.em_pattern and len(self.em_pattern) > days_diff:
                em_index = self.em_pattern[days_diff]
                dm_index = self.dm_pattern[days_diff]
            else:
                # Calculate based on the pattern formula
                em_index = days_diff % 4
                dm_index = (em_index + 3) % 4  # DM is always 3 positions ahead
        
        return em_index, dm_index
    
    def generate_pattern_sequence(self, days=365):
        """Generate pattern sequence for a number of days"""
        em_sequence = []
        dm_sequence = []
        
        for day in range(days):
            em_index = day % 4
            dm_index = (em_index + 3) % 4
            em_sequence.append(em_index)
            dm_sequence.append(dm_index)
        
        return em_sequence, dm_sequence
    
    def save(self, *args, **kwargs):
        # Auto-generate patterns if empty
        if not self.em_pattern or not self.dm_pattern:
            em_pattern, dm_pattern = self.generate_pattern_sequence(365)
            self.em_pattern = em_pattern
            self.dm_pattern = dm_pattern
        
        super().save(*args, **kwargs)

class MonitoringAssignment(models.Model):
    """Daily assignment of analysts to monitoring duties"""
    date = models.DateField()
    monitoring_type = models.ForeignKey(MonitoringType, on_delete=models.CASCADE)
    analyst = models.ForeignKey(Analyst, on_delete=models.CASCADE, related_name='assignments')
    
    # Calculated time window
    window_start = models.DateTimeField()
    window_end = models.DateTimeField()
    duration_hours = models.FloatField(editable=False)
    
    # Special flags
    is_monday_assignment = models.BooleanField(default=False)
    is_extended_window = models.BooleanField(default=False)
    
    # Status tracking
    STATUS_CHOICES = [
        ('SCHEDULED', 'Scheduled'),
        ('CONFIRMED', 'Confirmed'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='SCHEDULED')
    notes = models.TextField(blank=True)
    completion_notes = models.TextField(blank=True)
    
    # Report tracking
    report_submitted = models.BooleanField(default=False)
    report_submitted_at = models.DateTimeField(null=True, blank=True)
    report_verified = models.BooleanField(default=False)
    report_verified_by = models.ForeignKey(
        Analyst, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='verified_reports'
    )
    
    # Audit fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['date', 'monitoring_type']
        ordering = ['date', 'monitoring_type__code']
        indexes = [
            models.Index(fields=['date', 'analyst']),
            models.Index(fields=['status', 'date']),
            models.Index(fields=['analyst', 'date']),
        ]
        verbose_name = 'Monitoring Assignment'
        verbose_name_plural = 'Monitoring Assignments'
    
    def __str__(self):
        return f"{self.date} - {self.monitoring_type.get_code_display()}: {self.analyst.display_name}"
    
    def save(self, *args, **kwargs):
        # Auto-calculate duration
        if self.window_start and self.window_end:
            delta = self.window_end - self.window_start
            self.duration_hours = round(delta.total_seconds() / 3600, 2)
        else:
            # If no window set, calculate based on monitoring type
            if self.monitoring_type and self.date:
                self.window_start, self.window_end = self.monitoring_type.get_time_window_for_date(self.date)
                delta = self.window_end - self.window_start
                self.duration_hours = round(delta.total_seconds() / 3600, 2)
        
        # Check if it's Monday
        self.is_monday_assignment = self.date.weekday() == 0
        
        # Check if extended window (for Monday special cases)
        if self.is_monday_assignment:
            if self.monitoring_type.code == 'EM' and self.duration_hours > 14:
                self.is_extended_window = True
            elif self.monitoring_type.code == 'DM' and self.duration_hours > 24:
                self.is_extended_window = True
        
        super().save(*args, **kwargs)
    
    @property
    def is_past_due(self):
        """Check if assignment is past due"""
        return self.date < date.today() and self.status not in ['COMPLETED', 'CANCELLED']
    
    @property
    def is_current(self):
        """Check if assignment is for today"""
        return self.date == date.today()
    
    @property
    def is_future(self):
        """Check if assignment is in the future"""
        return self.date > date.today()
    
    def get_time_window_display(self):
        """Get formatted time window string"""
        return f"{self.window_start.strftime('%Y-%m-%d %H:%M')} to {self.window_end.strftime('%Y-%m-%d %H:%M')}"

class ShiftSwapRequest(models.Model):
    """Request to swap shifts between analysts"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Original assignment
    original_assignment = models.ForeignKey(
        MonitoringAssignment, 
        on_delete=models.CASCADE,
        related_name='swap_requests_outgoing'
    )
    
    # Requested swap analyst
    requested_analyst = models.ForeignKey(
        Analyst,
        on_delete=models.CASCADE,
        related_name='swap_requests_received'
    )
    
    # Status
    STATUS_CHOICES = [
        ('PENDING', 'Pending Approval'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('CANCELLED', 'Cancelled'),
        ('EXPIRED', 'Expired'),
    ]
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    reason = models.TextField()
    swap_notes = models.TextField(blank=True)
    
    # Reciprocal assignment (created when approved)
    reciprocal_assignment = models.OneToOneField(
        MonitoringAssignment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='incoming_swap'
    )
    
    # Approval chain
    requested_by = models.ForeignKey(
        Analyst, 
        on_delete=models.CASCADE, 
        related_name='swap_requests_made'
    )
    approved_by = models.ForeignKey(
        Analyst, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='swap_requests_approved'
    )
    
    # Dates
    requested_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    expiry_date = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-requested_at']
        verbose_name = 'Shift Swap Request'
        verbose_name_plural = 'Shift Swap Requests'
        indexes = [
            models.Index(fields=['status', 'expiry_date']),
        ]
    
    def clean(self):
        """Validate swap request"""
        from django.core.exceptions import ValidationError
        
        # Check if assignment date is in the past
        if self.original_assignment.date < date.today():
            raise ValidationError("Cannot swap past assignments")
        
        # Check if requested analyst is already assigned on that date
        existing_assignment = MonitoringAssignment.objects.filter(
            date=self.original_assignment.date,
            analyst=self.requested_analyst
        ).first()
        
        if existing_assignment:
            raise ValidationError(
                f"{self.requested_analyst.display_name} already has {existing_assignment.monitoring_type} on {self.original_assignment.date}"
            )
        
        # Check pattern integrity - EM and DM must be different analysts
        if self.original_assignment.monitoring_type.code == 'EM':
            dm_assignment = MonitoringAssignment.objects.filter(
                date=self.original_assignment.date,
                monitoring_type__code='DM'
            ).first()
            if dm_assignment and dm_assignment.analyst == self.requested_analyst:
                raise ValidationError("EM and DM cannot be assigned to the same analyst on the same day")
    
    def approve_swap(self, approved_by_analyst):
        """Approve and execute the swap"""
        from django.utils import timezone
        
        if self.status != 'PENDING':
            raise ValueError("Swap request is not pending")
        
        # Create reciprocal assignment
        reciprocal = MonitoringAssignment.objects.create(
            date=self.original_assignment.date,
            monitoring_type=self.original_assignment.monitoring_type,
            analyst=self.requested_analyst,
            window_start=self.original_assignment.window_start,
            window_end=self.original_assignment.window_end,
            status='CONFIRMED',
            notes=f"Swapped with {self.original_assignment.analyst.display_name}. {self.reason}"
        )
        
        # Update original assignment
        self.original_assignment.analyst = self.requested_analyst
        self.original_assignment.notes = f"Originally assigned to {self.requested_by.display_name}, swapped with {self.requested_analyst.display_name}"
        self.original_assignment.save()
        
        # Update swap request
        self.reciprocal_assignment = reciprocal
        self.approved_by = approved_by_analyst
        self.status = 'APPROVED'
        self.responded_at = timezone.now()
        self.save()
        
        return reciprocal
    
    def __str__(self):
        return f"Swap: {self.original_assignment.analyst.display_name} ↔ {self.requested_analyst.display_name} on {self.original_assignment.date}"

class LeaveRequest(models.Model):
    """Analyst leave request with coverage management"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    analyst = models.ForeignKey(
        Analyst, 
        on_delete=models.CASCADE, 
        related_name='leave_requests'
    )
    
    # Leave period
    start_date = models.DateField()
    end_date = models.DateField()
    
    # Leave details
    LEAVE_TYPES = [
        ('VACATION', 'Vacation'),
        ('SICK', 'Sick Leave'),
        ('PERSONAL', 'Personal Leave'),
        ('TRAINING', 'Training'),
        ('OTHER', 'Other'),
    ]
    
    leave_type = models.CharField(max_length=20, choices=LEAVE_TYPES)
    reason = models.TextField()
    emergency_contact = models.TextField(blank=True)
    
    # Status
    STATUS_CHOICES = [
        ('PENDING', 'Pending Approval'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    
    # Coverage arrangements
    covered_by = models.ForeignKey(
        Analyst, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='coverage_assignments'
    )
    coverage_notes = models.TextField(blank=True)
    auto_adjust_pattern = models.BooleanField(
        default=True,
        help_text="Automatically adjust rotation pattern during leave"
    )
    
    # Impact assessment
    affected_assignments = models.ManyToManyField(
        MonitoringAssignment,
        blank=True,
        related_name='affected_by_leave'
    )
    
    # Audit
    requested_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    approved_by = models.ForeignKey(
        Analyst, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='leave_requests_approved'
    )
    
    class Meta:
        ordering = ['-requested_at']
        verbose_name = 'Leave Request'
        verbose_name_plural = 'Leave Requests'
        indexes = [
            models.Index(fields=['analyst', 'status']),
            models.Index(fields=['start_date', 'end_date']),
        ]
    
    def clean(self):
        """Validate leave request"""
        from django.core.exceptions import ValidationError
        
        if self.end_date < self.start_date:
            raise ValidationError("End date must be after start date")
        
        if self.start_date < date.today():
            raise ValidationError("Cannot request leave for past dates")
    
    def assess_impact(self):
        """Assess which assignments are affected by this leave"""
        assignments = MonitoringAssignment.objects.filter(
            analyst=self.analyst,
            date__range=[self.start_date, self.end_date],
            status__in=['SCHEDULED', 'CONFIRMED']
        )
        
        self.affected_assignments.clear()
        for assignment in assignments:
            self.affected_assignments.add(assignment)
        
        return assignments.count()
    
    def approve_leave(self, approved_by_analyst, coverage_analyst=None):
        """Approve leave and arrange coverage"""
        from django.utils import timezone
        
        if self.status != 'PENDING':
            raise ValueError("Leave request is not pending")
        
        # Assess impact
        affected_count = self.assess_impact()
        
        # Arrange coverage if provided
        if coverage_analyst:
            self.covered_by = coverage_analyst
            self.coverage_notes = f"Coverage arranged by {approved_by_analyst.display_name}"
        
        # Update status
        self.approved_by = approved_by_analyst
        self.status = 'APPROVED'
        self.updated_at = timezone.now()
        self.save()
        
        # Handle coverage assignments if auto-adjust is enabled
        if self.auto_adjust_pattern and self.covered_by:
            self._arrange_coverage()
        
        return affected_count
    
    def _arrange_coverage(self):
        """Arrange coverage for affected assignments"""
        for assignment in self.affected_assignments.all():
            # Create coverage assignment
            MonitoringAssignment.objects.create(
                date=assignment.date,
                monitoring_type=assignment.monitoring_type,
                analyst=self.covered_by,
                window_start=assignment.window_start,
                window_end=assignment.window_end,
                status='CONFIRMED',
                notes=f"Covering for {self.analyst.display_name} on leave. Original assignment ID: {assignment.id}",
                is_monday_assignment=assignment.is_monday_assignment,
                is_extended_window=assignment.is_extended_window
            )
            
            # Mark original as covered
            assignment.status = 'CANCELLED'
            assignment.notes = f"Cancelled due to leave. Covered by {self.covered_by.display_name}"
            assignment.save()
    
    def __str__(self):
        return f"{self.analyst.display_name} Leave: {self.start_date} to {self.end_date}"

class ReportSubmission(models.Model):
    """Track report submissions and quality"""
    assignment = models.OneToOneField(
        MonitoringAssignment,
        on_delete=models.CASCADE,
        related_name='report_submission'
    )
    
    # Submission details
    submitted_at = models.DateTimeField(auto_now_add=True)
    submitted_by = models.ForeignKey(
        Analyst, 
        on_delete=models.CASCADE, 
        related_name='submitted_reports'
    )
    
    # Report content
    report_file = models.FileField(
        upload_to='monitoring_reports/%Y/%m/%d/', 
        blank=True, 
        null=True
    )
    summary = models.TextField()
    critical_issues = models.TextField(blank=True)
    recommendations = models.TextField(blank=True)
    
    # Quality metrics
    completeness_score = models.IntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        default=100
    )
    timeliness_score = models.IntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        default=100,
        help_text="Score based on submission time vs deadline"
    )
    
    # Review
    reviewed_by = models.ForeignKey(
        Analyst, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='reviewed_reports'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)
    is_approved = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-submitted_at']
        verbose_name = 'Report Submission'
        verbose_name_plural = 'Report Submissions'
    
    def __str__(self):
        return f"Report for {self.assignment.date} - {self.assignment.monitoring_type}"

class Notification(models.Model):
    """System notifications for analysts"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        Analyst, 
        on_delete=models.CASCADE, 
        related_name='notifications'
    )
    
    NOTIFICATION_TYPES = [
        ('SCHEDULE_CHANGE', 'Schedule Change'),
        ('SWAP_REQUEST', 'Swap Request'),
        ('SWAP_APPROVED', 'Swap Approved'),
        ('LEAVE_APPROVED', 'Leave Approved'),
        ('REPORT_DUE', 'Report Due'),
        ('SHIFT_REMINDER', 'Shift Reminder'),
        ('SYSTEM', 'System Notification'),
    ]
    
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    related_object_id = models.CharField(max_length=100, blank=True)
    related_object_type = models.CharField(max_length=50, blank=True)
    
    # Status
    is_read = models.BooleanField(default=False)
    is_important = models.BooleanField(default=False)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    scheduled_for = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read']),
            models.Index(fields=['scheduled_for', 'notification_type']),
        ]
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'
    
    def __str__(self):
        return f"{self.notification_type}: {self.title} for {self.recipient.display_name}"

class ScheduleGenerator(models.Model):
    """Generates and manages schedules based on pattern"""
    name = models.CharField(max_length=100, default="SOC Schedule Generator")
    pattern = models.ForeignKey(SchedulePattern, on_delete=models.CASCADE)
    
    # Generation settings
    auto_generate = models.BooleanField(default=True)
    generate_days_ahead = models.IntegerField(default=30)
    last_generated = models.DateTimeField(null=True, blank=True)
    
    # Validation rules
    enforce_pattern = models.BooleanField(default=True)
    allow_manual_overrides = models.BooleanField(default=False)
    require_approval_for_changes = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = 'Schedule Generator'
        verbose_name_plural = 'Schedule Generators'
    
    def generate_schedule(self, start_date, end_date):
        """Generate schedule for date range"""
        from django.db import transaction
        
        assignments_created = 0
        
        with transaction.atomic():
            current_date = start_date
            
            while current_date <= end_date:
                # Skip if assignments already exist
                existing_assignments = MonitoringAssignment.objects.filter(date=current_date)
                if existing_assignments.exists():
                    current_date += timedelta(days=1)
                    continue
                
                # Get pattern assignments for this date
                em_index, dm_index = self.pattern.get_assignments_for_date(current_date)
                
                # Get analysts
                em_analyst = Analyst.objects.filter(
                    pattern_position=em_index, 
                    is_active=True
                ).first()
                dm_analyst = Analyst.objects.filter(
                    pattern_position=dm_index, 
                    is_active=True
                ).first()
                
                if not em_analyst or not dm_analyst:
                    raise ValueError(f"Analysts not found for pattern positions {em_index}, {dm_index}")
                
                # Get monitoring types
                em_type = MonitoringType.objects.filter(code='EM').first()
                dm_type = MonitoringType.objects.filter(code='DM').first()
                
                if not em_type or not dm_type:
                    raise ValueError("Monitoring types not configured")
                
                # Calculate time windows
                em_start, em_end = em_type.get_time_window_for_date(current_date)
                dm_start, dm_end = dm_type.get_time_window_for_date(current_date)
                
                # Create EM assignment
                MonitoringAssignment.objects.create(
                    date=current_date,
                    monitoring_type=em_type,
                    analyst=em_analyst,
                    window_start=em_start,
                    window_end=em_end,
                    status='CONFIRMED'
                )
                assignments_created += 1
                
                # Create DM assignment
                MonitoringAssignment.objects.create(
                    date=current_date,
                    monitoring_type=dm_type,
                    analyst=dm_analyst,
                    window_start=dm_start,
                    window_end=dm_end,
                    status='CONFIRMED'
                )
                assignments_created += 1
                
                current_date += timedelta(days=1)
            
            self.last_generated = timezone.now()
            self.save()
        
        return assignments_created
    
    def generate_next_5_months(self):
        """Generate schedule for next 5 months"""
        today = date.today()
        end_date = today + timedelta(days=150)  # Approximately 5 months
        
        return self.generate_schedule(today, end_date)
    
    def __str__(self):
        last_gen = self.last_generated.strftime("%Y-%m-%d %H:%M") if self.last_generated else "Never"
        return f"{self.name} (Last: {last_gen})"

# Signal to create/update User when Analyst is saved
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=Analyst)
def create_user_for_analyst(sender, instance, created, **kwargs):
    """Automatically create User account when Analyst is created"""
    if created and not instance.user:
        instance.ensure_user_account()
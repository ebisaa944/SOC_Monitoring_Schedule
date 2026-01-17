# schedule_app/forms.py
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import date, timedelta
from .models import (
    MonitoringAssignment, ShiftSwapRequest, LeaveRequest,
    ReportSubmission, Analyst, MonitoringType
)

class DateInput(forms.DateInput):
    input_type = 'date'

class DateTimeInput(forms.DateTimeInput):
    input_type = 'datetime-local'

class MonitoringAssignmentForm(forms.ModelForm):
    class Meta:
        model = MonitoringAssignment
        fields = ['date', 'monitoring_type', 'analyst', 'notes']
        widgets = {
            'date': DateInput(attrs={'class': 'form-control'}),
            'monitoring_type': forms.Select(attrs={'class': 'form-control'}),
            'analyst': forms.Select(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show active analysts
        self.fields['analyst'].queryset = Analyst.objects.filter(is_active=True)
        # Only show active monitoring types
        self.fields['monitoring_type'].queryset = MonitoringType.objects.all()
    
    def clean(self):
        cleaned_data = super().clean()
        date_value = cleaned_data.get('date')
        monitoring_type = cleaned_data.get('monitoring_type')
        analyst = cleaned_data.get('analyst')
        
        if date_value and monitoring_type and analyst:
            # Check if assignment already exists for this date and monitoring type
            existing = MonitoringAssignment.objects.filter(
                date=date_value,
                monitoring_type=monitoring_type
            ).exclude(pk=self.instance.pk if self.instance else None)
            
            if existing.exists():
                raise ValidationError(
                    f"{monitoring_type} is already assigned for {date_value}"
                )
            
            # Check if analyst is already assigned to other monitoring type on same day
            other_assignment = MonitoringAssignment.objects.filter(
                date=date_value,
                analyst=analyst
            ).exclude(pk=self.instance.pk if self.instance else None)
            
            if other_assignment.exists():
                other_type = other_assignment.first().monitoring_type
                raise ValidationError(
                    f"{analyst.name} is already assigned to {other_type} on {date_value}"
                )
        
        return cleaned_data

class ShiftSwapRequestForm(forms.ModelForm):
    class Meta:
        model = ShiftSwapRequest
        fields = ['requested_analyst', 'reason']
        widgets = {
            'requested_analyst': forms.Select(attrs={'class': 'form-control'}),
            'reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Explain why you need to swap this shift...'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.assignment = kwargs.pop('assignment', None)
        self.requesting_analyst = kwargs.pop('requesting_analyst', None)
        super().__init__(*args, **kwargs)
        
        if self.assignment:
            # Exclude the current analyst and analysts already assigned that day
            assigned_analysts = MonitoringAssignment.objects.filter(
                date=self.assignment.date
            ).values_list('analyst', flat=True)
            
            self.fields['requested_analyst'].queryset = Analyst.objects.filter(
                is_active=True
            ).exclude(
                pk__in=assigned_analysts
            ).exclude(
                pk=self.assignment.analyst.pk
            )
    
    def clean(self):
        cleaned_data = super().clean()
        
        if self.assignment:
            # Check if assignment is in the past
            if self.assignment.date < date.today():
                raise ValidationError("Cannot swap past assignments")
            
            # Check if swap request already exists
            existing = ShiftSwapRequest.objects.filter(
                original_assignment=self.assignment,
                status='PENDING'
            ).exists()
            
            if existing:
                raise ValidationError("A swap request is already pending for this assignment")
        
        return cleaned_data

class LeaveRequestForm(forms.ModelForm):
    class Meta:
        model = LeaveRequest
        fields = ['start_date', 'end_date', 'leave_type', 'reason', 'emergency_contact', 'auto_adjust_pattern']
        widgets = {
            'start_date': DateInput(attrs={'class': 'form-control'}),
            'end_date': DateInput(attrs={'class': 'form-control'}),
            'leave_type': forms.Select(attrs={'class': 'form-control'}),
            'reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'emergency_contact': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'auto_adjust_pattern': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.analyst = kwargs.pop('analyst', None)
        super().__init__(*args, **kwargs)
    
    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        if start_date and end_date:
            if end_date < start_date:
                raise ValidationError("End date must be after start date")
            
            if start_date < date.today():
                raise ValidationError("Cannot request leave for past dates")
            
            # Check for overlapping leave requests
            if self.analyst:
                overlapping = LeaveRequest.objects.filter(
                    analyst=self.analyst,
                    start_date__lte=end_date,
                    end_date__gte=start_date,
                    status__in=['PENDING', 'APPROVED']
                ).exclude(pk=self.instance.pk if self.instance else None)
                
                if overlapping.exists():
                    raise ValidationError("You already have leave requested/approved for this period")
        
        return cleaned_data

class ReportSubmissionForm(forms.ModelForm):
    class Meta:
        model = ReportSubmission
        fields = ['summary', 'critical_issues', 'recommendations', 'report_file']
        widgets = {
            'summary': forms.Textarea(attrs={'class': 'form-control', 'rows': 5, 'placeholder': 'Provide a summary of your monitoring findings...'}),
            'critical_issues': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'List any critical issues found...'}),
            'recommendations': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Provide recommendations based on your findings...'}),
            'report_file': forms.FileInput(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.assignment = kwargs.pop('assignment', None)
        super().__init__(*args, **kwargs)
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Check if report is being submitted on time
        if self.assignment:
            # For EM reports, due by 9:00 AM on assignment date
            # For DM reports, due by 6:00 PM on assignment date
            pass
        
        return cleaned_data

class ScheduleGenerationForm(forms.Form):
    start_date = forms.DateField(
        widget=DateInput(attrs={'class': 'form-control'}),
        initial=date.today
    )
    end_date = forms.DateField(
        widget=DateInput(attrs={'class': 'form-control'}),
        initial=lambda: date.today() + timedelta(days=150)
    )
    overwrite_existing = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text="Overwrite existing assignments in this date range"
    )
    
    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        if start_date and end_date:
            if end_date < start_date:
                raise ValidationError("End date must be after start date")
            
            # Limit to 180 days max
            if (end_date - start_date).days > 180:
                raise ValidationError("Cannot generate schedule for more than 180 days at once")
        
        return cleaned_data

class AnalystFilterForm(forms.Form):
    analyst = forms.ModelChoiceField(
        queryset=Analyst.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    start_date = forms.DateField(
        required=False,
        widget=DateInput(attrs={'class': 'form-control'})
    )
    end_date = forms.DateField(
        required=False,
        widget=DateInput(attrs={'class': 'form-control'})
    )
    monitoring_type = forms.ChoiceField(
        choices=[('', 'All')] + list(MonitoringType.MONITORING_TYPES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

class BulkAssignmentForm(forms.Form):
    """Form for bulk assignment operations"""
    analysts = forms.ModelMultipleChoiceField(
        queryset=Analyst.objects.filter(is_active=True),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        required=True
    )
    start_date = forms.DateField(widget=DateInput(attrs={'class': 'form-control'}))
    end_date = forms.DateField(widget=DateInput(attrs={'class': 'form-control'}))
    monitoring_type = forms.ModelChoiceField(
        queryset=MonitoringType.objects.all(),
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    action = forms.ChoiceField(
        choices=[
            ('ASSIGN', 'Assign to these dates'),
            ('REMOVE', 'Remove from these dates'),
            ('REPLACE', 'Replace existing assignments')
        ],
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        if start_date and end_date and end_date < start_date:
            raise ValidationError("End date must be after start date")
        
        return cleaned_data
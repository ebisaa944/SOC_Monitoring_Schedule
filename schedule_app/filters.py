# schedule_app/filters.py
import django_filters
from .models import (
    MonitoringAssignment,
    ShiftSwapRequest,
    LeaveRequest,
    Analyst,
    ReportSubmission,
)
from django_filters import DateFilter, ChoiceFilter
from .models import MonitoringAssignment, ShiftSwapRequest, LeaveRequest, Analyst

class MonitoringAssignmentFilter(django_filters.FilterSet):
    date = DateFilter(field_name='date', lookup_expr='exact')
    date_range = DateFilter(field_name='date', lookup_expr='range')
    start_date = DateFilter(field_name='date', lookup_expr='gte')
    end_date = DateFilter(field_name='date', lookup_expr='lte')
    analyst = django_filters.ModelChoiceFilter(queryset=Analyst.objects.all())
    monitoring_type = django_filters.CharFilter(field_name='monitoring_type__code')
    status = django_filters.CharFilter(field_name='status')
    is_monday_assignment = django_filters.BooleanFilter(field_name='is_monday_assignment')
    is_extended_window = django_filters.BooleanFilter(field_name='is_extended_window')
    
    class Meta:
        model = MonitoringAssignment
        fields = ['date', 'analyst', 'monitoring_type', 'status']
    
    @property
    def qs(self):
        parent = super().qs
        user = getattr(self.request, 'user', None)
        
        # If user is an analyst, only show their assignments
        if user and hasattr(user, 'analyst'):
            return parent.filter(analyst=user.analyst)
        return parent

class ShiftSwapRequestFilter(django_filters.FilterSet):
    status = ChoiceFilter(choices=ShiftSwapRequest.STATUS_CHOICES)
    requested_date = DateFilter(field_name='original_assignment__date')
    requested_after = DateFilter(field_name='requested_at', lookup_expr='gte')
    requested_before = DateFilter(field_name='requested_at', lookup_expr='lte')
    
    class Meta:
        model = ShiftSwapRequest
        fields = ['status', 'requested_by', 'requested_analyst']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.filters['requested_by'].queryset = Analyst.objects.all()
        self.filters['requested_analyst'].queryset = Analyst.objects.all()

class LeaveRequestFilter(django_filters.FilterSet):
    start_date = DateFilter(field_name='start_date', lookup_expr='gte')
    end_date = DateFilter(field_name='end_date', lookup_expr='lte')
    status = ChoiceFilter(choices=LeaveRequest.STATUS_CHOICES)
    leave_type = ChoiceFilter(choices=LeaveRequest.LEAVE_TYPES)
    
    class Meta:
        model = LeaveRequest
        fields = ['analyst', 'status', 'leave_type', 'start_date', 'end_date']

class AnalystScheduleFilter(django_filters.FilterSet):
    """Filter for analyst's schedule view"""
    month = django_filters.NumberFilter(method='filter_by_month')
    year = django_filters.NumberFilter(method='filter_by_year')
    upcoming = django_filters.BooleanFilter(method='filter_upcoming')
    
    class Meta:
        model = MonitoringAssignment
        fields = ['month', 'year', 'upcoming']
    
    def filter_by_month(self, queryset, name, value):
        return queryset.filter(date__month=value)
    
    def filter_by_year(self, queryset, name, value):
        return queryset.filter(date__year=value)
    
    def filter_upcoming(self, queryset, name, value):
        if value:
            from datetime import date
            return queryset.filter(date__gte=date.today())
        return queryset

class ReportFilter(django_filters.FilterSet):
    """Filter for report submissions"""
    submitted_after = DateFilter(field_name='submitted_at', lookup_expr='gte')
    submitted_before = DateFilter(field_name='submitted_at', lookup_expr='lte')
    completeness_min = django_filters.NumberFilter(
        field_name='completeness_score', lookup_expr='gte'
    )
    completeness_max = django_filters.NumberFilter(
        field_name='completeness_score', lookup_expr='lte'
    )

    class Meta:
        model = ReportSubmission   # ✅ MUST be the class
        fields = ['is_approved', 'submitted_by']
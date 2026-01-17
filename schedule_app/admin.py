# schedule_app/admin.py
from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Analyst, MonitoringType, SchedulePattern,
    MonitoringAssignment, ShiftSwapRequest, LeaveRequest,
    ReportSubmission, Notification, ScheduleGenerator
)

@admin.register(Analyst)
class AnalystAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'phone', 'pattern_position', 'is_active']
    list_filter = ['is_active', 'pattern_position']
    search_fields = ['name', 'email']

@admin.register(MonitoringType)
class MonitoringTypeAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'get_time_window_display']
    
    def get_time_window_display(self, obj):
        return f"{obj.default_start_hour:02d}:{obj.default_start_minute:02d} to {obj.default_end_hour:02d}:{obj.default_end_minute:02d}"
    get_time_window_display.short_description = 'Time Window'

@admin.register(SchedulePattern)
class SchedulePatternAdmin(admin.ModelAdmin):
    list_display = ['name', 'reference_start_date', 'is_active']
    readonly_fields = ['em_pattern_preview', 'dm_pattern_preview']
    
    def em_pattern_preview(self, obj):
        return format_html('<pre>{}</pre>', str(obj.em_pattern[:20]))
    em_pattern_preview.short_description = 'EM Pattern (first 20)'
    
    def dm_pattern_preview(self, obj):
        return format_html('<pre>{}</pre>', str(obj.dm_pattern[:20]))
    dm_pattern_preview.short_description = 'DM Pattern (first 20)'

@admin.register(MonitoringAssignment)
class MonitoringAssignmentAdmin(admin.ModelAdmin):
    list_display = ['date', 'monitoring_type', 'analyst', 'status', 'duration_hours', 'is_extended_window']
    list_filter = ['status', 'monitoring_type', 'analyst', 'date', 'is_monday_assignment']
    search_fields = ['analyst__name', 'notes']
    date_hierarchy = 'date'
    
    fieldsets = (
        ('Assignment Details', {
            'fields': ('date', 'monitoring_type', 'analyst', 'status')
        }),
        ('Time Window', {
            'fields': ('window_start', 'window_end', 'duration_hours')
        }),
        ('Flags', {
            'fields': ('is_monday_assignment', 'is_extended_window')
        }),
        ('Report Tracking', {
            'fields': ('report_submitted', 'report_submitted_at', 'report_verified')
        }),
        ('Notes', {
            'fields': ('notes', 'completion_notes')
        }),
    )
    
    readonly_fields = ['duration_hours']

@admin.register(ShiftSwapRequest)
class ShiftSwapRequestAdmin(admin.ModelAdmin):
    list_display = ['original_assignment', 'requested_analyst', 'status', 'requested_by', 'requested_at']
    list_filter = ['status', 'requested_at']
    search_fields = ['original_assignment__analyst__name', 'requested_analyst__name']
    
    actions = ['approve_selected_swaps', 'reject_selected_swaps']
    
    def approve_selected_swaps(self, request, queryset):
        for swap in queryset.filter(status='PENDING'):
            try:
                swap.approve_swap(request.user.analyst)
                self.message_user(request, f"Approved swap: {swap}")
            except Exception as e:
                self.message_user(request, f"Error approving {swap}: {str(e)}", level='error')
    
    def reject_selected_swaps(self, request, queryset):
        queryset.update(status='REJECTED', responded_at=timezone.now())
        self.message_user(request, f"Rejected {queryset.count()} swap requests")

@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ['analyst', 'start_date', 'end_date', 'leave_type', 'status', 'covered_by']
    list_filter = ['status', 'leave_type', 'start_date']
    search_fields = ['analyst__name', 'reason']
    
    fieldsets = (
        ('Leave Details', {
            'fields': ('analyst', 'start_date', 'end_date', 'leave_type', 'reason')
        }),
        ('Coverage', {
            'fields': ('covered_by', 'coverage_notes', 'auto_adjust_pattern')
        }),
        ('Status', {
            'fields': ('status', 'approved_by', 'affected_assignments')
        }),
    )
    
    filter_horizontal = ['affected_assignments']
    
    actions = ['approve_selected_leaves']
    
    def approve_selected_leaves(self, request, queryset):
        for leave in queryset.filter(status='PENDING'):
            try:
                affected = leave.approve_leave(request.user.analyst)
                self.message_user(request, f"Approved leave for {leave.analyst}, affected {affected} assignments")
            except Exception as e:
                self.message_user(request, f"Error approving {leave}: {str(e)}", level='error')

@admin.register(ReportSubmission)
class ReportSubmissionAdmin(admin.ModelAdmin):
    list_display = ['assignment', 'submitted_by', 'submitted_at', 'completeness_score', 'is_approved']
    list_filter = ['is_approved', 'submitted_at']
    search_fields = ['assignment__analyst__name', 'summary']

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['recipient', 'notification_type', 'title', 'is_read', 'created_at']
    list_filter = ['notification_type', 'is_read', 'created_at']
    search_fields = ['recipient__name', 'title', 'message']

@admin.register(ScheduleGenerator)
class ScheduleGeneratorAdmin(admin.ModelAdmin):
    list_display = ['name', 'pattern', 'auto_generate', 'last_generated']
    actions = ['generate_next_5_months']
    
    def generate_next_5_months(self, request, queryset):
        for generator in queryset:
            try:
                count = generator.generate_next_5_months()
                self.message_user(request, f"Generated {count} assignments for {generator.name}")
            except Exception as e:
                self.message_user(request, f"Error generating schedule: {str(e)}", level='error')
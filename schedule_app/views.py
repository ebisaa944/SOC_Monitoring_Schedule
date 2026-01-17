# schedule_app/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView, FormView
from django.urls import reverse_lazy
from django.db.models import Q, Count, Sum, Prefetch
from django.utils import timezone
from django.core.paginator import Paginator
from datetime import date, datetime, timedelta
import calendar
from dateutil.relativedelta import relativedelta

from .models import (
    Analyst, MonitoringAssignment, ShiftSwapRequest, LeaveRequest,
    ReportSubmission, Notification, MonitoringType
)
from .forms import (
    MonitoringAssignmentForm, ShiftSwapRequestForm, LeaveRequestForm,
    ReportSubmissionForm, ScheduleGenerationForm, AnalystFilterForm,
    BulkAssignmentForm
)
from .filters import MonitoringAssignmentFilter, ShiftSwapRequestFilter, LeaveRequestFilter

# Context processor for notifications (add this to context_processors.py too)
def notifications_context(request):
    """Add notifications and analyst info to all templates"""
    context = {}
    if request.user.is_authenticated:
        # Get analyst by user relationship (not by username field)
        try:
            analyst = Analyst.objects.get(user=request.user)
            context['analyst'] = analyst
            
            # Get unread notifications count
            unread_count = Notification.objects.filter(
                recipient=analyst,
                is_read=False
            ).count()
            context['unread_notification_count'] = unread_count
            
            # Get pending swaps count for current analyst
            pending_swaps = ShiftSwapRequest.objects.filter(
                requested_analyst=analyst,
                status='PENDING'
            ).count()
            context['pending_swap_count'] = pending_swaps
            
        except Analyst.DoesNotExist:
            context['analyst'] = None
            context['unread_notification_count'] = 0
            context['pending_swap_count'] = 0
    else:
        context['analyst'] = None
        context['unread_notification_count'] = 0
        context['pending_swap_count'] = 0
    
    return context


# Authentication Views
def custom_login(request):
    """Custom login view"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            messages.success(request, 'Successfully logged in!')
            
            # Create login notification - Check if user corresponds to an analyst
            try:
                # Try to find analyst by user relationship
                analyst = Analyst.objects.get(user=user)
                Notification.objects.create(
                    recipient=analyst,
                    notification_type='SYSTEM',
                    title='Login Successful',
                    message=f'You logged in at {timezone.now().strftime("%Y-%m-%d %H:%M")}',
                    is_important=False
                )
            except Analyst.DoesNotExist:
                pass  # User is not an analyst (e.g., admin)
            
            next_url = request.GET.get('next', 'dashboard')
            return redirect(next_url)
        else:
            messages.error(request, 'Invalid username or password')
    
    return render(request, 'schedule_app/login.html')

@login_required
def custom_logout(request):
    """Custom logout view"""
    logout(request)
    messages.success(request, 'Successfully logged out!')
    return render(request, 'schedule_app/logout.html')

# Dashboard View
class DashboardView(LoginRequiredMixin, TemplateView):
    """Main dashboard view"""
    template_name = 'schedule_app/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        today = date.today()
        
        # Get analyst object by user relationship (FIXED: using user, not username field)
        analyst = None
        try:
            analyst = Analyst.objects.get(user=user)
        except Analyst.DoesNotExist:
            pass
        
        # Today's assignments
        today_assignments = MonitoringAssignment.objects.filter(
            date=today
        ).select_related('analyst', 'monitoring_type')
        
        # Upcoming assignments (next 7 days)
        upcoming_assignments = MonitoringAssignment.objects.filter(
            date__range=[today, today + timedelta(days=7)]
        ).select_related('analyst', 'monitoring_type').order_by('date', 'monitoring_type__code')
        
        # Pending swap requests for current analyst
        pending_swaps = ShiftSwapRequest.objects.filter(
            status='PENDING'
        )
        if analyst:
            pending_swaps = pending_swaps.filter(requested_analyst=analyst)
        
        # Unread notifications for current analyst
        unread_notifications = Notification.objects.filter(
            is_read=False
        )
        if analyst:
            unread_notifications = unread_notifications.filter(recipient=analyst)
        
        # Leave requests pending approval (for admins)
        pending_leaves = LeaveRequest.objects.filter(status='PENDING')
        
        # Monthly stats
        month_start = today.replace(day=1)
        month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        
        monthly_assignments = MonitoringAssignment.objects.filter(
            date__range=[month_start, month_end]
        )
        
        # Analyst-specific stats
        analyst_em_count = 0
        analyst_dm_count = 0
        analyst_monday_count = 0
        
        if analyst:
            analyst_assignments = MonitoringAssignment.objects.filter(
                analyst=analyst,
                date__range=[month_start, month_end]
            )
            analyst_em_count = analyst_assignments.filter(
                monitoring_type__code='EM'
            ).count()
            analyst_dm_count = analyst_assignments.filter(
                monitoring_type__code='DM'
            ).count()
            analyst_monday_count = analyst_assignments.filter(
                is_monday_assignment=True
            ).count()
        
        # Active analysts
        active_analysts = Analyst.objects.filter(is_active=True)
        
        # Get other assignments for today (for same-day display)
        other_today_assignments = MonitoringAssignment.objects.filter(
            date=today
        ).exclude(analyst=analyst) if analyst else MonitoringAssignment.objects.filter(date=today)
        
        context.update({
            'today': today,
            'analyst': analyst,
            'today_assignments': today_assignments,
            'upcoming_assignments': upcoming_assignments,
            'pending_swaps': pending_swaps,
            'unread_notifications': unread_notifications,
            'pending_leaves': pending_leaves,
            'monthly_assignments': monthly_assignments,
            'analysts': active_analysts,
            'analyst_em_count': analyst_em_count,
            'analyst_dm_count': analyst_dm_count,
            'analyst_monday_count': analyst_monday_count,
            'active_analysts_count': active_analysts.count(),
            'other_today_assignments': other_today_assignments,
            'monthly_reports_count': ReportSubmission.objects.filter(
                submitted_at__range=[month_start, month_end]
            ).count(),
        })
        
        return context

# Schedule Views
class ScheduleListView(LoginRequiredMixin, ListView):
    """View all schedules with filtering"""
    model = MonitoringAssignment
    template_name = 'schedule_app/schedule_list.html'
    context_object_name = 'assignments'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = MonitoringAssignment.objects.all().select_related(
            'analyst', 'monitoring_type'
        ).order_by('date', 'monitoring_type__code')
        
        # Apply filters
        self.filterset = MonitoringAssignmentFilter(self.request.GET, queryset=queryset)
        
        # If user is an analyst, show only their assignments by default
        try:
            analyst = Analyst.objects.get(user=self.request.user)
            if 'analyst' not in self.request.GET and 'date' not in self.request.GET:
                queryset = queryset.filter(analyst=analyst)
        except Analyst.DoesNotExist:
            pass
        
        return self.filterset.qs
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form'] = AnalystFilterForm(self.request.GET or None)
        context['filterset'] = self.filterset
        context['analysts'] = Analyst.objects.filter(is_active=True)
        context['monitoring_types'] = MonitoringType.objects.all()
        context['today'] = date.today()
        
        # Add stats
        context['total_count'] = self.get_queryset().count()
        context['em_count'] = self.get_queryset().filter(monitoring_type__code='EM').count()
        context['dm_count'] = self.get_queryset().filter(monitoring_type__code='DM').count()
        
        return context

class ScheduleCalendarView(LoginRequiredMixin, TemplateView):
    """Calendar view of schedule"""
    template_name = 'schedule_app/schedule_calendar.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get assignments for the next 60 days
        start_date = date.today()
        end_date = start_date + timedelta(days=60)
        
        assignments = MonitoringAssignment.objects.filter(
            date__range=[start_date, end_date]
        ).select_related('analyst', 'monitoring_type')
        
        # Get analysts for filter
        context['analysts'] = Analyst.objects.filter(is_active=True)
        context['assignments'] = assignments
        context['today'] = date.today()
        
        return context

class ScheduleWeeklyView(LoginRequiredMixin, TemplateView):
    """Weekly schedule view"""
    template_name = 'schedule_app/schedule_weekly.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get week from request or use current week
        week_param = self.request.GET.get('week')
        if week_param:
            try:
                week_date = datetime.strptime(week_param, '%Y-%m-%d').date()
            except ValueError:
                week_date = date.today()
        else:
            week_date = date.today()
        
        # Calculate week start (Monday)
        week_start = week_date - timedelta(days=week_date.weekday())
        week_end = week_start + timedelta(days=6)
        
        # Get assignments for the week
        assignments = MonitoringAssignment.objects.filter(
            date__range=[week_start, week_end]
        ).select_related('analyst', 'monitoring_type')
        
        # Group assignments by date
        assignments_by_date = {}
        for assignment in assignments:
            date_str = assignment.date.isoformat()
            if date_str not in assignments_by_date:
                assignments_by_date[date_str] = []
            assignments_by_date[date_str].append(assignment)
        
        # Generate week dates
        week_dates = [week_start + timedelta(days=i) for i in range(7)]
        
        # Calculate statistics
        week_em_count = assignments.filter(monitoring_type__code='EM').count()
        week_dm_count = assignments.filter(monitoring_type__code='DM').count()
        week_extended_count = assignments.filter(is_extended_window=True).count()
        week_monday_count = assignments.filter(is_monday_assignment=True).count()
        
        # Analyst workload for the week
        analyst_workload = {}
        for assignment in assignments:
            analyst_name = assignment.analyst.display_name
            analyst_workload[analyst_name] = analyst_workload.get(analyst_name, 0) + 1
        
        # Navigation
        prev_week = (week_start - timedelta(days=7)).isoformat()
        next_week = (week_start + timedelta(days=7)).isoformat()
        today_week = date.today() - timedelta(days=date.today().weekday())
        
        context.update({
            'week_start': week_start,
            'week_end': week_end,
            'week_dates': week_dates,
            'assignments_by_date': assignments_by_date,
            'week_em_count': week_em_count,
            'week_dm_count': week_dm_count,
            'week_extended_count': week_extended_count,
            'week_monday_count': week_monday_count,
            'analyst_workload': analyst_workload,
            'max_workload': max(analyst_workload.values()) if analyst_workload else 1,
            'prev_week': prev_week,
            'next_week': next_week,
            'today_week': today_week.isoformat(),
            'week_number': week_start.isocalendar()[1],
            'today': date.today(),
        })
        
        return context

class ScheduleMonthlyView(LoginRequiredMixin, TemplateView):
    """Monthly schedule view"""
    template_name = 'schedule_app/schedule_monthly.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get month from request or use current month
        month_param = self.request.GET.get('month')
        if month_param:
            try:
                current_month = datetime.strptime(month_param + '-01', '%Y-%m-%d').date()
            except ValueError:
                current_month = date.today().replace(day=1)
        else:
            current_month = date.today().replace(day=1)
        
        # Calculate month start and end
        month_end = (current_month + relativedelta(months=1)) - timedelta(days=1)
        
        # Get assignments for the month
        assignments = MonitoringAssignment.objects.filter(
            date__range=[current_month, month_end]
        ).select_related('analyst', 'monitoring_type')
        
        # Group assignments by date
        assignments_by_date = {}
        for assignment in assignments:
            date_str = assignment.date.isoformat()
            if date_str not in assignments_by_date:
                assignments_by_date[date_str] = []
            assignments_by_date[date_str].append(assignment)
        
        # Generate calendar grid
        cal = calendar.Calendar()
        month_calendar = cal.monthdatescalendar(current_month.year, current_month.month)
        
        # Calculate statistics
        month_em_count = assignments.filter(monitoring_type__code='EM').count()
        month_dm_count = assignments.filter(monitoring_type__code='DM').count()
        month_monday_count = assignments.filter(is_monday_assignment=True).count()
        
        # Analyst monthly count
        analyst_monthly_count = {}
        for assignment in assignments:
            analyst_name = assignment.analyst.display_name
            analyst_monthly_count[analyst_name] = analyst_monthly_count.get(analyst_name, 0) + 1
        
        # Get upcoming Monday duties
        upcoming_monday_duties = []
        today = date.today()
        for i in range(4):  # Next 4 Mondays
            monday = today + timedelta(days=(7 - today.weekday()) + (i * 7))
            monday_assignments = MonitoringAssignment.objects.filter(date=monday)
            
            em_assignment = monday_assignments.filter(monitoring_type__code='EM').first()
            dm_assignment = monday_assignments.filter(monitoring_type__code='DM').first()
            
            if em_assignment and dm_assignment:
                duty = {
                    'date': monday,
                    'days_until': (monday - today).days,
                    'em_analyst': em_assignment.analyst.display_name,
                    'dm_analyst': dm_assignment.analyst.display_name,
                    'em_window': f"{em_assignment.window_start.strftime('%H:%M')} to {em_assignment.window_end.strftime('%H:%M')}",
                    'dm_window': f"{dm_assignment.window_start.strftime('%H:%M')} to {dm_assignment.window_end.strftime('%H:%M')}",
                }
                upcoming_monday_duties.append(duty)
        
        # Navigation
        prev_month = (current_month - relativedelta(months=1)).strftime('%Y-%m')
        next_month = (current_month + relativedelta(months=1)).strftime('%Y-%m')
        today_month = date.today().strftime('%Y-%m')
        
        context.update({
            'current_month': current_month,
            'month_calendar': month_calendar,
            'assignments_by_date': assignments_by_date,
            'month_em_count': month_em_count,
            'month_dm_count': month_dm_count,
            'month_monday_count': month_monday_count,
            'analyst_monthly_count': analyst_monthly_count,
            'max_monthly_count': max(analyst_monthly_count.values()) if analyst_monthly_count else 1,
            'total_assignments': month_em_count + month_dm_count,
            'analysts_count': Analyst.objects.filter(is_active=True).count(),
            'upcoming_monday_duties': upcoming_monday_duties,
            'prev_month': prev_month,
            'next_month': next_month,
            'today_month': today_month,
            'days_in_month': month_end.day,
            'month_weeks': len(month_calendar),
            'today': date.today(),
        })
        
        return context

# Assignment Views
class AssignmentDetailView(LoginRequiredMixin, DetailView):
    """View assignment details"""
    model = MonitoringAssignment
    template_name = 'schedule_app/assignment_detail.html'
    context_object_name = 'assignment'
    
    def get_queryset(self):
        return MonitoringAssignment.objects.select_related(
            'analyst', 'monitoring_type'
        ).prefetch_related('swap_requests_outgoing')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        assignment = self.object
        user = self.request.user
        
        # Get analyst by user relationship (FIXED)
        try:
            analyst = Analyst.objects.get(user=user)
        except Analyst.DoesNotExist:
            analyst = None
        
        # Check if user can request swap
        can_request_swap = (
            analyst and
            assignment.analyst == analyst and
            assignment.date >= date.today() and
            assignment.status in ['SCHEDULED', 'CONFIRMED']
        )
        
        # Get related swap requests
        swap_requests = ShiftSwapRequest.objects.filter(
            original_assignment=assignment
        ).select_related('requested_analyst', 'requested_by').order_by('-requested_at')
        
        # Get same day assignments
        same_day_assignments = MonitoringAssignment.objects.filter(
            date=assignment.date
        ).exclude(id=assignment.id).select_related('analyst', 'monitoring_type')
        
        context.update({
            'can_request_swap': can_request_swap,
            'swap_requests': swap_requests,
            'same_day_assignments': same_day_assignments,
            'today': date.today(),
        })
        
        return context

class CreateAssignmentView(PermissionRequiredMixin, CreateView):
    """Create new assignment (admin only)"""
    model = MonitoringAssignment
    form_class = MonitoringAssignmentForm
    template_name = 'schedule_app/assignment_form.html'
    permission_required = 'schedule_app.add_monitoringassignment'
    
    def get_success_url(self):
        save_and_add = self.request.POST.get('save_and_add_another')
        if save_and_add:
            return reverse_lazy('create_assignment')
        return reverse_lazy('schedule_list')
    
    def form_valid(self, form):
        # Calculate time window based on date and monitoring type
        assignment = form.save(commit=False)
        
        # Get monitoring type
        monitoring_type = form.cleaned_data['monitoring_type']
        target_date = form.cleaned_data['date']
        
        # Calculate time window
        start_time, end_time = monitoring_type.get_time_window_for_date(target_date)
        assignment.window_start = start_time
        assignment.window_end = end_time
        
        # Save the assignment
        response = super().form_valid(form)
        
        # Create notification
        Notification.objects.create(
            recipient=assignment.analyst,
            notification_type='SCHEDULE_CHANGE',
            title=f'New Assignment: {assignment.monitoring_type} on {assignment.date}',
            message=f'You have been assigned to {assignment.monitoring_type} on {assignment.date}',
            related_object_id=str(assignment.id),
            related_object_type='MonitoringAssignment',
            is_important=True
        )
        
        messages.success(self.request, f'Assignment created for {assignment.analyst.display_name} on {assignment.date}')
        return response
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['today'] = date.today()
        return context

class UpdateAssignmentView(PermissionRequiredMixin, UpdateView):
    """Update assignment (admin only)"""
    model = MonitoringAssignment
    form_class = MonitoringAssignmentForm
    template_name = 'schedule_app/assignment_form.html'
    permission_required = 'schedule_app.change_monitoringassignment'
    success_url = reverse_lazy('schedule_list')
    
    def form_valid(self, form):
        # Calculate time window based on date and monitoring type
        assignment = form.save(commit=False)
        
        # Get monitoring type
        monitoring_type = form.cleaned_data['monitoring_type']
        target_date = form.cleaned_data['date']
        
        # Calculate time window
        start_time, end_time = monitoring_type.get_time_window_for_date(target_date)
        assignment.window_start = start_time
        assignment.window_end = end_time
        
        response = super().form_valid(form)
        
        # Create notification
        Notification.objects.create(
            recipient=assignment.analyst,
            notification_type='SCHEDULE_CHANGE',
            title=f'Assignment Updated: {assignment.monitoring_type} on {assignment.date}',
            message=f'Your assignment to {assignment.monitoring_type} on {assignment.date} has been updated',
            related_object_id=str(assignment.id),
            related_object_type='MonitoringAssignment'
        )
        
        messages.success(self.request, f'Assignment updated for {assignment.analyst.display_name} on {assignment.date}')
        return response
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['today'] = date.today()
        return context

class DeleteAssignmentView(PermissionRequiredMixin, DeleteView):
    """Delete assignment (admin only)"""
    model = MonitoringAssignment
    template_name = 'schedule_app/assignment_confirm_delete.html'
    permission_required = 'schedule_app.delete_monitoringassignment'
    success_url = reverse_lazy('schedule_list')
    
    def delete(self, request, *args, **kwargs):
        assignment = self.get_object()
        
        # Create notification before deletion
        Notification.objects.create(
            recipient=assignment.analyst,
            notification_type='SCHEDULE_CHANGE',
            title=f'Assignment Cancelled: {assignment.monitoring_type} on {assignment.date}',
            message=f'Your assignment to {assignment.monitoring_type} on {assignment.date} has been cancelled',
            is_important=True
        )
        
        messages.success(request, 'Assignment deleted successfully')
        return super().delete(request, *args, **kwargs)

# Swap Request Views
class SwapRequestCreateView(LoginRequiredMixin, CreateView):
    """Request a shift swap"""
    model = ShiftSwapRequest
    form_class = ShiftSwapRequestForm
    template_name = 'schedule_app/swap_request_form.html'
    
    def dispatch(self, request, *args, **kwargs):
        # Get the assignment
        self.assignment = get_object_or_404(MonitoringAssignment, pk=kwargs['assignment_id'])
        
        # Check permissions - FIXED: using user relationship
        try:
            analyst = Analyst.objects.get(user=request.user)
            if analyst != self.assignment.analyst:
                messages.error(request, 'You can only request swaps for your own assignments')
                return redirect('assignment_detail', pk=self.assignment.pk)
        except Analyst.DoesNotExist:
            messages.error(request, 'Analyst profile not found')
            return redirect('dashboard')
        
        # Check if assignment is in the past
        if self.assignment.date < date.today():
            messages.error(request, 'Cannot swap past assignments')
            return redirect('assignment_detail', pk=self.assignment.pk)
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['assignment'] = self.assignment
        
        try:
            analyst = Analyst.objects.get(user=self.request.user)
            kwargs['requesting_analyst'] = analyst
        except Analyst.DoesNotExist:
            pass
        
        return kwargs
    
    def form_valid(self, form):
        try:
            analyst = Analyst.objects.get(user=self.request.user)
            form.instance.original_assignment = self.assignment
            form.instance.requested_by = analyst
            form.instance.status = 'PENDING'
            
            response = super().form_valid(form)
            
            # Create notification for requested analyst
            Notification.objects.create(
                recipient=form.instance.requested_analyst,
                notification_type='SWAP_REQUEST',
                title=f'Shift Swap Request from {analyst.display_name}',
                message=f'{analyst.display_name} has requested to swap their {self.assignment.monitoring_type} shift on {self.assignment.date}',
                related_object_id=str(form.instance.id),
                related_object_type='ShiftSwapRequest',
                is_important=True
            )
            
            messages.success(self.request, 'Swap request sent successfully')
            return response
        except Analyst.DoesNotExist:
            messages.error(self.request, 'Analyst profile not found')
            return redirect('dashboard')
    
    def get_success_url(self):
        return reverse_lazy('assignment_detail', kwargs={'pk': self.assignment.pk})
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['assignment'] = self.assignment
        context['today'] = date.today()
        return context

class SwapRequestListView(LoginRequiredMixin, ListView):
    """View swap requests"""
    model = ShiftSwapRequest
    template_name = 'schedule_app/swap_request_list.html'
    context_object_name = 'swap_requests'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = ShiftSwapRequest.objects.all().select_related(
            'original_assignment', 'original_assignment__analyst',
            'original_assignment__monitoring_type', 'requested_analyst',
            'requested_by'
        ).order_by('-requested_at')
        
        # Apply filters
        self.filterset = ShiftSwapRequestFilter(self.request.GET, queryset=queryset)
        
        # If user is an analyst, show only their related swap requests - FIXED
        try:
            analyst = Analyst.objects.get(user=self.request.user)
            queryset = queryset.filter(
                Q(requested_by=analyst) |
                Q(requested_analyst=analyst) |
                Q(original_assignment__analyst=analyst)
            ).distinct()
        except Analyst.DoesNotExist:
            pass
        
        return self.filterset.qs
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filterset'] = self.filterset
        
        # Count pending requests for current user
        try:
            analyst = Analyst.objects.get(user=self.request.user)
            context['pending_requests_to_me'] = ShiftSwapRequest.objects.filter(
                requested_analyst=analyst,
                status='PENDING'
            ).count()
        except Analyst.DoesNotExist:
            context['pending_requests_to_me'] = 0
        
        return context

class SwapRequestDetailView(LoginRequiredMixin, DetailView):
    """View swap request details"""
    model = ShiftSwapRequest
    template_name = 'schedule_app/swap_request_detail.html'
    context_object_name = 'swap_request'
    
    def get_queryset(self):
        return ShiftSwapRequest.objects.select_related(
            'original_assignment', 'original_assignment__analyst',
            'original_assignment__monitoring_type', 'requested_analyst',
            'requested_by', 'approved_by', 'reciprocal_assignment'
        )
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        swap_request = self.object
        
        # Get current analyst - FIXED
        try:
            analyst = Analyst.objects.get(user=self.request.user)
        except Analyst.DoesNotExist:
            analyst = None
        
        # Check if user can approve this swap
        context['can_approve'] = (
            analyst and
            swap_request.requested_analyst == analyst and
            swap_request.status == 'PENDING'
        )
        
        # Check if user can cancel this swap
        context['can_cancel'] = (
            analyst and
            swap_request.requested_by == analyst and
            swap_request.status == 'PENDING'
        )
        
        context['today'] = date.today()
        return context

@login_required
def approve_swap_request(request, pk):
    """Approve a swap request"""
    swap_request = get_object_or_404(ShiftSwapRequest, pk=pk)
    
    # Check permissions - FIXED
    try:
        analyst = Analyst.objects.get(user=request.user)
    except Analyst.DoesNotExist:
        messages.error(request, 'Analyst profile not found')
        return redirect('swap_request_list')
    
    if analyst != swap_request.requested_analyst:
        messages.error(request, 'You can only approve swap requests sent to you')
        return redirect('swap_request_detail', pk=pk)
    
    if swap_request.status != 'PENDING':
        messages.error(request, 'This swap request is no longer pending')
        return redirect('swap_request_detail', pk=pk)
    
    try:
        swap_request.approve_swap(analyst)
        
        # Create notifications
        Notification.objects.create(
            recipient=swap_request.requested_by,
            notification_type='SWAP_APPROVED',
            title='Swap Request Approved',
            message=f'{swap_request.requested_analyst.display_name} has approved your swap request for {swap_request.original_assignment.date}',
            related_object_id=str(swap_request.id),
            related_object_type='ShiftSwapRequest'
        )
        
        messages.success(request, 'Swap approved successfully')
    except Exception as e:
        messages.error(request, f'Error approving swap: {str(e)}')
    
    return redirect('swap_request_detail', pk=pk)

@login_required
def reject_swap_request(request, pk):
    """Reject a swap request"""
    swap_request = get_object_or_404(ShiftSwapRequest, pk=pk)
    
    # Check permissions - FIXED
    try:
        analyst = Analyst.objects.get(user=request.user)
    except Analyst.DoesNotExist:
        messages.error(request, 'Analyst profile not found')
        return redirect('swap_request_list')
    
    if analyst != swap_request.requested_analyst:
        messages.error(request, 'You can only reject swap requests sent to you')
        return redirect('swap_request_detail', pk=pk)
    
    if swap_request.status != 'PENDING':
        messages.error(request, 'This swap request is no longer pending')
        return redirect('swap_request_detail', pk=pk)
    
    swap_request.status = 'REJECTED'
    swap_request.responded_at = timezone.now()
    swap_request.save()
    
    # Create notification
    Notification.objects.create(
        recipient=swap_request.requested_by,
        notification_type='SWAP_REQUEST',
        title='Swap Request Rejected',
        message=f'{swap_request.requested_analyst.display_name} has rejected your swap request for {swap_request.original_assignment.date}',
        related_object_id=str(swap_request.id),
        related_object_type='ShiftSwapRequest'
    )
    
    messages.success(request, 'Swap rejected successfully')
    return redirect('swap_request_detail', pk=pk)

# Leave Request Views
class LeaveRequestCreateView(LoginRequiredMixin, CreateView):
    """Create leave request"""
    model = LeaveRequest
    form_class = LeaveRequestForm
    template_name = 'schedule_app/leave_request_form.html'
    success_url = reverse_lazy('leave_request_list')
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        try:
            analyst = Analyst.objects.get(user=self.request.user)
            kwargs['analyst'] = analyst
        except Analyst.DoesNotExist:
            pass
        return kwargs
    
    def form_valid(self, form):
        try:
            analyst = Analyst.objects.get(user=self.request.user)
            form.instance.analyst = analyst
        except Analyst.DoesNotExist:
            messages.error(self.request, 'Analyst profile not found')
            return self.form_invalid(form)
        
        # Assess impact before saving
        leave_request = form.save(commit=False)
        leave_request.save()
        form.save_m2m()  # Save many-to-many relationships
        
        # Assess impact
        affected_count = leave_request.assess_impact()
        
        # Create notification for approvers
        approvers = Analyst.objects.filter(
            Q(user__is_superuser=True) |
            Q(user__is_staff=True)
        ).distinct()
        
        for approver in approvers:
            Notification.objects.create(
                recipient=approver,
                notification_type='LEAVE_APPROVED',
                title=f'New Leave Request from {analyst.display_name}',
                message=f'{analyst.display_name} has requested leave from {form.instance.start_date} to {form.instance.end_date}',
                related_object_id=str(form.instance.id),
                related_object_type='LeaveRequest',
                is_important=True
            )
        
        messages.success(self.request, f'Leave request submitted successfully. Affects {affected_count} assignments.')
        return super().form_valid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['today'] = date.today()
        return context

class LeaveRequestListView(LoginRequiredMixin, ListView):
    """View leave requests"""
    model = LeaveRequest
    template_name = 'schedule_app/leave_request_list.html'
    context_object_name = 'leave_requests'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = LeaveRequest.objects.all().select_related(
            'analyst', 'covered_by', 'approved_by'
        ).prefetch_related('affected_assignments').order_by('-requested_at')
        
        # Apply filters
        self.filterset = LeaveRequestFilter(self.request.GET, queryset=queryset)
        
        # If user is an analyst (not staff), show only their own requests - FIXED
        try:
            analyst = Analyst.objects.get(user=self.request.user)
            if not self.request.user.is_staff:
                queryset = queryset.filter(analyst=analyst)
        except Analyst.DoesNotExist:
            pass
        
        return self.filterset.qs
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filterset'] = self.filterset
        context['today'] = date.today()
        
        # Get analyst if exists - FIXED
        try:
            analyst = Analyst.objects.get(user=self.request.user)
            context['analyst'] = analyst
        except Analyst.DoesNotExist:
            context['analyst'] = None
        
        return context

class LeaveRequestDetailView(LoginRequiredMixin, DetailView):
    """View leave request details"""
    model = LeaveRequest
    template_name = 'schedule_app/leave_request_detail.html'
    context_object_name = 'leave_request'
    
    def get_queryset(self):
        return LeaveRequest.objects.select_related(
            'analyst', 'covered_by', 'approved_by'
        ).prefetch_related('affected_assignments')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get current analyst - FIXED
        try:
            analyst = Analyst.objects.get(user=self.request.user)
            context['current_analyst'] = analyst
        except Analyst.DoesNotExist:
            context['current_analyst'] = None
        
        # Check if user can approve this leave
        context['can_approve'] = (
            self.request.user.is_staff and
            self.object.status == 'PENDING'
        )
        
        context['today'] = date.today()
        return context

@login_required
@permission_required('schedule_app.can_manage_leave', raise_exception=True)
def approve_leave_request(request, pk):
    """Approve leave request"""
    leave_request = get_object_or_404(LeaveRequest, pk=pk)
    
    if leave_request.status != 'PENDING':
        messages.error(request, 'This leave request is no longer pending')
        return redirect('leave_request_detail', pk=pk)
    
    try:
        approver = Analyst.objects.get(user=request.user)
    except Analyst.DoesNotExist:
        messages.error(request, 'Analyst profile not found')
        return redirect('leave_request_detail', pk=pk)
    
    # Get coverage analyst from request
    coverage_analyst_id = request.POST.get('coverage_analyst')
    coverage_analyst = None
    if coverage_analyst_id:
        try:
            coverage_analyst = Analyst.objects.get(id=coverage_analyst_id)
        except Analyst.DoesNotExist:
            pass
    
    try:
        affected_count = leave_request.approve_leave(approver, coverage_analyst)
        messages.success(request, f'Leave approved successfully. {affected_count} assignments affected.')
    except Exception as e:
        messages.error(request, f'Error approving leave: {str(e)}')
    
    return redirect('leave_request_detail', pk=pk)

# Analyst Views
class AnalystListView(LoginRequiredMixin, ListView):
    """View all analysts"""
    model = Analyst
    template_name = 'schedule_app/analyst_list.html'
    context_object_name = 'analysts'
    
    def get_queryset(self):
        return Analyst.objects.filter(is_active=True).order_by('display_name')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Add assignment counts for each analyst
        analysts_with_counts = []
        for analyst in context['analysts']:
            em_count = MonitoringAssignment.objects.filter(
                analyst=analyst,
                monitoring_type__code='EM'
            ).count()
            dm_count = MonitoringAssignment.objects.filter(
                analyst=analyst,
                monitoring_type__code='DM'
            ).count()
            total_count = em_count + dm_count
            
            analysts_with_counts.append({
                'analyst': analyst,
                'em_count': em_count,
                'dm_count': dm_count,
                'total_count': total_count,
            })
        
        context['analysts_with_counts'] = analysts_with_counts
        return context

class AnalystDetailView(LoginRequiredMixin, DetailView):
    """View analyst details"""
    model = Analyst
    template_name = 'schedule_app/analyst_detail.html'
    context_object_name = 'analyst_detail'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        analyst = self.object
        
        # Get upcoming assignments
        upcoming_assignments = MonitoringAssignment.objects.filter(
            analyst=analyst,
            date__gte=date.today()
        ).select_related('monitoring_type').order_by('date')[:10]
        
        # Get past assignments (last month)
        month_ago = date.today() - timedelta(days=30)
        past_assignments = MonitoringAssignment.objects.filter(
            analyst=analyst,
            date__range=[month_ago, date.today()]
        ).select_related('monitoring_type').order_by('-date')[:10]
        
        # Get statistics
        total_assignments = MonitoringAssignment.objects.filter(analyst=analyst).count()
        em_assignments = MonitoringAssignment.objects.filter(
            analyst=analyst,
            monitoring_type__code='EM'
        ).count()
        dm_assignments = MonitoringAssignment.objects.filter(
            analyst=analyst,
            monitoring_type__code='DM'
        ).count()
        monday_duties = MonitoringAssignment.objects.filter(
            analyst=analyst,
            is_monday_assignment=True
        ).count()
        
        # Get leave requests
        leave_requests = LeaveRequest.objects.filter(analyst=analyst).order_by('-start_date')[:5]
        
        context.update({
            'upcoming_assignments': upcoming_assignments,
            'past_assignments': past_assignments,
            'total_assignments': total_assignments,
            'em_assignments': em_assignments,
            'dm_assignments': dm_assignments,
            'monday_duties': monday_duties,
            'leave_requests': leave_requests,
            'today': date.today(),
        })
        
        return context

@login_required
def my_schedule(request):
    """View current user's schedule"""
    try:
        analyst = Analyst.objects.get(user=request.user)
        return redirect('analyst_detail', pk=analyst.id)
    except Analyst.DoesNotExist:
        messages.error(request, 'Analyst profile not found')
        return redirect('dashboard')

# Report Views
@login_required
def report_submission_create(request):
    """Create report submission"""
    # This would be implemented similar to other create views
    # For now, redirect to dashboard
    messages.info(request, 'Report submission feature coming soon')
    return redirect('dashboard')

@login_required
def my_reports(request):
    """View current user's reports"""
    # This would be implemented
    messages.info(request, 'My reports feature coming soon')
    return redirect('dashboard')

# Schedule Generation Views
@login_required
@permission_required('schedule_app.can_generate_schedule', raise_exception=True)
def generate_schedule(request):
    """Generate schedule view"""
    if request.method == 'POST':
        form = ScheduleGenerationForm(request.POST)
        if form.is_valid():
            # This would call the schedule generator
            # For now, show success message
            messages.success(request, 'Schedule generation feature coming soon')
            return redirect('schedule_list')
    else:
        form = ScheduleGenerationForm()
    
    return render(request, 'schedule_app/generate_schedule.html', {'form': form})

@login_required
@permission_required('schedule_app.can_generate_schedule', raise_exception=True)
def bulk_operations(request):
    """Bulk operations view"""
    if request.method == 'POST':
        form = BulkAssignmentForm(request.POST)
        if form.is_valid():
            # This would process bulk operations
            # For now, show success message
            messages.success(request, 'Bulk operations feature coming soon')
            return redirect('schedule_list')
    else:
        form = BulkAssignmentForm()
    
    return render(request, 'schedule_app/bulk_operations.html', {'form': form})

# Notification Views
@login_required
def notifications_view(request):
    """View all notifications"""
    try:
        analyst = Analyst.objects.get(user=request.user)
        notifications = Notification.objects.filter(
            recipient=analyst
        ).order_by('-created_at')
        
        # Mark all as read when viewing
        unread_notifications = notifications.filter(is_read=False)
        unread_notifications.update(is_read=True)
        
        context = {
            'notifications': notifications,
            'analyst': analyst,
            'today': date.today(),
        }
        return render(request, 'schedule_app/notifications.html', context)
    except Analyst.DoesNotExist:
        messages.error(request, 'Analyst profile not found')
        return redirect('dashboard')

# About and Help Views
class AboutView(LoginRequiredMixin, TemplateView):
    """About page"""
    template_name = 'schedule_app/about.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['analysts'] = Analyst.objects.filter(is_active=True)
        return context

class HelpView(LoginRequiredMixin, TemplateView):
    """Help page"""
    template_name = 'schedule_app/help.html'

# API Views
def api_upcoming_assignments(request):
    """API endpoint for upcoming assignments"""
    from django.http import JsonResponse
    from datetime import date, timedelta
    
    try:
        analyst = Analyst.objects.get(user=request.user)
        today = date.today()
        upcoming = MonitoringAssignment.objects.filter(
            analyst=analyst,
            date__range=[today, today + timedelta(days=7)]
        ).select_related('monitoring_type')
        
        data = {
            'assignments': [
                {
                    'date': a.date.isoformat(),
                    'monitoring_type': a.monitoring_type.get_code_display(),
                    'analyst': a.analyst.display_name,
                    'time_window': f"{a.window_start.strftime('%H:%M')} to {a.window_end.strftime('%H:%M')}",
                }
                for a in upcoming
            ]
        }
        return JsonResponse(data)
    except Analyst.DoesNotExist:
        return JsonResponse({'assignments': []})

def api_unread_notification_count(request):
    """API endpoint for unread notification count"""
    from django.http import JsonResponse
    
    try:
        analyst = Analyst.objects.get(user=request.user)
        count = Notification.objects.filter(
            recipient=analyst,
            is_read=False
        ).count()
        
        # Get latest notification
        latest = Notification.objects.filter(
            recipient=analyst
        ).order_by('-created_at').first()
        
        data = {
            'count': count,
            'latest_notification': {
                'title': latest.title if latest else '',
                'message': latest.message if latest else '',
            } if latest else None
        }
        return JsonResponse(data)
    except Analyst.DoesNotExist:
        return JsonResponse({'count': 0, 'latest_notification': None})

def api_check_schedule_updates(request):
    """API endpoint to check for schedule updates"""
    from django.http import JsonResponse
    from datetime import datetime
    
    last_update = request.GET.get('last_update')
    # In a real implementation, you would check if schedule was updated since last_update
    # For now, return no updates
    return JsonResponse({
        'updated': False,
        'timestamp': datetime.now().isoformat()
    })

def api_calendar_events(request):
    """API endpoint for calendar events"""
    from django.http import JsonResponse
    from datetime import datetime
    
    start_date = request.GET.get('start')
    end_date = request.GET.get('end')
    
    try:
        start = datetime.strptime(start_date, '%Y-%m-%d').date()
        end = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        assignments = MonitoringAssignment.objects.filter(
            date__range=[start, end]
        ).select_related('analyst', 'monitoring_type')
        
        events = []
        for assignment in assignments:
            events.append({
                'id': assignment.id,
                'title': f"{assignment.monitoring_type.code}: {assignment.analyst.display_name}",
                'start': assignment.window_start.isoformat(),
                'end': assignment.window_end.isoformat(),
                'extendedProps': {
                    'monitoring_type': assignment.monitoring_type.code,
                    'analyst_name': assignment.analyst.display_name,
                    'is_extended_window': assignment.is_extended_window,
                    'is_monday_assignment': assignment.is_monday_assignment,
                    'status': assignment.status,
                    'duration_hours': float(assignment.duration_hours),
                }
            })
        
        return JsonResponse({'events': events})
    except Exception as e:
        return JsonResponse({'events': [], 'error': str(e)})
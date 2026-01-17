# schedule_app/urls.py
from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Authentication
    path('login/', views.custom_login, name='login'),
    path('logout/', views.custom_logout, name='logout'),
    path('password-change/', 
         auth_views.PasswordChangeView.as_view(
             template_name='schedule_app/password_change.html',
             success_url='/password-change-done/'
         ), 
         name='password_change'),
    path('password-change-done/', 
         auth_views.PasswordChangeDoneView.as_view(
             template_name='schedule_app/password_change_done.html'
         ), 
         name='password_change_done'),
    
    # Dashboard
    path('', views.DashboardView.as_view(), name='dashboard'),
    
    # Schedule Views
    path('schedule/', views.ScheduleListView.as_view(), name='schedule_list'),
    path('schedule/calendar/', views.ScheduleCalendarView.as_view(), name='schedule_calendar'),
    path('schedule/weekly/', views.ScheduleWeeklyView.as_view(), name='schedule_weekly'),
    path('schedule/monthly/', views.ScheduleMonthlyView.as_view(), name='schedule_monthly'),
    
    # Assignment CRUD
    path('assignments/<int:pk>/', views.AssignmentDetailView.as_view(), name='assignment_detail'),
    path('assignments/create/', views.CreateAssignmentView.as_view(), name='create_assignment'),
    path('assignments/<int:pk>/edit/', views.UpdateAssignmentView.as_view(), name='update_assignment'),
    path('assignments/<int:pk>/delete/', views.DeleteAssignmentView.as_view(), name='delete_assignment'),
    
    # Swap Requests
    path('swap-requests/', views.SwapRequestListView.as_view(), name='swap_request_list'),
    path('swap-requests/<int:pk>/', views.SwapRequestDetailView.as_view(), name='swap_request_detail'),
    path('assignments/<int:assignment_id>/swap/', views.SwapRequestCreateView.as_view(), name='swap_request_create'),
    path('swap-requests/<int:pk>/approve/', views.approve_swap_request, name='approve_swap_request'),
    path('swap-requests/<int:pk>/reject/', views.reject_swap_request, name='reject_swap_request'),
    
    # Leave Requests
    path('leave-requests/', views.LeaveRequestListView.as_view(), name='leave_request_list'),
    path('leave-requests/create/', views.LeaveRequestCreateView.as_view(), name='leave_request_create'),
    path('leave-requests/<int:pk>/', views.LeaveRequestDetailView.as_view(), name='leave_request_detail'),
    path('leave-requests/<int:pk>/approve/', views.approve_leave_request, name='approve_leave_request'),
    
    # Analyst Views
    path('analysts/', views.AnalystListView.as_view(), name='analyst_list'),
    path('analysts/<int:pk>/', views.AnalystDetailView.as_view(), name='analyst_detail'),
    path('my-schedule/', views.my_schedule, name='my_schedule'),
    
    # Report Views
    path('reports/submit/', views.report_submission_create, name='report_submission_create'),
    path('my-reports/', views.my_reports, name='my_reports'),
    
    # Schedule Generation
    path('schedule/generate/', views.generate_schedule, name='generate_schedule'),
    path('schedule/bulk/', views.bulk_operations, name='bulk_operations'),
    
    # Notifications
    path('notifications/', views.notifications_view, name='notifications'),
    
    # Information Pages
    path('about/', views.AboutView.as_view(), name='about'),
    path('help/', views.HelpView.as_view(), name='help'),
    
    # API Endpoints (for AJAX calls)
    path('api/upcoming-assignments/', views.api_upcoming_assignments, name='api_upcoming_assignments'),
    path('api/notifications/unread-count/', views.api_unread_notification_count, name='api_unread_notification_count'),
    path('api/schedule/check-updates/', views.api_check_schedule_updates, name='api_check_schedule_updates'),
    path('api/calendar/events/', views.api_calendar_events, name='api_calendar_events'),
]

# schedule_app/permissions.py
from rest_framework import permissions

class IsAnalystOrReadOnly(permissions.BasePermission):
    """Allow analysts to edit their own data, read-only for others"""
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Check if user is the analyst
        return obj.analyst.user == request.user

class CanApproveSwaps(permissions.BasePermission):
    """Only allow analysts with approval permission to approve swaps"""
    def has_permission(self, request, view):
        if request.method == 'POST':
            return True
        return request.user.has_perm('schedule_app.can_approve_swap')

class CanManageLeave(permissions.BasePermission):
    """Only allow analysts with leave management permission"""
    def has_permission(self, request, view):
        if request.method == 'GET':
            return True
        return request.user.has_perm('schedule_app.can_manage_leave')

class IsOwnerOrAdmin(permissions.BasePermission):
    """Only allow owners or admins to modify"""
    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        
        # Check if user owns the object
        if hasattr(obj, 'analyst') and hasattr(obj.analyst, 'user'):
            return obj.analyst.user == request.user
        elif hasattr(obj, 'user'):
            return obj.user == request.user
        elif hasattr(obj, 'requested_by'):
            return obj.requested_by.user == request.user
        
        return False

class IsAssignedAnalyst(permissions.BasePermission):
    """Only allow the assigned analyst to update assignment status"""
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Check if user is the assigned analyst
        return obj.analyst.user == request.user

class CanGenerateSchedule(permissions.BasePermission):
    """Only allow admins and schedule managers to generate schedules"""
    def has_permission(self, request, view):
        return request.user.is_staff or request.user.has_perm('schedule_app.can_generate_schedule')
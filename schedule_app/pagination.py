# schedule_app/pagination.py
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
    
    def get_paginated_response(self, data):
        return Response({
            'links': {
                'next': self.get_next_link(),
                'previous': self.get_previous_link()
            },
            'count': self.page.paginator.count,
            'total_pages': self.page.paginator.num_pages,
            'current_page': self.page.number,
            'results': data
        })

class LargeResultsSetPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200

class SchedulePagination(PageNumberPagination):
    page_size = 7  # One week of assignments
    page_size_query_param = 'page_size'
    max_page_size = 28  # One month
    
    def get_paginated_response(self, data):
        return Response({
            'links': {
                'next': self.get_next_link(),
                'previous': self.get_previous_link()
            },
            'count': self.page.paginator.count,
            'total_pages': self.page.paginator.num_pages,
            'current_page': self.page.number,
            'results': data,
            'weekly_summary': self.get_weekly_summary(data)
        })
    
    def get_weekly_summary(self, data):
        """Generate a weekly summary of assignments"""
        from collections import defaultdict
        
        summary = defaultdict(lambda: {'EM': 0, 'DM': 0, 'analysts': set()})
        
        for item in data:
            week_start = item['date'] - timedelta(days=item['date'].weekday())
            week_key = week_start.strftime('%Y-%m-%d')
            summary[week_key][item['monitoring_type']] += 1
            summary[week_key]['analysts'].add(item['analyst_name'])
        
        return summary

class AnalystSchedulePagination(PageNumberPagination):
    page_size = 30  # One month of assignments
    page_size_query_param = 'page_size'
    max_page_size = 90  # Three months
    
    def get_paginated_response(self, data):
        # Calculate summary statistics
        total_assignments = len(data)
        em_count = sum(1 for item in data if item.get('monitoring_type') == 'EM')
        dm_count = sum(1 for item in data if item.get('monitoring_type') == 'DM')
        
        return Response({
            'links': {
                'next': self.get_next_link(),
                'previous': self.get_previous_link()
            },
            'count': self.page.paginator.count,
            'total_pages': self.page.paginator.num_pages,
            'current_page': self.page.number,
            'summary': {
                'total_assignments': total_assignments,
                'em_count': em_count,
                'dm_count': dm_count,
                'em_percentage': (em_count / total_assignments * 100) if total_assignments > 0 else 0,
                'dm_percentage': (dm_count / total_assignments * 100) if total_assignments > 0 else 0,
            },
            'results': data
        })
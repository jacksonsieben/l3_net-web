from django.urls import path
from . import views

app_name = 'validation'

urlpatterns = [
    path('', views.RunAssignmentListView.as_view(), name='run_assignment_list'),
    path('exams/', views.ExamListView.as_view(), name='exam_list'),
    path('exams/<int:pk>/', views.ExamDetailView.as_view(), name='exam_detail'),
    path('exams/<int:exam_id>/image/', views.stream_exam_image, name='exam_image'),
    path('api/exam/<int:pk>/', views.get_exam_data, name='get_exam_data'),
    path('api/validation/update-severity/', views.update_validation_severity, name='update_validation_severity'),
    path('api/validation/submit-all/', views.submit_all_validations, name='submit_all_validations'),
    path('api/run/update-status/', views.update_run_status, name='update_run_status'),
    
    # New API endpoints for version management
    path('api/hf-versions/', views.get_hf_versions, name='get_hf_versions'),
    path('api/exams/create/', views.create_exam_api, name='create_exam_api'),
    path('api/exams/list/', views.list_exams_api, name='list_exams_api'),
    
    # Admin-only URLs
    path('admin/exams/', views.AdminExamListView.as_view(), name='admin_exam_list'),
    path('admin/exam/create/', views.AdminExamCreateView.as_view(), name='admin_exam_create'),
    path('admin/exam/<int:pk>/edit/', views.AdminExamEditView.as_view(), name='admin_exam_edit'),
    path('admin/exam/<int:pk>/delete/', views.AdminExamDeleteView.as_view(), name='admin_exam_delete'),
    
    # Run management URLs
    path('admin/runs/', views.AdminRunListView.as_view(), name='admin_run_list'),
    path('admin/run/<int:pk>/edit/', views.AdminRunEditView.as_view(), name='admin_run_edit'),
    path('admin/run/<int:pk>/delete/', views.AdminRunDeleteView.as_view(), name='admin_run_delete'),
    path('admin/run/<int:pk>/assign/', views.AdminRunAssignView.as_view(), name='admin_run_assign'),
    path('admin/run/assign/', views.AdminRunAssignmentView.as_view(), name='admin_run_assignment'),
    
    # AJAX endpoints for lazy loading
    path('ajax/run-statistics/', views.get_run_statistics, name='ajax_run_statistics'),
    path('ajax/run-details/<int:run_id>/', views.get_run_details, name='ajax_run_details'),
    path('ajax/bulk-run-details/', views.bulk_get_run_details, name='ajax_bulk_run_details'),
    
    # Analytics and reporting URLs (Admin only)
    path('analytics/', views.analytics_dashboard, name='analytics_dashboard'),
    path('analytics/run/<int:run_id>/', views.run_analytics_detail, name='run_analytics_detail'),
    path('export/csv/', views.export_validation_results_csv, name='export_validation_csv'),
    path('export/csv/<int:run_id>/', views.export_validation_results_csv, name='export_validation_csv'),
]

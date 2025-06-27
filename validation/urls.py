from django.urls import path
from . import views

app_name = 'validation'

urlpatterns = [
    path('', views.RunAssignmentListView.as_view(), name='run_assignment_list'),
    path('exams/', views.ExamListView.as_view(), name='exam_list'),
    path('exams/<int:pk>/', views.ExamDetailView.as_view(), name='exam_detail'),
    path('exams/<int:exam_id>/image/<int:run_id>/', views.stream_exam_image, name='exam_image'),
    path('api/exam/<int:pk>/', views.get_exam_data, name='get_exam_data'),
    
    # Admin-only URLs
    path('admin/exam/create/', views.AdminExamCreateView.as_view(), name='admin_exam_create'),
    path('admin/exam/<int:pk>/edit/', views.AdminExamEditView.as_view(), name='admin_exam_edit'),
    path('admin/exam/<int:pk>/delete/', views.AdminExamDeleteView.as_view(), name='admin_exam_delete'),
    
    # Run management URLs
    path('admin/runs/', views.AdminRunListView.as_view(), name='admin_run_list'),
    path('admin/run/<int:pk>/edit/', views.AdminRunEditView.as_view(), name='admin_run_edit'),
    path('admin/run/<int:pk>/delete/', views.AdminRunDeleteView.as_view(), name='admin_run_delete'),
    path('admin/run/<int:pk>/assign/', views.AdminRunAssignView.as_view(), name='admin_run_assign'),
    path('admin/run/assign/', views.AdminRunAssignmentView.as_view(), name='admin_run_assignment'),
]

from django.urls import path
from . import views

app_name = 'validation'

urlpatterns = [
    path('', views.ExamListView.as_view(), name='exam_list'),
    path('<int:pk>/', views.ExamDetailView.as_view(), name='exam_detail'),
    path('api/exam/<int:pk>/', views.get_exam_data, name='get_exam_data'),
]

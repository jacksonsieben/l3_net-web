from django.shortcuts import render, get_object_or_404
from django.views.generic import ListView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse

from .models.exam import Exam
from .models.run import Run
from .models.polygon import Polygon
from .models.pred_severity import PredSeverity
from .models.pred_vertebra import PredVertebra
from .models.model_version import ModelVersion

# Create your views here.
class ExamListView(LoginRequiredMixin, ListView):
    """View to display a list of all exams for validation."""
    model = Exam
    template_name = 'validation/exam_list.html'
    context_object_name = 'exams'
    login_url = '/users/login/'
    
    def get_queryset(self):
        return Exam.objects.all().order_by('-created_at')

class ExamDetailView(LoginRequiredMixin, DetailView):
    """View to display an individual exam with its predictions for validation."""
    model = Exam
    template_name = 'validation/exam_detail.html'
    context_object_name = 'exam'
    login_url = '/users/login/'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Get the latest run for this exam
        run = Run.objects.filter(exam_id=self.object).order_by('-run_date').first()
        
        if run:
            # Get vertebra predictions for this run
            vertebrae = PredSeverity.objects.filter(run_id=run)
            
            # Get severity predictions
            severity_predictions = []
            vertebrae_predictions = []
            # Get all severities for this run
            severities = PredSeverity.objects.filter(run_id=run)
            vertebrae = PredVertebra.objects.filter(run_id=run)
            
            for severity in severities:
                # Check if severity has a bounding box
                if hasattr(severity, 'bounding_box') and severity.bounding_box:
                    # Find the closest vertebra for this severity
                    for vertebra in vertebrae:
                        severity_predictions.append({
                            # 'vertebra_name': vertebra.name,
                            'severity_name': severity.severity_name,
                            'confidence': severity.confidence * 100,  # Convert to percentage
                            'bounding_box': {
                                'x1': severity.bounding_box.x1,
                                'y1': severity.bounding_box.y1,
                                'x2': severity.bounding_box.x2,
                                'y2': severity.bounding_box.y2,
                            }
                        })
                        # Just add one association for demo purposes
                        break
            for vertebra in vertebrae:
                vertebrae_predictions.append({
                    'vertebra_name': vertebra.name,
                    'confidence': vertebra.confidence * 100,  # Convert to percentage
                    'polygon': {
                        'x1': vertebra.polygon.x1,
                        'y1': vertebra.polygon.y1,
                        'x2': vertebra.polygon.x2,
                        'y2': vertebra.polygon.y2,
                    }
                })
            
            context['vertebrae'] = vertebrae
            context['severity_predictions'] = severity_predictions
            context['vertebrae_predictions'] = vertebrae_predictions
            context['run'] = run
            
        return context

def get_exam_data(request, pk):
    """API endpoint to get exam data in JSON format."""
    exam = get_object_or_404(Exam, pk=pk)
    run = Run.objects.filter(exam_id=exam).order_by('-run_date').first()
    
    if not run:
        return JsonResponse({'error': 'No runs found for this exam'}, status=404)
    
    # Get vertebra predictions
    vertebrae = PredVertebra.objects.filter(run_id=run)
    
    # Format data for response
    data = {
        'exam_id': exam.id,
        'external_id': exam.external_id,
        'image_path': exam.image_path,
        'predictions': []
    }
    
    # Get all severities for this run
    severities = PredSeverity.objects.filter(run_id=run)
    
    for severity in severities:
        # Check if severity has a bounding box
        if hasattr(severity, 'bounding_box') and severity.bounding_box:
            # Find a vertebra to pair with this severity
            for vertebra in vertebrae:
                data['predictions'].append({
                    'vertebra_name': vertebra.name,
                    'severity_name': severity.severity_name,
                    'confidence': severity.confidence * 100,  # Convert to percentage
                    'bounding_box': {
                        'x1': severity.bounding_box.x1,
                        'y1': severity.bounding_box.y1,
                        'x2': severity.bounding_box.x2,
                        'y2': severity.bounding_box.y2,
                    }
                })
                # Just pair with one vertebra for demonstration
                break
    
    return JsonResponse(data)

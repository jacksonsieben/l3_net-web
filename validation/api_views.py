from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.authtoken.models import Token
from rest_framework import serializers
from django.contrib.auth import authenticate, get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404

from .models import (
    Exam, Run, ModelVersion, Polygon, 
    PredVertebra, PredSeverity, Validation, RunAssignment
)
from .serializers import (
    ExamSerializer, ExamCreateSerializer, RunSerializer, 
    RunWithPredictionsSerializer, ModelVersionSerializer,
    PredVertebraSerializer, PredSeveritySerializer,
    ValidationSerializer, RunAssignmentSerializer
)

User = get_user_model()


# ============ AUTHENTICATION SERIALIZERS ============

class EmailAuthTokenSerializer(serializers.Serializer):
    """Custom token serializer that uses email instead of username."""
    email = serializers.EmailField(label="Email")
    password = serializers.CharField(
        label="Password",
        style={'input_type': 'password'},
        trim_whitespace=False
    )
    
    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')
        
        if email and password:
            user = authenticate(request=self.context.get('request'),
                              email=email, password=password)
            
            if not user:
                msg = 'Unable to log in with provided credentials.'
                raise serializers.ValidationError(msg, code='authorization')
        else:
            msg = 'Must include "email" and "password".'
            raise serializers.ValidationError(msg, code='authorization')
        
        attrs['user'] = user
        return attrs


# ============ AUTHENTICATION API VIEWS ============

class CustomAuthToken(ObtainAuthToken):
    """
    Custom token authentication view that returns user info along with token.
    
    POST /api/auth/token/ - Obtain token
    Body: {"email": "your_email", "password": "your_password"}
    """
    permission_classes = [AllowAny]
    serializer_class = EmailAuthTokenSerializer
    
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data,
                                           context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        token, created = Token.objects.get_or_create(user=user)
        return Response({
            'token': token.key,
            'user_id': user.pk,
            'email': user.email,
            'full_name': user.full_name,
        })


@api_view(['POST'])
@permission_classes([IsAdminUser])
def logout_user(request):
    """
    Logout user by deleting their token.
    
    POST /api/auth/logout/
    Headers: Authorization: Token your_token_here
    """
    try:
        # Delete the user's token
        request.user.auth_token.delete()
        return Response({'message': 'Successfully logged out'})
    except Exception as e:
        return Response(
            {'error': f'Failed to logout: {str(e)}'},
            status=status.HTTP_400_BAD_REQUEST
        )


@api_view(['GET'])
@permission_classes([IsAdminUser])
def user_profile(request):
    """
    Get current user's profile information.
    
    GET /api/auth/profile/
    Headers: Authorization: Token your_token_here
    """
    user = request.user
    return Response({
        'user_id': user.pk,
        'email': user.email,
        'full_name': user.full_name,
        'is_staff': user.is_staff,
        'is_active': user.is_active,
        'date_joined': user.date_joined,
    })


# ============ EXAM API VIEWS ============
class ExamListCreateView(generics.ListCreateAPIView):
    """
    List all exams or create a new exam.
    
    GET /api/exams/ - List all exams
    POST /api/exams/ - Create a new exam
    """
    queryset = Exam.objects.all().order_by('-created_at')
    permission_classes = [IsAdminUser]
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ExamCreateSerializer
        return ExamSerializer


class ExamDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update or delete an exam.
    
    GET /api/exams/{id}/ - Get exam details
    PUT /api/exams/{id}/ - Update exam
    DELETE /api/exams/{id}/ - Delete exam
    """
    queryset = Exam.objects.all()
    serializer_class = ExamSerializer
    permission_classes = [IsAdminUser]


@api_view(['GET'])
@permission_classes([IsAdminUser])
def get_exam_by_external_id(request, external_id):
    """
    Get exam details by external_id.
    
    GET /api/exams/external/{external_id}/ - Get exam by external ID
    """
    try:
        exam = get_object_or_404(Exam, external_id=external_id)
        serializer = ExamSerializer(exam)
        return Response(serializer.data)
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error retrieving exam: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============ MODEL VERSION API VIEWS ============
class ModelVersionListCreateView(generics.ListCreateAPIView):
    """
    List all model versions or create a new one.
    
    GET /api/model-versions/ - List all model versions
    POST /api/model-versions/ - Create a new model version
    """
    queryset = ModelVersion.objects.all().order_by('-id')
    serializer_class = ModelVersionSerializer
    permission_classes = [IsAdminUser]


class RunListCreateView(generics.ListCreateAPIView):
    """
    List all runs or create a new run.
    
    GET /api/runs/ - List all runs
    POST /api/runs/ - Create a new run
    """
    queryset = Run.objects.all().order_by('-run_date')
    serializer_class = RunSerializer
    permission_classes = [IsAdminUser]


class RunDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update or delete a run.
    
    GET /api/runs/{id}/ - Get run details
    PUT /api/runs/{id}/ - Update run
    DELETE /api/runs/{id}/ - Delete run
    """
    queryset = Run.objects.all()
    serializer_class = RunSerializer
    permission_classes = [IsAdminUser]


@api_view(['POST'])
@permission_classes([IsAdminUser])
def create_run_with_predictions(request):
    """
    Create a complete run with predictions in a single API call.
    
    POST /api/runs/with-predictions/
    
    Expected JSON structure:
    {
        "name": "Run Name",
        "description": "Run description",
        "exam_ids": [1, 2, 3],
        "vertebra_predictions": [
            {
                "name": "L1",
                "confidence": 0.95,
                "model_version_id": 1,
                "exam_id": 1,
                "polygon": {
                    "x1": 0.1,
                    "y1": 0.2,
                    "x2": 0.3,
                    "y2": 0.4
                }
            }
        ],
        "severity_predictions": [
            {
                "severity_name": "MODERATE",
                "confidence": 0.87,
                "model_version_id": 1,
                "exam_id": 1,
                "vertebrae_level": "L1_L2",
                "bounding_box": {
                    "x1": 0.15,
                    "y1": 0.25,
                    "x2": 0.35,
                    "y2": 0.45
                }
            }
        ]
    }
    """
    serializer = RunWithPredictionsSerializer(data=request.data)
    
    if serializer.is_valid():
        try:
            with transaction.atomic():
                run = serializer.save()
                return Response({
                    'success': True,
                    'message': f'Run "{run.name}" created successfully with predictions.',
                    'run_id': run.id,
                    'run': RunSerializer(run).data
                }, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({
                'success': False,
                'message': f'Error creating run: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    return Response({
        'success': False,
        'errors': serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def add_predictions_to_run(request, run_id):
    """
    Add predictions to an existing run.
    
    POST /api/runs/{run_id}/predictions/
    
    Expected JSON structure:
    {
        "vertebra_predictions": [
            {
                "name": "L2",
                "confidence": 0.92,
                "model_version_id": 1,
                "polygon": {
                    "x1": 0.2,
                    "y1": 0.3,
                    "x2": 0.4,
                    "y2": 0.5
                }
            }
        ],
        "severity_predictions": [
            {
                "severity_name": "SEVERE",
                "confidence": 0.89,
                "model_version_id": 1,
                "bounding_box": {
                    "x1": 0.25,
                    "y1": 0.35,
                    "x2": 0.45,
                    "y2": 0.55
                }
            }
        ]
    }
    """
    run = get_object_or_404(Run, id=run_id)
    
    vertebra_predictions_data = request.data.get('vertebra_predictions', [])
    severity_predictions_data = request.data.get('severity_predictions', [])
    
    try:
        with transaction.atomic():
            created_vertebrae = []
            created_severities = []
            
            # Create vertebra predictions
            for pred_data in vertebra_predictions_data:
                serializer = PredVertebraSerializer(data=pred_data)
                if serializer.is_valid():
                    vertebra = serializer.save(run_id=run)
                    created_vertebrae.append(vertebra)
                else:
                    return Response({
                        'success': False,
                        'errors': {'vertebra_predictions': serializer.errors}
                    }, status=status.HTTP_400_BAD_REQUEST)
            
            # Create severity predictions
            for pred_data in severity_predictions_data:
                serializer = PredSeveritySerializer(data=pred_data)
                if serializer.is_valid():
                    severity = serializer.save(run_id=run)
                    created_severities.append(severity)
                else:
                    return Response({
                        'success': False,
                        'errors': {'severity_predictions': serializer.errors}
                    }, status=status.HTTP_400_BAD_REQUEST)
            
            return Response({
                'success': True,
                'message': f'Added {len(created_vertebrae)} vertebra predictions and {len(created_severities)} severity predictions to run "{run.name}".',
                'created': {
                    'vertebrae_count': len(created_vertebrae),
                    'severities_count': len(created_severities)
                }
            }, status=status.HTTP_201_CREATED)
            
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error adding predictions: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def get_run_predictions(request, run_id):
    """
    Get all predictions for a specific run.
    
    GET /api/runs/{run_id}/predictions/
    """
    run = get_object_or_404(Run, id=run_id)
    
    vertebrae = PredVertebra.objects.filter(run_id=run).select_related('polygon', 'model_version')
    severities = PredSeverity.objects.filter(run_id=run).select_related('bounding_box', 'model_version')
    
    return Response({
        'run_id': run.id,
        'run_name': run.name,
        'vertebra_predictions': PredVertebraSerializer(vertebrae, many=True).data,
        'severity_predictions': PredSeveritySerializer(severities, many=True).data
    })


@api_view(['POST'])
@permission_classes([IsAdminUser])
def assign_run_to_user(request):
    """
    Assign a run to a user for validation.
    
    POST /api/assign-run/
    
    Expected JSON:
    {
        "run_id": 1,
        "user_id": 2,
        "notes": "Optional notes about the assignment"
    }
    """
    run_id = request.data.get('run_id')
    user_id = request.data.get('user_id')
    notes = request.data.get('notes', '')
    
    if not run_id:
        return Response({
            'success': False,
            'message': 'run_id is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    if not user_id:
        return Response({
            'success': False,
            'message': 'user_id is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        run = get_object_or_404(Run, id=run_id)
        from users.models import CustomUser
        user = get_object_or_404(CustomUser, id=user_id)
        
        # Check if assignment already exists
        assignment, created = RunAssignment.objects.get_or_create(
            run=run,
            user=user,
            defaults={
                'assigned_by': request.user,
                'notes': notes
            }
        )
        
        if created:
            return Response({
                'success': True,
                'message': f'Run "{run.name}" assigned to {user.email} successfully.',
                'assignment': RunAssignmentSerializer(assignment).data
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'success': False,
                'message': f'Run "{run.name}" is already assigned to {user.email}.',
                'assignment': RunAssignmentSerializer(assignment).data
            }, status=status.HTTP_200_OK)
            
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error creating assignment: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])
def api_status(request):
    """
    API status endpoint to check if the API is working.
    
    GET /api/status/
    """
    return Response({
        'status': 'OK',
        'message': 'Spinal Stenosis Validation API is running',
        'user': request.user.email if request.user.is_authenticated else None,
        'endpoints': {
            'exams': '/api/exams/',
            'runs': '/api/runs/',
            'model_versions': '/api/model-versions/',
            'create_run_with_predictions': '/api/runs/with-predictions/',
            'assign_run': '/api/assign-run/',
            'status': '/api/status/'
        }
    })

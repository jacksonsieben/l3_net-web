from django.db import models

# Import all models from the models directory
from .models.polygon import Polygon
from .models.pred_severity import PredSeverity
from .models.pred_vertebra import PredVertebra
from .models.model_version import ModelVersion
from .models.run import Run
from .models.exam import Exam
from .models.validation import Validation

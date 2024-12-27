"""Service layer initialization."""
from datetime import datetime

from .spreadsheet_service import SpreadsheetService
from .form_service import FormService
from .ui_service import UIService
from .form_builder_service import FormBuilderService
from .copy_service import CopyService
from .payment_service import PaymentService
from .charts_service import ChartsService

__all__ = [
    'SpreadsheetService',
    'FormService',
    'UIService',
    'FormBuilderService',
    'CopyService',
    'PaymentService',
    'ChartsService'
]

# Version and timestamp for deployment verification
VERSION = "2024-12-14-v1"
TIMESTAMP = datetime.now().isoformat()

import sys
import os

# اضافه کردن پوشه اصلی به مسیر پایتون
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app

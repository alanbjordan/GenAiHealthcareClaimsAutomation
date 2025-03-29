from celery.result import AsyncResult
from celery import Celery
import ssl
import os

# Replace these with your actual Redis details
app = Celery('vaclaimguard', 
             broker=os.getenv("BROKER"), 
             backend=os.getenv("BACKEND")  # Ensure backend is also Redis

app.conf.update(
    broker_use_ssl={
        'ssl_cert_reqs': ssl.CERT_REQUIRED
    },
    redis_backend_use_ssl={
        'ssl_cert_reqs': ssl.CERT_REQUIRED
    }
)

# Assuming you have the task ID from the response or elsewhere
task_id = os.getenv(TASK_ID)

# Check the task result from the Celery backend (Redis)
result = AsyncResult(task_id)

# Check task state
print("Task state:", result.state)

# Get task result if completed
if result.state == 'SUCCESS':
    print("Task result:", result.result)

from celery.result import AsyncResult
from celery import Celery
import ssl

# Replace these with your actual Redis details
app = Celery('vaclaimguard', 
             broker='rediss://:e9QG8zns7nfaWIqwhG3jbvlBEJnmvnDcjAzCaKxrbp8=@vaclaimguard.redis.cache.windows.net:6380/0', 
             backend='rediss://:e9QG8zns7nfaWIqwhG3jbvlBEJnmvnDcjAzCaKxrbp8=@vaclaimguard.redis.cache.windows.net:6380/0')  # Ensure backend is also Redis

app.conf.update(
    broker_use_ssl={
        'ssl_cert_reqs': ssl.CERT_REQUIRED
    },
    redis_backend_use_ssl={
        'ssl_cert_reqs': ssl.CERT_REQUIRED
    }
)

# Assuming you have the task ID from the response or elsewhere
task_id = '069b0c7f-b0f3-4da6-98de-51539e63fa54'

# Check the task result from the Celery backend (Redis)
result = AsyncResult(task_id)

# Check task state
print("Task state:", result.state)

# Get task result if completed
if result.state == 'SUCCESS':
    print("Task result:", result.result)

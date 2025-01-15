# Step 1: base image
FROM python:3.9-slim

# 1) Install system packages for M2Crypto
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    libssl-dev \
    swig \
 && rm -rf /var/lib/apt/lists/*

# Step 2: create and use working directory
WORKDIR /app

# Step 3: copy your requirements file into /app
COPY requirements.txt /app/

# Copy the requirements file and install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt
RUN pip install --upgrade openai
RUN pip install --upgrade pinecone-client
RUN pip install --upgrade chardet
# Step 5: copy the rest of your code
COPY . /app/

# Step 6: expose a port (e.g. 5000)
EXPOSE 5000

# Step 7: run your Flask app (via gunicorn, for production)
CMD ["gunicorn", "--bind=0.0.0.0:5000", "app:app"]
